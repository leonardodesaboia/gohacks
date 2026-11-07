"""Identidade do fornecedor entre sistemas (T3).

O mesmo fornecedor aparece como fornecedor_id (ERP), cod_fornecedor_compras e CNPJ só
com números (Compras), CNPJ do emitente (NF, pode ser filial) e e-mail/nome (comunicações).
A chave estável é a **raiz do CNPJ (8 dígitos)**; filial = mesma raiz, outro estabelecimento.
Tudo aqui é puro (sem I/O), exceto `montar_catalogo`, que lê pelo ToolGateway.

Regra de segurança: dado ausente, inválido ou ambíguo nunca é "resolvido na marra";
devolve status explícito para o MotorDecisao escalar (fail-closed).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import FornecedorRef

DISPENSA_OC = frozenset({"utilidades"})  # politicas.csv: tres_vias.dispensas.oc
_CNPJ_EM_TEXTO = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_PONTOS = {"email_exato": 4, "dominio": 3, "cnpj": 3, "nome": 1}


class Status(StrEnum):
    OK = "ok"
    DIVERGENTE = "divergente"
    AUSENTE = "ausente"
    AMBIGUO = "ambiguo"
    INVALIDO = "invalido"


# ------------------------------------------------------------------ CNPJ
def normalizar_cnpj(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def raiz_cnpj(valor: str | None) -> str:
    d = normalizar_cnpj(valor)
    return d[:8] if len(d) >= 8 else ""


def cnpj_valido(valor: str | None) -> bool:
    d = normalizar_cnpj(valor)
    if len(d) != 14 or len(set(d)) == 1:
        return False

    def digito(base: str, pesos: list[int]) -> int:
        resto = sum(int(c) * p for c, p in zip(base, pesos)) % 11
        return 0 if resto < 2 else 11 - resto

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return digito(d[:12], p1) == int(d[12]) and digito(d[:13], [6, *p1]) == int(d[13])


def completar_cnpj(raiz: str, ordem: int) -> str:
    """CNPJ completo (14 dígitos) de um estabelecimento da raiz: raiz + ordem (4 dígitos) + dígitos verificadores."""
    base = f"{raiz}{ordem:04d}"

    def digito(b: str, pesos: list[int]) -> int:
        resto = sum(int(c) * p for c, p in zip(b, pesos)) % 11
        return 0 if resto < 2 else 11 - resto

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = digito(base, p1)
    d2 = digito(base + str(d1), [6, *p1])
    return f"{base}{d1}{d2}"


def _norm_texto(valor: str | None) -> str:
    sem_acento = unicodedata.normalize("NFKD", valor or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def _dominio(email: str | None) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower() if "@" in (email or "") else ""


# --------------------------------------------------------------- catálogo
def fornecedor_ref(linha: Mapping[str, Any]) -> FornecedorRef:
    """Converte a linha de consultar_fornecedor em FornecedorRef (levanta se o CNPJ não for válido)."""
    cnpj = normalizar_cnpj(linha["cnpj"])
    if not cnpj_valido(cnpj):
        raise ValueError(f"CNPJ inválido no cadastro de {linha['fornecedor_id']}")
    return FornecedorRef(
        id_origem=linha["fornecedor_id"],
        cnpj=cnpj,
        raiz_cnpj=cnpj[:8],
        categoria=linha["categoria"],
        razao_social=linha.get("razao_social"),
        nome_fantasia=linha.get("nome_fantasia"),
        email_cadastrado=linha.get("email_cadastrado"),
        telefone_cadastrado=linha.get("telefone_cadastrado"),
    )


class Catalogo:
    def __init__(self, fornecedores: list[FornecedorRef]) -> None:
        self.todos: tuple[FornecedorRef, ...] = tuple(fornecedores)
        self._por_id = {f.id_origem: f for f in self.todos}
        self._por_raiz: dict[str, list[FornecedorRef]] = {}
        for f in self.todos:
            self._por_raiz.setdefault(f.raiz_cnpj, []).append(f)

    def por_id(self, fornecedor_id: str) -> FornecedorRef | None:
        return self._por_id.get(fornecedor_id)

    def por_raiz(self, raiz: str) -> tuple[FornecedorRef, ...]:
        return tuple(self._por_raiz.get(raiz, ()))

    def __len__(self) -> int:
        return len(self.todos)


def montar_catalogo(gateway) -> Catalogo:
    """Monta o catálogo só com ferramentas do analista_cp: ids vistos em títulos + consultar_fornecedor."""
    titulos = gateway.chamar("buscar_titulos", limite=1_000_000)
    ids = sorted({t["fornecedor_id"] for t in titulos})
    return Catalogo([fornecedor_ref(gateway.chamar("consultar_fornecedor", fornecedor_id=i)) for i in ids])


# ------------------------------------------------------------- resolução
@dataclass(frozen=True)
class ResolucaoCnpj:
    status: Status
    fornecedor: FornecedorRef | None = None
    estabelecimento: str | None = None  # matriz | filial
    motivo: str | None = None


def resolver_cnpj(catalogo: Catalogo, cnpj: str | None) -> ResolucaoCnpj:
    d = normalizar_cnpj(cnpj)
    if not cnpj_valido(d):
        return ResolucaoCnpj(Status.INVALIDO, motivo=f"CNPJ inválido: {cnpj!r}")
    achados = catalogo.por_raiz(d[:8])
    if not achados:
        return ResolucaoCnpj(Status.AUSENTE, motivo=f"raiz {d[:8]} não pertence a nenhum fornecedor")
    if len(achados) > 1:
        return ResolucaoCnpj(Status.AMBIGUO, motivo="raiz compartilhada por mais de um fornecedor")
    f = achados[0]
    return ResolucaoCnpj(Status.OK, f, "matriz" if d == f.cnpj else "filial")


@dataclass(frozen=True)
class ResolucaoTitulo:
    titulo_id: str
    status: Status
    fornecedor: FornecedorRef | None
    motivos: tuple[str, ...] = ()
    fornecedor_da_oc: str | None = None


def resolver_titulo(catalogo: Catalogo, titulo: Mapping[str, Any], oc: Mapping[str, Any] | None) -> ResolucaoTitulo:
    """Confere que o fornecedor escolhido por quem lançou é coerente com a OC e com o boleto.

    `oc` é a linha de consultar_pedido_compra do `oc_id` do título (ou None se não localizada/sem OC).
    DIVERGENTE (fornecedor errado) tem prioridade sobre AUSENTE (falta evidência).
    """
    tid = titulo["titulo_id"]
    fornecedor = catalogo.por_id(titulo["fornecedor_id"])
    if fornecedor is None:
        return ResolucaoTitulo(tid, Status.AUSENTE, None, (f"fornecedor {titulo['fornecedor_id']} fora do catálogo",))

    divergencias: list[str] = []
    ausencias: list[str] = []
    dono_oc: str | None = None

    if titulo.get("oc_id"):
        if oc is None:
            ausencias.append(f"OC {titulo['oc_id']} não localizada")
        else:
            donos = catalogo.por_raiz(raiz_cnpj(oc["cnpj_fornecedor"]))
            dono_oc = donos[0].id_origem if len(donos) == 1 else None
            if raiz_cnpj(oc["cnpj_fornecedor"]) != fornecedor.raiz_cnpj:
                divergencias.append(
                    f"fornecedor do título ({fornecedor.id_origem}) difere do fornecedor da OC {titulo['oc_id']}"
                    f" ({dono_oc or 'CNPJ fora do catálogo'})"
                )
    elif fornecedor.categoria not in DISPENSA_OC:
        ausencias.append(f"título sem OC e categoria '{fornecedor.categoria}' não é dispensada")

    beneficiario = titulo.get("cnpj_beneficiario_boleto") or ""
    if beneficiario:
        if not cnpj_valido(beneficiario):
            divergencias.append(f"CNPJ do beneficiário do boleto inválido: {beneficiario}")
        elif raiz_cnpj(beneficiario) != fornecedor.raiz_cnpj:
            divergencias.append("beneficiário do boleto não pertence ao fornecedor do título")

    status = Status.DIVERGENTE if divergencias else Status.AUSENTE if ausencias else Status.OK
    return ResolucaoTitulo(tid, status, fornecedor, tuple(divergencias + ausencias), dono_oc)


# ------------------------------------------------------------ comunicações
@dataclass(frozen=True)
class CandidatoVinculo:
    fornecedor_id: str
    pontos: int
    sinais: tuple[str, ...]
    remetente_confere: bool


@dataclass(frozen=True)
class Vinculo:
    comunicacao_id: str
    status: Status
    candidatos: tuple[CandidatoVinculo, ...] = ()
    motivo: str | None = None

    @property
    def melhor(self) -> CandidatoVinculo | None:
        return self.candidatos[0] if self.candidatos else None


def vincular_comunicacao(catalogo: Catalogo, comunicacao: Mapping[str, Any]) -> Vinculo:
    """Liga uma comunicação a um fornecedor por sinais explícitos; nunca por inferência da IA.

    `remetente_confere` (e-mail igual ou mesmo domínio do cadastro) é o sinal determinístico
    que a T5 usa: um candidato por CNPJ/nome com remetente que não confere é suspeito.
    """
    remetente = (comunicacao.get("remetente") or "").strip().lower()
    dominio = _dominio(remetente)
    texto_cnpj = f"{comunicacao.get('anexos', '')} {comunicacao.get('texto', '')}"
    raizes_no_texto = {raiz_cnpj(m.group(0)) for m in _CNPJ_EM_TEXTO.finditer(texto_cnpj)}
    texto_nome = _norm_texto(f"{comunicacao.get('nome_remetente', '')} {comunicacao.get('assunto', '')}")

    candidatos: list[CandidatoVinculo] = []
    for f in catalogo.todos:
        sinais: list[str] = []
        email = (f.email_cadastrado or "").lower()
        if remetente and remetente == email:
            sinais.append("email_exato")
        elif dominio and dominio == _dominio(email):
            sinais.append("dominio")
        if f.raiz_cnpj in raizes_no_texto:
            sinais.append("cnpj")
        nome = _norm_texto(f.nome_fantasia)
        if nome and nome in texto_nome:
            sinais.append("nome")
        if sinais:
            candidatos.append(
                CandidatoVinculo(
                    f.id_origem,
                    sum(_PONTOS[s] for s in sinais),
                    tuple(sinais),
                    "email_exato" in sinais or "dominio" in sinais,
                )
            )
    candidatos.sort(key=lambda c: (-c.pontos, c.fornecedor_id))
    cid = comunicacao["comunicacao_id"]
    if not candidatos:
        return Vinculo(cid, Status.AUSENTE, motivo="nenhum fornecedor do catálogo corresponde ao remetente")
    if len(candidatos) > 1 and candidatos[0].pontos == candidatos[1].pontos:
        return Vinculo(cid, Status.AMBIGUO, tuple(candidatos), "empate entre fornecedores")
    if candidatos[0].pontos < 3:
        return Vinculo(cid, Status.AMBIGUO, tuple(candidatos), "evidência fraca (apenas nome)")
    return Vinculo(cid, Status.OK, tuple(candidatos))
