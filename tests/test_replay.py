import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sentinela.adapters.replay import (
    AcaoRecusada,
    AprovacaoNecessaria,
    LoteFechado,
    NaoEncontrado,
    ReplayAdapter,
)
from sentinela.clock import SimClock, carregar_feriados_remessa
from sentinela.contracts import Papel
from sentinela.gateway import ToolGateway
from sentinela.roles import FERRAMENTAS_PROIBIDAS_ANALISTA_CP, PermissaoNegada

DATA = Path(__file__).resolve().parents[1] / "data" / "raw"
CORTE = datetime(2026, 11, 2, 8, 0)

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/raw ausente")


def csv_raw(nome):
    with (DATA / f"{nome}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def novo(agora=CORTE):
    clock = SimClock(agora, carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))
    return ReplayAdapter(DATA, clock), clock


def primeiro_agendado(ad, lote="RM20261103-MER", max_valor=Decimal("5000")):
    for linha in ad.listar_agenda_remessa(lote_remessa=lote):
        if linha["valor"] <= max_valor:
            return linha
    pytest.skip("nenhum título agendado elegível")


# ---------------------------------------------------------------- estado no corte
def test_titulos_no_corte_coincidem_com_o_csv():
    ad, _ = novo()
    base = csv_raw("contas_a_pagar")
    for r in base:
        v = ad.consultar_titulo(r["titulo_id"])
        assert (v["status"], v["lote_remessa"]) == (r["status"], r["lote_remessa"]), r["titulo_id"]
    assert len(base) == 7120


def test_agenda_no_corte_coincide_com_o_csv():
    ad, _ = novo()
    esperado = {(r["lote_remessa"], r["titulo_id"], Decimal(r["valor"]), r["destino_pagamento"]) for r in csv_raw("agenda_remessa")}
    obtido = {(r["lote_remessa"], r["titulo_id"], r["valor"], r["destino_pagamento"]) for r in ad.listar_agenda_remessa()}
    assert obtido == esperado


def test_cadastro_no_corte_coincide_com_o_csv():
    ad, _ = novo()
    for r in csv_raw("fornecedores"):
        assert ad.consultar_fornecedor(fornecedor_id=r["fornecedor_id"]) == r


# ------------------------------------------------------------------- sem futuro
@pytest.mark.parametrize("agora", [datetime(2026, 10, 5, 12), datetime(2026, 10, 20, 9), datetime(2026, 10, 29, 15), CORTE])
def test_nao_vaza_futuro(agora):
    ad, _ = novo(agora)
    for v in ad.buscar_titulos(limite=100000):
        assert datetime.fromisoformat(v["data_lancamento"]) <= agora
        for campo in ("data_aprovacao", "data_baixa", "data_cancelamento"):
            if v[campo]:
                assert datetime.fromisoformat(v[campo]) <= agora
    for c in ad.listar_comunicacoes():
        assert datetime.fromisoformat(c["data_hora"]) <= agora


def test_nf_futura_so_aparece_depois_de_chegar():
    nf = max(csv_raw("notas_fiscais"), key=lambda r: r["data_recebimento_portal"])
    chegada = datetime.fromisoformat(nf["data_recebimento_portal"])
    antes, _ = novo(datetime(chegada.year, chegada.month, chegada.day - 1, 0, 0))
    with pytest.raises(NaoEncontrado):
        antes.consultar_nf(chave_acesso=nf["chave_acesso"])
    depois, _ = novo(datetime(2026, 11, 2, 8, 0))
    achada = depois.consultar_nf(chave_acesso=nf["chave_acesso"])
    assert achada["valor_total"] == Decimal(nf["valor_total"])
    assert achada["duplicatas"]


def test_aprovacao_de_oc_posterior_ao_corte_fica_mascarada():
    futuras = [r for r in csv_raw("pedidos_compra") if r["data_aprovacao"] > "2026-11-02 08:00"]
    assert futuras
    ad, _ = novo()
    for r in futuras:
        v = ad.consultar_pedido_compra(oc_id=r["oc_id"])
        assert (v["aprovado_por"], v["data_aprovacao"], v["status"]) == ("", "", "pendente_aprovacao")


# ------------------------------------------------- caso Embalarte (FP4615) no tempo
def test_embalarte_comunicacao_e_cadastro_no_tempo():
    ad, clock = novo(datetime(2026, 10, 29, 14, 0))
    assert not ad.listar_comunicacoes(remetente="embalartte")
    antigo = ad.consultar_fornecedor(fornecedor_id="FP4615")
    assert (antigo["banco"], antigo["conta"]) == ("774", "9517944-5")
    clock.definir(datetime(2026, 10, 29, 16, 0))
    msgs = ad.listar_comunicacoes(remetente="embalartte")
    assert [m["comunicacao_id"] for m in msgs] == ["EM571119"]
    assert ad.consultar_fornecedor(fornecedor_id="FP4615")["conta"] == "9517944-5"  # cadastro ainda não mudou
    clock.definir(datetime(2026, 10, 30, 16, 5))
    novo_cad = ad.consultar_fornecedor(fornecedor_id="FP4615")
    assert (novo_cad["banco"], novo_cad["conta"], novo_cad["ultima_alteracao_por"]) == ("905", "4471203-9", "usuario_07")


# ------------------------------------------------------------------- leituras
def test_buscar_titulos_filtros():
    ad, _ = novo()
    emb = ad.buscar_titulos(fornecedor_id="FP4615", status="agendado", limite=1000)
    assert emb and all(v["fornecedor_id"] == "FP4615" and v["status"] == "agendado" for v in emb)
    cnpj = ad.consultar_fornecedor(fornecedor_id="FP4615")["cnpj"]
    por_cnpj = ad.buscar_titulos(cnpj=cnpj.replace(".", "").replace("/", "").replace("-", ""), status="agendado", limite=1000)
    assert {v["titulo_id"] for v in por_cnpj} == {v["titulo_id"] for v in emb}
    assert all(isinstance(v["valor"], Decimal) for v in emb)
    assert len(ad.buscar_titulos(limite=3)) == 3


def test_consultas_inexistentes():
    ad, _ = novo()
    with pytest.raises(NaoEncontrado):
        ad.consultar_titulo("TP000000")
    with pytest.raises(NaoEncontrado):
        ad.consultar_fornecedor(fornecedor_id="FP0000")
    with pytest.raises(AcaoRecusada):
        ad.consultar_nf(numero_nf="1")


def test_politicas_e_pessoas():
    ad, _ = novo()
    p = ad.consultar_politicas()
    assert p["alcadas"]["analista_cp.liberar_ou_agendar_ate"] == "5000.0"
    assert p["remessa"]["bancos_pagadores.Banco Meridiano.fechamento_do_lote"] == "10:00"


# ------------------------------------------------------------------- execuções
def test_retirar_do_lote_reflete_no_estado_e_na_agenda():
    ad, _ = novo()
    alvo = primeiro_agendado(ad)
    r = ad.retirar_do_lote(alvo["titulo_id"], motivo="teste")
    assert r["estado"] == "aberto"
    v = ad.consultar_titulo(alvo["titulo_id"])
    assert (v["status"], v["lote_remessa"]) == ("aberto", "")
    assert alvo["titulo_id"] not in {x["titulo_id"] for x in ad.listar_agenda_remessa()}
    assert ad.acoes[-1]["ferramenta"] == "retirar_do_lote"
    with pytest.raises(AcaoRecusada):
        ad.retirar_do_lote(alvo["titulo_id"], motivo="de novo")
    with pytest.raises(AcaoRecusada):
        ad.retirar_do_lote("TP426275", motivo="")


def test_lote_fechado_recusa_retirada_e_agendamento():
    ad, clock = novo()
    alvo = primeiro_agendado(ad)
    clock.definir(datetime(2026, 11, 3, 10, 0))
    with pytest.raises(LoteFechado):
        ad.retirar_do_lote(alvo["titulo_id"], motivo="tarde demais")
    assert alvo["titulo_id"] not in {x["titulo_id"] for x in ad.listar_agenda_remessa()}


def test_reagendar_apos_retirar_e_regras_de_alcada():
    ad, _ = novo()
    alvo = primeiro_agendado(ad)
    ad.retirar_do_lote(alvo["titulo_id"], motivo="teste")
    with pytest.raises(AcaoRecusada):
        ad.agendar_titulo(alvo["titulo_id"], "lote-invalido")
    with pytest.raises(AcaoRecusada):
        ad.agendar_titulo(alvo["titulo_id"], "RM20261107-MER")  # sábado
    ad.agendar_titulo(alvo["titulo_id"], alvo["lote_remessa"])
    assert ad.consultar_titulo(alvo["titulo_id"])["status"] == "agendado"
    caro = next(x for x in ad.listar_agenda_remessa() if x["valor"] > Decimal("5000"))
    ad.retirar_do_lote(caro["titulo_id"], motivo="teste")
    with pytest.raises(AprovacaoNecessaria):
        ad.agendar_titulo(caro["titulo_id"], caro["lote_remessa"])


def test_antecipacao_exige_aprovacao_dupla():
    ad, _ = novo()
    alvo = next(x for x in ad.listar_agenda_remessa() if x["valor"] <= Decimal("5000") and x["vencimento"] > "2026-11-04")
    ad.retirar_do_lote(alvo["titulo_id"], motivo="teste")
    with pytest.raises(AprovacaoNecessaria):
        ad.agendar_titulo(alvo["titulo_id"], "RM20261103-MER")


def test_corrigir_lancamento_regras():
    ad, _ = novo()
    alvo = primeiro_agendado(ad)
    tid = alvo["titulo_id"]
    with pytest.raises(AcaoRecusada):
        ad.corrigir_lancamento(tid, "valor", "10.00", evidencias=[])
    with pytest.raises(AcaoRecusada):
        ad.corrigir_lancamento(tid, "historico", "x", evidencias=["e"])
    for campo in ("fornecedor_id", "forma_pagamento", "linha_digitavel"):
        with pytest.raises(AprovacaoNecessaria):
            ad.corrigir_lancamento(tid, campo, "x", evidencias=["e"])
    with pytest.raises(AprovacaoNecessaria):
        ad.corrigir_lancamento(tid, "valor", alvo["valor"] + Decimal("5000.01"), evidencias=["e"])
    r = ad.corrigir_lancamento(tid, "valor", alvo["valor"] + Decimal("100"), evidencias=["e"], justificativa="teste")
    assert r["valor_novo"] == alvo["valor"] + Decimal("100")
    assert ad.consultar_titulo(tid)["valor"] == alvo["valor"] + Decimal("100")
    ad.corrigir_lancamento(tid, "numero_nf_digitado", "999", evidencias=["e"])
    assert ad.consultar_titulo(tid)["numero_nf_digitado"] == "999"
    with pytest.raises(AcaoRecusada):
        ad.corrigir_lancamento(tid, "vencimento", "31/12/2026", evidencias=["e"])


def test_cancelar_titulo_regras():
    ad, _ = novo()
    with pytest.raises(AcaoRecusada):
        ad.cancelar_titulo("TP426275", motivo="x", evidencias=["e"])  # título pago
    alvo = primeiro_agendado(ad)
    with pytest.raises(AcaoRecusada):
        ad.cancelar_titulo(alvo["titulo_id"], motivo="x", evidencias=[])
    ad.cancelar_titulo(alvo["titulo_id"], motivo="duplicidade", evidencias=["e"])
    v = ad.consultar_titulo(alvo["titulo_id"])
    assert (v["status"], v["lote_remessa"]) == ("cancelado", "")
    caro = next(x for x in ad.listar_agenda_remessa() if x["valor"] > Decimal("5000"))
    with pytest.raises(AprovacaoNecessaria):
        ad.cancelar_titulo(caro["titulo_id"], motivo="x", evidencias=["e"])


def test_contato_so_pelo_canal_do_cadastro():
    ad, _ = novo()
    cad = ad.consultar_fornecedor(fornecedor_id="FP4615")
    r = ad.contatar_fornecedor("FP4615", "email", "Confirmar dados bancários")
    assert r["enviado_para"] == cad["email_cadastrado"]
    with pytest.raises(AcaoRecusada):
        ad.contatar_fornecedor("FP4615", "whatsapp_do_remetente", "oi")


def test_acionar_pessoa_solicitar_e_responder():
    ad, _ = novo()
    r = ad.acionar_pessoa("PS01", motivo="suspeita de fraude", urgencia="alta", titulos=["TP1"])
    assert r["pessoa"] == "Renata Paiva"
    with pytest.raises(AcaoRecusada):
        ad.acionar_pessoa("PS99", motivo="x")
    s = ad.solicitar_aprovacao("agendar_titulo", {"titulo_id": "TP1"}, ["evidência"])
    assert s["solicitacao_id"] == "SOL-0001"
    with pytest.raises(AcaoRecusada):
        ad.solicitar_aprovacao("agendar_titulo", {}, [])
    assert ad.responder_colaborador("SOL-0001", "ok")["estado"] == "respondida"


# ------------------------------------------------- integração com o gateway
def test_gateway_com_replay_executa_e_nega():
    ad, clock = novo()
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    ad.registrar_em(gw)
    gw.chamar("consultar_fornecedor", fornecedor_id="FP4615")
    assert gw.historico[-1].instante == clock.agora
    with pytest.raises(PermissaoNegada):
        gw.chamar("consultar_historico_cadastro", fornecedor_id="FP4615")
    with pytest.raises(PermissaoNegada):
        gw.chamar("consultar_extrato", banco="meridiano")


@pytest.mark.parametrize("ferramenta", sorted(FERRAMENTAS_PROIBIDAS_ANALISTA_CP))
def test_adaptador_nao_expoe_ferramentas_proibidas(ferramenta):
    ad, _ = novo()
    assert not hasattr(ad, ferramenta)
