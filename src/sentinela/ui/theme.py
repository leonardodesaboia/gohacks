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
    "agendar_titulo": ("gc-selo--segue", "Segue sozinho", "✓"),
    "manter": ("gc-selo--segue", "Segue sozinho", "✓"),
    "corrigir_lancamento": ("gc-selo--corrigido", "Corrigido", "✎"),
    "retirar_do_lote": ("gc-selo--retirado", "Retirado do lote", "⏸"),
    "acionar_pessoa": ("gc-selo--humano", "Chamei alguém", "✋"),
    "solicitar_aprovacao": ("gc-selo--humano", "Chamei alguém", "✋"),
    "escalar": ("gc-selo--degradado", "Revisão manual", "⚠"),
    "cancelar_titulo": ("gc-selo--cancelado", "Cancelado", "✕"),
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


_CNPJ_TEXTO = re.compile(r"\b(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})\b")
_CONTA_TEXTO = re.compile(r"(C/C|conta(?: corrente)?)(\s*(?:n[ºo°.]*|:)?\s*)(\d[\d.]*-?\d?)", re.IGNORECASE)
_LINHA_TEXTO = re.compile(r"\b\d{47}\b")
_PIX_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


def mascarar_texto(texto: str | None) -> str:
    """Mascara CNPJ, conta, linha digitável e chave Pix (UUID) dentro de texto livre, p.ex. de uma mensagem citada."""
    if not texto:
        return ""
    texto = _LINHA_TEXTO.sub(lambda m: "****…" + m.group(0)[-6:], texto)
    texto = _CNPJ_TEXTO.sub(lambda m: f"{m.group(1)}.***.***/{m.group(4)}-{m.group(5)}", texto)
    texto = _CONTA_TEXTO.sub(lambda m: f"{m.group(1)}{m.group(2)}{mascarar_conta(m.group(3))}", texto)
    return _PIX_UUID.sub(lambda m: mascarar_pix(m.group(0)), texto)
