"""Renderizador HTML único da demo: a mesma página alimenta a tela Streamlit e o site estático.

Regras de qualidade (docs/06-DESIGN-SYSTEM.md): tudo que vem de mensagem é escapado; dados sensíveis já chegam
mascarados do viewmodel; HTML semântico (article, section, dl, table com caption, details); a linha do tempo em SVG é
decorativa (`aria-hidden`) e tem equivalente textual em lista; números tabulares; sem rótulos em caixa alta.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any
from urllib.parse import quote

from . import viewmodel as vm
from .theme import TOKENS, formatar_brl, selo_decisao

e = html.escape

RODAPE = (
    "Projeto individual para o GoHacks Talent 2026. Dados sintéticos fornecidos pelo evento; replay local sobre a foto de "
    "02/11/2026 às 08:00. Não é um produto da Gocase nem da Gogroup."
)


def _selo(classe: str, rotulo: str, icone: str) -> str:
    return f'<span class="gc-selo {classe}"><span aria-hidden="true">{icone}</span>{e(rotulo)}</span>'


def _hora_br(texto: str) -> str:
    try:
        return f"{datetime.fromisoformat(texto):%d/%m às %H:%M}"
    except ValueError:
        return texto


def _quando(dt: datetime) -> str:
    return f"{dt:%d/%m} às {dt:%H:%M}"


# ------------------------------------------------------------------ linha do tempo
def _svg_tempo(t: dict[str, Any]) -> str:
    """SVG autocontido (cores e fonte como atributos, sem depender do CSS da página): serve inline no site estático e
    como imagem embutida no Streamlit, cujo sanitizador de HTML remove o elemento <svg>."""
    c = TOKENS
    fonte = 'font-family="Figtree, Segoe UI, Arial, sans-serif"'
    forte = f'{fonte} font-weight="700" font-size="15" fill="{c["ink"]}"'
    fraco = f'{fonte} font-weight="600" font-size="14" fill="{c["ink_2"]}"'
    W, H, x0, x1, y = 1000, 150, 28, 972, 82
    total = max((t["fim"] - t["inicio"]).total_seconds(), 1)

    def x(dt: datetime) -> float:
        return x0 + (x1 - x0) * max(0.0, min(1.0, (dt - t["inicio"]).total_seconds() / total))

    def ancora(px: float) -> str:
        return "end" if px > 780 else "start" if px < 170 else "middle"

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" class="sx-svg" viewBox="0 0 {W} {H}" aria-hidden="true" focusable="false">']
    p.append(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{c["linha"]}" stroke-width="6" stroke-linecap="round"/>')
    xa = x(t["agora"])
    p.append(f'<line x1="{x0}" y1="{y}" x2="{xa:.1f}" y2="{y}" stroke="{c["azul"]}" stroke-width="6" stroke-linecap="round"/>')
    for tq in t["tiques"]:
        p.append(f'<circle cx="{x(tq):.1f}" cy="{y}" r="4.5" fill="{c["fundo"]}" stroke="{c["azul"]}" stroke-width="2"/>')
    p.append(f'<line x1="{x1}" y1="{y - 38}" x2="{x1}" y2="{y + 38}" stroke="{c["azul"]}" stroke-width="5"/>')
    p.append(f'<text x="{x1 - 10}" y="{y - 46}" text-anchor="end" {forte.replace(c["ink"], c["azul"])}>Corte do lote {e(t["corte_lote"])}, {t["fim"]:%H:%M} de {t["fim"]:%d/%m}</text>')
    p.append(f'<text x="{x0}" y="{y + 36}" {fraco}>{t["inicio"]:%H:%M} de {t["inicio"]:%d/%m}</text>')
    for m in t["marcos"]:
        px = x(m["t"])
        if m["tipo"] == "mensagem":
            p.append(f'<circle cx="{px:.1f}" cy="{y}" r="7.5" fill="{c["rosa"]}" stroke="{c["ink"]}" stroke-width="2.5"/>')
            p.append(f'<text x="{px:.1f}" y="{y - 22}" text-anchor="{ancora(px)}" {forte}>Mensagem às {m["t"]:%H:%M}</text>')
        elif m["tipo"] == "protecao":
            p.append(f'<circle cx="{px:.1f}" cy="{y}" r="8.5" fill="{c["coral"]}" stroke="{c["ink"]}" stroke-width="2.5"/>')
            p.append(f'<text x="{px:.1f}" y="{y + 40}" text-anchor="{ancora(px)}" {forte}>{m["t"]:%H:%M}: {e(m["rotulo"])}</text>')
        else:
            p.append(f'<rect x="{px - 8:.1f}" y="{y - 8}" width="16" height="16" transform="rotate(45 {px:.1f} {y})" fill="{c["lima"]}" stroke="{c["ink"]}" stroke-width="2.5"/>')
            p.append(f'<text x="{px:.1f}" y="{y + 40}" text-anchor="{ancora(px)}" {forte}>{m["t"]:%H:%M}: pré-fechamento</text>')
    p.append(f'<line x1="{xa:.1f}" y1="{y - 62}" x2="{xa:.1f}" y2="{y + 24}" stroke="{c["ink"]}" stroke-width="2.5"/>')
    p.append(f'<text x="{xa + (6 if ancora(xa) == "middle" else 0):.1f}" y="{y - 68}" text-anchor="{"start" if ancora(xa) == "middle" else ancora(xa)}" {fraco}>Agora, {t["agora"]:%H:%M}</text>')
    p.append("</svg>")
    return "".join(p)


def _figura(svg: str, embutido: bool) -> str:
    if embutido:
        return svg
    return f'<img class="sx-svg" alt="" aria-hidden="true" src="data:image/svg+xml;charset=utf-8,{quote(svg, safe="")}">'


def html_tempo(s: vm.Sessao, svg_embutido: bool = True) -> str:
    t = vm.linha_do_tempo(s)
    itens = [f'<li><time datetime="{t["inicio"]:%Y-%m-%dT%H:%M}">{_quando(t["inicio"])}</time> Início do cenário.</li>']
    itens += [f'<li><time datetime="{m["t"]:%Y-%m-%dT%H:%M}">{_quando(m["t"])}</time> {e(m["rotulo"])}.</li>' for m in t["marcos"]]
    itens.append(f'<li><time datetime="{t["agora"]:%Y-%m-%dT%H:%M}">{_quando(t["agora"])}</time> Agora ({len(t["tiques"])} tiques executados).</li>')
    itens.append(f'<li><time datetime="{t["fim"]:%Y-%m-%dT%H:%M}">{_quando(t["fim"])}</time> Corte do lote {e(t["corte_lote"])}.</li>')
    return (
        '<section class="sx-tempo" aria-labelledby="h-tempo"><h2 class="sx-h2" id="h-tempo">Antes do corte</h2>'
        f'{_figura(_svg_tempo(t), svg_embutido)}<ol class="sx-marcos">{"".join(itens)}</ol></section>'
    )


# ------------------------------------------------------------------ hero
def _falta_voce(s: vm.Sessao) -> str:
    """A única pendência do analista, logo abaixo da manchete: o que fazer e quem já foi chamado."""
    if not s.registros:
        return ""
    cartoes, _ = vm.cartoes_comunicacao(s)
    altos = [c for c in cartoes if c["nivel"] == "alto"]
    if not altos:
        return ""
    c = altos[0]
    quem = f" Já acionamos {e(c['pessoas'][0].split(',')[0])}." if c["pessoas"] else ""
    return f'<p class="sx-falta"><strong>Falta você:</strong> {e(_o_que_fazer(c))}{quem}</p>'


def html_hero(s: vm.Sessao) -> str:
    titulo, sub = vm.manchete(s)
    c = vm.contagem(s)
    return (
        '<header class="sx-hero"><div class="sx-hero-topo"><div><div class="sx-marca">Sentinela CP</div>'
        '<div class="sx-tagline">Cada pagamento conferido antes de o dinheiro sair.</div></div>'
        '<span class="gc-sticker">Replay local</span></div>'
        f'<h1 class="sx-titulo">{e(titulo)}</h1><p class="sx-sub">{e(sub)}</p>{_falta_voce(s)}'
        f'<p class="sx-relogio"><span class="sx-relogio-num">{s.clock.agora:%d/%m %H:%M}</span> no relógio simulado. '
        f'Próximo corte: <strong>{e(c["lote"])}</strong> em <span class="sx-num">{e(c["restante"])}</span>.</p></header>'
    )


# ------------------------------------------------------------------ resumo e fila do analista
def html_resumo(s: vm.Sessao) -> str:
    """O fluxo do agente em 4 passos, com o número de cada um: explica a aplicação e mostra o que já aconteceu."""
    t = vm.totais(s)
    cartoes, sem_alerta = vm.cartoes_comunicacao(s)
    suspeitas = sum(1 for c in cartoes if c["nivel"] == "alto")
    passos = [
        ("sx-passo--chega", "Chega uma mensagem", len(cartoes) + sem_alerta, "mensagens lidas", "E-mails e WhatsApp que chegam ao financeiro."),
        ("sx-passo--ia", "A IA lê", suspeitas, "suspeitas", "Só extrai o que a mensagem pede e cita o trecho. Não decide nada."),
        ("sx-passo--codigo", "O código decide", t["retirados"], "retirados do lote, no total", "Regras fixas: retirar do lote, corrigir ou seguir."),
        ("sx-passo--acao", "Chama a pessoa certa", t["pessoas"], "pessoas chamadas", "Com o dossiê pronto. Chamar não é aprovar."),
    ]
    cels = "".join(
        f'<li class="sx-passo {cl}"><span class="sx-passo-n" aria-hidden="true">{i}</span><h3 class="sx-passo-tit">{e(tit)}</h3>'
        f'<p class="sx-passo-num"><span class="sx-num">{n}</span> {e(rot)}</p><p class="sx-passo-desc">{e(desc)}</p></li>'
        for i, (cl, tit, n, rot, desc) in enumerate(passos, 1)
    )
    return (
        '<section aria-labelledby="h-fluxo"><h2 class="sx-h2" id="h-fluxo">Como o agente trabalha</h2>'
        '<p class="sx-leg">Um analista de contas a pagar que nunca dorme: confere cada pagamento antes de o banco fechar o lote e só incomoda gente de verdade quando precisa.</p>'
        f'<ol class="sx-fluxo">{cels}</ol></section>'
    )


def _o_que_fazer(c: dict[str, Any]) -> str:
    sinais = set(c.get("sinais") or [])
    if "troca_bancaria_solicitada" in sinais:
        return "Ligar para o telefone que já está no cadastro e registrar a confirmação antes de liberar qualquer pagamento."
    if "tentativa_de_instrucao" in sinais or "remetente_nao_confere" in sinais:
        return "Não responder, não abrir links nem anexos. Encaminhar para quem foi chamado."
    return "Revisar a mensagem e decidir se libera."


def _alerta(c: dict[str, Any]) -> str:
    alto = c["nivel"] == "alto"
    selo = _selo("gc-selo--retirado", "Risco alto", "⚠") if alto else _selo("gc-selo--humano", "Atenção", "✋")
    pedido = next((v for k, v in c["ia_leu"] if k == "Pedido"), "Mensagem")
    por_que = c["regra_decidiu"][:1] or ["Sem sinais de risco."]
    resto = c["regra_decidiu"][1:]
    campos = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in c["ia_leu"])
    trecho = f"<blockquote>“{e(c['trecho'])}”</blockquote>" if c["trecho"] else ""
    feito = f'Chamou {e("; ".join(c["pessoas"]))}, com o dossiê.' if c["pessoas"] else "Marcou para revisão. Ninguém precisou ser chamado."
    lista_resto = "<ul>" + "".join(f"<li>{e(m)}</li>" for m in resto) + "</ul>" if resto else ""
    mais = lista_resto + trecho + f'<dl class="sx-campos">{campos}</dl>'
    motivos = "".join(f"<span>{e(m)}</span>" for m in por_que)
    return (
        f'<article class="sx-caso sx-caso--{c["nivel"]}"><header class="sx-caso-topo">{selo}<h3 class="sx-caso-titulo">{e(pedido)}</h3>'
        f'<time class="sx-hora" datetime="{e(c["data_hora"][:16].replace(" ", "T"))}">{e(_hora_br(c["data_hora"]))}</time></header>'
        f'<p class="sx-quem">{e(c["remetente"])} · “{e(c["assunto"])}” · {e(c["id"])}</p>'
        f'<dl class="sx-dossie3"><div><dt>Por que desconfiamos</dt><dd>{motivos}</dd></div>'
        f'<div><dt>O que o agente fez</dt><dd>{feito}</dd></div>'
        f'<div class="sx-voce"><dt>O que falta de você</dt><dd>{e(_o_que_fazer(c))}</dd></div></dl>'
        f'<details class="sx-mais"><summary>Ver evidências</summary>{mais}</details></article>'
    )


def html_alertas(s: vm.Sessao) -> str:
    cartoes, sem_alerta = vm.cartoes_comunicacao(s)
    altos = [c for c in cartoes if c["nivel"] == "alto"]
    atencao = [c for c in cartoes if c["nivel"] != "alto"]
    p = ['<section aria-labelledby="h-fila"><h2 class="sx-h2" id="h-fila">Fila do analista</h2>',
         f'<p class="sx-leg">{len(altos)} com risco alto. {sem_alerta} mensagens lidas sem alerta. A IA só extrai, citando o trecho. Quem decide é o código.</p>']
    p += [_alerta(c) for c in altos[:1]]
    if altos[1:]:
        p.append(f'<details class="sx-mais"><summary>{len(altos) - 1} outros casos de risco alto</summary>{"".join(_alerta(c) for c in altos[1:])}</details>')
    if atencao:
        p.append(f'<details class="sx-mais"><summary>{len(atencao)} mensagens pedem atenção, sem risco alto</summary>{"".join(_alerta(c) for c in atencao)}</details>')
    p.append("</section>")
    return "".join(p)


def html_alertas_primeiro(s: vm.Sessao) -> str:
    """Só o caso mais urgente, para a aba inicial. O resto está na aba da fila."""
    cartoes, _ = vm.cartoes_comunicacao(s)
    altos = [c for c in cartoes if c["nivel"] == "alto"]
    if not altos:
        return ""
    return f'<section aria-labelledby="h-agora"><h2 class="sx-h2" id="h-agora">O caso mais urgente</h2>{_alerta(altos[0])}</section>'


# ------------------------------------------------------------------ lote
def html_lote(s: vm.Sessao) -> str:
    ad = vm.lote_antes_depois(s)
    forn = s.laco.catalogo.por_id(s.cenario.foco)
    nome = (forn.nome_fantasia if forn else None) or s.cenario.foco
    p = ['<section aria-labelledby="h-lote"><h2 class="sx-h2" id="h-lote">O que mudou no lote</h2>']
    if not ad:
        p.append(f'<p class="sx-leg">Nenhum título de {e(nome)} estava agendado em lote aberto no início.</p></section>')
        return "".join(p)
    prot = sum(1 for x in ad if x["protegido"])
    p.append(f'<p class="sx-lead"><strong class="sx-grande sx-num">{prot} de {len(ad)}</strong> títulos de {e(nome)} que estavam em lote aberto '
             f'{"já saíram do lote" if prot else "ainda estão no lote"}.</p>')
    tiles = []
    for x in ad:
        estado = "fora do lote" if x["protegido"] else "ainda no lote"
        rot = f'{x["titulo"]}, {formatar_brl(x["valor"])}, {estado}'
        tiles.append(f'<li class="sx-tile {"sx-tile--fora" if x["protegido"] else "sx-tile--lote"}"><span class="sx-so-leitor">{e(rot)}</span></li>')
    p.append(f'<ul class="sx-tiles" role="list" aria-label="Um quadrado por título de {e(nome)}">{"".join(tiles)}</ul>')
    p.append('<p class="sx-legenda"><span class="sx-chave sx-tile--lote"></span> ainda no lote <span class="sx-chave sx-tile--fora"></span> fora do lote</p>')
    linhas = "".join(
        f'<tr><th scope="row">{e(x["titulo"])}</th><td class="num">{e(formatar_brl(x["valor"]))}</td><td>{e(x["forma"])}</td><td>{e(x["lote_antes"])}</td>'
        f'<td>{selo_decisao("retirar_do_lote") if x["protegido"] else _selo("gc-selo--segue", "Ainda no lote", "•")}</td></tr>'
        for x in ad
    )
    p.append(
        '<details class="sx-mais"><summary>Ver a lista dos títulos</summary><div class="sx-rolagem" tabindex="0" role="region" aria-label="Títulos do fornecedor, rolável"><table class="sx-tabela"><caption class="sx-so-leitor">Títulos do fornecedor em foco, antes e depois</caption>'
        f'<thead><tr><th scope="col">Título</th><th scope="col">Valor</th><th scope="col">Pagamento</th><th scope="col">Lote antes</th><th scope="col">Agora</th></tr></thead><tbody>{linhas}</tbody></table></div></details></section>'
    )
    return "".join(p)


# ------------------------------------------------------------------ chamados e ações
def html_chamados(s: vm.Sessao) -> str:
    ch = vm.chamados(s)
    p = ['<section aria-labelledby="h-chamados"><h2 class="sx-h2" id="h-chamados">Quem foi chamado</h2>']
    if not ch["acionamentos"] and not ch["solicitacoes"]:
        p.append('<p class="sx-leg">Ninguém foi chamado ainda.</p></section>')
        return "".join(p)
    grupos: dict[str, list[dict[str, Any]]] = {}
    for a in ch["acionamentos"]:
        grupos.setdefault(a["pessoa"], []).append(a)
    itens = []
    for lista in grupos.values():
        a = lista[0]
        urg = _selo("gc-selo--retirado", "Urgência alta", "⚠") if any(x["urgencia"] == "alta" for x in lista) else ""
        n = len(lista)
        qtd = f"{n} mensagens suspeitas" if n > 1 else "1 mensagem suspeita"
        dossies = "".join(f"<li>{e(_corta(x['dossie'], 240))}</li>" for x in lista)
        itens.append(
            f'<li class="sx-chamado"><div class="sx-chamado-topo"><strong>{e(a["pessoa"].split(" (")[0])}</strong>'
            f'<span class="sx-quem">{e(a["cargo"].split(", ", 1)[-1] if ", " in a["cargo"] else "")}</span>{urg}'
            f'<time class="sx-hora" datetime="{a["quando"]:%Y-%m-%dT%H:%M}">{a["quando"]:%d/%m %H:%M}</time></div>'
            f'<p class="sx-dossie">{qtd}</p><details class="sx-mais sx-mais--fino"><summary>Ver dossiês</summary><ul class="sx-dossie">{dossies}</ul></details></li>'
        )
    p.append(f'<ul class="sx-chamados" role="list">{"".join(itens[:4])}</ul>')
    if len(itens) > 4:
        p.append(f'<details class="sx-mais"><summary>Mais {len(itens) - 4} pessoas chamadas</summary><ul class="sx-chamados" role="list">{"".join(itens[4:])}</ul></details>')
    p.append('<p class="sx-leg">Chamar alguém não é aprovar: a liberação continua exigindo a aprovação prevista na política.</p>')
    if ch["solicitacoes"]:
        linhas = "".join(
            f'<tr><td>{x["quando"]:%d/%m %H:%M}</td><td>{e(x["acao"])}</td><td>{e(x["aprovador"])}</td><td class="num">{x["titulos"]}</td></tr>' for x in ch["solicitacoes"]
        )
        p.append(
            '<div class="sx-rolagem" tabindex="0" role="region" aria-label="Pedidos de aprovação, rolável"><table class="sx-tabela"><caption>Pedidos de aprovação, agrupados por incidente</caption>'
            f'<thead><tr><th scope="col">Quando</th><th scope="col">Ação a aprovar</th><th scope="col">Aprovador</th><th scope="col">Títulos</th></tr></thead><tbody>{linhas}</tbody></table></div>'
        )
    p.append("</section>")
    return "".join(p)


REGRAS = {
    "R0": "dado ausente ou ambíguo", "R1": "suspeita de fraude ou identidade", "R2": "possível duplicidade", "R3": "falta evidência",
    "R4": "troca de conta recente", "R5": "pedido de compra x nota fiscal", "R6": "valor ou vencimento", "R7": "tudo certo",
}


def _corta(texto: str, limite: int) -> str:
    """Corta na fronteira de palavra, nunca no meio."""
    if len(texto) <= limite:
        return texto
    return texto[:limite].rsplit(" ", 1)[0].rstrip(",;:. ") + "…"


def html_acoes(s: vm.Sessao) -> str:
    nomes = vm.nomes_pessoas(s)
    linhas = vm.decisoes_recentes(s, 12)
    p = ['<section aria-labelledby="h-acoes"><h2 class="sx-h2" id="h-acoes">O que o agente fez no último tique</h2>']
    if not linhas:
        p.append('<p class="sx-leg">Nenhuma ação neste tique: tudo foi conferido dentro da política.</p></section>')
        return "".join(p)
    corpo = "".join(
        f'<tr><td class="num">{e(formatar_brl(l["valor"])) if l["valor"] is not None else "—"}</td><td>{e(l["ref"])}</td><td>{selo_decisao(l["acao"])}</td>'
        f'<td>{e(REGRAS.get(str(l["regra"])[:2], l["regra"]))}</td><td class="sx-motivo">{e(_corta(l["motivo"], 150))}</td><td>{e(nomes.get(l["pessoa"], l["pessoa"]).split(",")[0])}</td></tr>'
        for l in linhas
    )
    p.append(
        '<div class="sx-rolagem" tabindex="0" role="region" aria-label="Ações do último tique, rolável"><table class="sx-tabela"><caption class="sx-so-leitor">Ações do último tique, por valor</caption>'
        '<thead><tr><th scope="col">Valor</th><th scope="col">Título</th><th scope="col">Ação</th><th scope="col">Regra aplicada</th><th scope="col">Motivo</th><th scope="col">Chamou</th></tr></thead>'
        f'<tbody>{corpo}</tbody></table></div><p class="sx-leg">Os 12 de maior valor com ação. Os demais títulos foram conferidos e seguem sem ação.</p></section>'
    )
    return "".join(p)


# ------------------------------------------------------------------ página
def pagina(s: vm.Sessao, svg_embutido: bool = True) -> str:
    """`svg_embutido=True` (site estático): SVG inline. False (Streamlit): imagem SVG embutida, que o sanitizador aceita."""
    corpo = [html_hero(s)]
    corpo += [f'<div class="sx-secao" data-aba="{i}">{h}</div>' for i, _, h in abas(s, svg_embutido)]
    corpo.append(html_rodape())
    return f'<div class="sx-pagina">{"".join(corpo)}</div>'


# ------------------------------------------------------------------ abas
ABAS = [("geral", "Agora"), ("fila", "Fila do analista"), ("lote", "Lote"), ("chamados", "Quem foi chamado"), ("registro", "Registro técnico")]


def html_rodape() -> str:
    return f'<p class="sx-rodape">{e(RODAPE)}</p>'


def abas(s: vm.Sessao, svg_embutido: bool = True) -> list[tuple[str, str, str]]:
    """O conteúdo da tela dividido em abas: (id, rótulo, html). Rótulos fixos: o Streamlit zera a aba ativa se mudarem."""
    vazio = '<p class="sx-vazio">Ainda não há o que mostrar. Use <strong>Avançar 1 hora</strong>: o agente só vê o que já chegou, e o relógio só anda para a frente.</p>'
    com_dados = bool(s.registros)
    conteudo = {
        "geral": (html_alertas_primeiro(s) + html_lote(s) + html_tempo(s, svg_embutido) if com_dados else vazio + html_tempo(s, svg_embutido))
        + f'<details class="sx-mais"><summary>Como o agente trabalha</summary>{html_resumo(s)}</details>',
        "fila": html_alertas(s) if com_dados else vazio,
        "lote": html_lote(s) if com_dados else vazio,
        "chamados": html_chamados(s) if com_dados else vazio,
        "registro": html_acoes(s) if com_dados else vazio,
    }
    return [(i, rot, conteudo[i]) for i, rot in ABAS]
