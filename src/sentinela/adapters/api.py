"""Stub da API operacional do evento.

A existência dessa API não foi confirmada (CLAUDE.md §8). A API pública do evento
não prova integração com as ferramentas de pagamento. Enquanto isso, usar ReplayAdapter.
Quando houver contrato (autenticação, ferramentas, avanço do relógio), implementar aqui
a mesma interface de ReplayAdapter: `registrar_em(gateway)` e os 16 métodos do analista_cp.
"""

from __future__ import annotations


class ApiAdapter:
    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        self.base_url = base_url
        self.token = token

    def registrar_em(self, gateway) -> None:
        raise NotImplementedError("API operacional não confirmada; usar ReplayAdapter (modo replay).")
