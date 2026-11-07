"""Tela de narração da demo do Sentinela CP (Streamlit). Visual: docs/06-DESIGN-SYSTEM.md (identidade Gocase).

Só controles e relógio: o HTML vem de `render.pagina` (o mesmo que alimenta o site estático) e a lógica, de `viewmodel`.
Rodar:  streamlit run src/sentinela/ui/app.py
Sempre declarada como REPLAY LOCAL (dados sintéticos; foto de 02/11/2026 08:00). Todo texto de mensagem é escapado.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # src/, para rodar sem instalar o pacote

import streamlit as st  # noqa: E402

from sentinela.ui import render  # noqa: E402
from sentinela.ui import viewmodel as vm  # noqa: E402
from sentinela.ui.theme import injetar_css  # noqa: E402

st.set_page_config(page_title="Sentinela CP", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
injetar_css()

# ------------------------------------------------------------------ controles (no topo: valem para telão e celular)
opcoes = list(vm.CENARIOS)
escolha = st.segmented_control("Cenário", opcoes, default=opcoes[0], format_func=lambda k: vm.CENARIOS[k].curto, key="cenario", selection_mode="single")
chave = escolha or st.session_state.get("config", (opcoes[0], "mock"))[0]  # se o usuário desmarcar, mantém o cenário atual
st.caption(vm.CENARIOS[chave].descricao)

extratores = ["mock"] + (["openai"] if os.environ.get("OPENAI_API_KEY") else []) + (["claude"] if os.environ.get("ANTHROPIC_API_KEY") else [])
extrator = st.session_state.get("extrator", "mock")
if len(extratores) > 1:
    with st.expander("Quem lê as mensagens"):
        extrator = st.radio("Leitor das mensagens", extratores, horizontal=True, key="extrator", help="mock = regras determinísticas; openai e claude usam a chave do ambiente")
if extrator not in extratores:
    extrator = "mock"

if st.session_state.get("config") != (chave, extrator):
    with st.spinner("Carregando os dados do replay…"):
        st.session_state["sessao"] = vm.criar_sessao(chave, extrator)
    st.session_state["config"] = (chave, extrator)
s: vm.Sessao = st.session_state["sessao"]

c1, c2, c3 = st.columns(3)
if c1.button("Avançar 1 hora", key="avancar", type="primary", disabled=s.clock.terminou, use_container_width=True):
    vm.avancar(s)
if c2.button("Até o pré-fechamento", key="pre", disabled=s.clock.terminou, use_container_width=True, help="Avança tique a tique até o pré-fechamento do próximo lote"):
    vm.avancar_ate_pre_fechamento(s)
if c3.button("Recomeçar o cenário", key="reiniciar", use_container_width=True):
    with st.spinner("Recomeçando…"):
        st.session_state["sessao"] = s = vm.criar_sessao(chave, extrator)

# ------------------------------------------------------------------ a página
st.html(f'<div lang="pt-BR">{render.html_hero(s)}</div>')
secoes = render.abas(s, svg_embutido=False)  # svg como imagem: o sanitizador do st.html remove <svg>
guias = st.tabs([rot for _, rot, _ in secoes])
for guia, (_, _, conteudo) in zip(guias, secoes):
    with guia:
        st.html(f'<div class="sx-pagina" lang="pt-BR">{conteudo}</div>')
st.html(f'<div lang="pt-BR">{render.html_rodape()}</div>')
