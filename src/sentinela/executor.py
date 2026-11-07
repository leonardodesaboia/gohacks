"""Executor T9: ações T6 via ToolGateway, com estado verificável no Store.

Resposta da ferramenta não é prova de sucesso. Verificadores consultam apenas pelo
gateway; resultado não verificável ou timeout permanece incerto, sem retry cego.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .contracts import Acao, AcaoPlanejada, Decisao, Papel
from .gateway import ToolGateway
from .store import Store, hash_payload

Verificador = Callable[[AcaoPlanejada, ToolGateway, Any | None], bool | None]
ACOES_INTERNAS = frozenset({Acao.MANTER, Acao.ESCALAR})


@dataclass(frozen=True)
class ResultadoExecucao:
    estado: str  # confirmado | incerto | escalado | duplicado | mantido
    motivo: str
    chaves: tuple[str, ...] = ()
    evidencias: tuple[str, ...] = ()


def verificar_titulo(acao: AcaoPlanejada, gateway: ToolGateway, _resposta: Any | None) -> bool | None:
    """Verifica estado de título por `consultar_titulo`; None é ausência de prova."""
    p = acao.parametros
    if acao.acao not in (Acao.RETIRAR, Acao.AGENDAR, Acao.CANCELAR, Acao.CORRIGIR):
        return None
    titulo = gateway.chamar("consultar_titulo", titulo_id=p["titulo_id"])
    if acao.acao == Acao.RETIRAR:
        return titulo["status"] == "aberto" and not titulo.get("lote_remessa")
    if acao.acao == Acao.AGENDAR:
        return titulo["status"] == "agendado" and titulo["lote_remessa"] == p["lote_remessa"]
    if acao.acao == Acao.CANCELAR:
        return titulo["status"] == "cancelado"
    campo = p["campo"]
    atual = titulo.get(campo)
    esperado = p["valor_novo"]
    return atual == esperado or str(atual) == str(esperado)


class Executor:
    def __init__(self, gateway: ToolGateway, store: Store, verificar: Verificador = verificar_titulo) -> None:
        if gateway.papel is not Papel.ANALISTA_CP:
            raise ValueError("Executor exige gateway analista_cp")
        self.gateway = gateway
        self.store = store
        self.verificar = verificar

    @staticmethod
    def _parametros(acao: AcaoPlanejada) -> dict[str, Any]:
        parametros = dict(acao.parametros)
        if acao.acao == Acao.SOLICITAR_APROVACAO:
            # T6 carrega titulo_id no envelope; a ferramenta o aceita apenas no payload.
            tid = parametros.pop("titulo_id", None)
            parametros["parametros"] = {
                **parametros.get("parametros", {}), **({"titulo_id": tid} if tid else {})
            }
        return parametros

    def _verificar(self, acao: AcaoPlanejada, resposta: Any | None) -> bool | None:
        return self.verificar(acao, self.gateway, resposta)

    def executar(self, referencia: str, fornecedor_id: str, decisao: Decisao,
                 evidencias: tuple[str, ...] = ()) -> ResultadoExecucao:
        """Executa sequência ordenada, parando no primeiro estado incerto/negado.

        `referencia` é título ou `comunicacao:ID`, igual à usada na decisão;
        evidências são IDs/trechos de suporte para escalonamento, não instruções.
        """
        instante = self.gateway.agora()
        if not decisao.acoes:
            if decisao.acao not in ACOES_INTERNAS:
                return ResultadoExecucao("escalado", "decisão sem plano de ação executável", evidencias=evidencias)
            self.store.registrar_decisao(referencia, decisao, instante)
            estado = "mantido" if decisao.acao == Acao.MANTER else "escalado"
            self.store.auditar("resultado_interno", decisao.chave_idempotencia,
                               {"estado": estado, "regra": decisao.regra_aplicada}, instante)
            return ResultadoExecucao(estado, decisao.motivo, evidencias=evidencias)
        if (decisao.acao != decisao.acoes[0].acao or
                any(a.acao in ACOES_INTERNAS for a in decisao.acoes)):
            return ResultadoExecucao("escalado", "plano inconsistente ou ação interna não pode ser ferramenta",
                                     evidencias=evidencias)
        self.store.registrar_decisao(referencia, decisao, instante)
        chaves: list[str] = []
        for acao in decisao.acoes:
            parametros = self._parametros(acao)
            # Chave por ação individual, independente da chave de Decisao/evento.
            persistida = self.store.reservar_acao(referencia, acao.acao.value, parametros,
                                                  decisao.versao_evidencias)
            chave = persistida.chave
            chaves.append(chave)
            if persistida.estado == "aplicada":
                continue
            if acao.acao == Acao.ACIONAR_PESSOA and decisao.incidente:
                pessoa = str(parametros["pessoa_id"])
                if not self.store.reservar_alerta(fornecedor_id, decisao.incidente, pessoa):
                    if persistida.estado == "reservada":
                        # Reserva distinta já corresponde ao mesmo incidente/pessoa.
                        return ResultadoExecucao("duplicado", "pessoa já acionada ou reservada para este incidente",
                                                 tuple(chaves), evidencias)
                    # A mesma ação já existe: será verificada abaixo, nunca reenviada cegamente.
            if persistida.estado in ("em_execucao", "incerta"):
                estado = self.store.reconciliar_acao(
                    chave, lambda: self._verificar(acao, persistida.resultado), instante=instante)
                if estado.estado == "aplicada":
                    if acao.acao == Acao.ACIONAR_PESSOA and decisao.incidente:
                        self.store.marcar_alerta(fornecedor_id, decisao.incidente,
                                                str(parametros["pessoa_id"]), "enviado", instante)
                    continue
                if estado.estado != "nao_aplicada":
                    return ResultadoExecucao("incerto", "resultado anterior não verificável; escalar, não repetir",
                                             tuple(chaves), evidencias)
                # O sistema confirmou ausência do efeito: Store permite nova tentativa.
            if persistida.estado == "falha":
                return ResultadoExecucao("escalado", "ação anterior falhou; requer nova decisão",
                                         tuple(chaves), evidencias)
            # `nao_aplicada` só é produzido pela consulta de reconciliação do Store.
            self.store.auditar("intencao_acao", chave,
                               {"acao": acao.acao.value, "referencia": referencia,
                                "parametros_hash": hash_payload(parametros), "regra": decisao.regra_aplicada}, instante)
            self.store.iniciar_acao(chave)
            resposta: Any | None = None
            try:
                resposta = self.gateway.chamar(acao.acao.value, **parametros)
            except Exception as exc:
                # Recusa explícita sem efeito: falha. Erro genérico/timeout: efeito pode ter ocorrido.
                from .adapters.replay import AcaoRecusada
                from .roles import PermissaoNegada
                from .gateway import (FerramentaDesconhecida, HandlerNaoRegistrado,
                                      LimiteDiarioExcedido)

                conhecida = isinstance(exc, (AcaoRecusada, PermissaoNegada,
                                            FerramentaDesconhecida, HandlerNaoRegistrado,
                                            LimiteDiarioExcedido))
                self.store.marcar_resultado(chave, "falha" if conhecida else "incerta",
                                            {"erro": type(exc).__name__}, instante)
                self.store.auditar("resultado_verificacao", chave,
                                   {"estado": self.store.obter_acao(chave).estado, "erro": type(exc).__name__}, instante)
                if (acao.acao == Acao.ACIONAR_PESSOA and decisao.incidente
                        and self.store.obter_acao(chave).estado == "incerta"):
                    self.store.marcar_alerta(fornecedor_id, decisao.incidente,
                                            str(parametros["pessoa_id"]), "incerto", instante)
                return ResultadoExecucao("escalado", f"{acao.acao.value}: {type(exc).__name__}: {exc}; requer revisão humana",
                                         tuple(chaves), evidencias)
            try:
                confirmado = self._verificar(acao, resposta)
            except Exception:
                confirmado = None
            estado = self.store.reconciliar_acao(chave, lambda: confirmado,
                                                 resultado=resposta if confirmado is True else None,
                                                 instante=instante)
            self.store.auditar("resultado_verificacao", chave,
                               {"estado": estado.estado, "confirmacao": confirmado}, instante)
            if estado.estado == "aplicada":
                if acao.acao == Acao.ACIONAR_PESSOA and decisao.incidente:
                    self.store.marcar_alerta(fornecedor_id, decisao.incidente,
                                            str(parametros["pessoa_id"]), "enviado", instante)
                continue
            if acao.acao == Acao.ACIONAR_PESSOA and decisao.incidente:
                self.store.marcar_alerta(fornecedor_id, decisao.incidente,
                                        str(parametros["pessoa_id"]), "incerto", instante)
            return ResultadoExecucao("incerto" if estado.estado == "incerta" else "escalado",
                                     "efeito da ferramenta não confirmado; ação seguinte não executada",
                                     tuple(chaves), evidencias)
        return ResultadoExecucao("confirmado", "todas as ações verificadas", tuple(chaves), evidencias)
