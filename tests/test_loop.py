from datetime import datetime
from pathlib import Path

import pytest

from sentinela.adapters.replay import ReplayAdapter
from sentinela.clock import SimClock, carregar_feriados_remessa
from sentinela.comms.extractor import ExtratorMock
from sentinela.contracts import Acao, Papel
from sentinela.decision import FatosConferencia
from sentinela.gateway import ToolGateway
from sentinela.loop import Laco, TipoEvento, conferencia_fail_closed

DATA = Path(__file__).resolve().parents[1] / "data" / "raw"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/raw ausente")


def conferencia_ok(titulo, gateway, identidade, oc):
    return FatosConferencia("ok")


def novo(inicio, conferir=conferencia_ok, **kw):
    clock = SimClock(inicio, carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))
    ad = ReplayAdapter(DATA, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    ad.registrar_em(gw)
    return Laco(ad, gw, clock, ExtratorMock(), conferir, **kw), ad, clock, gw


def execucoes(regs, acao=None, resultado=None):
    return [e for r in regs for e in r.execucoes if (acao is None or e.acao is acao) and (resultado is None or e.resultado == resultado)]


def eventos(regs, tipo=None):
    return [e for r in regs for e in r.eventos if tipo is None or e.tipo is tipo]


# ---------------------------------------------------------- Embalarte, retroativo
def test_mensagem_chega_entre_tiques_e_o_lote_e_protegido_antes_do_corte():
    laco, ad, clock, gw = novo(datetime(2026, 10, 29, 14, 0), fornecedores={"FP4615"})
    antes = laco.rodar_ate(datetime(2026, 10, 29, 16, 0))  # tiques 14:00 e 15:00: a mensagem (15:42) ainda não existe
    assert not [e for e in eventos(antes, TipoEvento.COMUNICACAO) if e.referencia == "EM571119"]
    assert not execucoes(antes, Acao.RETIRAR)
    em_lote_aberto = [
        t for t in gw.chamar("buscar_titulos", fornecedor_id="FP4615", status="agendado", limite=1000)
        if not clock.lote_fechado(t["lote_remessa"]) and t["forma_pagamento"] in ("ted", "pix")
    ]
    assert em_lote_aberto
    depois = laco.rodar_ate(datetime(2026, 10, 29, 17, 0))  # tique 16:00: a mensagem aparece
    assert [e.referencia for e in eventos(depois, TipoEvento.COMUNICACAO)].count("EM571119") == 1
    retirados = {e.parametros["titulo_id"] for e in execucoes(depois, Acao.RETIRAR, "ok")}
    assert retirados == {t["titulo_id"] for t in em_lote_aberto}
    for t in em_lote_aberto:  # estado do ambiente depois de agir, e antes do primeiro corte desses títulos
        v = gw.chamar("consultar_titulo", titulo_id=t["titulo_id"])
        assert (v["status"], v["lote_remessa"]) == ("aberto", "")
        assert clock.fechamento(t["lote_remessa"]) > datetime(2026, 10, 29, 16, 0)
    ps01 = [e for e in execucoes(depois, Acao.ACIONAR_PESSOA, "ok") if e.parametros["pessoa_id"] == "PS01"]
    assert len(ps01) == 1  # um acionamento por incidente, não um por título
    assert sum(1 for a in ad.acionamentos if a["pessoa_id"] == "PS01" and a["urgencia"] == "alta") >= 1


def test_nenhum_titulo_de_lote_ja_fechado_e_tocado():
    laco, ad, clock, gw = novo(datetime(2026, 10, 29, 14, 0), fornecedores={"FP4615"})
    regs = laco.rodar_ate(datetime(2026, 10, 29, 17, 0))
    for e in execucoes(regs, Acao.RETIRAR):
        assert e.resultado == "ok"  # nada foi recusado por lote fechado: o agente só age onde ainda dá tempo


# ------------------------------------------------------------- pré-fechamento
def test_pendencia_sem_resolucao_e_retirada_no_pre_fechamento_e_nao_antes():
    base, ad0, c0, gw0 = novo(datetime(2026, 11, 2, 8, 0))
    alvo = next(l for l in gw0.chamar("listar_agenda_remessa", lote_remessa="RM20261103-MER") if l["valor"] <= 5000 and l["forma_pagamento"] == "boleto")
    tid, forn = alvo["titulo_id"], alvo["fornecedor_id"]

    def conferir(titulo, gateway, identidade, oc):
        return FatosConferencia("ausente", motivo="NF não encontrada") if titulo["titulo_id"] == tid else FatosConferencia("ok")

    laco, ad, clock, gw = novo(datetime(2026, 11, 2, 8, 0), conferir, fornecedores={forn})
    ate_08h = laco.rodar_ate(datetime(2026, 11, 3, 9, 0))  # tiques até 08:00 de 03/11
    assert gw.chamar("consultar_titulo", titulo_id=tid)["status"] == "agendado"  # ainda não é hora de agir sobre a pendência
    assert any(e.acao is Acao.ACIONAR_PESSOA and e.resultado == "ok" for e in execucoes(ate_08h))
    assert not eventos(ate_08h, TipoEvento.PRE_FECHAMENTO) or all(e.instante >= datetime(2026, 11, 3, 8, 0) for e in eventos(ate_08h, TipoEvento.PRE_FECHAMENTO))
    pre = laco.rodar_ate(datetime(2026, 11, 3, 10, 0))  # tique 09:00: último antes do corte das 10:00
    assert [e.referencia for e in eventos(pre, TipoEvento.PRE_FECHAMENTO)] == ["RM20261103-MER"]
    retirada = [e for e in execucoes(pre, Acao.RETIRAR, "ok") if e.parametros["titulo_id"] == tid]
    assert len(retirada) == 1 and "pré-fechamento" in retirada[0].parametros["motivo"]
    assert clock.agora == datetime(2026, 11, 3, 10, 0)  # a ação ocorreu no tique anterior ao corte, não no instante dele
    v = gw.chamar("consultar_titulo", titulo_id=tid)
    assert (v["status"], v["lote_remessa"]) == ("aberto", "")


def test_pre_fechamento_so_ocorre_antes_de_cortes_de_dia_util():
    laco, ad, clock, gw = novo(datetime(2026, 11, 2, 8, 0), fornecedores={"FP4615"})
    regs = laco.rodar_ate(datetime(2026, 11, 4, 0, 0))
    momentos = [(e.referencia, e.instante) for e in eventos(regs, TipoEvento.PRE_FECHAMENTO)]
    assert momentos == [("RM20261103-MER", datetime(2026, 11, 3, 9, 0)), ("RM20261103-LIT", datetime(2026, 11, 3, 13, 0))]  # 02/11 é feriado


def test_troca_de_conta_confirmada_nao_tem_pagamento_retido_no_pre_fechamento():
    # FP4202 trocou de banco com confirmação registrada (o analista não vê o histórico): pede aprovação, mas não retém pagamentos
    laco, ad, clock, gw = novo(datetime(2026, 11, 2, 8, 0), fornecedores={"FP4202"})
    regs = laco.rodar_ate(datetime(2026, 11, 3, 10, 0))
    assert len(eventos(regs, TipoEvento.PRE_FECHAMENTO)) == 1
    assert not execucoes(regs, Acao.RETIRAR)
    assert [s["parametros"]["incidente"] for s in ad.solicitacoes] == ["FP4202|troca_bancaria"]


# ---------------------------------------------------------------- idempotência
def test_reprocessar_o_tique_nao_repete_acoes():
    laco, ad, clock, gw = novo(datetime(2026, 10, 29, 16, 0), fornecedores={"FP4615"})
    primeiro = laco.executar_tique()
    n_ok = len(execucoes([primeiro], resultado="ok"))
    assert n_ok > 0
    de_novo = laco.executar_tique()  # mesmo instante, sem evidência nova
    assert not execucoes([de_novo], resultado="ok") and not eventos([de_novo])
    d = next(d for _, d in primeiro.decisoes if d.acoes)
    repetidas = laco.executor.executar(d, "X", clock.agora)
    assert all(e.resultado == "duplicada" for e in repetidas)


def test_mesma_pessoa_nao_e_acionada_duas_vezes_pelo_mesmo_incidente():
    laco, ad, clock, gw = novo(datetime(2026, 10, 29, 16, 0), fornecedores={"FP4615"})
    reg = laco.executar_tique()
    # dois incidentes distintos já visíveis às 16:00 (Pigmentos 11:05 e Embalarte 15:42): um acionamento de PS01 por incidente
    assert len([a for a in ad.acionamentos if a["pessoa_id"] == "PS01"]) == 2
    # os ~25 títulos por TED do Embalarte compartilham o incidente da comunicação: nenhum acionamento extra, só "duplicada"
    por_titulo = [e for e in reg.execucoes if e.acao is Acao.ACIONAR_PESSOA and e.referencia.startswith("TP")]
    assert por_titulo and all(e.resultado == "duplicada" for e in por_titulo)
    laco.executar_tique()
    assert len([a for a in ad.acionamentos if a["pessoa_id"] == "PS01"]) == 2


# ------------------------------------------------------------------ fail-closed
def test_sem_conferencia_ligada_nada_e_agendado_corrigido_ou_cancelado():
    laco, ad, clock, gw = novo(datetime(2026, 11, 2, 8, 0), conferencia_fail_closed, fornecedores={"FP4345"})
    regs = laco.rodar_ate(datetime(2026, 11, 2, 12, 0))
    assert not execucoes(regs, Acao.AGENDAR) and not execucoes(regs, Acao.CORRIGIR) and not execucoes(regs, Acao.CANCELAR)
    from collections import Counter

    pessoas = Counter(e.parametros["pessoa_id"] for e in execucoes(regs, Acao.ACIONAR_PESSOA, "ok"))
    # 3 impersonações (PS08) + token do "banco" (PS02) + 2 incidentes de fraude (PS01) + pendência de evidência do fornecedor (PS05):
    # um acionamento por incidente, não um por título (o fornecedor tem dezenas de títulos agendados)
    assert pessoas == Counter({"PS08": 3, "PS01": 2, "PS02": 1, "PS05": 1})


# ------------------------------------------------------- fila inicial completa
def test_fila_inicial_completa_no_corte_protege_so_o_que_deve():
    laco, ad, clock, gw = novo(datetime(2026, 11, 2, 8, 0))
    reg = laco.executar_tique()
    abertos = [t for t in gw.chamar("buscar_titulos", limite=1_000_000) if t["status"] in ("aberto", "agendado")]
    assert len(reg.decisoes) >= 2398
    retirados = {e.parametros["titulo_id"] for e in execucoes([reg], Acao.RETIRAR, "ok")}
    assert {"TP431754", "TP431946", "TP432337"} <= retirados  # boleto trocado e fornecedor diferente da OC
    emb = {t["titulo_id"] for t in gw.chamar("buscar_titulos", fornecedor_id="FP4615", limite=1000)}
    assert retirados & emb  # títulos por TED do Embalarte
    pigmentos_outros = [t for t in gw.chamar("buscar_titulos", fornecedor_id="FP4345", status="agendado", limite=1000) if t["titulo_id"] != "TP431754"]
    assert pigmentos_outros  # os demais títulos legítimos do fornecedor do boleto trocado continuam agendados
    # troca de conta de remetente legítimo: uma solicitação de aprovação por fornecedor (não uma por título)
    assert sorted(len(s["parametros"]["itens"]) for s in ad.solicitacoes) == [4, 27, 48, 52]
    assert {s["parametros"]["incidente"] for s in ad.solicitacoes} == {f"{f}|troca_bancaria" for f in ("FP3614", "FP5079", "FP3345", "FP4202")}
    assert len(ad.acionamentos) == 8 and not execucoes([reg], Acao.CORRIGIR)
    assert not execucoes([reg], Acao.AGENDAR)  # sem lote alvo definido, o laço não agenda nada sozinho
    assert not execucoes([reg], resultado="erro")
    assert len(abertos) >= 2398
