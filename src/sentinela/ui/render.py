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
def html_hero(s: vm.Sessao) -> str:
    titulo, sub = vm.manchete(s)
    c = vm.contagem(s)
    return (
        '<header class="sx-hero"><div class="sx-hero-topo"><div><div class="sx-marca">Sentinela CP</div>'
        '<div class="sx-tagline">Cada pagamento conferido antes de o dinheiro sair.</div></div>'
        '<span class="gc-sticker">Replay local</span></div>'
        f'<h1 class="sx-titulo">{e(titulo)}</h1><p class="sx-sub">{e(sub)}</p>'
        f'<p class="sx-relogio"><span class="sx-relogio-num">{s.clock.agora:%d/%m %H:%M}</span> no relógio simulado. '
        f'Próximo corte: <strong>{e(c["lote"])}</strong> em <span class="sx-num">{e(c["restante"])}</span>.</p></header>'
    )


# ------------------------------------------------------------------ resumo e fila do analista
def html_resumo(s: vm.Sessao) -> str:
    t = vm.totais(s)
    itens = [(t["retirados"], "retirados do lote"), (t["corrigidos"], "corrigidos"), (t["aprovacoes"], "aprovações pedidas"), (t["pessoas"], "pessoas chamadas")]
    cels = "".join(f'<div class="sx-kpi"><dd class="sx-kpi-num sx-num">{n}</dd><dt>{e(rot)}</dt></div>' for n, rot in itens)
    return f'<section aria-label="Resumo"><dl class="sx-kpis">{cels}</dl></section>'


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
    por_que = c["regra_decidiu"][:2] or ["Sem sinais de risco."]
    resto = c["regra_decidiu"][2:]
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
        f'<dl class="sx-dossie3"><div><dt>Por que é suspeito</dt><dd>{motivos}</dd></div>'
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
    p += [_alerta(c) for c in altos]
    if atencao:
        p.append(f'<details class="sx-mais"><summary>{len(atencao)} mensagens pedem atenção, sem risco alto</summary>{"".join(_alerta(c) for c in atencao)}</details>')
    p.append("</section>")
    return "".join(p)


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
        tiles.append(f'<li class="sx-tile {"sx-tile--fora" if x["protegido"] else "sx-tile--lote"}" title="{e(rot)}"><span class="sx-so-leitor">{e(rot)}</span></li>')
    p.append(f'<ul class="sx-tiles" role="list" aria-label="Um quadrado por título de {e(nome)}">{"".join(tiles)}</ul>')
    p.append('<p class="sx-legenda"><span class="sx-chave sx-tile--lote"></span> ainda no lote <span class="sx-chave sx-tile--fora"></span> fora do lote</p>')
    linhas = "".join(
        f'<tr><th scope="row">{e(x["titulo"])}</th><td class="num">{e(formatar_brl(x["valor"]))}</td><td>{e(x["forma"])}</td><td>{e(x["lote_antes"])}</td>'
        f'<td>{selo_decisao("retirar_do_lote") if x["protegido"] else _selo("gc-selo--segue", "Ainda no lote", "•")}</td></tr>'
        for x in ad
    )
    p.append(
        '<details class="sx-mais"><summary>Ver a lista dos títulos</summary><div class="sx-rolagem"><table class="sx-tabela"><caption class="sx-so-leitor">Títulos do fornecedor em foco, antes e depois</caption>'
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
    itens = []
    for a in ch["acionamentos"]:
        urg = _selo("gc-selo--retirado", "Urgência alta", "⚠") if a["urgencia"] == "alta" else ""
        itens.append(
            f'<li class="sx-chamado"><div class="sx-chamado-topo"><strong>{e(a["pessoa"].split(" (")[0])}</strong>'
            f'<span class="sx-quem">{e(a["cargo"].split(", ", 1)[-1] if ", " in a["cargo"] else "")}</span>{urg}'
            f'<time class="sx-hora">{a["quando"]:%d/%m %H:%M}</time></div><details class="sx-mais sx-mais--fino"><summary>Ver dossiê</summary><p class="sx-dossie">{e(a["dossie"][:240])}</p></details></li>'
        )
    p.append(f'<ul class="sx-chamados" role="list">{"".join(itens[:4])}</ul>')
    if len(itens) > 4:
        p.append(f'<details class="sx-mais"><summary>Mais {len(itens) - 4} chamados</summary><ul class="sx-chamados" role="list">{"".join(itens[4:])}</ul></details>')
    p.append('<p class="sx-leg">Chamar alguém não é aprovar: a liberação continua exigindo a aprovação prevista na política.</p>')
    if ch["solicitacoes"]:
        linhas = "".join(
            f'<tr><td>{x["quando"]:%d/%m %H:%M}</td><td>{e(x["acao"])}</td><td>{e(x["aprovador"])}</td><td class="num">{x["titulos"]}</td></tr>' for x in ch["solicitacoes"]
        )
        p.append(
            '<table class="sx-tabela"><caption>Pedidos de aprovação, agrupados por incidente</caption>'
            f'<thead><tr><th scope="col">Quando</th><th scope="col">Ação a aprovar</th><th scope="col">Aprovador</th><th scope="col">Títulos</th></tr></thead><tbody>{linhas}</tbody></table>'
        )
    p.append("</section>")
    return "".join(p)


def html_acoes(s: vm.Sessao) -> str:
    linhas = vm.decisoes_recentes(s, 12)
    p = ['<section aria-labelledby="h-acoes"><details class="sx-mais sx-mais--grande"><summary id="h-acoes">Detalhe técnico: o que o agente fez no último tique</summary>']
    if not linhas:
        p.append('<p class="sx-leg">Nenhuma ação neste tique: tudo foi conferido dentro da política.</p></details></section>')
        return "".join(p)
    corpo = "".join(
        f'<tr><td class="num">{e(formatar_brl(l["valor"])) if l["valor"] is not None else "—"}</td><td>{e(l["ref"])}</td><td>{selo_decisao(l["acao"])}</td>'
        f'<td>{e(l["regra"])}</td><td class="sx-motivo">{e(l["motivo"][:150])}</td><td>{e(l["pessoa"])}</td></tr>'
        for l in linhas
    )
    p.append(
        '<div class="sx-rolagem"><table class="sx-tabela"><caption class="sx-so-leitor">Ações do último tique, por valor</caption>'
        '<thead><tr><th scope="col">Valor</th><th scope="col">Título</th><th scope="col">Ação</th><th scope="col">Regra aplicada</th><th scope="col">Motivo</th><th scope="col">Chamou</th></tr></thead>'
        f'<tbody>{corpo}</tbody></table></div><p class="sx-leg">Os 12 de maior valor com ação. Os demais títulos foram conferidos e seguem sem ação.</p></details></section>'
    )
    return "".join(p)


# ------------------------------------------------------------------ página
def pagina(s: vm.Sessao, svg_embutido: bool = True) -> str:
    """`svg_embutido=True` (site estático): SVG inline. False (Streamlit): imagem SVG embutida, que o sanitizador aceita."""
    corpo = [html_hero(s), html_resumo(s)]
    if not s.registros:
        corpo.append('<p class="sx-vazio">Ainda não há o que mostrar. Use <strong>Avançar 1 hora</strong>: o agente só vê o que já chegou, e o relógio só anda para a frente.</p>')
        corpo.append(html_tempo(s, svg_embutido))
    else:
        corpo.append(f'<div class="sx-grade"><div class="sx-col">{html_alertas(s)}</div><div class="sx-col">{html_lote(s)}{html_chamados(s)}</div></div>')
        corpo.append(html_tempo(s, svg_embutido))
        corpo.append(html_acoes(s))
    corpo.append(f'<p class="sx-rodape">{e(RODAPE)}</p>')
    return f'<div class="sx-pagina">{"".join(corpo)}</div>'
