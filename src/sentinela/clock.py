"""Relógio simulado, dias úteis de remessa e cortes de lote (T2).

Dia útil de remessa = segunda a sexta, exceto as datas de feriados_bancarios.csv com
`sem_expediente_bancario = sim` **e** `afeta_remessa` começando com "sim". Feriados
estaduais/municipais (compensação nacional funciona) não bloqueiam remessa.
Fechamento: Banco Meridiano 10:00 (MER), Banco Litoral 14:00 (LIT), em dia útil.
"""

from __future__ import annotations

import csv
import math
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path

FECHAMENTO_POR_BANCO: dict[str, time] = {"MER": time(10, 0), "LIT": time(14, 0)}
NOME_BANCO: dict[str, str] = {"MER": "Banco Meridiano", "LIT": "Banco Litoral"}
INICIO_PADRAO = datetime(2026, 11, 2, 8, 0)
FIM_PADRAO = datetime(2026, 11, 9, 8, 0)

_LOTE = re.compile(r"RM(\d{8})-(MER|LIT)")


def carregar_feriados_remessa(caminho: Path) -> frozenset[date]:
    datas: set[date] = set()
    with caminho.open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            if linha["sem_expediente_bancario"].strip() == "sim" and linha["afeta_remessa"].strip().startswith("sim"):
                datas.add(date.fromisoformat(linha["data"]))
    return frozenset(datas)


def parse_lote(lote_id: str) -> tuple[date, str]:
    m = _LOTE.fullmatch(lote_id or "")
    if not m:
        raise ValueError(f"lote inválido: {lote_id!r} (esperado RMaaaammdd-MER|LIT)")
    d = m.group(1)
    return date(int(d[:4]), int(d[4:6]), int(d[6:])), m.group(2)


def nome_lote(dia: date, sufixo: str) -> str:
    return f"RM{dia:%Y%m%d}-{sufixo}"


class SimClock:
    """Relógio de tiques de 1 hora. Chamável: `clock()` devolve o instante atual."""

    def __init__(self, inicio: datetime = INICIO_PADRAO, feriados: frozenset[date] = frozenset(), fim: datetime = FIM_PADRAO):
        self.inicio = inicio
        self.fim = fim
        self.feriados = feriados
        self._agora = inicio

    def __call__(self) -> datetime:
        return self._agora

    @property
    def agora(self) -> datetime:
        return self._agora

    @property
    def terminou(self) -> bool:
        return self._agora >= self.fim

    def avancar(self, horas: float = 1) -> datetime:
        if horas <= 0:
            raise ValueError("o relógio só avança")
        self._agora += timedelta(hours=horas)
        return self._agora

    def definir(self, instante: datetime) -> datetime:
        if instante < self._agora:
            raise ValueError("o relógio não retrocede")
        self._agora = instante
        return self._agora

    def eh_dia_util(self, dia: date) -> bool:
        return dia.weekday() < 5 and dia not in self.feriados

    def proximo_dia_util(self, dia: date, inclusive: bool = True) -> date:
        d = dia if inclusive else dia + timedelta(days=1)
        while not self.eh_dia_util(d):
            d += timedelta(days=1)
        return d

    @staticmethod
    def fechamento(lote_id: str) -> datetime:
        dia, sufixo = parse_lote(lote_id)
        return datetime.combine(dia, FECHAMENTO_POR_BANCO[sufixo])

    def lote_fechado(self, lote_id: str) -> bool:
        """Fechado a partir do instante exato de fechamento (conservador)."""
        return self._agora >= self.fechamento(lote_id)

    def proximo_fechamento(self) -> tuple[str, datetime]:
        """Primeiro fechamento estritamente depois de agora (dia útil)."""
        dia = self._agora.date()
        for _ in range(30):
            if self.eh_dia_util(dia):
                for sufixo, hora in sorted(FECHAMENTO_POR_BANCO.items(), key=lambda kv: kv[1]):
                    momento = datetime.combine(dia, hora)
                    if momento > self._agora:
                        return nome_lote(dia, sufixo), momento
            dia += timedelta(days=1)
        raise RuntimeError("nenhum fechamento encontrado nos próximos 30 dias")

    def ultimo_tique_antes(self, alvo: datetime) -> datetime:
        """Último tique da grade (início + n horas) estritamente anterior a `alvo`."""
        n = math.ceil((alvo - self.inicio) / timedelta(hours=1)) - 1
        return self.inicio + timedelta(hours=n)
