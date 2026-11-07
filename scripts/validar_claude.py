"""Valida um extrator por LLM com a API REAL, comparando com o extrator mock (T5/T11).

Uso:  python scripts/validar_claude.py [--extrator claude|openai] [--amostra 10] [--todos]
  claude : ANTHROPIC_API_KEY; modelo em SENTINELA_MODEL (padrão claude-sonnet-5-5)
  openai : OPENAI_API_KEY (+ OPENAI_BASE_URL se for provedor compatível, como um gateway); modelo em SENTINELA_MODEL_OPENAI
A chave vem do ambiente ou de .env e nunca é impressa nem gravada em relatório. Envia à API apenas as comunicações
sintéticas do evento.

O que mede (não "se o modelo é bom", e sim se o pipeline continua correto com ele):
  - extração ancorada na mensagem (a trava contra alucinação) e taxa de DEGRADED;
  - concordância de tipo de pedido e, principalmente, do NÍVEL DE RISCO com o mock;
  - os casos críticos (Embalarte, 2ª via com beneficiário trocado, injeção, impersonações) têm de dar o mesmo nível.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sentinela.adapters.replay import ReplayAdapter  # noqa: E402
from sentinela.clock import SimClock, carregar_feriados_remessa  # noqa: E402
from sentinela.comms.extractor import ExtratorMock, criar_extrator  # noqa: E402
from sentinela.comms.risk import analisar  # noqa: E402
from sentinela.contracts import Papel, StatusExtracao  # noqa: E402
from sentinela.gateway import ToolGateway  # noqa: E402
from sentinela.identity import montar_catalogo, vincular_comunicacao  # noqa: E402

CRITICOS = {
    "EM571119": "Embalarte: troca de conta + instrução ao robô",
    "EM571116": "2ª via com beneficiário trocado (outlook.com)",
    "EM570996": "texto dirigido ao assistente (remetente legítimo)",
    "EM570977": "falsa Receita (arquivo)",
    "EM570998": "falso cartório (protesto)",
    "EM571100": "falso Banco Meridiano (token)",
    "EM570891": "troca de conta de remetente legítimo",
    "EM570878": "cobrança rotineira com boleto",
    "EM570948": "2ª via legítima",
}


CHAVES = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def carregar_chave(extrator: str) -> bool:
    try:
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env")
    except ImportError:
        pass
    return bool(os.environ.get(CHAVES[extrator]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extrator", choices=sorted(CHAVES), default="claude")
    ap.add_argument("--amostra", type=int, default=10, help="mensagens aleatórias além dos casos críticos")
    ap.add_argument("--todos", action="store_true", help="as 246 mensagens (custo e tempo maiores)")
    ap.add_argument("--saida", default=None, help="padrão: reports/validacao_<extrator>.md")
    a = ap.parse_args()
    if not carregar_chave(a.extrator):
        print(f"{CHAVES[a.extrator]} ausente. Defina no ambiente ou em .env (não commitar) e rode de novo.", file=sys.stderr)
        return 2

    dados = RAIZ / "data" / "raw"
    clock = SimClock(datetime(2026, 11, 2, 8, 0), carregar_feriados_remessa(dados / "feriados_bancarios.csv"))
    adapter = ReplayAdapter(dados, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    adapter.registrar_em(gw)
    catalogo = montar_catalogo(gw)
    comms = {c["comunicacao_id"]: c for c in gw.chamar("listar_comunicacoes")}
    if a.todos:
        ids = list(comms)
    else:
        resto = sorted(set(comms) - set(CRITICOS))
        ids = [i for i in CRITICOS if i in comms] + random.Random(0).sample(resto, min(a.amostra, len(resto)))

    llm, mock = criar_extrator(a.extrator), ExtratorMock()
    linhas, degradadas, tipo_igual, nivel_igual = [], 0, 0, 0
    for cid in ids:
        c = comms[cid]
        ec, em = llm.extrair(c), mock.extrair(c)
        melhor = vincular_comunicacao(catalogo, c).melhor
        cadastro = gw.chamar("consultar_fornecedor", fornecedor_id=melhor.fornecedor_id) if melhor else None
        rc, rm = analisar(catalogo, c, ec, cadastro), analisar(catalogo, c, em, cadastro)
        degradada = ec.status is StatusExtracao.DEGRADED
        degradadas += degradada
        tipo_igual += ec.tipo_pedido == em.tipo_pedido
        nivel_igual += rc.nivel == rm.nivel
        linhas.append((cid, CRITICOS.get(cid, ""), ec.tipo_pedido.value, em.tipo_pedido.value, rc.nivel.value, rm.nivel.value, "DEGRADED: " + (ec.limitacao or "") if degradada else "ok"))

    n = len(ids)
    L = [f"# Validação do extrator `{a.extrator}` com a API real", "",
         f"Modelo: `{llm.modelo}` · mensagens: {n} · gerado em {datetime.now():%d/%m/%Y %H:%M}. Dados sintéticos do evento.", "",
         f"- Extrações degradadas (falha, saída inválida ou não ancorada): **{degradadas}/{n}**",
         f"- Mesmo tipo de pedido que o mock: **{tipo_igual}/{n}**",
         f"- **Mesmo nível de risco que o mock: {nivel_igual}/{n}**", "",
         "| comunicação | caso | tipo (LLM) | tipo (mock) | risco (LLM) | risco (mock) | status |", "|---|---|---|---|---|---|---|"]
    L += [f"| {c} | {d} | {t1} | {t2} | {n1} | {n2} | {s} |" for c, d, t1, t2, n1, n2, s in linhas]
    divergentes = [x for x in linhas if x[4] != x[5]]
    L += ["", "## Leitura", "",
          "- Divergência de **risco** em caso crítico é falha do pipeline com o modelo: investigar antes de apresentar." if any(x[0] in CRITICOS for x in divergentes) else "- Todos os casos críticos têm o mesmo nível de risco que o mock.",
          f"- Divergências de risco: {[x[0] for x in divergentes] or 'nenhuma'}.", ""]
    texto = "\n".join(L)
    saida = Path(a.saida) if a.saida else RAIZ / "reports" / f"validacao_{a.extrator}.md"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0 if not any(x[0] in CRITICOS for x in divergentes) and degradadas == 0 else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
