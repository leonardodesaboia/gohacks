"""Tema Gocase para a UI. Única fonte de cores em Python; o CSS vive em assets/tokens.css."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

TOKENS: dict[str, str] = {
    "azul": "#005BAA",
    "coral": "#F37053",
    "rosa": "#EC3FAA",
    "turquesa": "#94D6DA",
    "lima": "#E9ED9A",
    "rosa_claro": "#FFD6DC",
    "ink": "#0B1F33",
    "ink_2": "#3C566E",
    "linha": "#D9E3EC",
    "fundo": "#FFFFFF",
    "fundo_2": "#F6F9FC",
}

# decisão -> (classe do selo, rótulo, ícone). Estado nunca depende só de cor.
COR_DECISAO: dict[str, tuple[str, str, str]] = {
    "agendar_titulo": ("gc-selo--segue", "SEGUE SOZINHO", "✓"),
    "manter": ("gc-selo--segue", "SEGUE SOZINHO", "✓"),
    "corrigir_lancamento": ("gc-selo--corrigido", "CORRIGIDO", "✎"),
    "retirar_do_lote": ("gc-selo--retirado", "RETIRADO DO LOTE", "⏸"),
    "acionar_pessoa": ("gc-selo--humano", "CHAMEI ALGUÉM", "✋"),
    "solicitar_aprovacao": ("gc-selo--humano", "CHAMEI ALGUÉM", "✋"),
    "escalar": ("gc-selo--degradado", "REVISÃO MANUAL", "⚠"),
    "cancelar_titulo": ("gc-selo--cancelado", "CANCELADO", "✕"),
}

_TOKENS_CSS = Path(__file__).resolve().parents[3] / "assets" / "tokens.css"


def selo_decisao(acao: str) -> str:
    classe, rotulo, icone = COR_DECISAO.get(acao, COR_DECISAO["escalar"])
    return f'<span class="gc-selo {classe}"><span aria-hidden="true">{icone}</span>{rotulo}</span>'


def injetar_css() -> None:
    import streamlit as st

    css = _TOKENS_CSS.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def formatar_brl(valor: Decimal | float | int | str) -> str:
    v = Decimal(str(valor)).quantize(Decimal("0.01"))
    inteiro, _, frac = f"{v:,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{frac}"


def mascarar_cnpj(cnpj: str) -> str:
    d = re.sub(r"\D", "", cnpj)
    if len(d) != 14:
        return "**.***.***/****-**"
    return f"{d[:2]}.***.***/{d[8:12]}-{d[12:]}"


def mascarar_conta(conta: str) -> str:
    c = conta.strip()
    return "****" + (f"-{c[-1]}" if c else "")


def mascarar_pix(chave: str) -> str:
    c = chave.strip()
    return "****…" + c[-5:] if len(c) > 5 else "****"
