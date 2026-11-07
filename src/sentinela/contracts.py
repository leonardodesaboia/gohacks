"""Contratos internos agnósticos de fonte (docs/02-ARQUITETURA.md).

Dinheiro sempre em Decimal. Adaptadores traduzem CSV/API para estes modelos.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Papel(StrEnum):
    ANALISTA_CP = "analista_cp"
    AUDITOR = "auditor"
    APROVADOR = "aprovador"


class Acao(StrEnum):
    AGENDAR = "agendar_titulo"
    CORRIGIR = "corrigir_lancamento"
    RETIRAR = "retirar_do_lote"
    CANCELAR = "cancelar_titulo"
    SOLICITAR_APROVACAO = "solicitar_aprovacao"
    ACIONAR_PESSOA = "acionar_pessoa"
    CONTATAR_FORNECEDOR = "contatar_fornecedor"
    MANTER = "manter"
    ESCALAR = "escalar"


class Confianca(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class StatusExtracao(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class TipoPedido(StrEnum):
    TROCA_DADOS_BANCARIOS = "troca_dados_bancarios"
    SEGUNDA_VIA_BOLETO = "segunda_via_boleto"
    COBRANCA = "cobranca"
    ENVIO_BOLETO_NF = "envio_boleto_nf"
    AMEACA_PROTESTO = "ameaca_protesto_ou_cobranca_agressiva"
    SOLICITACAO_TOKEN = "solicitacao_seguranca_token"
    PHISHING = "phishing_ou_arquivo_suspeito"
    OUTRO = "outro"


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Pagamento(_Base):
    id: str
    origem: str
    fornecedor_id: str
    nf_numero: str | None = None
    nf_serie: str | None = None
    parcela: str | None = None
    valor: Decimal
    moeda: str = "BRL"
    vencimento: date
    estado: str
    lote: str | None = None
    forma_pagamento: str | None = None
    versao_observada: int = 0


class FornecedorRef(_Base):
    id_origem: str
    cnpj: str = Field(description="CNPJ completo, só dígitos")
    raiz_cnpj: str = Field(min_length=8, max_length=8)
    categoria: str
    razao_social: str | None = None
    nome_fantasia: str | None = None
    email_cadastrado: str | None = None
    telefone_cadastrado: str | None = None


class Evidencia(_Base):
    fonte: str
    registro: str
    trecho: str | None = None
    instante_fato: datetime | None = None
    instante_disponibilidade: datetime
    metodo_extracao: str = "campo"


class Dossie(_Base):
    pagamento: Pagamento
    evidencias: tuple[Evidencia, ...] = ()
    inconsistencias: tuple[str, ...] = ()
    dados_ausentes: tuple[str, ...] = ()
    acao_proposta: Acao | None = None
    confianca: Confianca = Confianca.ALTA


class AcaoPlanejada(_Base):
    acao: Acao
    parametros: dict[str, Any] = Field(default_factory=dict)


class Decisao(_Base):
    acao: Acao  # ação principal (a primeira de `acoes`)
    regra_aplicada: str
    alcada: str
    aprovacao_necessaria: str | None = None
    versao_evidencias: int
    chave_idempotencia: str
    motivo: str
    pessoa_a_acionar: str | None = None
    acoes: tuple[AcaoPlanejada, ...] = ()
    fallback_no_corte: Acao | None = None  # o que o pré-fechamento faz se o humano não resolver a tempo
    incidente: str | None = None  # chave para agrupar alertas do mesmo incidente


class DadosBancariosCitados(_Base):
    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None
    chave_pix: str | None = None
    favorecido: str | None = None
    cnpj: str | None = None
    trecho_suporte: str | None = None


class ExtracaoComunicacao(_Base):
    """Saída estruturada do extrator (LLM ou mock). A IA só extrai; nunca decide."""

    comunicacao_id: str
    status: StatusExtracao = StatusExtracao.OK
    tipo_pedido: TipoPedido = TipoPedido.OUTRO
    identidade_alegada: str | None = None
    dados_bancarios: DadosBancariosCitados | None = None
    numero_nf: str | None = None
    oc: str | None = None
    valor: Decimal | None = None
    vencimento: date | None = None
    alegacoes: tuple[str, ...] = ()
    tentativas_de_instrucao: tuple[str, ...] = ()
    urgencia_ou_pressao: bool = False
    confianca: Confianca = Confianca.BAIXA
    trecho_suporte: str | None = None
    limitacao: str | None = None
