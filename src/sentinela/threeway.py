"""Conferência pura de três vias; regras `tres_vias` de politicas.csv.

As tabelas chegam de um adaptador autorizado. Este módulo não lê arquivos e não
executa ações. Matches incertos nunca usam valor para escolher uma NF.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Sequence

from .identity import ResolucaoTitulo, Status, cnpj_valido, normalizar_cnpj, raiz_cnpj

CENTAVO = Decimal("0.01")
TOLERANCIA_TITULO = Decimal("0.10")


def digitos(valor: str) -> str:
    return normalizar_cnpj(valor)


def numero_normalizado(valor: str) -> str:
    return str(int(valor)) if valor and valor.isdecimal() else ""


def numero_e_serie(valor: str) -> tuple[str, str | None]:
    partes = re.fullmatch(r"\s*(\d+)(?:[-/](\d+))?\s*", valor or "")
    if not partes:
        return "", None
    return numero_normalizado(partes[1]), numero_normalizado(partes[2]) if partes[2] else None


def proximo_dia_util(dia: date, feriados: frozenset[date]) -> date:
    while dia.weekday() >= 5 or dia in feriados:
        dia += timedelta(days=1)
    return dia


def valor_com_acrescimos(valor: Decimal, dias_atraso: int) -> Decimal:
    """Multa 2% + juros simples 1%/30 dias pro rata, arredondados em centavos."""
    return (valor * (Decimal("1.02") + Decimal("0.01") * Decimal(dias_atraso) / 30)).quantize(
        CENTAVO, rounding=ROUND_HALF_UP
    )


@dataclass(frozen=True)
class Conferencia:
    titulo_id: str
    resultado: str  # ok, divergente, ausente, ambiguo
    tipo: str
    motivo: str
    chave_acesso: str = ""
    candidatos: tuple[str, ...] = ()
    parcela: str = ""
    valor_esperado: Decimal | None = None
    diferenca: Decimal | None = None
    tolerancia_oc: Decimal | None = None
    valor_oc_referencia: Decimal | None = None
    vencimento_esperado: date | None = None


def conferir_titulo(
    titulo: Mapping[str, str],
    fornecedor: Mapping[str, str] | None,
    notas: Sequence[Mapping[str, str]],
    duplicatas: Sequence[Mapping[str, str]],
    oc: Mapping[str, str] | None,
    feriados: frozenset[date] = frozenset(),
    identidade: ResolucaoTitulo | None = None,
) -> Conferencia:
    """CNPJ raiz → número/série → CNPJ completo/OC quando discriminantes → chave única."""
    tid = titulo["titulo_id"]
    parcela = titulo.get("parcela", "")

    def falha(resultado: str, tipo: str, motivo: str, **kw) -> Conferencia:
        return Conferencia(tid, resultado, tipo, motivo, parcela=parcela, **kw)

    if not fornecedor or not cnpj_valido(fornecedor.get("cnpj")):
        return falha("ausente", "fornecedor", "Cadastro de fornecedor ausente ou CNPJ inválido")
    if titulo.get("fornecedor_id") != fornecedor.get("fornecedor_id"):
        return falha("ambiguo", "fornecedor", "Fornecedor da evidência não é o fornecedor escolhido no título")
    if identidade is not None and identidade.titulo_id != tid:
        return falha("ambiguo", "identidade", "Resolução de identidade pertence a outro título")
    categoria = fornecedor.get("categoria", "")
    esperado: Decimal | None = None
    chave = ""
    candidatos: tuple[str, ...] = ()
    vencimento_esperado: date | None = None
    referencia_oc: Decimal | None = None
    tolerancia_oc: Decimal | None = None
    inconsistencias: list[str] = []
    if identidade is not None:
        if identidade.status == Status.DIVERGENTE:
            inconsistencias.append("identidade")
        elif identidade.status != Status.OK:
            return falha("ambiguo" if identidade.status == Status.AMBIGUO else "ausente", "identidade",
                         "; ".join(identidade.motivos) or "Identidade não resolvida")
    if categoria != "aluguel":
        numero, serie = numero_e_serie(titulo.get("numero_nf_digitado", ""))
        if not numero:
            return falha("ausente", "nf_numero", "Número de NF ausente ou inválido")
        raiz = raiz_cnpj(fornecedor["cnpj"])
        achados = [n for n in notas if cnpj_valido(n.get("cnpj_emitente")) and raiz_cnpj(n["cnpj_emitente"]) == raiz
                   and numero_normalizado(n.get("numero_nf", "")) == numero
                   and (serie is None or numero_normalizado(n.get("serie", "")) == serie)]
        if not achados:
            return falha("ausente", "nf", "Nenhuma NF para emitente, número e série")
        if len({n["chave_acesso"] for n in achados}) > 1:
            cnpj = digitos(fornecedor["cnpj"])
            exatos = [n for n in achados if digitos(n["cnpj_emitente"]) == cnpj]
            if len({n["chave_acesso"] for n in exatos}) == 1:
                achados = exatos
            else:
                vinculados = [n for n in achados if n.get("oc_informada") == titulo.get("oc_id") and titulo.get("oc_id")]
                if len({n["chave_acesso"] for n in vinculados}) == 1:
                    achados = vinculados
        candidatos = tuple(sorted({n["chave_acesso"] for n in achados}))
        if len(candidatos) != 1:
            return falha("ambiguo", "nf", "Mais de uma chave de acesso possível", candidatos=candidatos)
        nf = next(n for n in achados if n["chave_acesso"] == candidatos[0])
        chave = candidatos[0]
        partes = re.fullmatch(r"(\d+)/(\d+)", parcela)
        if not partes or int(partes[1]) < 1 or int(partes[1]) > int(partes[2]):
            return falha("ausente", "parcela", "Parcela n/total ausente ou inválida", chave_acesso=chave)
        dups = [d for d in duplicatas if d["chave_acesso"] == chave and numero_normalizado(d["n_dup"]) == str(int(partes[1]))]
        if not dups:
            return falha("ausente", "duplicata", "Duplicata da parcela não encontrada", chave_acesso=chave)
        if len(dups) != 1 or len([d for d in duplicatas if d["chave_acesso"] == chave]) != int(partes[2]):
            return falha("ambiguo", "duplicata", "Quantidade ou identidade das duplicatas incompatível", chave_acesso=chave)
        dup = dups[0]
        esperado = Decimal(dup["valor"])
        vencimento_esperado = date.fromisoformat(dup["vencimento"])
        vencimento_titulo = date.fromisoformat(titulo["vencimento"])
        if vencimento_titulo not in (vencimento_esperado, proximo_dia_util(vencimento_esperado, feriados)):
            inconsistencias.append("vencimento")
        pago_em = titulo.get("data_pagamento", "")
        if titulo.get("status") == "pago" and pago_em and date.fromisoformat(pago_em[:10]) > vencimento_esperado:
            dias = (date.fromisoformat(pago_em[:10]) - vencimento_esperado).days
            acrescido = valor_com_acrescimos(esperado, dias)
            if abs(Decimal(titulo["valor"]) - acrescido) <= TOLERANCIA_TITULO:
                esperado = acrescido
        if categoria != "utilidades":
            if oc is None:
                return falha("ausente", "oc", "OC ausente", chave_acesso=chave, valor_esperado=esperado)
            if oc.get("oc_id") != titulo.get("oc_id"):
                return falha("ambiguo", "oc", "OC fornecida não corresponde ao título", chave_acesso=chave)
            if not cnpj_valido(oc.get("cnpj_fornecedor")) or raiz_cnpj(oc["cnpj_fornecedor"]) != raiz:
                inconsistencias.append("fornecedor_oc")
            if oc.get("status") not in ("aprovada", "encerrada"):
                inconsistencias.append("oc_sem_aprovacao")
            if nf.get("oc_informada") and nf["oc_informada"] != oc.get("oc_id"):
                inconsistencias.append("oc_nf")
            referencia_oc = Decimal(oc["valor_mensal"] if oc.get("tipo") == "contrato" and oc.get("valor_mensal") else oc["valor_total"])
            tolerancia_oc = max(referencia_oc * Decimal("0.02"), Decimal("50"))
            if Decimal(nf["valor_total"]) - referencia_oc > tolerancia_oc:
                inconsistencias.append("nf_acima_oc")
    else:
        if oc is None:
            return falha("ausente", "contrato", "Aluguel sem OC/contrato disponível")
        if oc.get("oc_id") != titulo.get("oc_id"):
            return falha("ambiguo", "contrato", "Contrato não corresponde ao título")
        if oc.get("status") not in ("aprovada", "encerrada"):
            inconsistencias.append("contrato_sem_aprovacao")
        if not cnpj_valido(oc.get("cnpj_fornecedor")) or raiz_cnpj(oc["cnpj_fornecedor"]) != raiz_cnpj(fornecedor["cnpj"]):
            inconsistencias.append("fornecedor_oc")
        referencia_oc = Decimal(oc.get("valor_mensal") or oc["valor_total"])
        esperado = referencia_oc
    diferenca = Decimal(titulo["valor"]) - esperado
    if abs(diferenca) > TOLERANCIA_TITULO:
        inconsistencias.insert(0, "valor_titulo")
    return Conferencia(
        titulo_id=tid, resultado="divergente" if inconsistencias else "ok",
        tipo=";".join(inconsistencias) if inconsistencias else "conferido",
        motivo="; ".join(inconsistencias) if inconsistencias else "Conferência dentro das tolerâncias",
        chave_acesso=chave, candidatos=candidatos, parcela=parcela,
        valor_esperado=esperado, diferenca=diferenca,
        tolerancia_oc=tolerancia_oc, valor_oc_referencia=referencia_oc,
        vencimento_esperado=vencimento_esperado,
    )
