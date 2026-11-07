"""Roda o Sentinela CP em replay local e escreve um resumo da execução (T11).

Declara-se SEMPRE como replay local (os CSVs são uma foto de 02/11/2026 08:00); `--inicio` anterior a isso
é replay retroativo (o estado de títulos e cadastro é reconstruído no instante).

Uso:
  python scripts/rodar_replay.py                               # fila inicial no corte + 24 h
  python scripts/rodar_replay.py --inicio 2026-10-29T14:00 --ate 2026-10-29T17:00 --fornecedores FP4615
Variáveis: SENTINELA_EXTRATOR=mock|claude (padrão mock), ANTHROPIC_API_KEY para o claude.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sentinela.adapters.replay import ReplayAdapter  # noqa: E402
from sentinela.clock import SimClock, carregar_feriados_remessa  # noqa: E402
from sentinela.comms.extractor import criar_extrator  # noqa: E402
from sentinela.conferencia import conferir_pelo_gateway  # noqa: E402
from sentinela.contracts import Papel  # noqa: E402
from sentinela.gateway import ToolGateway  # noqa: E402
from sentinela.loop import ExecutorPersistente, Laco, verificador_replay  # noqa: E402
from sentinela.store import Store  # noqa: E402


def rodar(inicio: datetime, fim: datetime, fornecedores: set[str] | None, db: str, dados: Path):
    clock = SimClock(inicio, carregar_feriados_remessa(dados / "feriados_bancarios.csv"))
    adapter = ReplayAdapter(dados, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    adapter.registrar_em(gw)
    store = Store(db)
    laco = Laco(adapter, gw, clock, criar_extrator(), conferir_pelo_gateway(clock.feriados), fornecedores=fornecedores,
                executor=ExecutorPersistente(gw, store, verificador_replay(adapter)))
    return laco.rodar_ate(fim), adapter, store


def resumo(registros, adapter, store, inicio, fim, fornecedores, extrator) -> str:
    decisoes = [d for r in registros for _, d in r.decisoes]
    execs = [e for r in registros for e in r.execucoes]
    L = ["# Execução em replay local — Sentinela CP", "",
         f"**REPLAY LOCAL** (dados sintéticos; foto de 02/11/2026 08:00). Janela simulada: {inicio:%d/%m %H:%M} → {fim:%d/%m %H:%M}"
         f" ({len(registros)} tiques). Extrator: `{extrator}`. Escopo: {', '.join(sorted(fornecedores)) if fornecedores else 'todos os fornecedores'}.", ""]
    L += ["## Decisões por regra", "", "| Regra | Decisões |", "|---|---:|"] + [f"| {k} | {v} |" for k, v in Counter(d.regra_aplicada for d in decisoes).most_common()]
    L += ["", "## Ações executadas (resultado verificado pelo estado do ambiente quando possível)", "", "| Ação | Resultado | Quantidade |", "|---|---|---:|"]
    L += [f"| {a} | {r} | {n} |" for (a, r), n in sorted(Counter((e.acao.value, e.resultado) for e in execs).items())]
    L += ["", "## Estado do ambiente ao final", "",
          f"- Acionamentos de pessoas: {dict(Counter(a['pessoa_id'] for a in adapter.acionamentos))}",
          f"- Solicitações de aprovação (agrupadas por incidente): {len(adapter.solicitacoes)}",
          f"- Ações persistidas por estado: {dict((r[0], r[1]) for r in store.db.execute('SELECT estado, COUNT(*) FROM acoes GROUP BY estado'))}", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inicio", default="2026-11-02T08:00")
    ap.add_argument("--ate", default=None, help="padrão: início + 24 h")
    ap.add_argument("--fornecedores", nargs="*", default=None)
    ap.add_argument("--db", default=":memory:")
    ap.add_argument("--data-dir", default=str(RAIZ / "data" / "raw"))
    ap.add_argument("--saida", default=str(RAIZ / "reports" / "replay.md"))
    a = ap.parse_args()
    inicio = datetime.fromisoformat(a.inicio)
    fim = datetime.fromisoformat(a.ate) if a.ate else inicio + timedelta(hours=24)
    escopo = set(a.fornecedores) if a.fornecedores else None
    registros, adapter, store = rodar(inicio, fim, escopo, a.db, Path(a.data_dir))
    texto = resumo(registros, adapter, store, inicio, fim, escopo, criar_extrator().nome)
    Path(a.saida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.saida).write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
