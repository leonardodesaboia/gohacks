import itertools
import random
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentinela.adapters.replay import ReplayAdapter
from sentinela.clock import SimClock, carregar_feriados_remessa
from sentinela.comms.extractor import ExtratorMock
from sentinela.comms.risk import AnaliseRisco, Nivel, Sinal, analisar_comunicacao
from sentinela.contracts import Acao, Papel, Pagamento
from sentinela.decision import (
    FatosConferencia,
    FatosTitulo,
    agregado_alcada,
    alteracao_recente,
    chave_idempotencia,
    decidir,
    decidir_comunicacao,
    fatos_de_conferencia,
)
from sentinela.gateway import ToolGateway
from sentinela.identity import ResolucaoTitulo, Status, montar_catalogo, resolver_titulo
from sentinela.roles import FERRAMENTAS_ANALISTA_CP, exigir

D = Decimal
LOTE = "RM20261103-MER"


# ------------------------------------------------------------------ fábricas
def pag(valor="1000.00", estado="agendado", lote=LOTE, forn="FP1000", tid="TP1", venc=date(2026, 11, 3), forma=None, nf="123"):
    return Pagamento(id=tid, origem="erp", fornecedor_id=forn, nf_numero=nf, parcela="1/1", valor=D(valor), vencimento=venc, estado=estado, lote=lote if estado == "agendado" else None, forma_pagamento=forma)


def ident(status=Status.OK, motivos=(), tid="TP1"):
    return ResolucaoTitulo(tid, status, None, tuple(motivos))


def conf(resultado="ok", incons=(), esperado=None, dif=None, venc=None, motivo=""):
    return FatosConferencia(resultado, tuple(incons), motivo, esperado, dif, venc, "CHAVE")


def risco(nivel=Nivel.ALTO, sinais=(Sinal.REMETENTE_NAO_CONFERE,), forn="FP1000", pessoas=("PS01",), **extra):
    return AnaliseRisco("EM1", forn, Status.OK, False, nivel, tuple(sinais), ("motivo de teste",), nivel is Nivel.ALTO, Sinal.TROCA_BANCARIA_SOLICITADA in sinais, tuple(pessoas), **extra)


def fatos(**kw):
    base = dict(pagamento=pag(), categoria="produto", identidade=ident(), conferencia=conf())
    base.update(kw)
    return FatosTitulo(**base)


def acoes(d):
    return [a.acao for a in d.acoes]


# ------------------------------------------------------------------- ramos
def test_r0_titulo_pago_ou_cancelado_nao_faz_nada():
    for estado in ("pago", "cancelado"):
        d = decidir(fatos(pagamento=pag(estado=estado)))
        assert d.regra_aplicada == "R0_estado_final" and d.acoes == () and d.acao is Acao.MANTER


def test_r7_limpo_agendado_mantem():
    d = decidir(fatos())
    assert d.regra_aplicada == "R7_limpo_manter" and d.acoes == ()


def test_r7_limpo_aberto_agenda_sozinho_dentro_da_alcada():
    d = decidir(fatos(pagamento=pag("4999.99", "aberto"), lote_alvo=LOTE))
    assert acoes(d) == [Acao.AGENDAR] and d.acoes[0].parametros == {"titulo_id": "TP1", "lote_remessa": LOTE}


def test_r7_limpo_aberto_sem_lote_alvo_nao_age():
    assert decidir(fatos(pagamento=pag(estado="aberto"))).regra_aplicada == "R7_limpo_sem_lote"


def test_r7_acima_da_alcada_pede_aprovacao_com_nivel_certo():
    d = decidir(fatos(pagamento=pag("5000.01", "aberto"), lote_alvo=LOTE))
    assert acoes(d) == [Acao.SOLICITAR_APROVACAO] and d.aprovacao_necessaria == "aprovador"
    d = decidir(fatos(pagamento=pag("60000.00", "aberto"), lote_alvo=LOTE))
    assert d.aprovacao_necessaria == "diretora financeira (PS03)"


def test_r7_acima_da_alcada_com_aprovacao_registrada_agenda():
    d = decidir(fatos(pagamento=pag("9000.00", "aberto"), lote_alvo=LOTE, aprovacao_registrada=True))
    assert acoes(d) == [Acao.AGENDAR]


def test_r7_agendado_acima_da_alcada_e_mantido_sem_pedir_aprovacao():
    # entrou no lote por outro fluxo; o agente só confere (pedir aprovação de 1.465 títulos já agendados seria ruído)
    d = decidir(fatos(pagamento=pag("9000.00")))
    assert d.regra_aplicada == "R7_limpo_manter" and d.acoes == ()


def test_fracionamento_soma_por_fornecedor_nf_e_vencimento():
    base = {"fornecedor_id": "FP1", "numero_nf_digitado": "0123-1", "vencimento": "2026-11-03", "valor": "2000.00", "status": "aberto"}
    mesmos = [dict(base, titulo_id=f"T{i}") for i in range(3)]
    assert agregado_alcada(mesmos[0], mesmos) == D("6000.00")
    parcelas = [dict(base, vencimento=f"2026-1{i}-03") for i in (1, 2)]  # parcelamento normal não soma
    assert agregado_alcada(parcelas[0], parcelas) == D("2000.00")
    d = decidir(fatos(pagamento=pag("2000.00", "aberto"), lote_alvo=LOTE, agregado_alcada=D("6000.00")))
    assert acoes(d) == [Acao.SOLICITAR_APROVACAO]  # dividir para caber na alçada é indevido


def test_r7_antecipacao_exige_aprovacao_dupla():
    d = decidir(fatos(pagamento=pag("100.00", "aberto"), lote_alvo=LOTE, antecipacao=True))
    assert acoes(d) == [Acao.SOLICITAR_APROVACAO] and d.aprovacao_necessaria.startswith("dupla")


def test_r1_risco_alto_retira_do_lote_e_aciona_ps01():
    d = decidir(fatos(riscos=(risco(),)))
    assert acoes(d) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA] and d.pessoa_a_acionar == "PS01"
    assert d.acoes[1].parametros["urgencia"] == "alta" and d.incidente == "FP1000|fraude" and d.fallback_no_corte is None


def test_risco_de_conta_so_afeta_titulos_por_ted_ou_pix():
    r = risco(sinais=(Sinal.TROCA_BANCARIA_SOLICITADA, Sinal.REMETENTE_NAO_CONFERE), afeta_destino_cadastral=True)
    for forma in ("ted", "pix", None):  # forma desconhecida é tratada como afetada (fail-closed)
        assert Acao.RETIRAR in acoes(decidir(fatos(pagamento=pag(forma=forma), riscos=(r,)))), forma
    boleto = decidir(fatos(pagamento=pag(forma="boleto"), riscos=(r,)))
    assert boleto.regra_aplicada == "R7_limpo_manter" and boleto.acoes == ()  # boleto vai para o beneficiário do boleto, não para o cadastro


def test_risco_de_boleto_so_afeta_a_nf_citada():
    r = risco(sinais=(Sinal.BOLETO_BENEFICIARIO_DIVERGENTE, Sinal.SEGUNDA_VIA_BOLETO), afeta_boleto=True, numero_nf="57551")
    citada = decidir(fatos(pagamento=pag(forma="boleto", nf="0057551"), riscos=(r,)))  # zeros à esquerda não enganam
    assert acoes(citada) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA]
    outra = decidir(fatos(pagamento=pag(forma="boleto", nf="99999"), riscos=(r,)))
    assert outra.regra_aplicada == "R7_limpo_manter"  # os demais títulos legítimos do fornecedor não são retirados


def test_r1_titulo_aberto_nao_retira_mas_aciona():
    d = decidir(fatos(pagamento=pag(estado="aberto"), riscos=(risco(),)))
    assert acoes(d) == [Acao.ACIONAR_PESSOA]


def test_r1_lote_fechado_aciona_tesoureiro():
    d = decidir(fatos(riscos=(risco(),), lote_aberto=False))
    assert d.regra_aplicada == "R1_fraude_lote_fechado" and d.pessoa_a_acionar == "PS02" and Acao.RETIRAR not in acoes(d)


def test_r1_identidade_divergente_retira():
    d = decidir(fatos(identidade=ident(Status.DIVERGENTE, ["beneficiário do boleto não pertence ao fornecedor do título"])))
    assert acoes(d) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA] and d.incidente == "titulo:TP1|identidade"


def test_r1_risco_atencao_sozinho_nao_trava_titulo():
    d = decidir(fatos(riscos=(risco(Nivel.ATENCAO, (Sinal.TENTATIVA_DE_INSTRUCAO, Sinal.ALEGACAO_NAO_VERIFICAVEL)),)))
    assert d.regra_aplicada == "R7_limpo_manter"  # instrução plantada não muda a decisão


def test_r2_duplicidade_comprovada_cancela_dentro_da_alcada():
    d = decidir(fatos(pagamento=pag("800.00"), duplicidade_de="TP0"))
    assert acoes(d) == [Acao.CANCELAR] and d.acoes[0].parametros["evidencias"]


def test_r2_duplicidade_acima_da_alcada_retira_e_pede_aprovacao():
    d = decidir(fatos(pagamento=pag("9000.00"), duplicidade_de="TP0"))
    assert acoes(d) == [Acao.RETIRAR, Acao.SOLICITAR_APROVACAO] and Acao.CANCELAR not in acoes(d)


def test_r3_evidencia_ausente_ou_ambigua_nao_executa():
    for resultado in ("ausente", "ambiguo"):
        d = decidir(fatos(conferencia=conf(resultado, motivo="NF não encontrada")))
        assert acoes(d) == [Acao.ACIONAR_PESSOA] and d.pessoa_a_acionar == "PS04" and d.fallback_no_corte is Acao.RETIRAR
    d = decidir(fatos(identidade=ident(Status.AUSENTE, ["fornecedor fora do catálogo"])))
    assert d.pessoa_a_acionar == "PS01"


def test_r4_troca_bancaria_recente_pede_aprovacao_dupla_sem_reter_pagamento():
    r = risco(Nivel.ATENCAO, (Sinal.TROCA_BANCARIA_SOLICITADA, Sinal.CADASTRO_JA_COINCIDE_COM_PEDIDO))
    d = decidir(fatos(riscos=(r,), alteracao_cadastral_recente=True))
    assert d.regra_aplicada == "R4_troca_bancaria_recente" and acoes(d) == [Acao.SOLICITAR_APROVACAO]
    assert d.aprovacao_necessaria == "dupla: aprovador + PS01" and d.fallback_no_corte is None  # nunca retira: a troca pode estar confirmada
    sem_recente = decidir(fatos(riscos=(r,), alteracao_cadastral_recente=False))
    assert sem_recente.regra_aplicada == "R7_limpo_manter"


def test_r5_divergencia_de_oc_aciona_comprador_da_categoria():
    d = decidir(fatos(conferencia=conf("divergente", ["nf_acima_oc"]), categoria="embalagens"))
    assert acoes(d) == [Acao.ACIONAR_PESSOA] and d.pessoa_a_acionar == "PS04" and d.fallback_no_corte is Acao.RETIRAR
    assert decidir(fatos(conferencia=conf("divergente", ["oc_sem_aprovacao"]), categoria="servicos")).pessoa_a_acionar == "PS05"


def test_r5_excesso_com_divergencia_de_oc_retira_na_hora():
    d = decidir(fatos(conferencia=conf("divergente", ["valor_titulo", "nf_acima_oc"], D("100"), D("900"))))
    assert acoes(d) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA]


def test_r6_valor_unica_causa_dentro_da_alcada_corrige():
    d = decidir(fatos(conferencia=conf("divergente", ["valor_titulo"], D("550.00"), D("4950.00"))))
    p = d.acoes[0].parametros
    assert acoes(d) == [Acao.CORRIGIR] and (p["campo"], p["valor_novo"]) == ("valor", D("550.00")) and p["evidencias"]


def test_r6_valor_acima_da_alcada_retira_se_excesso_e_pede_aprovador():
    d = decidir(fatos(conferencia=conf("divergente", ["valor_titulo"], D("9087.38"), D("81786.42"))))
    assert acoes(d) == [Acao.RETIRAR, Acao.SOLICITAR_APROVACAO] and d.aprovacao_necessaria == "diretora financeira (PS03)"
    falta = decidir(fatos(conferencia=conf("divergente", ["valor_titulo"], D("20000"), D("-14000"))))
    assert acoes(falta) == [Acao.SOLICITAR_APROVACAO]  # pagar a menos não perde dinheiro: não retira


def test_r6_vencimento_unica_causa_corrige():
    d = decidir(fatos(conferencia=conf("divergente", ["vencimento"], venc=date(2026, 11, 10))))
    assert d.acoes[0].parametros["campo"] == "vencimento" and d.acoes[0].parametros["valor_novo"] == "2026-11-10"


def test_r6_mais_de_uma_causa_escala():
    d = decidir(fatos(conferencia=conf("divergente", ["valor_titulo", "vencimento"], D("100"), D("50"))))
    assert d.regra_aplicada == "R6_causa_nao_unica" and acoes(d) == [Acao.ACIONAR_PESSOA]


# --------------------------------------------------- comunicação e idempotência
def test_decidir_comunicacao_so_aciona_em_risco_alto():
    assert decidir_comunicacao(risco(Nivel.ATENCAO)) is None
    d = decidir_comunicacao(risco(forn=None, pessoas=("PS08", "PS02")))
    assert [a.parametros["pessoa_id"] for a in d.acoes] == ["PS08", "PS02"] and d.incidente == "remetente_sem_vinculo|EM1"
    assert decidir_comunicacao(risco()).incidente == "FP1000|fraude"  # mesmo incidente das decisões de título


def test_incidente_agrupa_comunicacao_e_titulos_do_fornecedor():
    assert decidir(fatos(riscos=(risco(),))).incidente == decidir_comunicacao(risco()).incidente


def test_chave_de_idempotencia_muda_com_versao_e_acao():
    d1, d2 = decidir(fatos(riscos=(risco(),))), decidir(fatos(riscos=(risco(),), versao_evidencias=1))
    assert d1.chave_idempotencia != d2.chave_idempotencia
    assert decidir(fatos(riscos=(risco(),))).chave_idempotencia == d1.chave_idempotencia
    assert chave_idempotencia("X", [], 0) != chave_idempotencia("Y", [], 0)


def test_alteracao_recente_e_fatos_de_conferencia():
    agora = datetime(2026, 11, 2, 8, 0)
    assert alteracao_recente({"data_ultima_alteracao": "2026-10-30 16:05:00"}, agora)
    assert not alteracao_recente({"data_ultima_alteracao": "2026-09-01 10:00:00"}, agora)
    assert not alteracao_recente({}, agora)
    c = SimpleNamespace(resultado="divergente", tipo="valor_titulo;vencimento", motivo="m", valor_esperado=D("1"), diferenca=D("2"), vencimento_esperado=None, chave_acesso="K")
    assert fatos_de_conferencia(c).inconsistencias == ("valor_titulo", "vencimento")
    assert fatos_de_conferencia(SimpleNamespace(resultado="ok", tipo="conferido")).inconsistencias == ()


# ------------------------------------------------------ propriedades (varredura)
def _grade():
    espacos = dict(
        estado=["aberto", "agendado", "pago", "cancelado"],
        valor=["100.00", "5000.00", "5000.01", "60000.00"],
        agregado=[None, D("6000")],
        ident=[Status.OK, Status.DIVERGENTE, Status.AUSENTE],
        conf=[
            conf("ok"),
            conf("divergente", ["valor_titulo"], D("10"), D("100")),
            conf("divergente", ["valor_titulo"], D("10"), D("6000")),
            conf("divergente", ["vencimento"], venc=date(2026, 11, 10)),
            conf("divergente", ["nf_acima_oc"]),
            conf("divergente", ["valor_titulo", "vencimento"], D("10"), D("100")),
            conf("ausente"),
            conf("ambiguo"),
        ],
        riscos=[(), (risco(),), (risco(Nivel.ATENCAO, (Sinal.TROCA_BANCARIA_SOLICITADA,)),)],
        recente=[False, True],
        lote_aberto=[True, False],
        dup=[None, "TP0"],
        aprov=[False, True],
        alvo=[None, LOTE],
    )
    todas = list(itertools.product(*espacos.values()))
    abertas = [c for c in todas if c[0] in ("aberto", "agendado")]
    finais = [c for c in todas if c[0] not in ("aberto", "agendado")]
    rng = random.Random(0)
    rng.shuffle(abertas)
    rng.shuffle(finais)
    return abertas[:12000] + finais[:300]


def _fatos_de(c):
    estado, valor, agregado, st, cf, riscos, recente, lote_aberto, dup, aprov, alvo = c
    return FatosTitulo(
        pagamento=pag(valor, estado),
        categoria="produto",
        identidade=ident(st),
        conferencia=cf,
        riscos=riscos,
        alteracao_cadastral_recente=recente,
        agregado_alcada=agregado,
        aprovacao_registrada=aprov,
        lote_aberto=lote_aberto,
        lote_alvo=alvo,
        duplicidade_de=dup,
    )


def test_propriedades_em_12300_combinacoes():
    grade = _grade()
    agendou = 0
    for c in grade:
        f = _fatos_de(c)
        d = decidir(f)
        v = f.pagamento.valor
        agregado = f.agregado_alcada if f.agregado_alcada is not None else v
        ac = acoes(d)
        # nunca fora do papel
        for a in ac:
            exigir(Papel.ANALISTA_CP, a.value)
            assert a.value in FERRAMENTAS_ANALISTA_CP
        # determinismo e chave estável
        assert decidir(f) == d
        # estado final não age
        if f.pagamento.estado in ("pago", "cancelado"):
            assert d.acoes == ()
            continue
        # nunca agenda e retira ao mesmo tempo
        assert not (Acao.AGENDAR in ac and Acao.RETIRAR in ac)
        # alçada
        if Acao.AGENDAR in ac:
            agendou += 1
            assert max(v, agregado) <= D("5000") or f.aprovacao_registrada
        if Acao.CANCELAR in ac:
            assert f.duplicidade_de and v <= D("5000") and agregado <= D("5000")
        for a in d.acoes:
            if a.acao is Acao.CORRIGIR and a.parametros["campo"] == "valor":
                assert abs(f.conferencia.diferenca) <= D("5000")
            if a.acao is Acao.CORRIGIR:
                assert a.parametros["evidencias"]
            if a.acao is Acao.ACIONAR_PESSOA:
                assert a.parametros["pessoa_id"] in {f"PS{i:02d}" for i in range(1, 12)}
        # fail-closed: sem evidência não executa
        sem_evidencia = f.conferencia.resultado in ("ausente", "ambiguo") or f.identidade.status in (Status.AUSENTE, Status.AMBIGUO, Status.INVALIDO)
        fraude = bool(f.riscos and f.riscos[0].nivel is Nivel.ALTO) or f.identidade.status is Status.DIVERGENTE
        if sem_evidencia and not fraude and not f.duplicidade_de:
            assert not ({Acao.AGENDAR, Acao.CORRIGIR, Acao.CANCELAR} & set(ac))
        # risco alto em título agendado com lote aberto: retira e não executa nada de pagamento
        if fraude and f.pagamento.estado == "agendado" and f.lote_aberto:
            assert Acao.RETIRAR in ac and not ({Acao.AGENDAR, Acao.CORRIGIR, Acao.CANCELAR} & set(ac))
    assert agendou >= 10  # sanidade; a alçada do agendamento é varrida de forma exaustiva no teste abaixo


def test_alcada_do_agendamento_e_exaustiva_no_caminho_limpo():
    agendamentos = 0
    for valor, agregado, aprov, alvo, antecip, estado in itertools.product(
        ["100.00", "4999.99", "5000.00", "5000.01", "60000.00"],
        [None, D("100"), D("5000"), D("6000"), D("60000")],
        [False, True],
        [None, LOTE],
        [False, True],
        ["aberto", "agendado"],
    ):
        f = FatosTitulo(pagamento=pag(valor, estado), categoria="produto", identidade=ident(), conferencia=conf(), agregado_alcada=agregado, aprovacao_registrada=aprov, lote_alvo=alvo, antecipacao=antecip)
        d = decidir(f)
        v = f.pagamento.valor
        total = max(v, agregado if agregado is not None else v)
        if Acao.AGENDAR in acoes(d):
            agendamentos += 1
            assert estado == "aberto" and alvo == LOTE and not antecip
            assert total <= D("5000") or aprov
        if estado == "aberto" and alvo and (antecip or (total > D("5000") and not aprov)):
            assert acoes(d) == [Acao.SOLICITAR_APROVACAO]
        if estado == "agendado":
            assert acoes(d) == []  # título já agendado e coerente: só conferir
    assert agendamentos > 0


# ------------------------------------------------------ casos reais (dados do evento)
DATA = Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture(scope="module")
def real():
    if not DATA.exists():
        pytest.skip("data/raw ausente")
    clock = SimClock(datetime(2026, 11, 2, 8, 0), carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))
    ad = ReplayAdapter(DATA, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    ad.registrar_em(gw)
    cat = montar_catalogo(gw)
    comms = {c["comunicacao_id"]: c for c in gw.chamar("listar_comunicacoes")}
    return gw, cat, comms


def fatos_reais(gw, cat, titulo, riscos=(), conferencia=None):
    oc = gw.chamar("consultar_pedido_compra", oc_id=titulo["oc_id"]) if titulo["oc_id"] else None
    forn = cat.por_id(titulo["fornecedor_id"])
    return FatosTitulo(
        pagamento=Pagamento(id=titulo["titulo_id"], origem="erp", fornecedor_id=titulo["fornecedor_id"], nf_numero=titulo["numero_nf_digitado"], parcela=titulo["parcela"], valor=titulo["valor"], vencimento=date.fromisoformat(titulo["vencimento"]), estado=titulo["status"], lote=titulo["lote_remessa"] or None, forma_pagamento=titulo["forma_pagamento"]),
        categoria=forn.categoria,
        identidade=resolver_titulo(cat, titulo, oc),
        conferencia=conferencia or conf("ok"),  # a conferência 3 vias real é da T4; aqui só identidade e comunicações
        riscos=riscos,
        aprovacao_registrada=bool(titulo["aprovado_por"]),
    )


def test_real_boleto_com_beneficiario_trocado_retira_e_aciona(real):
    gw, cat, comms = real
    r = analisar_comunicacao(gw, cat, ExtratorMock(), comms["EM571116"])
    d = decidir(fatos_reais(gw, cat, gw.chamar("consultar_titulo", titulo_id="TP431754"), (r,)))
    assert acoes(d) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA] and d.pessoa_a_acionar == "PS01"
    assert d.acoes[0].parametros["titulo_id"] == "TP431754" and d.incidente == "FP4345|fraude"


def test_real_fornecedor_diferente_da_oc_retira(real):
    gw, cat, _ = real
    for tid in ("TP431946", "TP432337"):
        d = decidir(fatos_reais(gw, cat, gw.chamar("consultar_titulo", titulo_id=tid)))
        assert acoes(d) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA], tid


def test_real_embalarte_retira_titulo_agendado_e_compartilha_incidente(real):
    gw, cat, comms = real
    r = analisar_comunicacao(gw, cat, ExtratorMock(), comms["EM571119"])
    agendados = gw.chamar("buscar_titulos", fornecedor_id="FP4615", status="agendado", limite=1000)
    por_conta = [t for t in agendados if t["forma_pagamento"] in ("ted", "pix")]
    por_boleto = [t for t in agendados if t["forma_pagamento"] == "boleto"]
    assert por_conta
    for t in por_conta[:10]:
        d = decidir(fatos_reais(gw, cat, t, (r,)))
        assert acoes(d) == [Acao.RETIRAR, Acao.ACIONAR_PESSOA]
    for t in por_boleto[:10]:  # boleto não usa a conta do cadastro
        assert acoes(decidir(fatos_reais(gw, cat, t, (r,)))) == []
    assert decidir_comunicacao(r).incidente == d.incidente == "FP4615|fraude"


def test_real_titulo_limpo_agendado_e_mantido(real):
    gw, cat, _ = real
    limpo = next(t for t in gw.chamar("buscar_titulos", status="agendado", limite=1000) if t["fornecedor_id"] not in ("FP4615", "FP4345", "FP5079", "FP3614") and t["valor"] <= D("5000"))
    d = decidir(fatos_reais(gw, cat, limpo))
    assert d.regra_aplicada == "R7_limpo_manter" and d.acoes == ()


def test_real_impersonacao_vai_para_juridico_sem_tocar_titulos(real):
    gw, cat, comms = real
    d = decidir_comunicacao(analisar_comunicacao(gw, cat, ExtratorMock(), comms["EM571100"]))
    assert [a.parametros["pessoa_id"] for a in d.acoes] == ["PS08", "PS02"]
