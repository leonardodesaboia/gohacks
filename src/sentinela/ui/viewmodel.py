"""Estado e blocos de tela da narração da demo (T10), sem Streamlit: testável e reutilizável.

A tela só desenha o que este módulo devolve. Tudo que vem de terceiros (mensagens) é tratado como dado:
o `app.py` escapa antes de virar HTML. Dados sensíveis (CNPJ, conta, Pix) saem mascarados.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ..adapters.replay import ReplayAdapter
from ..clock import SimClock, carregar_feriados_remessa
from ..comms.extractor import criar_extrator
from ..comms.risk import Nivel
from ..conferencia import conferir_pelo_gateway
from ..contracts import Papel
from ..gateway import ToolGateway
from ..loop import ExecutorPersistente, Laco, RegistroTique, TipoEvento, verificador_replay
from ..store import Store
from .theme import formatar_brl, mascarar_cnpj, mascarar_conta, mascarar_pix, mascarar_texto

DADOS = Path(__file__).resolve().parents[3] / "data" / "raw"


@dataclass(frozen=True)
class Cenario:
    titulo: str
    descricao: str
    inicio: datetime
    fim: datetime
    fornecedores: frozenset[str] | None
    foco: str  # fornecedor cujos títulos aparecem no antes/depois do lote


CENARIOS: dict[str, Cenario] = {
    "embalarte": Cenario(
        "A mensagem do Embalarte chega entre dois tiques",
        "Replay retroativo de 29/10: às 14:00 e 15:00 a mensagem ainda não existe; às 16:00 ela aparece e o lote é protegido antes do corte.",
        datetime(2026, 10, 29, 14, 0), datetime(2026, 10, 29, 18, 0), frozenset({"FP4615", "FP4345"}), "FP4615",
    ),
    "corte": Cenario(
        "Fila inicial no corte (02/11 08:00)",
        "Toda a fila e as 246 comunicações até o primeiro fechamento de lote (03/11 10:00): confere, corrige, retira e chama a pessoa certa.",
        datetime(2026, 11, 2, 8, 0), datetime(2026, 11, 3, 10, 0), None, "FP4615",
    ),
}


@dataclass
class Sessao:
    chave: str
    cenario: Cenario
    laco: Laco
    adapter: ReplayAdapter
    clock: SimClock
    gw: ToolGateway
    store: Store
    extrator: str
    registros: list[RegistroTique] = field(default_factory=list)
    antes: dict[str, dict[str, Any]] = field(default_factory=dict)


def _abrir_store_para_threads() -> Store:
    """O Streamlit executa cada interação do usuário numa thread diferente; o Store abre o SQLite sem permitir isso.
    Abrimos a conexão com `check_same_thread=False` (uma interação por vez em cada sessão, então o uso é serializado)."""
    original = sqlite3.connect
    with patch.object(sqlite3, "connect", lambda *a, **k: original(*a, check_same_thread=False, **k)):
        return Store(":memory:")


def criar_sessao(chave: str, extrator: str = "mock", dados: Path = DADOS) -> Sessao:
    cenario = CENARIOS[chave]
    clock = SimClock(cenario.inicio, carregar_feriados_remessa(dados / "feriados_bancarios.csv"), fim=cenario.fim)
    adapter = ReplayAdapter(dados, clock)
    gw = ToolGateway(Papel.ANALISTA_CP, clock)
    adapter.registrar_em(gw)
    store = _abrir_store_para_threads()
    laco = Laco(adapter, gw, clock, criar_extrator(extrator), conferir_pelo_gateway(clock.feriados), fornecedores=cenario.fornecedores,
                executor=ExecutorPersistente(gw, store, verificador_replay(adapter)))
    antes = {
        t["titulo_id"]: {"valor": t["valor"], "lote": t["lote_remessa"], "forma": t["forma_pagamento"]}
        for t in gw.chamar("buscar_titulos", fornecedor_id=cenario.foco, status="agendado", limite=10_000)
        if not clock.lote_fechado(t["lote_remessa"])
    }
    return Sessao(chave, cenario, laco, adapter, clock, gw, store, extrator, antes=antes)


def avancar(s: Sessao) -> RegistroTique | None:
    """Executa o tique do instante atual e avança o relógio 1 hora. None se o período já terminou."""
    if s.clock.terminou:
        return None
    reg = s.laco.executar_tique()
    s.registros.append(reg)
    s.clock.avancar(1)
    return reg


def avancar_ate_pre_fechamento(s: Sessao, limite: int = 200) -> int:
    """Avança tique a tique até executar um pré-fechamento (ou o fim). Devolve quantos tiques rodaram."""
    n = 0
    while n < limite:
        reg = avancar(s)
        if reg is None:
            break
        n += 1
        if any(e.tipo is TipoEvento.PRE_FECHAMENTO for e in reg.eventos):
            break
    return n


# ------------------------------------------------------------------ blocos de tela
def contagem(s: Sessao) -> dict[str, Any]:
    lote, momento = s.clock.proximo_fechamento()
    restante = momento - s.clock.agora
    horas, resto = divmod(int(restante.total_seconds()), 3600)
    return {"lote": lote, "momento": momento, "restante": f"{horas}h{resto // 60:02d}", "urgente": restante.total_seconds() <= 3600}


def _dados_extraidos(e: Any) -> list[tuple[str, str]]:
    linhas = [("tipo de pedido", e.tipo_pedido.value), ("confiança", e.confianca.value)]
    if e.identidade_alegada:
        linhas.append(("diz ser", e.identidade_alegada))
    db = e.dados_bancarios
    if db:
        if db.banco:
            linhas.append(("banco pedido", db.banco))
        if db.conta:
            linhas.append(("conta pedida", mascarar_conta(db.conta)))
        if db.chave_pix:
            linhas.append(("chave Pix", mascarar_pix(db.chave_pix)))
        if db.cnpj:
            linhas.append(("CNPJ citado", mascarar_cnpj(db.cnpj)))
    if e.numero_nf:
        linhas.append(("NF citada", e.numero_nf))
    if e.alegacoes:
        linhas.append(("alegações (não valem como confirmação)", mascarar_texto(" | ".join(e.alegacoes))))
    if e.tentativas_de_instrucao:
        linhas.append(("instrução dirigida ao sistema (ignorada)", mascarar_texto(" | ".join(e.tentativas_de_instrucao))))
    return linhas


def cartoes_comunicacao(s: Sessao, comunicacoes: dict[str, dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], int]:
    """Comunicações que pedem atenção (alto primeiro) e quantas foram lidas sem alerta."""
    if comunicacoes is None:
        comunicacoes = {c["comunicacao_id"]: c for c in s.gw.chamar("listar_comunicacoes")}
    cartoes, sem_alerta = [], 0
    for cid, a in s.laco.ultimas_analises.items():
        if a.nivel is Nivel.NENHUM:
            sem_alerta += 1
            continue
        e, c = s.laco.extracao_de(cid), comunicacoes.get(cid, {})
        cartoes.append({
            "id": cid, "remetente": c.get("remetente", ""), "assunto": c.get("assunto", ""), "data_hora": c.get("data_hora", ""),
            "nivel": a.nivel.value, "fornecedor": a.fornecedor_id, "trecho": mascarar_texto((e.trecho_suporte if e else None) or ""),
            "ia_leu": _dados_extraidos(e) if e else [],
            "regra_decidiu": [mascarar_texto(m) for m in a.motivos], "sinais": [x.value for x in a.sinais], "pessoas": list(a.pessoas_sugeridas),
            "revisao": a.requer_revisao_humana,
        })
    cartoes.sort(key=lambda x: (x["nivel"] != "alto", x["data_hora"]))
    return cartoes, sem_alerta


def decisoes_recentes(s: Sessao, limite: int = 40) -> list[dict[str, Any]]:
    """Decisões do último tique com ação, mais as de maior exposição primeiro."""
    if not s.registros:
        return []
    valores = {t["titulo_id"]: t["valor"] for t in s.gw.chamar("buscar_titulos", limite=1_000_000)} if limite else {}
    linhas = []
    for ref, d in s.registros[-1].decisoes:
        if not d.acoes:
            continue
        linhas.append({"ref": ref, "acao": d.acao.value, "regra": d.regra_aplicada, "motivo": mascarar_texto(d.motivo), "pessoa": d.pessoa_a_acionar or "", "valor": valores.get(ref)})
    linhas.sort(key=lambda x: -(x["valor"] or 0))
    return linhas[:limite]


def lote_antes_depois(s: Sessao) -> list[dict[str, Any]]:
    """Títulos do fornecedor em foco que estavam agendados em lote aberto no início, e como estão agora."""
    linhas = []
    for tid, antes in sorted(s.antes.items()):
        agora = s.adapter.consultar_titulo(tid)
        linhas.append({
            "titulo": tid, "valor": antes["valor"], "forma": antes["forma"], "lote_antes": antes["lote"],
            "estado_agora": agora["status"], "lote_agora": agora["lote_remessa"] or "—",
            "protegido": agora["status"] != "agendado",
        })
    return linhas


def chamados(s: Sessao) -> dict[str, list[dict[str, Any]]]:
    return {
        "acionamentos": [
            {"quando": a["instante"], "id": a["acionamento_id"], "pessoa": f"{a['nome']} ({a['pessoa_id']})", "urgencia": a["urgencia"], "dossie": mascarar_texto(a["motivo"])}
            for a in s.adapter.acionamentos
        ],
        "solicitacoes": [
            {"quando": x["instante"], "id": x["solicitacao_id"], "acao": x["acao"], "aprovador": x["aprovador_humano"] or "aprovador",
             "titulos": len(x["parametros"].get("itens", [])) if isinstance(x["parametros"], dict) else 1}
            for x in s.adapter.solicitacoes
        ],
    }


def execucoes(s: Sessao) -> list[dict[str, Any]]:
    return [
        {"quando": e.instante, "acao": e.acao.value, "referencia": e.referencia, "resultado": e.resultado}
        for r in s.registros for e in r.execucoes if e.resultado != "duplicada"
    ]


def totais(s: Sessao) -> dict[str, int]:
    exe = execucoes(s)
    return {
        "tiques": len(s.registros),
        "retirados": sum(1 for e in exe if e["acao"] == "retirar_do_lote" and e["resultado"] == "ok"),
        "corrigidos": sum(1 for e in exe if e["acao"] == "corrigir_lancamento" and e["resultado"] == "ok"),
        "pessoas": sum(1 for e in exe if e["acao"] == "acionar_pessoa" and e["resultado"] == "ok"),
        "aprovacoes": sum(1 for e in exe if e["acao"] == "solicitar_aprovacao" and e["resultado"] == "ok"),
    }


__all__ = ["CENARIOS", "criar_sessao", "avancar", "avancar_ate_pre_fechamento", "contagem", "cartoes_comunicacao", "decisoes_recentes",
           "lote_antes_depois", "chamados", "execucoes", "totais", "formatar_brl"]
