from datetime import date, datetime
from pathlib import Path

import pytest

from sentinela.clock import SimClock, carregar_feriados_remessa, nome_lote, parse_lote

CSV = Path(__file__).resolve().parents[1] / "docs" / "fonte-oficial" / "parametros.md"
FERIADOS_CSV = Path(__file__).resolve().parents[1] / "data" / "raw" / "feriados_bancarios.csv"

pytestmark = pytest.mark.skipif(not FERIADOS_CSV.exists(), reason="data/raw ausente")


@pytest.fixture
def clock():
    return SimClock(datetime(2026, 11, 2, 8, 0), carregar_feriados_remessa(FERIADOS_CSV))


def test_finados_e_fim_de_semana_nao_sao_uteis(clock):
    assert not clock.eh_dia_util(date(2026, 11, 2))  # Finados
    assert not clock.eh_dia_util(date(2026, 11, 7))  # sábado
    assert not clock.eh_dia_util(date(2026, 11, 15))  # domingo/feriado
    assert clock.eh_dia_util(date(2026, 11, 3))


def test_feriado_estadual_nao_bloqueia_remessa(clock):
    assert clock.eh_dia_util(date(2026, 3, 19))  # São José (CE): compensação nacional funciona
    assert not clock.eh_dia_util(date(2026, 4, 21))  # Tiradentes (nacional)


def test_proximo_dia_util(clock):
    assert clock.proximo_dia_util(date(2026, 11, 2)) == date(2026, 11, 3)
    assert clock.proximo_dia_util(date(2026, 11, 7)) == date(2026, 11, 9)
    assert clock.proximo_dia_util(date(2026, 11, 3), inclusive=False) == date(2026, 11, 4)


def test_parse_e_nome_lote():
    assert parse_lote("RM20261103-MER") == (date(2026, 11, 3), "MER")
    assert nome_lote(date(2026, 11, 3), "LIT") == "RM20261103-LIT"
    for ruim in ("", "RM2026113-MER", "RM20261103-XXX", "X"):
        with pytest.raises(ValueError):
            parse_lote(ruim)


def test_fechamentos(clock):
    assert SimClock.fechamento("RM20261103-MER") == datetime(2026, 11, 3, 10, 0)
    assert SimClock.fechamento("RM20261103-LIT") == datetime(2026, 11, 3, 14, 0)


def test_proximo_fechamento_sequencia(clock):
    assert clock.proximo_fechamento() == ("RM20261103-MER", datetime(2026, 11, 3, 10, 0))  # 02/11 é feriado
    clock.definir(datetime(2026, 11, 3, 10, 0))
    assert clock.proximo_fechamento()[0] == "RM20261103-LIT"
    clock.definir(datetime(2026, 11, 3, 14, 0))
    assert clock.proximo_fechamento()[0] == "RM20261104-MER"
    clock.definir(datetime(2026, 11, 6, 14, 0))  # sexta depois do corte
    assert clock.proximo_fechamento()[0] == "RM20261109-MER"  # pula o fim de semana


def test_lote_fechado_no_instante_exato(clock):
    clock.definir(datetime(2026, 11, 3, 9, 59))
    assert not clock.lote_fechado("RM20261103-MER")
    clock.definir(datetime(2026, 11, 3, 10, 0))
    assert clock.lote_fechado("RM20261103-MER")
    assert not clock.lote_fechado("RM20261103-LIT")


def test_relogio_so_avanca(clock):
    assert clock() == datetime(2026, 11, 2, 8, 0)
    assert clock.avancar() == datetime(2026, 11, 2, 9, 0)
    with pytest.raises(ValueError):
        clock.avancar(0)
    with pytest.raises(ValueError):
        clock.definir(datetime(2026, 11, 2, 8, 0))


def test_fim_do_periodo(clock):
    assert not clock.terminou
    clock.definir(datetime(2026, 11, 9, 8, 0))
    assert clock.terminou


def test_ultimo_tique_antes_do_corte(clock):
    assert clock.ultimo_tique_antes(datetime(2026, 11, 3, 10, 0)) == datetime(2026, 11, 3, 9, 0)
    assert clock.ultimo_tique_antes(datetime(2026, 11, 3, 10, 30)) == datetime(2026, 11, 3, 10, 0)
