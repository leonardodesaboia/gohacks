import csv
import importlib.util
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sentinela.clock import carregar_feriados_remessa
from sentinela.identity import Catalogo, Status, fornecedor_ref, resolver_titulo
from sentinela.threeway import conferir_titulo, numero_e_serie, valor_com_acrescimos

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="bases sintéticas indisponíveis")


def rows(nome):
    with (DATA / f"{nome}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def base():
    return {n: rows(n) for n in ("contas_a_pagar", "fornecedores", "notas_fiscais", "nf_duplicatas", "pedidos_compra")}


def caso(base, titulo_id):
    t = next(v for v in base["contas_a_pagar"] if v["titulo_id"] == titulo_id)
    f = next(v for v in base["fornecedores"] if v["fornecedor_id"] == t["fornecedor_id"])
    numero, _ = numero_e_serie(t["numero_nf_digitado"])
    nfs = [n for n in base["notas_fiscais"] if n["cnpj_emitente"][:8] == ''.join(c for c in f["cnpj"] if c.isdigit())[:8] and str(int(n["numero_nf"])) == numero] if numero else []
    ocs = [o for o in base["pedidos_compra"] if o["oc_id"] == t["oc_id"]]
    dups = [d for d in base["nf_duplicatas"] if d["chave_acesso"] in {n["chave_acesso"] for n in nfs}]
    return t, f, nfs, dups, ocs[0] if ocs else None


def conferir(base, titulo_id):
    return conferir_titulo(*caso(base, titulo_id), carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))


def test_parcela_correta_e_fator_dez_nao_total_da_nf(base):
    r = conferir(base, "TP431459")
    assert r.resultado == "divergente" and r.tipo == "valor_titulo"
    assert r.valor_esperado == Decimal("4838.00")
    assert r.diferenca == Decimal("43542.00") and len(r.chave_acesso) == 44
    assert r.parcela == "2/3"


def test_outro_erro_agendado(base):
    r = conferir(base, "TP431775")
    assert r.valor_esperado == Decimal("9087.38") and r.diferenca == Decimal("81786.42")


def test_aluguel_sem_nf_e_utilidades_sem_oc(base):
    assert conferir(base, "TP432883").resultado == "ok"
    assert conferir(base, "TP433169").resultado == "ok"
    assert conferir(base, "TP432883").chave_acesso == ""


def test_cancelado_e_relancado_nao_contam_como_duplicidade(base):
    antigo = next(t for t in base["contas_a_pagar"] if t["titulo_id"] == "TP431693")
    novo = next(t for t in base["contas_a_pagar"] if t["titulo_id"] == "TP431915")
    assert antigo["status"] == "cancelado" and novo["status"] == "pago"
    assert (antigo["fornecedor_id"], antigo["numero_nf_digitado"], antigo["parcela"]) == (novo["fornecedor_id"], novo["numero_nf_digitado"], novo["parcela"])


def test_ambiguidade_de_chaves_nao_e_resolvida_por_valor(base):
    t, f, nfs, dups, oc = caso(base, "TP431459")
    original = nfs[0]
    concorrente = {**original, "chave_acesso": "9" * 44, "valor_total": "999999.00"}
    r = conferir_titulo(t, f, [original, concorrente], dups, oc)
    # Mesmo CNPJ e OC: nenhuma dessas pistas separa as duas chaves.
    assert r.resultado == "ambiguo" and r.chave_acesso == ""
    assert len(r.candidatos) == 2 and r.valor_esperado is None


def test_nf_filial_com_mesma_raiz_e_aceita(base):
    t, f, nfs, dups, oc = caso(base, "TP431459")
    assert nfs
    original = nfs[0]
    assert original["cnpj_emitente"][:8] == ''.join(c for c in f["cnpj"] if c.isdigit())[:8]
    assert conferir_titulo(t, f, nfs, dups, oc).chave_acesso == original["chave_acesso"]


def test_oc_e_fornecedor_de_outra_evidencia_nao_sao_aceitos(base):
    t, f, nfs, dups, oc = caso(base, "TP431459")
    outro = {**f, "fornecedor_id": "FP0000"}
    assert conferir_titulo(t, outro, nfs, dups, oc).resultado == "ambiguo"
    assert conferir_titulo(t, f, nfs, dups, {**oc, "oc_id": "OC-00000"}).resultado == "ambiguo"


def test_integracao_t3_beneficiario_boleto_divergente_real(base):
    catalogo = Catalogo([fornecedor_ref(f) for f in base["fornecedores"]])
    t, f, nfs, dups, oc = caso(base, "TP431754")
    identidade = resolver_titulo(catalogo, t, oc)
    assert identidade.status == Status.DIVERGENTE
    assert any("beneficiário" in motivo for motivo in identidade.motivos)
    resultado = conferir_titulo(t, f, nfs, dups, oc, identidade=identidade)
    assert resultado.resultado == "divergente" and "identidade" in resultado.tipo
    assert resultado.chave_acesso and resultado.diferenca == Decimal("0")


def test_tolerancia_oc_e_valor_parcela(base):
    t, f, nfs, dups, oc = caso(base, "TP431459")
    nf = nfs[0]
    limite = max(Decimal(oc["valor_total"]) * Decimal(".02"), Decimal("50"))
    r = conferir_titulo({**t, "valor": "4838.10"}, f, [{**nf, "valor_total": str(Decimal(oc["valor_total"]) + limite)}], dups, oc)
    assert r.resultado == "ok"
    r = conferir_titulo({**t, "valor": "4838.11"}, f, [{**nf, "valor_total": str(Decimal(oc["valor_total"]) + limite + Decimal(".01"))}], dups, oc)
    assert r.resultado == "divergente" and "nf_acima_oc" in r.tipo and "valor_titulo" in r.tipo


def test_feriado_vencimento_e_juros(base):
    t, f, nfs, dups, oc = caso(base, "TP431459")
    dup = next(d for d in dups if d["n_dup"] == "002")
    # Casos reais servem como base; modificações testam as fronteiras da política.
    dup = {**dup, "vencimento": "2026-11-02"}
    alterado = {**t, "valor": dup["valor"], "vencimento": "2026-11-03"}
    r = conferir_titulo(alterado, f, nfs, [dup] + [d for d in dups if d["n_dup"] != "002"], oc,
                        carregar_feriados_remessa(DATA / "feriados_bancarios.csv"))
    assert r.resultado == "ok"
    assert conferir_titulo({**alterado, "vencimento": "2026-11-04"}, f, nfs, [dup] + [d for d in dups if d["n_dup"] != "002"], oc).tipo == "vencimento"
    pago = {**alterado, "status": "pago", "data_pagamento": "2026-11-12", "valor": str(valor_com_acrescimos(Decimal(dup["valor"]), 10))}
    assert conferir_titulo(pago, f, nfs, [dup] + [d for d in dups if d["n_dup"] != "002"], oc,
                           carregar_feriados_remessa(DATA / "feriados_bancarios.csv")).resultado == "ok"


def test_reproducao_cobre_universo_sem_numeros_alvo(tmp_path):
    spec = importlib.util.spec_from_file_location("reproduzir_metricas", ROOT / "scripts" / "reproduzir_metricas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    linhas, resumo = modulo.reproduzir(DATA, datetime(2026, 11, 2, 8))
    universo = {r["titulo_id"] for r in rows("contas_a_pagar") if r["status"] in ("aberto", "agendado")}
    assert {r["titulo_id"] for r in linhas} == universo
    assert sum(resumo["contagens"][k] for k in ("ok", "divergente", "ausente", "ambiguo")) == len(universo)
    assert resumo["totais"]["excesso_em_lote"] <= resumo["totais"]["excesso_nominal"]
    boleto = next(r for r in linhas if r["titulo_id"] == "TP431754")
    assert boleto["status_identidade"] == "divergente" and boleto["resultado"] == "divergente"
    modulo.gravar(linhas, resumo, tmp_path)
    with (tmp_path / "reproducao_metricas.csv").open(encoding="utf-8", newline="") as f:
        assert len(list(csv.DictReader(f))) == len(universo)
    with pytest.raises(ValueError, match="foto"):
        modulo.reproduzir(DATA, datetime(2026, 10, 29, 14))
