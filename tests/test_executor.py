import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sentinela.adapters.replay import ReplayAdapter
from sentinela.clock import SimClock, carregar_feriados_remessa
from sentinela.contracts import Acao, AcaoPlanejada, Decisao, Evidencia, Papel
from sentinela.executor import Executor, verificar_titulo
from sentinela.gateway import ToolGateway
from sentinela.store import Store

AGORA = datetime(2026, 11, 2, 8)
DATA = Path(__file__).resolve().parents[1] / "data" / "raw"


def ambiente(tmp_path, *, com_replay=True, verificar=verificar_titulo):
    clock = SimClock(AGORA, carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))
    gateway = ToolGateway(Papel.ANALISTA_CP, clock)
    adaptador = ReplayAdapter(DATA, clock) if com_replay else None
    if adaptador:
        adaptador.registrar_em(gateway)
    store = Store(tmp_path / "executor.db")
    return Executor(gateway, store, verificar), adaptador


def preparar(executor, titulo="TP431754"):
    return executor.store.registrar_evidencia(titulo, f"E-{titulo}", Evidencia(
        fonte="contas_a_pagar", registro=titulo, instante_disponibilidade=AGORA))


def decisao(acao, parametros, *, versao=1, chave="DEC-1", incidente=None, extras=()):
    return Decisao(acao=acao, regra_aplicada="R1_fraude_ou_identidade", alcada="analista_cp",
                   versao_evidencias=versao, chave_idempotencia=chave, motivo="evidência de risco",
                   incidente=incidente,
                   acoes=(AcaoPlanejada(acao=acao, parametros=parametros), *extras))


def registros(store, tipo):
    return [json.loads(row[0]) for row in store.db.execute(
        "SELECT payload FROM auditoria WHERE tipo=? ORDER BY id", (tipo,))]


@pytest.mark.skipif(not DATA.exists(), reason="bases sintéticas indisponíveis")
def test_sucesso_real_retirada_confirma_estado_e_audita_antes(tmp_path):
    executor, adaptador = ambiente(tmp_path)
    preparar(executor)
    antes = adaptador.consultar_titulo("TP431754")
    assert antes["status"] == "agendado"
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "beneficiário divergente"})
    resultado = executor.executar("TP431754", "FP4345", d, ("boleto: CNPJ divergente",))
    assert resultado.estado == "confirmado" and resultado.evidencias == ("boleto: CNPJ divergente",)
    assert adaptador.consultar_titulo("TP431754")["status"] == "aberto"
    assert [c.ferramenta for c in executor.gateway.historico[-2:]] == ["retirar_do_lote", "consultar_titulo"]
    tipos = [row[0] for row in executor.store.db.execute("SELECT tipo FROM auditoria ORDER BY id")]
    assert tipos.index("intencao_acao") < tipos.index("resultado_verificacao")
    assert len(registros(executor.store, "intencao_acao")) == 1
    assert len(registros(executor.store, "resultado_verificacao")) == 1
    assert executor.executar("TP431754", "FP4345", d).estado == "confirmado"
    assert len([a for a in adaptador.acoes if a["ferramenta"] == "retirar_do_lote"]) == 1
    executor.store.close()


@pytest.mark.skipif(not DATA.exists(), reason="bases sintéticas indisponíveis")
def test_sequencia_t6_retirar_e_acionar_para_se_exigir_verificador(tmp_path):
    executor, adaptador = ambiente(tmp_path, verificar=lambda a, g, r: verificar_titulo(a, g, r) if a.acao == Acao.RETIRAR else bool(g.chamar("consultar_titulo", titulo_id="TP431754")["status"] == "aberto" and r["acionamento_id"]))
    preparar(executor)
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "suspeita"}, incidente="FP4345|fraude",
                extras=(AcaoPlanejada(acao=Acao.ACIONAR_PESSOA, parametros={"pessoa_id": "PS01", "motivo": "suspeita", "urgencia": "alta", "titulos": ["TP431754"]}),))
    r = executor.executar("TP431754", "FP4345", d)
    assert r.estado == "confirmado" and len(r.chaves) == 2
    assert len(adaptador.acionamentos) == 1
    assert executor.store.db.execute("SELECT pessoas_acionadas FROM incidentes").fetchone()[0] == '["PS01"]'
    assert executor.executar("TP431754", "FP4345", d).estado == "confirmado"
    assert len(adaptador.acionamentos) == 1
    executor.store.close()


def test_negacao_permissao_vira_escalonamento_sem_bypass(tmp_path):
    executor, _ = ambiente(tmp_path, com_replay=False)
    preparar(executor)
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "x"})
    # Handler ausente é recusa explícita do gateway, não execução direta.
    r = executor.executar("TP431754", "FP4345", d)
    assert r.estado == "escalado" and "HandlerNaoRegistrado" in r.motivo
    assert executor.gateway.historico[-1].resultado == "sem_handler"
    assert executor.store.obter_acao(r.chaves[0]).estado == "falha"
    assert len(registros(executor.store, "intencao_acao")) == 1
    assert len(registros(executor.store, "resultado_verificacao")) == 1
    executor.store.close()


def test_falha_desconhecida_e_timeout_sao_incertos_sem_acesso_proibido(tmp_path):
    executor, _ = ambiente(tmp_path, com_replay=False)
    preparar(executor)
    calls = []

    def falha(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("sistema indisponível após receber comando")

    executor.gateway.registrar("retirar_do_lote", falha)
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "x"})
    primeiro = executor.executar("TP431754", "FP4345", d)
    assert primeiro.estado == "escalado" and executor.store.obter_acao(primeiro.chaves[0]).estado == "incerta"
    segundo = executor.executar("TP431754", "FP4345", d)
    assert segundo.estado == "incerto" and len(calls) == 1
    assert all(c.ferramenta != "consultar_extrato" for c in executor.gateway.historico)
    executor.store.close()


def test_comando_responde_mas_estado_nao_confirma_nao_segue_proxima_acao(tmp_path):
    executor, _ = ambiente(tmp_path, com_replay=False, verificar=lambda a, g, r: None)
    preparar(executor)
    chamadas = []
    executor.gateway.registrar("retirar_do_lote", lambda **kw: chamadas.append("retirar") or {"estado": "aberto"})
    executor.gateway.registrar("acionar_pessoa", lambda **kw: chamadas.append("acionar"))
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "x"},
                extras=(AcaoPlanejada(acao=Acao.ACIONAR_PESSOA, parametros={"pessoa_id": "PS01", "motivo": "x"}),))
    r = executor.executar("TP431754", "FP4345", d)
    assert r.estado == "incerto" and chamadas == ["retirar"]
    assert executor.store.obter_acao(r.chaves[0]).estado == "incerta"
    executor.store.close()


def test_timeout_com_efeito_aplicado_e_restart_reconcilia_antes_de_retry(tmp_path):
    caminho = tmp_path / "executor.db"
    executor, _ = ambiente(tmp_path, com_replay=False, verificar=lambda a, g, r: g.chamar("consultar_titulo", titulo_id="TP431754")["status"] == "aberto")
    preparar(executor)
    contador = []
    estado = {"status": "agendado"}

    def comando(**kw):
        contador.append("comando")
        estado["status"] = "aberto"
        raise TimeoutError("resposta perdida")

    executor.gateway.registrar("retirar_do_lote", comando)
    executor.gateway.registrar("consultar_titulo", lambda **kw: estado)
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "x"})
    primeiro = executor.executar("TP431754", "FP4345", d)
    assert primeiro.estado == "escalado"
    executor.store.close()
    with Store(caminho) as store:
        novo = Executor(executor.gateway, store, executor.verificar)
        r = novo.executar("TP431754", "FP4345", d)
        assert r.estado == "confirmado" and len(contador) == 1
        assert store.obter_acao(r.chaves[0]).tentativas == 1
        assert [c.ferramenta for c in executor.gateway.historico[-2:]] == ["retirar_do_lote", "consultar_titulo"]


def test_timeout_sem_efeito_confirmado_permite_retry_seguro(tmp_path):
    executor, _ = ambiente(tmp_path, com_replay=False)
    preparar(executor)
    status = {"status": "agendado", "lote_remessa": "RM20261103-MER"}
    chamadas = []

    def comando(**kw):
        chamadas.append(kw)
        if len(chamadas) == 1:
            raise TimeoutError("sem efeito")
        status.update(status="aberto", lote_remessa="")
        return {"estado": "aberto"}

    executor.gateway.registrar("retirar_do_lote", comando)
    executor.gateway.registrar("consultar_titulo", lambda **kw: status.copy())
    d = decisao(Acao.RETIRAR, {"titulo_id": "TP431754", "motivo": "x"})
    assert executor.executar("TP431754", "FP4345", d).estado == "escalado"
    r = executor.executar("TP431754", "FP4345", d)
    assert r.estado == "confirmado" and len(chamadas) == 2
    assert executor.store.obter_acao(r.chaves[0]).tentativas == 2
    executor.store.close()


def test_manter_e_escalar_nao_chamam_ferramentas(tmp_path):
    executor, _ = ambiente(tmp_path, com_replay=False)
    preparar(executor)
    manter = Decisao(acao=Acao.MANTER, regra_aplicada="R7_limpo_manter", alcada="analista_cp",
                    versao_evidencias=1, chave_idempotencia="manter", motivo="sem mudança")
    assert executor.executar("TP431754", "FP4345", manter).estado == "mantido"
    assert not executor.gateway.historico
    assert executor.store.db.execute("SELECT count(*) FROM acoes").fetchone()[0] == 0
    executor.store.close()


def test_aprovacao_t6_adapta_envelope_sem_ferramenta_extra(tmp_path):
    executor, _ = ambiente(tmp_path, com_replay=False, verificar=lambda a, g, r: None)
    preparar(executor)
    capturados = []
    executor.gateway.registrar("solicitar_aprovacao", lambda **kw: capturados.append(kw) or {"solicitacao_id": "SOL-1", "estado": "pendente"})
    d = decisao(Acao.SOLICITAR_APROVACAO, {"titulo_id": "TP431754", "acao": "agendar_titulo", "parametros": {"lote_remessa": "RM20261103-MER"}, "evidencias": ["conferido"], "aprovador_humano": "PS01"})
    r = executor.executar("TP431754", "FP4345", d)
    assert r.estado == "incerto" and "titulo_id" not in capturados[0]
    assert capturados[0]["acao"] == "agendar_titulo"
    assert capturados[0]["parametros"]["titulo_id"] == "TP431754"
    executor.store.close()
