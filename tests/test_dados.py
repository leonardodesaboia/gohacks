import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
DATA = RAIZ / "data" / "raw"

spec = importlib.util.spec_from_file_location("validar_dados", RAIZ / "scripts" / "validar_dados.py")
vd = importlib.util.module_from_spec(spec)
sys.modules["validar_dados"] = vd
spec.loader.exec_module(vd)

pytestmark = pytest.mark.skipif(not DATA.exists(), reason="data/raw ausente (dados do evento não versionados)")


def test_todos_os_arquivos_validam():
    resultados, globais = vd.validar(DATA)
    assert globais == []
    erros = {r.nome: r.erros for r in resultados if r.erros}
    assert erros == {}


def test_comunicacoes_e_csv_nao_jsonl():
    assert (DATA / "comunicacoes_fornecedores.csv").exists()
    assert not (DATA / "comunicacoes_fornecedores.jsonl").exists()


def test_classificacao_de_acesso_do_analista():
    por_acesso = {}
    for nome, (_, _, acesso) in vd.ESPERADO.items():
        por_acesso.setdefault(acesso, set()).add(nome)
    assert {"fornecedores", "contas_a_pagar", "agenda_remessa", "pedidos_compra", "notas_fiscais", "nf_duplicatas", "comunicacoes_fornecedores"} == por_acesso[vd.LEGIVEL]
    proibidos = {"alteracoes_cadastro", "extrato_banco_meridiano", "extrato_banco_litoral", "log_auditoria_erp", "aprovacoes", "usuarios_sistema", "lotes_remessa", "retorno_remessa", "dda_boletos"}
    assert proibidos == por_acesso[vd.BLOQUEADO]


def test_coluna_ausente_falha(tmp_path):
    (tmp_path / "nf_duplicatas.csv").write_text("chave_acesso,n_dup,valor\nx,001,1.00\n", encoding="utf-8")
    res = vd.validar_arquivo(tmp_path, "nf_duplicatas")
    assert any("colunas ausentes" in e for e in res.erros)


def test_data_fora_do_formato_falha(tmp_path):
    (tmp_path / "nf_duplicatas.csv").write_text("chave_acesso,n_dup,vencimento,valor\nx,001,02/11/2026,1.00\n", encoding="utf-8")
    res = vd.validar_arquivo(tmp_path, "nf_duplicatas")
    assert any("formato de data" in e for e in res.erros)


def test_arquivo_ausente_falha(tmp_path):
    res = vd.validar_arquivo(tmp_path, "fornecedores")
    assert res.erros == ["arquivo ausente"]
