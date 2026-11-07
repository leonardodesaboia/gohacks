"""Conferência de 3 vias ligada ao laço (T11): busca as notas **pelas ferramentas do analista_cp** e aplica
as regras de `threeway` (T4). O módulo `threeway` é importado só ao criar a conferência.

Como achar a NF: `consultar_nf` exige o CNPJ **exato** do emitente. A NF pode vir da matriz ou de filial
(mesma raiz, outro estabelecimento), então o agente tenta o CNPJ da matriz e as ordens seguintes
(0002…0005) da mesma raiz, sem nunca sair da raiz do fornecedor do título.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from .adapters.replay import NaoEncontrado
from .decision import FatosConferencia, fatos_de_conferencia
from .gateway import ToolGateway
from .identity import ResolucaoTitulo, completar_cnpj, raiz_cnpj

ORDENS_ESTABELECIMENTO = range(1, 6)


def buscar_notas(gateway: ToolGateway, fornecedor: Mapping[str, Any], numero_digitado: str | None, ordens=ORDENS_ESTABELECIMENTO) -> list[dict[str, Any]]:
    m = re.match(r"\s*(\d+)", numero_digitado or "")
    if not m:
        return []
    raiz = raiz_cnpj(fornecedor["cnpj"])
    achadas: dict[str, dict[str, Any]] = {}
    for ordem in ordens:
        try:
            resposta = gateway.chamar("consultar_nf", cnpj_emitente=completar_cnpj(raiz, ordem), numero_nf=m.group(1))
        except NaoEncontrado:
            continue
        for nf in resposta:
            achadas[nf["chave_acesso"]] = nf
    return list(achadas.values())


def conferir_pelo_gateway(feriados: frozenset[date], ordens=ORDENS_ESTABELECIMENTO):
    """Devolve a função `conferir` esperada pelo Laco, usando o `threeway` da T4."""
    from .threeway import conferir_titulo

    def conferir(titulo: Mapping[str, Any], gateway: ToolGateway, identidade: ResolucaoTitulo, oc: Mapping[str, Any] | None) -> FatosConferencia:
        try:
            fornecedor = gateway.chamar("consultar_fornecedor", fornecedor_id=titulo["fornecedor_id"])
        except NaoEncontrado:
            fornecedor = None
        notas = buscar_notas(gateway, fornecedor, titulo.get("numero_nf_digitado"), ordens) if fornecedor else []
        duplicatas = [{"chave_acesso": n["chave_acesso"], **d} for n in notas for d in n["duplicatas"]]
        return fatos_de_conferencia(conferir_titulo(titulo, fornecedor, notas, duplicatas, oc, feriados, identidade))

    return conferir
