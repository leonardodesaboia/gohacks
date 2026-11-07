"""Laço de eventos tique a tique (T8).

Cada tique de 1 hora: processa a fila do instante (comunicações novas, títulos novos, cadastro
alterado) e, no último tique antes de um fechamento de lote, faz o **pré-fechamento**: revalida os
títulos do lote e executa o `fallback_no_corte` das pendências que ninguém resolveu (retirar do lote).
Isso é o que protege o dinheiro "antes de sair": a ação acontece antes do corte, nunca no instante dele.

Desenho
- A conferência de 3 vias (T4) é **injetada** (`conferir`); o laço não depende da implementação dela.
- `ExecutorEmMemoria` executa pelo ToolGateway com deduplicação em memória (por chave de idempotência
  e por incidente). A versão persistente, com reconciliação após timeout, é a T9 (store).
- Eventos já tratados não são reprocessados; reavaliação só quando algo relevante muda
  (comunicação nova do fornecedor, cadastro alterado, pré-fechamento) e cada reavaliação tem uma
  versão de evidências para a chave de idempotência.
- Aprovação recebida (`AprovacaoRecebida`) ainda não existe: o ambiente simulado não devolve aprovações.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from .adapters.replay import AcaoRecusada, NaoEncontrado
from .clock import SimClock
from .comms.extractor import ExtratorComunicacao
from .comms.risk import AnaliseRisco, analisar
from .contracts import Acao, AcaoPlanejada, Decisao, Pagamento
from .decision import FatosConferencia, FatosTitulo, alteracao_recente, chave_fracionamento, decidir, decidir_comunicacao, indice_agregados
from .gateway import ToolGateway
from .identity import Catalogo, ResolucaoTitulo, montar_catalogo, resolver_titulo, vincular_comunicacao

Conferir = Callable[[Mapping[str, Any], ToolGateway, ResolucaoTitulo, "Mapping[str, Any] | None"], FatosConferencia]


class TipoEvento(StrEnum):
    TITULO = "titulo_disponivel_ou_alterado"
    COMUNICACAO = "comunicacao_recebida"
    CADASTRO = "cadastro_observado_alterado"
    PRE_FECHAMENTO = "pre_fechamento_lote"


@dataclass(frozen=True)
class Evento:
    tipo: TipoEvento
    referencia: str
    instante: datetime


@dataclass(frozen=True)
class Execucao:
    instante: datetime
    referencia: str
    acao: Acao
    parametros: dict[str, Any]
    resultado: str  # ok | duplicada | recusada | erro
    detalhe: str | None = None


@dataclass
class RegistroTique:
    instante: datetime
    eventos: list[Evento] = field(default_factory=list)
    decisoes: list[tuple[str, Decisao]] = field(default_factory=list)
    execucoes: list[Execucao] = field(default_factory=list)


def conferencia_fail_closed(titulo, gateway, identidade, oc) -> FatosConferencia:
    """Conferência padrão enquanto a T4 não estiver ligada: sem conferência, nada executa."""
    return FatosConferencia("ausente", motivo="conferência de 3 vias não ligada ao laço")


# ------------------------------------------------------------------ executor
class ExecutorEmMemoria:
    def __init__(self, gateway: ToolGateway) -> None:
        self.gw = gateway
        self._feitas: set[str] = set()
        self._alertas: set[tuple[str, str]] = set()

    @staticmethod
    def _parametros(a: AcaoPlanejada) -> dict[str, Any]:
        p = dict(a.parametros)
        if a.acao is Acao.SOLICITAR_APROVACAO:  # a ferramenta não tem titulo_id: vai dentro de `parametros`
            tid = p.pop("titulo_id", None)
            p["parametros"] = {**p.get("parametros", {}), **({"titulo_id": tid} if tid else {})}
        return p

    def _chamar(self, instante: datetime, referencia: str, a: AcaoPlanejada, chave: str, incidente_pessoa: tuple[str, str] | None) -> Execucao:
        params = self._parametros(a)
        if chave in self._feitas:
            return Execucao(instante, referencia, a.acao, params, "duplicada", "ação já executada para esta versão de evidências")
        if incidente_pessoa and incidente_pessoa in self._alertas:
            self._feitas.add(chave)
            return Execucao(instante, referencia, a.acao, params, "duplicada", "pessoa já acionada para este incidente")
        try:
            self.gw.chamar(a.acao.value, **params)
        except AcaoRecusada as exc:
            self._feitas.add(chave)  # recusa do ambiente é definitiva para esta versão
            return Execucao(instante, referencia, a.acao, params, "recusada", f"{type(exc).__name__}: {exc}")
        except Exception as exc:  # falha transitória: não marca como feita, tenta no próximo tique
            return Execucao(instante, referencia, a.acao, params, "erro", f"{type(exc).__name__}: {exc}")
        self._feitas.add(chave)
        if incidente_pessoa:
            self._alertas.add(incidente_pessoa)
        return Execucao(instante, referencia, a.acao, params, "ok")

    def solicitar_agrupado(self, incidente: str, acao_nome: str, itens: list[dict[str, Any]], evidencias: list[str], aprovador: str, instante: datetime) -> Execucao:
        """Uma única solicitação de aprovação por incidente, com todos os títulos (o humano decide de uma vez)."""
        itens = sorted(itens, key=lambda i: i["titulo_id"])
        chave = f"sol|{incidente}|{acao_nome}|{','.join(i['titulo_id'] for i in itens)}"
        a = AcaoPlanejada(
            acao=Acao.SOLICITAR_APROVACAO,
            parametros={"acao": acao_nome, "parametros": {"incidente": incidente, "itens": itens}, "evidencias": evidencias, "aprovador_humano": aprovador},
        )
        return self._chamar(instante, incidente, a, chave, None)

    def executar(self, decisao: Decisao, referencia: str, instante: datetime, ignorar: frozenset[int] = frozenset()) -> list[Execucao]:
        saida = []
        for i, a in enumerate(decisao.acoes):
            if i in ignorar:
                continue
            ip = (decisao.incidente, a.parametros["pessoa_id"]) if (a.acao is Acao.ACIONAR_PESSOA and decisao.incidente) else None
            saida.append(self._chamar(instante, referencia, a, f"{decisao.chave_idempotencia}:{i}", ip))
        return saida

    def executar_fallback(self, titulo_id: str, decisao: Decisao, instante: datetime) -> Execucao:
        a = AcaoPlanejada(acao=Acao.RETIRAR, parametros={"titulo_id": titulo_id, "motivo": f"pré-fechamento: pendência não resolvida ({decisao.regra_aplicada})"})
        return self._chamar(instante, titulo_id, a, f"{decisao.chave_idempotencia}:fallback", None)


# ------------------------------------------------------------------ laço
class Laco:
    def __init__(
        self,
        adapter: Any,
        gateway: ToolGateway,
        clock: SimClock,
        extrator: ExtratorComunicacao,
        conferir: Conferir = conferencia_fail_closed,
        *,
        fornecedores: Iterable[str] | None = None,
        lote_alvo: Callable[[Mapping[str, Any]], str | None] | None = None,
        executor: ExecutorEmMemoria | None = None,
    ) -> None:
        self.adapter, self.gw, self.clock, self.extrator, self.conferir = adapter, gateway, clock, extrator, conferir
        self.escopo = set(fornecedores) if fornecedores is not None else None
        self.lote_alvo = lote_alvo
        self.executor = executor or ExecutorEmMemoria(gateway)
        self.catalogo: Catalogo = montar_catalogo(gateway)
        self._comunicacoes_vistas: set[str] = set()
        self._titulos_vistos: set[str] = set()
        self._cadastro_visto: dict[str, str] = {}
        self._extracoes: dict[str, Any] = {}
        self._versoes: dict[str, tuple[Any, int]] = {}
        self.ultima_decisao: dict[str, Decisao] = {}
        self._grupos: dict[tuple[str, str], dict[str, Any]] = {}

    # ---- leituras do tique
    def _cadastros(self) -> dict[str, Mapping[str, Any]]:
        return {f.id_origem: self.gw.chamar("consultar_fornecedor", fornecedor_id=f.id_origem) for f in self.catalogo.todos}

    def _riscos(self, comunicacoes, cadastros) -> tuple[dict[str, list[AnaliseRisco]], dict[str, AnaliseRisco]]:
        por_fornecedor: dict[str, list[AnaliseRisco]] = {}
        por_comunicacao: dict[str, AnaliseRisco] = {}
        for c in comunicacoes:
            cid = c["comunicacao_id"]
            if cid not in self._extracoes:  # a IA lê cada mensagem uma vez
                self._extracoes[cid] = self.extrator.extrair(c)
            melhor = vincular_comunicacao(self.catalogo, c).melhor
            analise = analisar(self.catalogo, c, self._extracoes[cid], cadastros.get(melhor.fornecedor_id) if melhor else None)
            por_comunicacao[cid] = analise
            if analise.fornecedor_id:
                por_fornecedor.setdefault(analise.fornecedor_id, []).append(analise)
        return por_fornecedor, por_comunicacao

    def _versao(self, titulo_id: str, fingerprint: Any) -> int:
        anterior = self._versoes.get(titulo_id)
        versao = 0 if anterior is None else anterior[1] + (anterior[0] != fingerprint)
        self._versoes[titulo_id] = (fingerprint, versao)
        return versao

    def _fatos(self, t: Mapping[str, Any], agregados, riscos_forn, cadastros) -> FatosTitulo:
        oc = None
        if t["oc_id"]:
            try:
                oc = self.gw.chamar("consultar_pedido_compra", oc_id=t["oc_id"])
            except NaoEncontrado:
                oc = None
        identidade = resolver_titulo(self.catalogo, t, oc)
        conferencia = self.conferir(t, self.gw, identidade, oc)
        fornecedor = self.catalogo.por_id(t["fornecedor_id"])
        riscos = tuple(riscos_forn.get(t["fornecedor_id"], ()))
        recente = alteracao_recente(cadastros[t["fornecedor_id"]], self.clock.agora) if t["fornecedor_id"] in cadastros else False
        lote = t["lote_remessa"] or None
        lote_aberto = lote is None or not self.clock.lote_fechado(lote)
        fingerprint = (
            t["status"], lote, lote_aberto, identidade.status, identidade.motivos, conferencia.resultado, conferencia.inconsistencias,
            tuple(sorted((r.comunicacao_id, r.nivel.value, tuple(s.value for s in r.sinais)) for r in riscos)), recente,
        )
        return FatosTitulo(
            pagamento=Pagamento(
                id=t["titulo_id"], origem="erp", fornecedor_id=t["fornecedor_id"], nf_numero=t["numero_nf_digitado"] or None, parcela=t["parcela"],
                valor=t["valor"], vencimento=date.fromisoformat(t["vencimento"]), estado=t["status"], lote=lote, forma_pagamento=t["forma_pagamento"],
            ),
            categoria=fornecedor.categoria if fornecedor else "",
            identidade=identidade,
            conferencia=conferencia,
            riscos=riscos,
            alteracao_cadastral_recente=recente,
            agregado_alcada=agregados.get(chave_fracionamento(t)),
            aprovacao_registrada=bool(t["aprovado_por"]),
            lote_aberto=lote_aberto,
            lote_alvo=self.lote_alvo(t) if self.lote_alvo else None,
            versao_evidencias=self._versao(t["titulo_id"], fingerprint),
        )

    def _avaliar(self, t, agregados, riscos_forn, cadastros, reg: RegistroTique) -> Decisao:
        tid = t["titulo_id"]
        d = decidir(self._fatos(t, agregados, riscos_forn, cadastros))
        self.ultima_decisao[tid] = d
        reg.decisoes.append((tid, d))
        ignorar: set[int] = set()
        for i, a in enumerate(d.acoes):  # pedidos de aprovação do mesmo incidente saem juntos, no fim do tique
            if a.acao is Acao.SOLICITAR_APROVACAO and d.incidente:
                g = self._grupos.setdefault((d.incidente, a.parametros["acao"]), {"itens": [], "evidencias": [], "aprovador": a.parametros["aprovador_humano"]})
                g["itens"].append({"titulo_id": tid, **a.parametros["parametros"]})
                g["evidencias"] += [e for e in a.parametros["evidencias"] if e not in g["evidencias"]]
                ignorar.add(i)
        reg.execucoes += self.executor.executar(d, tid, self.clock.agora, frozenset(ignorar))
        return d

    # ---- tique
    def executar_tique(self) -> RegistroTique:
        agora = self.clock.agora
        reg = RegistroTique(agora)
        titulos = self.gw.chamar("buscar_titulos", limite=1_000_000)
        por_id = {t["titulo_id"]: t for t in titulos}
        agregados = indice_agregados(titulos)
        cadastros = self._cadastros()
        comunicacoes = self.gw.chamar("listar_comunicacoes")
        riscos_forn, riscos_com = self._riscos(comunicacoes, cadastros)

        afetados: set[str] = set()
        for c in comunicacoes:
            cid = c["comunicacao_id"]
            if cid in self._comunicacoes_vistas:
                continue
            self._comunicacoes_vistas.add(cid)
            reg.eventos.append(Evento(TipoEvento.COMUNICACAO, cid, agora))
            analise = riscos_com[cid]
            if analise.fornecedor_id:
                afetados.add(analise.fornecedor_id)
            d = decidir_comunicacao(analise, versao_evidencias=0)
            if d is not None:
                reg.decisoes.append((f"comunicacao:{cid}", d))
                reg.execucoes += self.executor.executar(d, f"comunicacao:{cid}", agora)

        for fid, row in cadastros.items():
            marca = row.get("data_ultima_alteracao", "")
            if fid in self._cadastro_visto and self._cadastro_visto[fid] != marca:
                reg.eventos.append(Evento(TipoEvento.CADASTRO, fid, agora))
                afetados.add(fid)
            self._cadastro_visto[fid] = marca

        def em_escopo(t: Mapping[str, Any]) -> bool:
            return t["status"] in ("aberto", "agendado") and (self.escopo is None or t["fornecedor_id"] in self.escopo)

        a_avaliar: dict[str, Mapping[str, Any]] = {}
        for t in titulos:
            if not em_escopo(t):
                continue
            if t["titulo_id"] not in self._titulos_vistos:
                self._titulos_vistos.add(t["titulo_id"])
                reg.eventos.append(Evento(TipoEvento.TITULO, t["titulo_id"], agora))
                a_avaliar[t["titulo_id"]] = t
            elif t["fornecedor_id"] in afetados:
                a_avaliar[t["titulo_id"]] = t

        lote_id, fechamento = self.clock.proximo_fechamento()
        pre_fechamento = self.clock.ultimo_tique_antes(fechamento) == agora
        if pre_fechamento:
            reg.eventos.append(Evento(TipoEvento.PRE_FECHAMENTO, lote_id, agora))
            for linha in self.gw.chamar("listar_agenda_remessa", lote_remessa=lote_id):
                t = por_id.get(linha["titulo_id"])
                if t is not None and em_escopo(t):
                    a_avaliar.setdefault(t["titulo_id"], t)

        for tid, t in a_avaliar.items():
            d = self._avaliar(t, agregados, riscos_forn, cadastros, reg)
            if pre_fechamento and d.fallback_no_corte is Acao.RETIRAR and t["status"] == "agendado" and t["lote_remessa"] == lote_id:
                reg.execucoes.append(self.executor.executar_fallback(tid, d, agora))
        for (incidente, acao_nome), g in self._grupos.items():
            reg.execucoes.append(self.executor.solicitar_agrupado(incidente, acao_nome, g["itens"], g["evidencias"], g["aprovador"], agora))
        self._grupos.clear()
        return reg

    def rodar_ate(self, fim: datetime) -> list[RegistroTique]:
        """Executa os tiques de `agora` até antes de `fim` (o tique de `fim` não roda)."""
        registros = []
        while self.clock.agora < fim and not self.clock.terminou:
            registros.append(self.executar_tique())
            self.clock.avancar(1)
        return registros
