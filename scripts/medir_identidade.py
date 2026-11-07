"""T3: mede a resolução de identidade e gera reports/identidade.md.

Títulos, OCs e comunicações são lidos pelas ferramentas do analista_cp (ToolGateway + replay).
Os emitentes de NF são lidos direto do CSV, como **análise offline** (não existe ferramenta que liste NFs).

Uso: python scripts/medir_identidade.py [--data-dir data/raw] [--saida reports/identidade.md]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sentinela.adapters.replay import NaoEncontrado, ReplayAdapter  # noqa: E402
from sentinela.clock import SimClock, carregar_feriados_remessa  # noqa: E402
from sentinela.contracts import Papel  # noqa: E402
from sentinela.gateway import ToolGateway  # noqa: E402
from sentinela.identity import Status, montar_catalogo, resolver_cnpj, resolver_titulo, vincular_comunicacao  # noqa: E402

CORTE = datetime(2026, 11, 2, 8, 0)


def medir(data_dir: Path) -> str:
    clock = SimClock(CORTE, carregar_feriados_remessa(data_dir / "feriados_bancarios.csv"))
    adapter = ReplayAdapter(data_dir, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    adapter.registrar_em(gw)

    catalogo = montar_catalogo(gw)
    titulos = gw.chamar("buscar_titulos", limite=1_000_000)

    contagem: Counter[Status] = Counter()
    problemas = []
    for t in titulos:
        oc = None
        if t["oc_id"]:
            try:
                oc = gw.chamar("consultar_pedido_compra", oc_id=t["oc_id"])
            except NaoEncontrado:
                oc = None
        r = resolver_titulo(catalogo, t, oc)
        contagem[r.status] += 1
        if r.status is not Status.OK:
            problemas.append((t, r))

    with (data_dir / "notas_fiscais.csv").open(encoding="utf-8", newline="") as f:
        nfs = list(csv.DictReader(f))
    emitentes: Counter[str] = Counter()
    filiais = []
    for nf in nfs:
        r = resolver_cnpj(catalogo, nf["cnpj_emitente"])
        emitentes[r.estabelecimento or r.status.value] += 1
        if r.estabelecimento == "filial" and len(filiais) < 5:
            filiais.append((nf, r))

    comms = gw.chamar("listar_comunicacoes")
    vinculos = [vincular_comunicacao(catalogo, c) for c in comms]
    status_com = Counter(v.status for v in vinculos)
    remetente_nao_confere = [
        (c, v) for c, v in zip(comms, vinculos) if v.status is not Status.OK or not (v.melhor and v.melhor.remetente_confere)
    ]

    L = ["# Identidade do fornecedor — medição (T3)", "", f"Instante: {CORTE:%d/%m/%Y %H:%M} (replay no corte). Gerado por `scripts/medir_identidade.py`.", ""]
    L += ["## Catálogo", f"- Fornecedores: **{len(catalogo)}** (CNPJ válido, raiz única por fornecedor)", ""]
    L += ["## Títulos (fornecedor × OC × boleto)", f"- Total: **{len(titulos)}**"]
    for s in Status:
        L.append(f"- {s.value}: **{contagem.get(s, 0)}**")
    L += ["", "### Títulos não-ok (todos)", "", "| titulo_id | status | valor | fornecedor | lote | motivo |", "|---|---|---|---|---|---|"]
    for t, r in problemas:
        L.append(f"| {t['titulo_id']} | {r.status.value} | {t['valor']} | {t['fornecedor_id']} | {t['status']} {t['lote_remessa']} | {'; '.join(r.motivos)} |")
    L += ["", "## Emitentes de NF (análise offline do portal)", f"- NFs: **{len(nfs)}**"]
    for k, v in emitentes.most_common():
        L.append(f"- {k}: **{v}**")
    L += ["", "### 5 casos reais de filial (mesma raiz, outro estabelecimento)", "", "| chave | emitente na NF | CNPJ na NF | fornecedor | CNPJ cadastrado |", "|---|---|---|---|---|"]
    for nf, r in filiais:
        L.append(f"| {nf['chave_acesso'][:12]}… | {nf['razao_social_emitente']} | {nf['cnpj_emitente']} | {r.fornecedor.id_origem} {r.fornecedor.nome_fantasia} | {r.fornecedor.cnpj} |")
    L += ["", "## Comunicações × fornecedor", f"- Total: **{len(comms)}**"]
    for s in Status:
        if status_com.get(s):
            L.append(f"- {s.value}: **{status_com[s]}**")
    L += [f"- remetente que **não** confere com o cadastro (ou sem vínculo): **{len(remetente_nao_confere)}**", "", "| comunicacao | remetente | assunto | vínculo | sinais |", "|---|---|---|---|---|"]
    for c, v in remetente_nao_confere:
        m = v.melhor
        L.append(f"| {c['comunicacao_id']} | {c['remetente']} | {c['assunto']} | {v.status.value} {m.fornecedor_id if m else ''} | {','.join(m.sinais) if m else '-'} |")
    L += ["", "## Ambiguidade", "- Não há raiz de CNPJ compartilhada entre fornecedores, então não há ambiguidade de **fornecedor**. A ambiguidade que importa é a de **NF** (número+série+emitente), tratada na T4.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(RAIZ / "data" / "raw"))
    ap.add_argument("--saida", default=str(RAIZ / "reports" / "identidade.md"))
    args = ap.parse_args()
    texto = medir(Path(args.data_dir))
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(texto, encoding="utf-8")
    print(texto)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
