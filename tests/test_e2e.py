"""Cenários de ponta a ponta da demo (docs/05-DEMO-E-PITCH.md), com a conferência de 3 vias real.

Replay local sobre a foto de 02/11/2026 08:00; extrator mock (determinístico, sem rede).
"""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("sentinela.store")
pytest.importorskip("sentinela.executor")
pytest.importorskip("sentinela.threeway")

RAIZ = Path(__file__).resolve().parents[1]
DATA = RAIZ / "data" / "raw"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/raw ausente")
sys.path.insert(0, str(RAIZ / "scripts"))

import rodar_replay  # noqa: E402
from sentinela.clock import nome_lote, parse_lote  # noqa: E402
from sentinela.conferencia import conferir_pelo_gateway  # noqa: E402
from sentinela.contracts import Acao  # noqa: E402
from test_loop import execucoes, novo  # noqa: E402

CORTE = datetime(2026, 11, 2, 8, 0)


@pytest.fixture(scope="module")
def corte():
    regs, adapter, store = rodar_replay.rodar(CORTE, datetime(2026, 11, 2, 9, 0), None, ":memory:", DATA)
    return regs, adapter, store


def titulo(adapter, tid):
    return adapter.consultar_titulo(tid)


# --------------------------------------------------- cenário 1: caso limpo agenda sozinho
def test_caso_limpo_titulo_aberto_e_agendado_sozinho_dentro_da_alcada():
    def lote_alvo_para(clock):
        def f(t):
            vencimento = date.fromisoformat(t["vencimento"])
            # no corte nenhum título aberto vence até 13/11 (horizonte da agenda): o caso limpo é programar adiante,
            # no lote do próprio vencimento (próximo dia útil), para os que vencem logo depois do horizonte
            if t["valor"] > 5000 or vencimento > date(2026, 11, 23):
                return None
            proximo, _ = clock.proximo_fechamento()
            dia = max(clock.proximo_dia_util(vencimento), parse_lote(proximo)[0])
            return nome_lote(dia, "MER")

        return f

    base, ad0, clock0, gw0 = novo(CORTE)
    laco, ad, clock, gw = novo(CORTE, conferir_pelo_gateway(base.clock.feriados), lote_alvo=lote_alvo_para(base.clock))
    reg = laco.executar_tique()
    agendados = execucoes([reg], Acao.AGENDAR, "ok")
    assert agendados  # há títulos abertos, limpos, ≤ R$ 5.000 e vencendo na janela
    for e in agendados:
        t = ad.consultar_titulo(e.parametros["titulo_id"])
        assert t["status"] == "agendado" and t["lote_remessa"] == e.parametros["lote_remessa"] and t["valor"] <= Decimal("5000")
        # nenhum título AFETADO por risco é agendado; títulos de outras NFs do mesmo fornecedor seguem normalmente
        por_conta = t["forma_pagamento"] in ("ted", "pix")
        assert not (t["fornecedor_id"] in ("FP4615", "FP5079", "FP3614", "FP3345", "FP4202") and por_conta)
        assert t["titulo_id"] != "TP431754"


# ---------------------------------------- cenário 2: erro operacional validado (corrige com evidência)
def test_erro_de_digitacao_de_fator_10_em_ted_e_corrigido_com_evidencia(corte):
    regs, ad, store = corte
    for tid, esperado in (("TP431634", "2406.36"), ("TP432136", "3111.66"), ("TP432802", "2445.11")):
        t = titulo(ad, tid)
        assert t["valor"] == Decimal(esperado) and t["status"] in ("agendado", "aberto"), tid
    correcoes = [e for r in regs for e in r.execucoes if e.acao is Acao.CORRIGIR and e.resultado == "ok" and e.parametros["campo"] == "valor"]
    assert len(correcoes) == 9 and all(e.parametros["evidencias"] and "duplicata" in e.parametros["justificativa"] for e in correcoes)
    assert {r[0] for r in store.db.execute("SELECT estado FROM acoes WHERE acao='corrigir_lancamento'")} == {"aplicada"}  # verificado no estado do título


def test_boleto_com_tarifa_nao_e_corrigido_e_nao_retem_pagamento(corte):
    regs, ad, _ = corte
    for tid, valor in (("TP430389", "841.58"), ("TP430641", "18321.00"), ("TP432847", "5053.22")):
        t = titulo(ad, tid)
        assert t["valor"] == Decimal(valor)  # o título continua igual ao boleto que será pago
    ids = {tid for r in regs for tid, d in r.decisoes if d.regra_aplicada == "R6_boleto_diverge_da_duplicata"}
    assert len(ids) == 12
    for tid in ids:
        assert titulo(ad, tid)["status"] in ("agendado", "aberto")
    assert titulo(ad, "TP430389")["status"] == "agendado"  # nada foi retirado do lote por uma diferença de R$ 4,50


# -------------------------------------------- cenário 3: comunicação suspeita e golpe de boleto
def test_golpe_de_boleto_retira_so_o_titulo_da_nf_citada(corte):
    _, ad, _ = corte
    assert titulo(ad, "TP431754")["status"] == "aberto"  # boleto da 2ª via com beneficiário trocado
    restantes = ad.buscar_titulos(fornecedor_id="FP4345", status="agendado", limite=1000)
    assert restantes and "TP431754" not in {t["titulo_id"] for t in restantes}  # demais títulos legítimos seguem


def test_embalarte_nenhum_pagamento_por_ted_segue_no_lote(corte):
    _, ad, _ = corte
    agendados = ad.buscar_titulos(fornecedor_id="FP4615", status="agendado", limite=1000)
    assert not [t for t in agendados if t["forma_pagamento"] in ("ted", "pix")]


def test_fornecedor_errado_na_oc_e_retirado(corte):
    _, ad, _ = corte
    assert titulo(ad, "TP431946")["status"] == "aberto" and titulo(ad, "TP432337")["status"] == "aberto"


def test_erro_de_valor_grande_em_titulo_agendado_e_retirado_e_pede_aprovacao(corte):
    _, ad, _ = corte
    for tid in ("TP431459", "TP431775"):  # R$ 48 mil e R$ 90 mil contra duplicatas 10x menores
        assert titulo(ad, tid)["status"] == "aberto"
    pedidos = [s for s in ad.solicitacoes if s["acao"] == "corrigir_lancamento"]
    assert pedidos and sum(len(s["parametros"]["itens"]) for s in pedidos) == 9


# ------------------------------------------------------- cenário 4: injeção e mensagem legítima
def test_instrucao_plantada_nao_altera_nenhuma_decisao_de_pagamento(corte):
    regs, ad, _ = corte
    decisoes = [(tid, d) for r in regs for tid, d in r.decisoes if tid.startswith("TP")]
    flex = {t["titulo_id"] for t in ad.buscar_titulos(fornecedor_id="FP5525", limite=1000)}
    for tid, d in decisoes:
        if tid in flex:
            assert not d.regra_aplicada.startswith("R1")  # a mensagem "libere sem conferir" não retira, cancela ou libera nada
    assert not execucoes(regs, Acao.AGENDAR) and not execucoes(regs, Acao.CANCELAR)


def test_somente_as_cinco_comunicacoes_de_risco_alto_geram_acionamento_de_comunicacao(corte):
    regs, _, _ = corte
    ids = {tid for r in regs for tid, d in r.decisoes if d.regra_aplicada == "C1_comunicacao_alto_risco"}
    assert ids == {f"comunicacao:{c}" for c in ("EM570977", "EM570998", "EM571100", "EM571116", "EM571119")}  # 241 legítimas não acionam ninguém


def test_acoes_de_notificacao_ficam_verificadas_no_replay(corte):
    _, _, store = corte
    estados = {r[0] for r in store.db.execute("SELECT estado FROM acoes")}
    assert estados <= {"aplicada", "reservada"}  # nada incerto, falho ou sem prova


# ------------------------------------------------------------------------- determinismo
def test_mesma_entrada_mesma_saida():
    def assinatura():
        regs, _, _ = rodar_replay.rodar(CORTE, datetime(2026, 11, 2, 9, 0), {"FP4615", "FP4345"}, ":memory:", DATA)
        return [(e.acao.value, e.resultado, e.referencia) for r in regs for e in r.execucoes], [(tid, d.regra_aplicada, d.chave_idempotencia) for r in regs for tid, d in r.decisoes]

    assert assinatura() == assinatura()
