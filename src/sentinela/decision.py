"""MotorDecisao (T6): função pura que transforma fatos verificados em uma Decisao.

Sem I/O e sem LLM. A IA só entrega evidência estruturada (comms.risk); aqui o código decide o que
executar, o que escalar e para quem. Princípios:

- **Fail-closed:** evidência ausente/ambígua nunca vira ação executável; vira acionamento humano.
- **Alçada por soma:** R$ 5.000 do analista_cp vale pelo agregado fornecedor + NF + dia.
- **Proteger antes de perguntar:** sinal de fraude retira do lote na hora; dúvida resolvível por
  humano aciona a pessoa e só retira no pré-fechamento se ninguém resolver (`fallback_no_corte`).
- **Acionar ≠ aprovar.** Aprovação só existe por `solicitar_aprovacao` -> `aprovar_acao`.
- Ações possíveis são só as do analista_cp; nenhuma decisão usa ferramenta de auditor/aprovador.

Ordem das regras (a primeira que casa vence): R0 estado final · R1 fraude/identidade ·
R2 duplicidade · R3 evidência ausente/ambígua · R4 troca bancária recente · R5 OC/NF ·
R6 valor/vencimento · R7 caso limpo.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from .comms.risk import AnaliseRisco, Nivel, Sinal
from .contracts import Acao, AcaoPlanejada, Decisao, Pagamento
from .identity import ResolucaoTitulo, Status

ALCADA_ANALISTA = Decimal("5000")
ALCADA_APROVADOR = Decimal("50000")
INCONS_OC = frozenset({"nf_acima_oc", "oc_sem_aprovacao", "oc_nf", "contrato_sem_aprovacao"})
PESSOA_POR_CATEGORIA = {
    "produto": "PS04",
    "embalagens": "PS04",
    "insumos_capa": "PS05",
    "servicos": "PS05",
    "ti_saas": "PS11",
    "marketing_agencia": "PS06",
    "influenciador": "PS06",
    "frete": "PS07",
    "aluguel": "PS10",
    "utilidades": "PS10",
}


# ------------------------------------------------------------------ entradas
@dataclass(frozen=True)
class FatosConferencia:
    """Resumo da conferência de 3 vias (T4), independente da implementação dela."""

    resultado: str  # ok | divergente | ausente | ambiguo
    inconsistencias: tuple[str, ...] = ()
    motivo: str = ""
    valor_esperado: Decimal | None = None
    diferenca: Decimal | None = None  # valor do título − valor esperado
    vencimento_esperado: date | None = None
    chave_acesso: str = ""


def fatos_de_conferencia(c: Any) -> FatosConferencia:
    """Converte threeway.Conferencia por atributos (duck typing; o motor não importa o T4)."""
    incons = tuple(t for t in str(getattr(c, "tipo", "")).split(";") if t) if c.resultado == "divergente" else ()
    return FatosConferencia(
        resultado=c.resultado,
        inconsistencias=incons,
        motivo=getattr(c, "motivo", ""),
        valor_esperado=getattr(c, "valor_esperado", None),
        diferenca=getattr(c, "diferenca", None),
        vencimento_esperado=getattr(c, "vencimento_esperado", None),
        chave_acesso=getattr(c, "chave_acesso", ""),
    )


@dataclass(frozen=True)
class FatosTitulo:
    pagamento: Pagamento
    categoria: str
    identidade: ResolucaoTitulo
    conferencia: FatosConferencia
    riscos: tuple[AnaliseRisco, ...] = ()  # comunicações vinculadas ao fornecedor do título
    alteracao_cadastral_recente: bool = False
    agregado_alcada: Decimal | None = None  # None => usa o valor do título
    aprovacao_registrada: bool = False
    lote_aberto: bool = True  # só faz sentido com estado "agendado"
    lote_alvo: str | None = None  # lote em que um título aberto limpo pode ser agendado
    antecipacao: bool = False
    duplicidade_de: str | None = None  # titulo_id do original, quando a duplicidade está comprovada
    versao_evidencias: int = 0


# ------------------------------------------------------------------ utilidades
def _brl(valor: Decimal) -> str:
    inteiro, _, frac = f"{valor.quantize(Decimal('0.01')):,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{frac}"


def nivel_aprovacao(valor: Decimal) -> str:
    return "aprovador" if valor <= ALCADA_APROVADOR else "diretora financeira (PS03)"


def pessoa_por_categoria(categoria: str) -> str:
    return PESSOA_POR_CATEGORIA.get(categoria, "PS01")


def _numero_nf(digitado: str | None) -> str:
    m = re.match(r"\s*(\d+)", digitado or "")
    return str(int(m.group(1))) if m else ""


def agregado_alcada(titulo: Mapping[str, Any], todos: Iterable[Mapping[str, Any]]) -> Decimal:
    """Soma dos títulos abertos/agendados do mesmo fornecedor + NF + vencimento (dia de pagamento).

    Interpretação de `alcadas.fracionamento` ("mesmo fornecedor e mesma NF no mesmo dia"): parcelas
    de uma NF com vencimentos diferentes são parcelamento normal e não se somam. Confirmar com a área.
    """

    def chave(t: Mapping[str, Any]) -> tuple[str, str, str]:
        return (t["fornecedor_id"], _numero_nf(t.get("numero_nf_digitado")), str(t["vencimento"]))

    alvo = chave(titulo)
    return sum(
        (Decimal(str(t["valor"])) for t in todos if chave(t) == alvo and t.get("status") in ("aberto", "agendado")),
        Decimal("0"),
    )


def alteracao_recente(cadastro: Mapping[str, Any], agora: datetime, dias: int = 30) -> bool:
    """Cadastro alterado há ≤ `dias`. Não distingue o campo: o analista não lê o histórico."""
    bruto = (cadastro.get("data_ultima_alteracao") or "").strip()
    if not bruto:
        return False
    return agora - datetime.fromisoformat(bruto) <= timedelta(days=dias)


def chave_idempotencia(referencia: str, acoes: Iterable[AcaoPlanejada], versao_evidencias: int) -> str:
    canon = json.dumps(
        {"ref": referencia, "acoes": [[a.acao.value, a.parametros] for a in acoes], "versao": versao_evidencias},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:24]


def _montar(
    referencia: str,
    versao: int,
    regra: str,
    acoes: list[AcaoPlanejada],
    motivo: str,
    alcada: str,
    *,
    aprovacao: str | None = None,
    pessoa: str | None = None,
    fallback: Acao | None = None,
    incidente: str | None = None,
) -> Decisao:
    return Decisao(
        acao=acoes[0].acao if acoes else Acao.MANTER,
        regra_aplicada=regra,
        alcada=alcada,
        aprovacao_necessaria=aprovacao,
        versao_evidencias=versao,
        chave_idempotencia=chave_idempotencia(referencia, acoes, versao),
        motivo=motivo,
        pessoa_a_acionar=pessoa,
        acoes=tuple(acoes),
        fallback_no_corte=fallback,
        incidente=incidente,
    )


def _retirar(tid: str, motivo: str) -> AcaoPlanejada:
    return AcaoPlanejada(acao=Acao.RETIRAR, parametros={"titulo_id": tid, "motivo": motivo})


def _acionar(pessoa: str, motivo: str, tid: str, urgencia: str = "normal") -> AcaoPlanejada:
    return AcaoPlanejada(acao=Acao.ACIONAR_PESSOA, parametros={"pessoa_id": pessoa, "motivo": motivo, "urgencia": urgencia, "titulos": [tid]})


def _solicitar(tid: str, acao: str, parametros: dict[str, Any], evidencias: list[str], aprovador: str) -> AcaoPlanejada:
    return AcaoPlanejada(
        acao=Acao.SOLICITAR_APROVACAO,
        parametros={"titulo_id": tid, "acao": acao, "parametros": parametros, "evidencias": evidencias, "aprovador_humano": aprovador},
    )


# ------------------------------------------------------------------ motor
def decidir(f: FatosTitulo) -> Decisao:
    p = f.pagamento
    tid, forn, versao = p.id, p.fornecedor_id, f.versao_evidencias
    valor = p.valor
    agregado = f.agregado_alcada if f.agregado_alcada is not None else valor
    alcada_txt = f"analista_cp até {_brl(ALCADA_ANALISTA)}; título {_brl(valor)}, agregado fornecedor+NF+dia {_brl(agregado)}"
    conf = f.conferencia
    incons = set(conf.inconsistencias)
    no_lote_aberto = p.estado == "agendado" and bool(p.lote) and f.lote_aberto
    lote_fechado = p.estado == "agendado" and not f.lote_aberto
    altos = [r for r in f.riscos if r.nivel is Nivel.ALTO]

    def dec(regra: str, acoes: list[AcaoPlanejada], motivo: str, **kw: Any) -> Decisao:
        return _montar(tid, versao, regra, acoes, motivo, alcada_txt, **kw)

    # R0: estado final
    if p.estado not in ("aberto", "agendado"):
        return dec("R0_estado_final", [], f"título {p.estado}: nada a fazer")

    # R1: fraude, risco alto em comunicação do fornecedor, ou fornecedor/beneficiário incoerente
    if altos or f.identidade.status is Status.DIVERGENTE or "fornecedor_oc" in incons:
        razoes: list[str] = []
        for r in altos:
            razoes.append(f"comunicação {r.comunicacao_id}: " + "; ".join(r.motivos[:3]))
        if f.identidade.status is Status.DIVERGENTE:
            razoes.append("identidade: " + "; ".join(f.identidade.motivos))
        if "fornecedor_oc" in incons and f.identidade.status is not Status.DIVERGENTE:
            razoes.append("o CNPJ do fornecedor da OC não é o do título")
        motivo = " | ".join(razoes)
        incidente = f"{forn}|fraude" if altos else f"titulo:{tid}|identidade"
        if lote_fechado:
            acoes = [
                _acionar("PS02", f"lote já fechado com título sob suspeita; verificar pagamento. {motivo}", tid, "alta"),
                _acionar("PS01", motivo, tid, "alta"),
            ]
            return dec("R1_fraude_lote_fechado", acoes, "suspeita com lote já fechado: o dinheiro pode ter saído. " + motivo, pessoa="PS02", incidente=incidente)
        acoes = ([_retirar(tid, motivo)] if no_lote_aberto else []) + [_acionar("PS01", motivo, tid, "alta")]
        aviso = "retirado do lote por precaução" if no_lote_aberto else "não agendar até resolver"
        return dec("R1_fraude_ou_identidade", acoes, f"sinal de risco ({aviso}). {motivo}", pessoa="PS01", incidente=incidente)

    # R2: duplicidade comprovada
    if f.duplicidade_de:
        evid = [f"duplicidade comprovada com {f.duplicidade_de}"]
        if lote_fechado:
            return dec("R2_duplicidade_lote_fechado", [_acionar("PS02", f"{tid} duplicado de {f.duplicidade_de} em lote já fechado", tid, "alta"), _acionar("PS09", "possível pagamento indevido em duplicidade", tid, "alta")], "duplicidade com lote fechado: possível pagamento indevido", pessoa="PS02", incidente=f"{forn}|duplicidade")
        if valor <= ALCADA_ANALISTA and agregado <= ALCADA_ANALISTA:
            return dec("R2_duplicidade_cancelar", [AcaoPlanejada(acao=Acao.CANCELAR, parametros={"titulo_id": tid, "motivo": f"duplicidade de {f.duplicidade_de}", "evidencias": evid})], f"{tid} é duplicidade comprovada de {f.duplicidade_de}", incidente=f"{forn}|duplicidade")
        acoes = ([_retirar(tid, f"duplicidade de {f.duplicidade_de} (acima da alçada)")] if no_lote_aberto else []) + [
            _solicitar(tid, "cancelar_titulo", {"motivo": f"duplicidade de {f.duplicidade_de}"}, evid, nivel_aprovacao(max(valor, agregado)))
        ]
        return dec("R2_duplicidade_acima_da_alcada", acoes, "duplicidade comprovada acima da alçada: cancelar exige aprovação", aprovacao=nivel_aprovacao(max(valor, agregado)), incidente=f"{forn}|duplicidade")

    # R3: evidência ausente ou ambígua (fail-closed)
    if conf.resultado in ("ausente", "ambiguo") or f.identidade.status in (Status.AUSENTE, Status.AMBIGUO, Status.INVALIDO):
        pessoa = "PS01" if f.identidade.status is not Status.OK else pessoa_por_categoria(f.categoria)
        causa = conf.motivo or "; ".join(f.identidade.motivos) or "evidência incompleta"
        acoes = [_acionar(pessoa, f"não foi possível conferir o título {tid}: {causa}", tid)]
        return dec("R3_evidencia_ausente_ou_ambigua", acoes, f"evidência {conf.resultado}: {causa}. Nada é executado até um humano resolver", pessoa=pessoa, fallback=Acao.RETIRAR if no_lote_aberto else None, incidente=f"{forn}|evidencia:{conf.resultado}")

    # R4: troca bancária pedida, cadastro mexido há ≤30 dias e confirmação não verificável -> aprovação dupla
    troca = [r for r in f.riscos if Sinal.TROCA_BANCARIA_SOLICITADA in r.sinais]
    if troca and f.alteracao_cadastral_recente:
        aprov = "dupla: aprovador + PS01" if max(valor, agregado) <= ALCADA_APROVADOR else "dupla: aprovador + PS03"
        evid = [f"comunicação {r.comunicacao_id}: " + "; ".join(r.motivos[:2]) for r in troca]
        acoes = [_solicitar(tid, "liberar_pagamento", {"motivo": "fornecedor com troca bancária recente sem confirmação verificável"}, evid, "PS01" if "PS01" in aprov else "PS03")]
        return dec("R4_troca_bancaria_recente", acoes, "fornecedor pediu troca de conta e o cadastro foi alterado há ≤30 dias; a confirmação por telefone anterior não é verificável pelo analista", aprovacao=aprov, fallback=Acao.RETIRAR if no_lote_aberto else None, incidente=f"{forn}|troca_bancaria")

    # R5: divergência OC × NF
    if incons & INCONS_OC:
        pessoa = pessoa_por_categoria(f.categoria)
        excesso = conf.diferenca is not None and conf.diferenca > Decimal("0.10")
        acoes = ([_retirar(tid, "título acima do esperado com divergência de OC/NF")] if (excesso and no_lote_aberto) else []) + [
            _acionar(pessoa, f"divergência de OC/NF no título {tid}: {', '.join(sorted(incons))}", tid)
        ]
        return dec("R5_divergencia_oc_nf", acoes, f"divergência de compra ({', '.join(sorted(incons))}): decisão do comprador", pessoa=pessoa, fallback=None if (excesso and no_lote_aberto) else (Acao.RETIRAR if no_lote_aberto else None), incidente=f"{forn}|oc_nf")

    # R6: valor ou vencimento
    if conf.resultado == "divergente":
        evid = [f"chave {conf.chave_acesso}: " + (conf.motivo or "divergência")]
        if incons == {"valor_titulo"} and conf.valor_esperado is not None and conf.diferenca is not None:
            if abs(conf.diferenca) <= ALCADA_ANALISTA:
                return dec(
                    "R6_corrigir_valor",
                    [AcaoPlanejada(acao=Acao.CORRIGIR, parametros={"titulo_id": tid, "campo": "valor", "valor_novo": conf.valor_esperado, "justificativa": "valor do título difere da duplicata da parcela", "evidencias": evid})],
                    f"valor do título difere da duplicata em {_brl(abs(conf.diferenca))}; única causa comprovada, dentro da alçada de correção",
                    incidente=f"{forn}|valor",
                )
            excesso = conf.diferenca > 0
            acoes = ([_retirar(tid, "valor acima da duplicata, correção acima da alçada")] if (excesso and no_lote_aberto) else []) + [
                _solicitar(tid, "corrigir_lancamento", {"campo": "valor", "valor_novo": conf.valor_esperado}, evid, nivel_aprovacao(abs(conf.diferenca)))
            ]
            return dec("R6_valor_acima_da_alcada", acoes, f"diferença de {_brl(abs(conf.diferenca))} acima da alçada de correção do analista", aprovacao=nivel_aprovacao(abs(conf.diferenca)), incidente=f"{forn}|valor")
        if incons == {"vencimento"} and conf.vencimento_esperado is not None:
            return dec(
                "R6_corrigir_vencimento",
                [AcaoPlanejada(acao=Acao.CORRIGIR, parametros={"titulo_id": tid, "campo": "vencimento", "valor_novo": conf.vencimento_esperado.isoformat(), "justificativa": "vencimento difere da duplicata", "evidencias": evid})],
                "vencimento do título difere da duplicata (e do próximo dia útil); única causa comprovada",
                incidente=f"{forn}|vencimento",
            )
        pessoa = pessoa_por_categoria(f.categoria)
        return dec("R6_causa_nao_unica", [_acionar(pessoa, f"divergências sem causa única no título {tid}: {', '.join(sorted(incons)) or conf.motivo}", tid)], "divergência sem uma única causa comprovável: decisão humana", pessoa=pessoa, fallback=Acao.RETIRAR if no_lote_aberto else None, incidente=f"{forn}|divergencia")

    # R7: caso limpo
    precisa_aprovacao = max(valor, agregado) > ALCADA_ANALISTA and not f.aprovacao_registrada
    if f.antecipacao and p.estado == "aberto":
        precisa_aprovacao = True
    if precisa_aprovacao:
        motivo = "antecipação exige aprovação dupla" if f.antecipacao else f"acima da alçada do analista ({_brl(max(valor, agregado))}) sem aprovação registrada"
        aprov = "dupla: aprovador + PS01" if f.antecipacao else nivel_aprovacao(max(valor, agregado))
        acoes = [_solicitar(tid, "agendar_titulo", {"lote_remessa": f.lote_alvo or p.lote}, ["conferência de 3 vias ok", "identidade ok"], aprov.split(" + ")[-1] if f.antecipacao else "aprovador")]
        return dec("R7_limpo_exige_aprovacao", acoes, motivo, aprovacao=aprov, fallback=Acao.RETIRAR if no_lote_aberto else None)
    if p.estado == "agendado":
        return dec("R7_limpo_manter", [], "conferido e coerente; permanece agendado")
    if f.lote_alvo is None:
        return dec("R7_limpo_sem_lote", [], "conferido e coerente, mas sem lote alvo definido")
    return dec("R7_limpo_agendar", [AcaoPlanejada(acao=Acao.AGENDAR, parametros={"titulo_id": tid, "lote_remessa": f.lote_alvo})], "conferido e coerente dentro da alçada: agendado automaticamente")


# ------------------------------------------------------- decisão de comunicação
def decidir_comunicacao(analise: AnaliseRisco, versao_evidencias: int = 0) -> Decisao | None:
    """Acionamento por comunicação de risco alto (1 por incidente). Atenção e nível nenhum não acionam."""
    if analise.nivel is not Nivel.ALTO:
        return None
    pessoas = analise.pessoas_sugeridas or ("PS01",)
    motivo = f"comunicação {analise.comunicacao_id}: " + "; ".join(analise.motivos[:3])
    tid_ref = f"comunicacao:{analise.comunicacao_id}"
    acoes = [
        AcaoPlanejada(acao=Acao.ACIONAR_PESSOA, parametros={"pessoa_id": p, "motivo": motivo, "urgencia": "alta", "titulos": []})
        for p in pessoas
    ]
    incidente = f"{analise.fornecedor_id}|fraude" if analise.fornecedor_id else f"remetente_sem_vinculo|{analise.comunicacao_id}"
    return _montar(
        tid_ref, versao_evidencias, "C1_comunicacao_alto_risco", acoes,
        f"risco alto em comunicação. {motivo}", "n/a: acionamento não executa pagamento",
        pessoa=pessoas[0], incidente=incidente,
    )
