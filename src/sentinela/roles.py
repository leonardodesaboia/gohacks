"""RegistroPapeis: papel -> ferramentas permitidas.

Espelha docs/fonte-oficial/ferramentas.csv (coluna papeis_permitidos). O teste
tests/test_roles.py garante que este registro não diverge do CSV oficial.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .contracts import Papel

FERRAMENTAS_ANALISTA_CP: frozenset[str] = frozenset(
    {
        "listar_agenda_remessa",
        "buscar_titulos",
        "consultar_titulo",
        "consultar_fornecedor",
        "consultar_pedido_compra",
        "consultar_nf",
        "listar_comunicacoes",
        "consultar_politicas",
        "corrigir_lancamento",
        "agendar_titulo",
        "retirar_do_lote",
        "cancelar_titulo",
        "contatar_fornecedor",
        "solicitar_aprovacao",
        "acionar_pessoa",
        "responder_colaborador",
    }
)

FERRAMENTAS_PROIBIDAS_ANALISTA_CP: frozenset[str] = frozenset(
    {
        "consultar_historico_cadastro",
        "consultar_extrato",
        "bloquear_titulo",
        "bloquear_fornecedor",
        "reverter_alteracao_cadastro",
        "abrir_incidente",
        "propor_correcao_processo",
        "aprovar_acao",
        "recusar_acao",
        "aprovar_alteracao_bancaria",
        "liberar_lote",
    }
)

LIMITES_DIARIOS: dict[str, int] = {"acionar_pessoa": 40, "contatar_fornecedor": 60}


class PermissaoNegada(PermissionError):
    """Papel sem permissão para a ferramenta."""


def carregar_do_csv(caminho: Path) -> dict[Papel, frozenset[str]]:
    """Lê ferramentas.csv e devolve papel -> ferramentas permitidas."""
    registro: dict[Papel, set[str]] = {p: set() for p in Papel}
    with caminho.open(encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            for papel in (p.strip() for p in linha["papeis_permitidos"].split(";")):
                if papel:
                    registro[Papel(papel)].add(linha["ferramenta"])
    return {p: frozenset(v) for p, v in registro.items()}


def permitido(papel: Papel, ferramenta: str) -> bool:
    if papel is Papel.ANALISTA_CP:
        return ferramenta in FERRAMENTAS_ANALISTA_CP
    raise NotImplementedError("O agente só joga o papel analista_cp (Fase 2 tem outros papéis).")


def exigir(papel: Papel, ferramenta: str) -> None:
    if not permitido(papel, ferramenta):
        raise PermissaoNegada(f"{papel.value} não pode usar {ferramenta}")
