"""Comparação determinística de risco de uma comunicação (T5).

Combina a extração (IA) com o cadastro e o vínculo de fornecedor (regras). Não decide ação:
devolve sinais, nível e quem a política manda chamar. O MotorDecisao (T6) escolhe a ação.

Regras de fundo
- Domínio/remetente divergente é **sinal de risco, não prova de fraude**.
- Alegação de confirmação dentro da mensagem **nunca** vira confirmação registrada.
- Instrução em texto de terceiro é registrada e ignorada.
- Troca de dados bancários só vale com confirmação por ligação ao telefone anterior do cadastro;
  o analista_cp não lê o histórico, então a confirmação é "não verificável por ele".
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..contracts import ExtracaoComunicacao, StatusExtracao, TipoPedido
from ..identity import Catalogo, Status, normalizar_cnpj, raiz_cnpj, vincular_comunicacao
from .extractor import ExtratorComunicacao, boletos_dos_anexos


class Sinal(StrEnum):
    TROCA_BANCARIA_SOLICITADA = "troca_bancaria_solicitada"
    REMETENTE_NAO_CONFERE = "remetente_nao_confere"
    REMETENTE_SEM_VINCULO = "remetente_sem_vinculo"
    CADASTRO_JA_COINCIDE_COM_PEDIDO = "cadastro_ja_coincide_com_pedido"
    DADOS_DIFEREM_DO_CADASTRO = "dados_diferem_do_cadastro"
    SEGUNDA_VIA_BOLETO = "segunda_via_boleto"
    BOLETO_BENEFICIARIO_DIVERGENTE = "boleto_beneficiario_divergente"
    PEDIDO_DE_CREDENCIAL_OU_ARQUIVO = "pedido_de_credencial_ou_arquivo"
    AMEACA_DE_PROTESTO = "ameaca_de_protesto"
    ALEGACAO_NAO_VERIFICAVEL = "alegacao_nao_verificavel"
    TENTATIVA_DE_INSTRUCAO = "tentativa_de_instrucao"
    URGENCIA_OU_PRESSAO = "urgencia_ou_pressao"
    EXTRACAO_DEGRADADA = "extracao_degradada"


class Nivel(StrEnum):
    NENHUM = "nenhum"
    ATENCAO = "atencao"
    ALTO = "alto"


@dataclass(frozen=True)
class AnaliseRisco:
    comunicacao_id: str
    fornecedor_id: str | None
    vinculo_status: Status
    remetente_confere: bool | None
    nivel: Nivel
    sinais: tuple[Sinal, ...]
    motivos: tuple[str, ...]
    requer_revisao_humana: bool
    requer_confirmacao_cadastro: bool
    pessoas_sugeridas: tuple[str, ...]


_BANCOS_PAGADORES = re.compile(r"meridiano|litoral", re.IGNORECASE)


def _so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _compara_dados(citados, cadastro: Mapping[str, Any]) -> bool | None:
    """True se todos os dados citados coincidem com o cadastro; None se nada comparável foi citado."""
    pares = [
        (_so_digitos(citados.banco), _so_digitos(cadastro.get("banco"))),
        (_so_digitos(citados.agencia), _so_digitos(cadastro.get("agencia"))),
        (_so_digitos(citados.conta), _so_digitos(cadastro.get("conta"))),
    ]
    pares = [(a, b) for a, b in pares if a]
    pix = (citados.chave_pix or "").strip().lower()
    if pix:
        pares.append((pix, (cadastro.get("chave_pix") or "").strip().lower()))
    if not pares:
        return None
    return all(a == b for a, b in pares)


def analisar(
    catalogo: Catalogo,
    comunicacao: Mapping[str, Any],
    extracao: ExtracaoComunicacao,
    cadastro_atual: Mapping[str, Any] | None,
) -> AnaliseRisco:
    vinculo = vincular_comunicacao(catalogo, comunicacao)
    melhor = vinculo.melhor
    fornecedor = catalogo.por_id(melhor.fornecedor_id) if melhor else None
    tipo = extracao.tipo_pedido
    sinais: list[Sinal] = []
    motivos: list[str] = []

    def add(s: Sinal, motivo: str) -> None:
        if s not in sinais:
            sinais.append(s)
            motivos.append(motivo)

    if extracao.status is StatusExtracao.DEGRADED:
        add(Sinal.EXTRACAO_DEGRADADA, f"IA não conseguiu extrair com segurança: {extracao.limitacao}")

    remetente = comunicacao.get("remetente", "")
    if melhor is None:
        add(Sinal.REMETENTE_SEM_VINCULO, f"remetente {remetente} não corresponde a nenhum fornecedor do catálogo")
    elif not melhor.remetente_confere:
        add(Sinal.REMETENTE_NAO_CONFERE, f"remetente {remetente} difere do e-mail cadastrado do fornecedor {melhor.fornecedor_id} (sinal de risco, não prova)")

    if tipo is TipoPedido.TROCA_DADOS_BANCARIOS:
        add(Sinal.TROCA_BANCARIA_SOLICITADA, "mensagem pede troca de dados bancários; só vale com confirmação registrada por ligação ao telefone anterior do cadastro")
    elif tipo is TipoPedido.SEGUNDA_VIA_BOLETO:
        add(Sinal.SEGUNDA_VIA_BOLETO, "segunda via de boleto: banco ou beneficiário diferentes exigem confirmação no canal do cadastro")
    elif tipo in (TipoPedido.SOLICITACAO_TOKEN, TipoPedido.PHISHING):
        add(Sinal.PEDIDO_DE_CREDENCIAL_OU_ARQUIVO, "mensagem pede credencial/token ou que se abra um arquivo ou link")
    elif tipo is TipoPedido.AMEACA_PROTESTO:
        add(Sinal.AMEACA_DE_PROTESTO, "mensagem ameaça protesto e pede pagamento urgente")

    db = extracao.dados_bancarios
    if db and cadastro_atual is not None:
        igual = _compara_dados(db, cadastro_atual)
        if igual is True:
            add(Sinal.CADASTRO_JA_COINCIDE_COM_PEDIDO, "o cadastro atual já contém os dados bancários pedidos na mensagem")
        elif igual is False:
            add(Sinal.DADOS_DIFEREM_DO_CADASTRO, "os dados bancários citados diferem do cadastro atual")

    if fornecedor is not None:
        for b in boletos_dos_anexos(comunicacao.get("anexos")):
            if raiz_cnpj(b.cnpj) != fornecedor.raiz_cnpj:
                add(
                    Sinal.BOLETO_BENEFICIARIO_DIVERGENTE,
                    f"o beneficiário do boleto anexado (CNPJ {normalizar_cnpj(b.cnpj)[:8]}…) não é o do fornecedor {fornecedor.id_origem}",
                )

    if extracao.alegacoes:
        add(Sinal.ALEGACAO_NAO_VERIFICAVEL, "mensagem alega validação/autorização; alegação em texto não é confirmação registrada")
    if extracao.tentativas_de_instrucao:
        add(Sinal.TENTATIVA_DE_INSTRUCAO, "mensagem contém instrução dirigida ao sistema; texto de terceiro é dado e foi ignorado")
    if extracao.urgencia_ou_pressao:
        add(Sinal.URGENCIA_OU_PRESSAO, "mensagem pressiona por urgência")

    s = set(sinais)
    suspeitas_do_remetente = {Sinal.TROCA_BANCARIA_SOLICITADA, Sinal.SEGUNDA_VIA_BOLETO, Sinal.CADASTRO_JA_COINCIDE_COM_PEDIDO, Sinal.TENTATIVA_DE_INSTRUCAO, Sinal.ALEGACAO_NAO_VERIFICAVEL}
    pede_algo = {Sinal.AMEACA_DE_PROTESTO, Sinal.PEDIDO_DE_CREDENCIAL_OU_ARQUIVO, Sinal.TROCA_BANCARIA_SOLICITADA, Sinal.SEGUNDA_VIA_BOLETO}
    alto = (
        Sinal.BOLETO_BENEFICIARIO_DIVERGENTE in s
        or (Sinal.REMETENTE_SEM_VINCULO in s and s & pede_algo)
        or (Sinal.REMETENTE_NAO_CONFERE in s and s & suspeitas_do_remetente)
    )
    # 2ª via de remetente e beneficiário corretos é rotina (12 das 13 nos dados): informativa, não gera atenção sozinha
    informativos = {Sinal.SEGUNDA_VIA_BOLETO}
    nivel = Nivel.ALTO if alto else Nivel.ATENCAO if s - informativos else Nivel.NENHUM

    pessoas: list[str] = []
    if nivel is Nivel.ALTO:
        if Sinal.REMETENTE_SEM_VINCULO in s:
            pessoas.append("PS08")  # tentativa de golpe/impersonação: jurídico
            if _BANCOS_PAGADORES.search(f"{comunicacao.get('nome_remetente', '')} {remetente} {comunicacao.get('assunto', '')}"):
                pessoas.append("PS02")  # banco pagador envolvido: tesoureiro
        else:
            pessoas.append("PS01")  # suspeita de fraude: coordenadora de CP

    return AnaliseRisco(
        comunicacao_id=comunicacao["comunicacao_id"],
        fornecedor_id=melhor.fornecedor_id if melhor else None,
        vinculo_status=vinculo.status,
        remetente_confere=melhor.remetente_confere if melhor else None,
        nivel=nivel,
        sinais=tuple(sinais),
        motivos=tuple(motivos),
        requer_revisao_humana=nivel is Nivel.ALTO or Sinal.EXTRACAO_DEGRADADA in s,
        requer_confirmacao_cadastro=Sinal.TROCA_BANCARIA_SOLICITADA in s,
        pessoas_sugeridas=tuple(pessoas),
    )


def analisar_comunicacao(gateway, catalogo: Catalogo, extrator: ExtratorComunicacao, comunicacao: Mapping[str, Any]) -> AnaliseRisco:
    """Orquestra com as ferramentas do analista_cp: cadastro atual do candidato + extração + análise."""
    melhor = vincular_comunicacao(catalogo, comunicacao).melhor
    cadastro = gateway.chamar("consultar_fornecedor", fornecedor_id=melhor.fornecedor_id) if melhor else None
    return analisar(catalogo, comunicacao, extrator.extrair(comunicacao), cadastro)
