"""Mesa de conferência de pagamentos com controles nativos do Streamlit."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from sentinela.ui import render
from sentinela.ui import viewmodel as vm
from sentinela.ui.theme import injetar_css

st.set_page_config(
    page_title="Sentinela CP | Contas a pagar",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)
injetar_css()
cabecalho = st.empty()

with st.container(border=True):
    configuracao, operacao = st.columns([1.1, 1.5], vertical_alignment="bottom")
    with configuracao:
        opcoes = list(vm.CENARIOS)
        escolha = st.segmented_control(
            "Cenário da simulação",
            opcoes,
            default=opcoes[0],
            format_func=lambda k: vm.CENARIOS[k].curto,
            key="cenario",
            selection_mode="single",
        )
        chave = escolha or st.session_state.get("config", (opcoes[0], "mock"))[0]

    extratores = (
        ["mock"]
        + (["openai"] if os.environ.get("OPENAI_API_KEY") else [])
        + (["claude"] if os.environ.get("ANTHROPIC_API_KEY") else [])
    )
    extrator = st.session_state.get("extrator", "mock")
    if len(extratores) > 1:
        with configuracao, st.expander("Configurar leitura das mensagens"):
            extrator = st.radio(
                "Leitor das mensagens",
                extratores,
                horizontal=True,
                key="extrator",
                format_func=lambda x: {
                    "mock": "Determinístico",
                    "openai": "OpenAI",
                    "claude": "Claude",
                }[x],
            )
    if extrator not in extratores:
        extrator = "mock"

    if st.session_state.get("config") != (chave, extrator):
        with st.spinner("Preparando a conferência…"):
            st.session_state["sessao"] = vm.criar_sessao(chave, extrator)
        st.session_state["config"] = (chave, extrator)
    s: vm.Sessao = st.session_state["sessao"]

    with operacao:
        c1, c2, c3 = st.columns([1, 1.3, 1.2])
        if c1.button(
            "Avançar 1 hora",
            key="avancar",
            type="primary",
            disabled=s.clock.terminou,
            use_container_width=True,
        ):
            with st.spinner("Conferindo pagamentos…"):
                vm.avancar(s)
        _, fechamento = s.clock.proximo_fechamento()
        tem_pre = s.clock.ultimo_tique_antes(fechamento) < s.clock.fim
        texto_pre = "Até o pré-fechamento" if tem_pre else "Concluir cenário"
        if c2.button(
            texto_pre,
            key="pre",
            disabled=s.clock.terminou,
            use_container_width=True,
            help="Confere cada hora até o pré-fechamento ou o fim do período simulado.",
        ):
            with st.spinner("Conferindo o cenário…"):
                vm.avancar_ate_pre_fechamento(s)
        if c3.button("Recomeçar o cenário", key="reiniciar", use_container_width=True):
            with st.spinner("Recomeçando…"):
                st.session_state["sessao"] = s = vm.criar_sessao(chave, extrator)
    st.caption(vm.CENARIOS[chave].descricao)

cabecalho.html(f'<div lang="pt-BR">{render.html_hero(s)}</div>')
secoes = render.abas(s, svg_embutido=False)
for guia, (_, _, conteudo) in zip(st.tabs([rot for _, rot, _ in secoes]), secoes):
    with guia:
        st.html(f'<div class="sx-pagina" lang="pt-BR">{conteudo}</div>')
st.html(f'<div lang="pt-BR">{render.html_rodape()}</div>')
