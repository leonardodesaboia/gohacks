from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("sentinela.store")  # T7 e T9 (outra sessão) podem ainda não estar no repositório
pytest.importorskip("sentinela.executor")

from sentinela.comms.extractor import ExtratorMock
from sentinela.contracts import Acao
from sentinela.decision import FatosConferencia
from sentinela.loop import ExecutorPersistente, Laco, TipoEvento, verificador_replay
from sentinela.store import Store
from test_loop import DATA, conferencia_ok, eventos, execucoes, novo

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/raw ausente")


def laco_persistente(inicio, caminho, conferir=conferencia_ok, ad_gw_clock=None, **kw):
    laco, ad, clock, gw = novo(inicio, conferir, **kw) if ad_gw_clock is None else (None, *ad_gw_clock)
    store = Store(caminho)
    executor = ExecutorPersistente(gw, store, verificador_replay(ad))
    if laco is None:
        laco = Laco(ad, gw, clock, ExtratorMock(), conferir, executor=executor, **kw)
    else:
        laco.executor = executor
    return laco, ad, clock, gw, store


def estados_das_acoes(store):
    return {r[0]: r[1] for r in store.db.execute("SELECT estado, COUNT(*) FROM acoes GROUP BY estado")}


# ------------------------------------------------------------- ponta a ponta
def test_embalarte_retroativo_com_store_tudo_verificado(tmp_path):
    laco, ad, clock, gw, store = laco_persistente(datetime(2026, 10, 29, 14, 0), tmp_path / "s.db", fornecedores={"FP4615"})
    laco.rodar_ate(datetime(2026, 10, 29, 16, 0))
    esperados = {
        t["titulo_id"] for t in gw.chamar("buscar_titulos", fornecedor_id="FP4615", status="agendado", limite=1000)
        if not clock.lote_fechado(t["lote_remessa"]) and t["forma_pagamento"] in ("ted", "pix")
    }
    assert esperados
    depois = laco.rodar_ate(datetime(2026, 10, 29, 17, 0))
    retirados = {e.parametros["titulo_id"] for e in execucoes(depois, Acao.RETIRAR, "ok")}
    assert retirados == esperados  # confirmado pelo estado do ambiente (consultar_titulo), não pela resposta da ferramenta
    estados = estados_das_acoes(store)
    assert "incerta" not in estados and "falha" not in estados  # nada ficou sem prova
    assert estados["aplicada"] >= len(esperados)
    tipos = {r[0] for r in store.db.execute("SELECT DISTINCT tipo FROM auditoria")}
    assert {"decisao", "decisao_completa", "intencao_acao", "resultado_verificacao"} <= tipos
    assert len([a for a in ad.acionamentos if a["pessoa_id"] == "PS01"]) == 2  # um por incidente (Pigmentos, Embalarte)


def test_reiniciar_sobre_o_mesmo_banco_nao_repete_nada(tmp_path):
    caminho = tmp_path / "s.db"
    laco, ad, clock, gw, store = laco_persistente(datetime(2026, 10, 29, 14, 0), caminho, fornecedores={"FP4615"})
    laco.rodar_ate(datetime(2026, 10, 29, 17, 0))
    n_acoes, n_acionamentos, n_solic = len(ad.acoes), len(ad.acionamentos), len(ad.solicitacoes)
    antes = estados_das_acoes(store)
    store.close()
    # "reinício": novo laço e novo executor sobre o mesmo banco; o ambiente (adapter) mantém o estado
    laco2, _, _, _, store2 = laco_persistente(None, caminho, ad_gw_clock=(ad, clock, gw), fornecedores={"FP4615"})
    reg = laco2.executar_tique()
    assert not execucoes([reg], resultado="ok")  # nada executado de novo
    laco2.rodar_ate(datetime(2026, 10, 29, 20, 0))
    assert (len(ad.acoes), len(ad.acionamentos), len(ad.solicitacoes)) == (n_acoes, n_acionamentos, n_solic)
    depois = estados_das_acoes(store2)
    # 'reservada' pode crescer: títulos já retirados ganham nova versão e a decisão deles (só acionar a PS01) é reservada,
    # mas não reenviada porque o incidente já foi alertado. O que não pode mudar: nada reaplicado, nada incerto ou falho.
    assert depois["aplicada"] == antes["aplicada"]
    assert "incerta" not in depois and "falha" not in depois


def test_pre_fechamento_persiste_o_fallback_como_decisao_propria(tmp_path):
    base, ad0, c0, gw0 = novo(datetime(2026, 11, 2, 8, 0))
    alvo = next(l for l in gw0.chamar("listar_agenda_remessa", lote_remessa="RM20261103-MER") if l["valor"] <= 5000 and l["forma_pagamento"] == "boleto")
    tid, forn = alvo["titulo_id"], alvo["fornecedor_id"]

    def conferir(titulo, gateway, identidade, oc):
        return FatosConferencia("ausente", motivo="NF não encontrada") if titulo["titulo_id"] == tid else FatosConferencia("ok")

    laco, ad, clock, gw, store = laco_persistente(datetime(2026, 11, 2, 8, 0), tmp_path / "s.db", conferir, fornecedores={forn})
    laco.rodar_ate(datetime(2026, 11, 3, 9, 0))
    assert gw.chamar("consultar_titulo", titulo_id=tid)["status"] == "agendado"
    pre = laco.rodar_ate(datetime(2026, 11, 3, 10, 0))
    assert [e.referencia for e in eventos(pre, TipoEvento.PRE_FECHAMENTO)] == ["RM20261103-MER"]
    assert [e.parametros["titulo_id"] for e in execucoes(pre, Acao.RETIRAR, "ok")] == [tid]
    linhas = store.db.execute("SELECT titulo_id, estado FROM acoes WHERE titulo_id LIKE ?", (f"{tid}#fallback:%",)).fetchall()
    assert [(r[1]) for r in linhas] == ["aplicada"]
    assert gw.chamar("consultar_titulo", titulo_id=tid)["status"] == "aberto"


def test_solicitacao_agrupada_e_persistida_e_nao_repete(tmp_path):
    caminho = tmp_path / "s.db"
    laco, ad, clock, gw, store = laco_persistente(datetime(2026, 11, 2, 8, 0), caminho, fornecedores={"FP4202"})
    reg = laco.executar_tique()
    assert len(ad.solicitacoes) == 1 and len(ad.solicitacoes[0]["parametros"]["itens"]) == 4
    linhas = store.db.execute("SELECT titulo_id, estado FROM acoes WHERE acao='solicitar_aprovacao'").fetchall()
    assert len(linhas) == 1 and linhas[0][0].startswith("incidente:FP4202|troca_bancaria:") and linhas[0][1] == "aplicada"
    assert [e.resultado for e in reg.execucoes if e.acao is Acao.SOLICITAR_APROVACAO] == ["ok"]
    store.close()
    laco2, _, _, _, _ = laco_persistente(None, caminho, ad_gw_clock=(ad, clock, gw), fornecedores={"FP4202"})
    laco2.executar_tique()
    assert len(ad.solicitacoes) == 1  # mesmo conjunto de títulos, mesma solicitação: não duplica


# ---------------------------------------------------------- segurança e falhas
def test_resultado_nao_verificavel_fica_incerto_e_nao_e_reenviado(tmp_path):
    laco, ad, clock, gw = novo(datetime(2026, 10, 29, 16, 0), fornecedores={"FP4615"})
    laco.executor = ExecutorPersistente(gw, Store(tmp_path / "s.db"))  # verificador padrão: só prova ações de título
    reg = laco.executar_tique()
    incertas = [e for e in reg.execucoes if e.acao is Acao.ACIONAR_PESSOA and e.resultado == "incerta"]
    assert incertas  # a resposta da ferramenta não é prova de que o acionamento chegou
    enviados = len(ad.acionamentos)
    laco.executar_tique()
    laco.executar_tique()
    assert len(ad.acionamentos) == enviados  # incerto: nunca reenviar às cegas


def test_conflito_de_idempotencia_escala_sem_derrubar_o_laco(tmp_path):
    laco, ad, clock, gw = novo(datetime(2026, 10, 29, 16, 0), fornecedores={"FP4615"})
    ex = ExecutorPersistente(gw, Store(tmp_path / "s.db"), verificador_replay(ad))
    comunicacao = next(c for c in gw.chamar("listar_comunicacoes") if c["comunicacao_id"] == "EM571119")
    from sentinela.comms.risk import analisar_comunicacao
    from sentinela.decision import decidir_comunicacao

    d = decidir_comunicacao(analisar_comunicacao(gw, laco.catalogo, ExtratorMock(), comunicacao))
    assert [e.resultado for e in ex.executar(d, "comunicacao:EM571119", clock.agora, fornecedor_id="FP4615")] == ["ok"]
    alterada = d.model_copy(update={"motivo": "outro motivo para a mesma versão"})
    saida = ex.executar(alterada, "comunicacao:EM571119", clock.agora, fornecedor_id="FP4615")
    assert [e.resultado for e in saida] == ["escalada"] and "ConflitoIdempotencia" in saida[0].detalhe
