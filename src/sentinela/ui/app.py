"""Tela de narração da demo do Sentinela CP (Streamlit). Visual: docs/06-DESIGN-SYSTEM.md (identidade Gocase).

É só narração: a lógica está em `viewmodel.py` e no laço. Rodar:  streamlit run src/sentinela/ui/app.py
Sempre declarada como REPLAY LOCAL (dados sintéticos; foto de 02/11/2026 08:00).
Todo texto vindo de mensagens de terceiros é escapado antes de virar HTML.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/, para rodar sem instalar o pacote

import streamlit as st  # noqa: E402

from sentinela.ui import viewmodel as vm  # noqa: E402
from sentinela.ui.theme import formatar_brl, injetar_css, selo_decisao  # noqa: E402

e = html.escape


def selo(classe: str, rotulo: str, icone: str) -> str:
    return f'<span class="gc-selo {classe}"><span aria-hidden="true">{icone}</span>{e(rotulo)}</span>'


def tabela(cabecalho: list[str], linhas: list[list[str]], numericas: tuple[int, ...] = ()) -> str:
    """Tabela HTML; as células já devem vir escapadas ou ser HTML nosso (selos)."""
    th = "".join(f"<th>{e(c)}</th>" for c in cabecalho)
    corpo = "".join("<tr>" + "".join(f'<td class="{"num" if i in numericas else ""}">{c}</td>' for i, c in enumerate(l)) + "</tr>" for l in linhas)
    return f'<table class="gc-tabela"><thead><tr>{th}</tr></thead><tbody>{corpo}</tbody></table>'


def cartao_numero(titulo: str, valor: int | str) -> str:
    return f'<div class="gc-card" style="flex:1 1 130px"><div class="gc-rotulo">{e(titulo)}</div><div class="gc-valor" style="font-size:32px">{e(str(valor))}</div></div>'


st.set_page_config(page_title="Sentinela CP", page_icon="🛡️", layout="wide")
injetar_css()

# ------------------------------------------------------------------ barra lateral
st.sidebar.markdown("### Sentinela CP")
chave = st.sidebar.selectbox("Cenário", list(vm.CENARIOS), format_func=lambda k: vm.CENARIOS[k].titulo, key="cenario")
opcoes_extrator = ["mock"] + (["openai"] if os.environ.get("OPENAI_API_KEY") else []) + (["claude"] if os.environ.get("ANTHROPIC_API_KEY") else [])
extrator = st.sidebar.selectbox("Quem lê as mensagens", opcoes_extrator, key="extrator", help="mock = regras determinísticas; openai/claude = LLM real (exige chave no ambiente)")
st.sidebar.caption(vm.CENARIOS[chave].descricao)

if st.session_state.get("config") != (chave, extrator):
    st.session_state["sessao"] = vm.criar_sessao(chave, extrator)
    st.session_state["config"] = (chave, extrator)
s: vm.Sessao = st.session_state["sessao"]

if st.sidebar.button("Executar tique e avançar 1 hora", key="avancar", type="primary", disabled=s.clock.terminou):
    vm.avancar(s)
if st.sidebar.button("Avançar até o pré-fechamento", key="pre", disabled=s.clock.terminou):
    vm.avancar_ate_pre_fechamento(s)
if st.sidebar.button("Reiniciar cenário", key="reiniciar"):
    st.session_state["sessao"] = s = vm.criar_sessao(chave, extrator)

# ------------------------------------------------------------------ cabeçalho
st.markdown(
    f"""<div class="gc-bloco-azul">
<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
<div><h1 style="color:#FFFFFF;margin:0">Sentinela CP</h1>
<div class="gc-destaque" style="color:#FFFFFF">Cada pagamento conferido antes de o dinheiro sair.</div></div>
<span class="gc-sticker">REPLAY LOCAL</span></div>
<div style="margin-top:8px;font-size:14px">Dados sintéticos do evento · foto de 02/11/2026 08:00 · a IA lê, o código decide · cenário: <b>{e(s.cenario.titulo)}</b></div>
</div>""",
    unsafe_allow_html=True,
)
st.write("")
c = vm.contagem(s)
t = vm.totais(s)
cartoes_topo = [
    f'<div class="gc-card" style="flex:1 1 170px"><div class="gc-rotulo">Relógio simulado</div><div class="gc-valor" style="font-size:28px">{s.clock.agora:%d/%m %H:%M}</div><div class="gc-rotulo">{t["tiques"]} tiques executados</div></div>',
    f'<div class="gc-contagem{" gc-contagem--urgente" if c["urgente"] else ""}" style="flex:1.4 1 230px">{e(c["restante"])}'
    f'<div class="gc-rotulo" style="color:inherit">para o lote {e(c["lote"])} fechar às {c["momento"]:%H:%M}</div></div>',
] + [
    cartao_numero(rotulo, t[chave_total])
    for rotulo, chave_total in (("retirados do lote", "retirados"), ("corrigidos", "corrigidos"), ("pessoas chamadas", "pessoas"), ("aprovações pedidas", "aprovacoes"))
]
st.markdown('<div style="display:flex;gap:12px;flex-wrap:wrap">' + "".join(cartoes_topo) + "</div>", unsafe_allow_html=True)

if not s.registros:
    st.info("Clique em **Executar tique e avançar 1 hora** (barra lateral) para começar. O relógio só avança para a frente, e o agente só vê o que já chegou.")
    st.stop()

# ------------------------------------------------------------------ 1. comunicações
cartoes, sem_alerta = vm.cartoes_comunicacao(s)
st.markdown("## 1 · O que chegou e o que a IA leu")
st.caption(f"{sem_alerta} comunicações lidas sem alerta. A IA só extrai (com o trecho citado); quem decide é a regra.")
for cartao in cartoes:
    alto = cartao["nivel"] == "alto"
    rotulo = selo("gc-selo--retirado", "RISCO ALTO", "⚠") if alto else selo("gc-selo--humano", "ATENÇÃO", "✋")
    cabecalho = f"{rotulo} <b>{e(cartao['id'])}</b> · {e(cartao['data_hora'])} · {e(cartao['remetente'])} · {e(cartao['assunto'])}"
    ia = "".join(f"<li><span class='gc-rotulo'>{e(k)}</span>: {e(v)}</li>" for k, v in cartao["ia_leu"])
    regra = "".join(f"<li>{e(m)}</li>" for m in cartao["regra_decidiu"])
    pessoas = f"<div class='gc-rotulo'>Quem a política manda chamar: {e(', '.join(cartao['pessoas']))}</div>" if cartao["pessoas"] else ""
    trecho = f"<blockquote>“{e(cartao['trecho'])}”</blockquote>" if cartao["trecho"] else ""
    corpo = (
        f'<div class="gc-card"><div>{cabecalho}</div>{trecho}'
        f'<div class="gc-ia"><ul style="margin:0">{ia}</ul></div>'
        f'<div class="gc-regra"><ul style="margin:0">{regra}</ul></div>{pessoas}</div>'
    )
    if alto:
        st.markdown(corpo, unsafe_allow_html=True)
    else:
        with st.expander(f"{cartao['id']} · {cartao['remetente']} · atenção"):
            st.markdown(corpo, unsafe_allow_html=True)

# ------------------------------------------------------------------ 2. decisões
st.markdown("## 2 · O que o agente fez no último tique")
linhas = vm.decisoes_recentes(s, 12)
if linhas:
    st.markdown(
        tabela(
            ["Valor", "Título", "Ação", "Regra aplicada (código)", "Motivo", "Chamou"],
            [[e(formatar_brl(l["valor"])) if l["valor"] is not None else "—", e(l["ref"]), selo_decisao(l["acao"]), e(l["regra"]), e(l["motivo"][:150]), e(l["pessoa"])] for l in linhas],
            numericas=(0,),
        ),
        unsafe_allow_html=True,
    )
    st.caption("Mostrando os 12 de maior valor com ação. Os demais títulos foram conferidos e seguem sem ação.")
else:
    st.caption("Nenhuma ação neste tique: tudo conferido dentro da política.")

# ------------------------------------------------------------------ 3. antes e depois do lote
st.markdown(f"## 3 · O lote, antes e depois (fornecedor {e(s.cenario.foco)})")
ad = vm.lote_antes_depois(s)
if ad:
    protegidos = sum(1 for x in ad if x["protegido"])
    st.markdown(f"**{protegidos} de {len(ad)}** títulos que estavam em lote aberto já saíram do lote antes do corte.")
    st.markdown(
        tabela(
            ["Título", "Valor", "Pagamento", "Lote antes", "Agora"],
            [[e(x["titulo"]), e(formatar_brl(x["valor"])), e(x["forma"]), e(x["lote_antes"]), selo_decisao("retirar_do_lote") if x["protegido"] else selo("gc-selo--segue", "AINDA NO LOTE", "•")] for x in ad[:15]],
            numericas=(1,),
        ),
        unsafe_allow_html=True,
    )
    if len(ad) > 15:
        st.caption(f"+ {len(ad) - 15} títulos.")

# ------------------------------------------------------------------ 4. chamados
st.markdown("## 4 · Quem foi chamado, com o dossiê")
ch = vm.chamados(s)
if ch["acionamentos"]:
    st.markdown(
        tabela(["Quando", "Pessoa", "Urgência", "Dossiê"], [[f"{a['quando']:%d/%m %H:%M}", e(a["pessoa"]), e(a["urgencia"]), e(a["dossie"][:220])] for a in ch["acionamentos"]]),
        unsafe_allow_html=True,
    )
    st.caption("Acionar não é aprovar: a liberação continua exigindo a aprovação prevista na política.")
if ch["solicitacoes"]:
    st.markdown(
        tabela(["Quando", "Ação a aprovar", "Aprovador", "Títulos"], [[f"{x['quando']:%d/%m %H:%M}", e(x["acao"]), e(x["aprovador"]), str(x["titulos"])] for x in ch["solicitacoes"]], numericas=(3,)),
        unsafe_allow_html=True,
    )

with st.expander("Linha do tempo de ações executadas"):
    for x in vm.execucoes(s)[-40:]:
        st.markdown(f"`{x['quando']:%d/%m %H:%M}` · {x['acao']} · {x['referencia']} · **{x['resultado']}**")
