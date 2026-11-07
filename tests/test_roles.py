from pathlib import Path

import pytest

from sentinela.contracts import Papel
from sentinela.roles import (
    FERRAMENTAS_ANALISTA_CP,
    FERRAMENTAS_PROIBIDAS_ANALISTA_CP,
    PermissaoNegada,
    carregar_do_csv,
    exigir,
)

CSV_OFICIAL = Path(__file__).resolve().parents[1] / "docs" / "fonte-oficial" / "ferramentas.csv"


def test_registro_espelha_csv_oficial():
    oficial = carregar_do_csv(CSV_OFICIAL)[Papel.ANALISTA_CP]
    assert oficial == FERRAMENTAS_ANALISTA_CP


def test_proibidas_nao_estao_no_csv_do_analista():
    oficial = carregar_do_csv(CSV_OFICIAL)[Papel.ANALISTA_CP]
    assert not (FERRAMENTAS_PROIBIDAS_ANALISTA_CP & oficial)


def test_contagens():
    assert len(FERRAMENTAS_ANALISTA_CP) == 16
    assert len(FERRAMENTAS_PROIBIDAS_ANALISTA_CP) == 11


@pytest.mark.parametrize("ferramenta", sorted(FERRAMENTAS_PROIBIDAS_ANALISTA_CP))
def test_ferramenta_proibida_levanta(ferramenta):
    with pytest.raises(PermissaoNegada):
        exigir(Papel.ANALISTA_CP, ferramenta)


@pytest.mark.parametrize("ferramenta", sorted(FERRAMENTAS_ANALISTA_CP))
def test_ferramenta_permitida_passa(ferramenta):
    exigir(Papel.ANALISTA_CP, ferramenta)
