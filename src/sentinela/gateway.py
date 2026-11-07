"""ToolGateway: ponto único de acesso a leituras e ações do agente (T1).

Ordem de verificação em `chamar`: ferramenta conhecida -> papel permitido ->
limite diário -> handler. Toda tentativa (inclusive negada) é registrada com o
instante simulado, para auditoria. O handler só roda se tudo passar.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .contracts import Papel
from .roles import (
    FERRAMENTAS_ANALISTA_CP,
    FERRAMENTAS_PROIBIDAS_ANALISTA_CP,
    LIMITES_DIARIOS,
    PermissaoNegada,
    exigir,
)

Handler = Callable[..., Any]


class LimiteDiarioExcedido(RuntimeError):
    """Limite diário da ferramenta (politica/ferramentas.csv) atingido no dia simulado."""


class FerramentaDesconhecida(LookupError):
    """Ferramenta fora do catálogo oficial."""


class HandlerNaoRegistrado(LookupError):
    """Ferramenta permitida, mas sem implementação ligada ao gateway."""


@dataclass(frozen=True)
class Chamada:
    instante: datetime
    papel: Papel
    ferramenta: str
    parametros: dict[str, Any]
    resultado: str  # ok | negada | limite | erro | desconhecida | sem_handler
    detalhe: str | None = None


@dataclass
class ToolGateway:
    papel: Papel
    agora: Callable[[], datetime]
    handlers: dict[str, Handler] = field(default_factory=dict)
    _historico: list[Chamada] = field(default_factory=list, init=False, repr=False)
    _uso_diario: Counter = field(default_factory=Counter, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.papel is not Papel.ANALISTA_CP:
            raise ValueError("O agente só joga o papel analista_cp.")

    @property
    def historico(self) -> tuple[Chamada, ...]:
        return tuple(self._historico)

    def registrar(self, ferramenta: str, handler: Handler) -> None:
        if ferramenta not in FERRAMENTAS_ANALISTA_CP:
            exigir(self.papel, ferramenta)  # levanta PermissaoNegada ou segue
            raise FerramentaDesconhecida(ferramenta)
        self.handlers[ferramenta] = handler

    def uso_no_dia(self, ferramenta: str, dia: date | None = None) -> int:
        return self._uso_diario[(dia or self.agora().date(), ferramenta)]

    def _log(self, instante: datetime, ferramenta: str, parametros: dict[str, Any], resultado: str, detalhe: str | None = None) -> None:
        self._historico.append(Chamada(instante, self.papel, ferramenta, dict(parametros), resultado, detalhe))

    def chamar(self, ferramenta: str, **parametros: Any) -> Any:
        instante = self.agora()

        if ferramenta not in FERRAMENTAS_ANALISTA_CP | FERRAMENTAS_PROIBIDAS_ANALISTA_CP:
            self._log(instante, ferramenta, parametros, "desconhecida")
            raise FerramentaDesconhecida(ferramenta)

        try:
            exigir(self.papel, ferramenta)
        except PermissaoNegada as exc:
            self._log(instante, ferramenta, parametros, "negada", str(exc))
            raise

        limite = LIMITES_DIARIOS.get(ferramenta)
        chave = (instante.date(), ferramenta)
        if limite is not None and self._uso_diario[chave] >= limite:
            self._log(instante, ferramenta, parametros, "limite", f"limite diário de {limite}")
            raise LimiteDiarioExcedido(f"{ferramenta}: limite diário de {limite} atingido em {instante.date()}")

        handler = self.handlers.get(ferramenta)
        if handler is None:
            self._log(instante, ferramenta, parametros, "sem_handler")
            raise HandlerNaoRegistrado(ferramenta)

        if limite is not None:
            self._uso_diario[chave] += 1
        try:
            resultado = handler(**parametros)
        except Exception as exc:
            self._log(instante, ferramenta, parametros, "erro", f"{type(exc).__name__}: {exc}")
            raise
        self._log(instante, ferramenta, parametros, "ok")
        return resultado
