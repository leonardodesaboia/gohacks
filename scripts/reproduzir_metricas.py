"""Reprodução offline dos sete passos de docs/03-DADOS.md, sem executar ações."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path("C:/Users/User/.ao/data/artifacts/sentinela-cp-5")
sys.path.insert(0, str(ROOT / "src"))
from sentinela.clock import carregar_feriados_remessa  # noqa: E402
from sentinela.identity import Catalogo, fornecedor_ref, resolver_titulo  # noqa: E402
from sentinela.threeway import conferir_titulo, digitos, numero_e_serie, numero_normalizado  # noqa: E402

INSTANTE_PADRAO = datetime(2026, 11, 2, 8)
CAMPOS = (
    "titulo_id", "status", "fornecedor_id", "categoria", "lancado_por", "numero_nf_digitado",
    "oc_id", "parcela", "chave_acesso", "chaves_candidatas", "resultado", "tipo", "motivo",
    "valor_titulo", "valor_esperado", "diferenca", "excesso", "insuficiencia",
    "lote_remessa", "excesso_em_lote", "exposicao_nominal_em_lote",
    "valor_oc_referencia", "tolerancia_oc", "vencimento_esperado",
    "fator_dez_aproximado",
    "status_identidade", "motivos_identidade",
)


def ler(diretorio: Path, nome: str) -> list[dict[str, str]]:
    with (diretorio / f"{nome}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def reproduzir(dados: Path, instante: datetime = INSTANTE_PADRAO) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Visão offline do universo, sem fornecer tabelas privilegiadas ao agente."""
    if instante != INSTANTE_PADRAO:
        raise ValueError("O CSV é uma foto em 02/11/2026 08:00; outro instante exige reconstruir status/agenda via replay")
    fornecedores = {r["fornecedor_id"]: r for r in ler(dados, "fornecedores")}
    catalogo = Catalogo([fornecedor_ref(r) for r in fornecedores.values()])
    ocs = {r["oc_id"]: r for r in ler(dados, "pedidos_compra") if r["data_emissao"] <= instante.date().isoformat()}
    notas_por_raiz_numero: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for nf in ler(dados, "notas_fiscais"):
        if nf["data_recebimento_portal"] <= instante.isoformat(sep=" "):
            notas_por_raiz_numero[(digitos(nf["cnpj_emitente"])[:8], numero_normalizado(nf["numero_nf"]))].append(nf)
    duplicatas_por_chave: dict[str, list[dict[str, str]]] = defaultdict(list)
    for dup in ler(dados, "nf_duplicatas"):
        duplicatas_por_chave[dup["chave_acesso"]].append(dup)
    feriados = carregar_feriados_remessa(dados / "feriados_bancarios.csv")
    agenda = {r["titulo_id"]: r for r in ler(dados, "agenda_remessa")}
    titulos = [r for r in ler(dados, "contas_a_pagar")
               if r["status"] in ("aberto", "agendado") and r["data_lancamento"] <= instante.isoformat(sep=" ")]
    contagens = Counter()
    autores = Counter()
    autores_divergentes = Counter()
    totais = defaultdict(lambda: Decimal("0"))
    linhas = []
    for titulo in titulos:
        fornecedor = fornecedores.get(titulo["fornecedor_id"])
        numero, _ = numero_e_serie(titulo["numero_nf_digitado"])
        notas = notas_por_raiz_numero.get((digitos(fornecedor["cnpj"])[:8], numero), []) if fornecedor and numero else []
        dups = [d for n in notas for d in duplicatas_por_chave[n["chave_acesso"]]]
        oc = ocs.get(titulo["oc_id"])
        if oc and oc["data_aprovacao"] and oc["data_aprovacao"] > instante.isoformat(sep=" "):
            oc = {**oc, "status": "pendente_aprovacao"}
        identidade = resolver_titulo(catalogo, titulo, oc)
        conf = conferir_titulo(titulo, fornecedor, notas, dups, oc, feriados, identidade=identidade)
        valor = Decimal(titulo["valor"])
        diferenca = conf.diferenca
        excesso = max(diferenca, Decimal("0")) if conf.resultado == "divergente" and "valor_titulo" in conf.tipo else Decimal("0")
        insuficiencia = max(-diferenca, Decimal("0")) if conf.resultado == "divergente" and "valor_titulo" in conf.tipo else Decimal("0")
        fator_dez = bool(conf.valor_esperado and "valor_titulo" in conf.tipo and
                         min(valor, conf.valor_esperado) > 0 and
                         Decimal("9.9") < max(valor, conf.valor_esperado) / min(valor, conf.valor_esperado) < Decimal("10.1"))
        em_lote = titulo["status"] == "agendado" and titulo["titulo_id"] in agenda
        linha = dict(zip(CAMPOS, (
            titulo["titulo_id"], titulo["status"], titulo["fornecedor_id"],
            fornecedor["categoria"] if fornecedor else "", titulo["lancado_por"],
            titulo["numero_nf_digitado"], titulo["oc_id"], titulo["parcela"],
            conf.chave_acesso, ";".join(conf.candidatos), conf.resultado, conf.tipo, conf.motivo,
            valor, conf.valor_esperado, diferenca, excesso, insuficiencia,
            titulo["lote_remessa"] if em_lote else "", excesso if em_lote else Decimal("0"),
            valor if em_lote else Decimal("0"), conf.valor_oc_referencia, conf.tolerancia_oc,
            conf.vencimento_esperado or "", fator_dez, identidade.status.value,
            "; ".join(identidade.motivos),
        )))
        linhas.append(linha)
        contagens[conf.resultado] += 1
        contagens[f"tipo:{conf.tipo}"] += 1
        if conf.chave_acesso:
            contagens["chave_unica"] += 1
        contagens[f"identidade:{identidade.status.value}"] += 1
        autores[titulo["lancado_por"]] += 1
        if conf.resultado == "divergente":
            autores_divergentes[titulo["lancado_por"]] += 1
        if fator_dez:
            contagens["fator_dez_aproximado"] += 1
        totais["excesso_nominal"] += excesso
        totais["insuficiencia_nominal"] += insuficiencia
        totais["excesso_em_lote"] += excesso if em_lote else Decimal("0")
        totais["exposicao_nominal_lote"] += valor if em_lote else Decimal("0")
    return linhas, dict(instante=instante, contagens=contagens, autores=autores,
                        autores_divergentes=autores_divergentes, totais=dict(totais))


def gravar(linhas: list[dict[str, object]], resumo: dict[str, object], destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    with (destino / "reproducao_metricas.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CAMPOS)
        writer.writeheader()
        writer.writerows(linhas)
    c = resumo["contagens"]
    t = resumo["totais"]
    texto = [
        "# Reprodução offline — conferência de três vias", "",
        f"Instante fixado: **{resumo['instante']:%Y-%m-%d %H:%M:%S}**. Universo: títulos `aberto`/`agendado` lançados até esse instante. Dados sintéticos; sem API, execução ou placar. Linhas detalhadas no CSV adjacente.", "",
        "## Cobertura e classificação", "",
        "| Classe | Títulos |", "|---|---:|",
        f"| Total | {len(linhas)} |",
        f"| Chave de acesso única | {c['chave_unica']} |",
        *[f"| {k} | {c[k]} |" for k in ("ok", "divergente", "ausente", "ambiguo")],
        f"| Dentre os divergentes de valor, razão 9,9–10,1× | {c['fator_dez_aproximado']} |",
        "", "Classes de resultado são mutuamente exclusivas; a chave única pode coexistir com divergência, ausência de OC ou duplicata.",
        "Identidade T3: " + ", ".join(f"{k[11:]}={v}" for k, v in sorted(c.items()) if k.startswith("identidade:"))
        + ". A classificação final prioriza ausência de NF: dois títulos com identidade divergente também têm NF não localizada;"
        " o terceiro (beneficiário de boleto divergente) está na classe divergente por identidade. Não somar contagens T3 às classes finais.",
        "", "## Tipos (combinações preservadas por título)", "",
        "| Tipo | Títulos |", "|---|---:|",
        *[f"| `{k[5:]}` | {v} |" for k, v in sorted(c.items()) if k.startswith("tipo:")],
        "", "## Valores nominais, não benefício", "",
        f"- Excesso título−duplicata/contrato nos divergentes: **{reais(t.get('excesso_nominal', Decimal(0)))}**.",
        f"- Insuficiência título−duplicata/contrato nos divergentes: **{reais(t.get('insuficiencia_nominal', Decimal(0)))}**.",
        f"- Subconjunto do excesso em títulos agendados na agenda: **{reais(t.get('excesso_em_lote', Decimal(0)))}**. **Não adicionar** ao excesso total.",
        f"- Valor nominal total dos agendados: **{reais(t.get('exposicao_nominal_lote', Decimal(0)))}**. Exposição não é perda ou economia, e contém o subconjunto acima.",
        "", "## Distribuição por lançador (apenas universo fixado)", "",
        "| Lançador | Títulos no universo | Divergentes (todos os tipos) |", "|---|---:|---:|",
        *[f"| {a} | {n} | {resumo['autores_divergentes'][a]} |" for a, n in sorted(resumo["autores"].items())],
        "", "Concentração não demonstra autoria, causa raiz ou fraude. Valor em lote é exposição condicionada à remessa futura, não dinheiro efetivamente pago. A conferência de aluguel usa valor mensal do contrato; não substitui conferência do boleto/conta. Não há inferência de duplicidade por títulos de parcelas ou cancelados.",
        "", "Critérios: NF por raiz CNPJ + número/série, desambiguada por CNPJ completo ou OC até uma chave; parcela `n/total` ↔ `n_dup`; OC×NF admite acréscimo máximo de `max(2% da OC, R$50)`; título×duplicata admite R$0,10; feriado de remessa conforme `feriados_bancarios.csv`. Multa/juros só justificam acréscimo quando há data de pagamento posterior. Arquivos de histórico/extrato não foram expostos ao agente.", "",
    ]
    (destino / "reproducao_metricas.md").write_text("\n".join(texto), encoding="utf-8")


def reais(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--output-dir", type=Path, default=ARTIFACTS,
                        help="raiz dos entregáveis; relatórios em <output-dir>/reports/")
    parser.add_argument("--instante", type=datetime.fromisoformat, default=INSTANTE_PADRAO)
    args = parser.parse_args()
    linhas, resumo = reproduzir(args.dados, args.instante)
    destino = args.output_dir / "reports"
    gravar(linhas, resumo, destino)
    print(f"Reprodução offline: {len(linhas)} títulos; classes {dict(resumo['contagens'])}; saída {destino}")


if __name__ == "__main__":
    main()
