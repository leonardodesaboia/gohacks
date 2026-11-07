import csv
from datetime import datetime
from pathlib import Path

import pytest

from sentinela.adapters.replay import NaoEncontrado, ReplayAdapter
from sentinela.clock import SimClock, carregar_feriados_remessa
from sentinela.contracts import Papel
from sentinela.gateway import ToolGateway
from sentinela.identity import (
    Status,
    montar_catalogo,
    normalizar_cnpj,
    raiz_cnpj,
    cnpj_valido,
    resolver_cnpj,
    resolver_titulo,
    vincular_comunicacao,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "raw"
CORTE = datetime(2026, 11, 2, 8, 0)

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/raw ausente")


def csv_raw(nome):
    with (DATA / f"{nome}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def ambiente():
    clock = SimClock(CORTE, carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))
    adapter = ReplayAdapter(DATA, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    adapter.registrar_em(gw)
    return gw, montar_catalogo(gw)


@pytest.fixture(scope="module")
def resolucoes(ambiente):
    gw, cat = ambiente
    saida = {}
    for t in gw.chamar("buscar_titulos", limite=1_000_000):
        oc = None
        if t["oc_id"]:
            try:
                oc = gw.chamar("consultar_pedido_compra", oc_id=t["oc_id"])
            except NaoEncontrado:
                oc = None
        saida[t["titulo_id"]] = (t, resolver_titulo(cat, t, oc))
    return saida


# ------------------------------------------------------------------- CNPJ
def test_normalizar_e_raiz():
    assert normalizar_cnpj("85.779.751/0001-00") == "85779751000100"
    assert raiz_cnpj("85.779.751/0001-00") == "85779751"
    assert raiz_cnpj("123") == ""
    assert normalizar_cnpj(None) == ""


def test_cnpj_valido_e_invalidos():
    assert cnpj_valido("85.779.751/0001-00")
    for ruim in ("", "123", "11111111111111", "85779751000101", "abc"):
        assert not cnpj_valido(ruim)


def test_todos_os_cnpjs_dos_fornecedores_sao_validos():
    assert all(cnpj_valido(r["cnpj"]) for r in csv_raw("fornecedores"))


# ---------------------------------------------------------------- catálogo
def test_catalogo_tem_131_fornecedores_com_raiz_unica(ambiente):
    _, cat = ambiente
    assert len(cat) == 131
    assert len({f.raiz_cnpj for f in cat.todos}) == 131
    assert cat.por_id("FP4615").nome_fantasia


def test_oc_resolve_para_um_fornecedor_e_codigo_compras_e_biunivoco(ambiente):
    _, cat = ambiente
    cod_para_raiz: dict[str, set[str]] = {}
    for oc in csv_raw("pedidos_compra"):
        r = resolver_cnpj(cat, oc["cnpj_fornecedor"])
        assert (r.status, r.estabelecimento) == (Status.OK, "matriz"), oc["oc_id"]
        cod_para_raiz.setdefault(oc["cod_fornecedor_compras"], set()).add(raiz_cnpj(oc["cnpj_fornecedor"]))
    assert all(len(v) == 1 for v in cod_para_raiz.values())
    assert len({next(iter(v)) for v in cod_para_raiz.values()}) == len(cod_para_raiz)  # raiz -> um código só
    assert {f"FN{i}" for i in range(1, 7)} <= set(cod_para_raiz)


def test_emitentes_de_nf_matriz_e_filial(ambiente):
    _, cat = ambiente
    contagem: dict[str, int] = {}
    for nf in csv_raw("notas_fiscais"):
        r = resolver_cnpj(cat, nf["cnpj_emitente"])
        assert r.status is Status.OK, nf["chave_acesso"]
        contagem[r.estabelecimento] = contagem.get(r.estabelecimento, 0) + 1
    assert contagem == {"matriz": 3951, "filial": 200}


def test_filial_real_da_nordplast_e_o_mesmo_fornecedor(ambiente):
    _, cat = ambiente
    r = resolver_cnpj(cat, "13030916000217")  # NORDPLAST INJETADOS SA FILIAL JABOATAO
    assert (r.status, r.estabelecimento, r.fornecedor.id_origem) == (Status.OK, "filial", "FP6212")


def test_resolver_cnpj_invalido_e_ausente(ambiente):
    _, cat = ambiente
    assert resolver_cnpj(cat, "11111111111111").status is Status.INVALIDO
    assert resolver_cnpj(cat, "").status is Status.INVALIDO
    assert resolver_cnpj(cat, "61.525.615/0001-26").status is Status.AUSENTE  # CNPJ do beneficiário suspeito


# ------------------------------------------------------------------ títulos
def test_resolucao_dos_titulos_no_corte(resolucoes):
    assert len(resolucoes) == 7120
    por_status = {}
    for _, r in resolucoes.values():
        por_status[r.status] = por_status.get(r.status, 0) + 1
    assert por_status == {Status.OK: 7117, Status.DIVERGENTE: 3}


def test_divergentes_sao_exatamente_os_tres_casos_reais(resolucoes):
    div = {tid for tid, (_, r) in resolucoes.items() if r.status is Status.DIVERGENTE}
    assert div == {"TP431754", "TP431946", "TP432337"}
    assert all(resolucoes[t][0]["status"] == "agendado" for t in div)


def test_fornecedor_do_titulo_difere_do_da_oc(resolucoes):
    _, r = resolucoes["TP431946"]
    assert (r.fornecedor.id_origem, r.fornecedor_da_oc) == ("FP5079", "FP6799")
    _, r = resolucoes["TP432337"]
    assert (r.fornecedor.id_origem, r.fornecedor_da_oc) == ("FP3614", "FP3302")


def test_boleto_de_segunda_via_tem_beneficiario_do_email_suspeito(ambiente, resolucoes):
    gw, cat = ambiente
    titulo, r = resolucoes["TP431754"]
    assert r.status is Status.DIVERGENTE and "beneficiário do boleto" in r.motivos[0]
    email = next(c for c in gw.chamar("listar_comunicacoes") if c["comunicacao_id"] == "EM571116")
    assert titulo["cnpj_beneficiario_boleto"] in email["anexos"]  # o boleto do e-mail é o do título
    assert raiz_cnpj(titulo["cnpj_beneficiario_boleto"]) != r.fornecedor.raiz_cnpj
    assert email["remetente"].endswith("@outlook.com")


BASE_TITULO = {"titulo_id": "TPX", "fornecedor_id": "FP4615", "oc_id": "OC-1", "cnpj_beneficiario_boleto": ""}


def test_oc_nao_localizada_e_ausente(ambiente):
    _, cat = ambiente
    r = resolver_titulo(cat, BASE_TITULO, None)
    assert r.status is Status.AUSENTE and "OC-1" in r.motivos[0]


def test_titulo_sem_oc_depende_da_categoria(ambiente):
    _, cat = ambiente
    util = next(f for f in cat.todos if f.categoria == "utilidades")
    prod = next(f for f in cat.todos if f.categoria == "produto")
    sem_oc = {**BASE_TITULO, "oc_id": ""}
    assert resolver_titulo(cat, {**sem_oc, "fornecedor_id": util.id_origem}, None).status is Status.OK
    assert resolver_titulo(cat, {**sem_oc, "fornecedor_id": prod.id_origem}, None).status is Status.AUSENTE


def test_fornecedor_fora_do_catalogo_e_ausente(ambiente):
    _, cat = ambiente
    assert resolver_titulo(cat, {**BASE_TITULO, "fornecedor_id": "FP0000"}, None).status is Status.AUSENTE


def test_divergencia_tem_prioridade_sobre_ausencia(ambiente):
    _, cat = ambiente
    t = {**BASE_TITULO, "oc_id": "", "fornecedor_id": next(f.id_origem for f in cat.todos if f.categoria == "produto"), "cnpj_beneficiario_boleto": "61.525.615/0001-26"}
    r = resolver_titulo(cat, t, None)
    assert r.status is Status.DIVERGENTE and len(r.motivos) == 2


def test_cnpj_de_beneficiario_invalido_diverge(ambiente):
    _, cat = ambiente
    r = resolver_titulo(cat, {**BASE_TITULO, "oc_id": "", "fornecedor_id": next(f.id_origem for f in cat.todos if f.categoria == "utilidades"), "cnpj_beneficiario_boleto": "11.111.111/1111-11"}, None)
    assert r.status is Status.DIVERGENTE


# -------------------------------------------------------------- comunicações
@pytest.fixture(scope="module")
def vinculos(ambiente):
    gw, cat = ambiente
    return {c["comunicacao_id"]: vincular_comunicacao(cat, c) for c in gw.chamar("listar_comunicacoes")}


def test_241_comunicacoes_vem_do_email_cadastrado(vinculos):
    legitimas = [v for v in vinculos.values() if v.status is Status.OK and v.melhor.remetente_confere]
    assert len(legitimas) == 241 and len(vinculos) == 246


def test_cinco_remetentes_nao_conferem_e_sao_os_conhecidos(vinculos):
    suspeitos = {k for k, v in vinculos.items() if not (v.status is Status.OK and v.melhor.remetente_confere)}
    assert suspeitos == {"EM570977", "EM570998", "EM571100", "EM571116", "EM571119"}


def test_embalarte_vincula_por_cnpj_e_nome_mas_remetente_nao_confere(vinculos):
    v = vinculos["EM571119"]
    assert (v.status, v.melhor.fornecedor_id, v.melhor.remetente_confere) == (Status.OK, "FP4615", False)
    assert set(v.melhor.sinais) == {"cnpj", "nome"}


def test_impersonacao_de_banco_receita_e_cartorio_nao_e_fornecedor(vinculos):
    for cid in ("EM570977", "EM570998", "EM571100"):
        assert vinculos[cid].status is Status.AUSENTE


def test_segunda_via_por_dominio_publico_so_tem_evidencia_de_nome(vinculos):
    v = vinculos["EM571116"]
    assert (v.status, v.melhor.fornecedor_id, v.melhor.remetente_confere) == (Status.AMBIGUO, "FP4345", False)
    assert v.melhor.sinais == ("nome",)


def test_empate_entre_fornecedores_e_ambiguo(ambiente):
    _, cat = ambiente
    a, b = cat.todos[0], cat.todos[1]
    comm = {"comunicacao_id": "EMX", "remetente": "x@desconhecido.com", "nome_remetente": "", "assunto": "", "texto": "", "anexos": f"{a.cnpj} {b.cnpj}"}
    assert vincular_comunicacao(cat, comm).status is Status.AMBIGUO
