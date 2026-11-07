"""Interface operacional compartilhada pelo Streamlit e pelo replay estático."""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any
from urllib.parse import quote

from . import viewmodel as vm
from .theme import TOKENS, formatar_brl, selo_decisao

e = html.escape
RODAPE = (
    "Projeto individual para o GoHacks Talent 2026. Dados sintéticos fornecidos pelo evento; "
    "replay local sobre a foto de 02/11/2026 às 08:00. Não é um produto da Gocase nem da Gogroup."
)
ABAS = [
    ("geral", "Visão geral"),
    ("fila", "Fila do analista"),
    ("lote", "Lote de pagamentos"),
    ("chamados", "Encaminhamentos"),
    ("registro", "Histórico de ações"),
]


def _selo(classe: str, rotulo: str, icone: str = "") -> str:
    return f'<span class="gc-selo {classe}"><span aria-hidden="true">{e(icone)}</span>{e(rotulo)}</span>'


def _hora_br(texto: str) -> str:
    try:
        return datetime.fromisoformat(texto).strftime("%d/%m às %H:%M")
    except ValueError:
        return texto


def _corta(texto: str, limite: int) -> str:
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0].rstrip(",;:. ") + "…"


def _leitor(s: vm.Sessao) -> str:
    return {
        "mock": "Leitura determinística",
        "openai": "Leitura com OpenAI",
        "claude": "Leitura com Claude",
    }.get(s.extrator, "Leitor não identificado")


def html_hero(s: vm.Sessao) -> str:
    cartoes, sem_alerta = vm.cartoes_comunicacao(s)
    t = vm.totais(s)
    pessoas = len({a["pessoa_id"] for a in s.adapter.acionamentos})
    altos = sum(c["nivel"] == "alto" for c in cartoes)
    ultima = (
        s.registros[-1].instante.strftime("%d/%m às %H:%M") if s.registros else "Ainda não iniciada"
    )
    estado = (
        "Concluída"
        if s.clock.terminou
        else "Em acompanhamento"
        if s.registros
        else "Pronta para iniciar"
    )
    indicadores = [
        (len(cartoes) + sem_alerta, "Mensagens lidas", "Documentos e pedidos recebidos"),
        (altos, "Mensagens de risco alto", "Revisão humana necessária"),
        (t["retirados"], "Retiradas no cenário", "Execuções confirmadas no replay"),
        (pessoas, "Pessoas acionadas", f"{t['pessoas']} acionamentos confirmados"),
    ]
    numeros = "".join(
        f'<div class="sx-metrica"><dt>{e(nome)}</dt><dd>{n}</dd><span>{e(ajuda)}</span></div>'
        for n, nome, ajuda in indicadores
    )
    return (
        '<header class="sx-hero"><div class="sx-hero-topo"><div class="sx-identidade">'
        '<span class="sx-logo" aria-hidden="true">S</span><div><span class="sx-marca">Sentinela <span class="sx-cp">CP</span></span>'
        '<span class="sx-tagline">Contas a pagar</span></div></div><div class="sx-ambiente">'
        f'<span class="gc-sticker">Replay local</span><span class="sx-leitor">{e(_leitor(s))}</span></div></div>'
        '<div class="sx-cabecalho"><div><h1 class="sx-titulo">Conferência de pagamentos</h1>'
        '<p class="sx-sub">Cada pagamento conferido antes de o dinheiro sair.</p></div>'
        f'<div class="sx-sincronizacao"><span class="sx-status">{estado}</span><span>Última análise: {ultima}</span>'
        f'<span class="sx-relogio-num">Relógio do replay: {s.clock.agora:%d/%m %H:%M}</span></div></div>'
        f'<dl class="sx-metricas">{numeros}</dl></header>'
    )


def _o_que_fazer(c: dict[str, Any]) -> str:
    sinais = set(c.get("sinais") or [])
    if "pedido_de_credencial_ou_arquivo" in sinais:
        return "Não informe senhas ou tokens e não abra links ou anexos. Encaminhe a mensagem à pessoa responsável."
    if "troca_bancaria_solicitada" in sinais:
        return "Confirme a mudança pelo telefone já registrado no cadastro. A liberação depende da aprovação prevista na política."
    if sinais & {"tentativa_de_instrucao", "remetente_nao_confere", "remetente_sem_vinculo"}:
        return "Valide o pedido pelo canal já cadastrado e encaminhe as evidências à pessoa responsável."
    if "extracao_degradada" in sinais:
        return "Confira a mensagem original. A leitura automática não produziu evidência suficiente para concluir a análise."
    return (
        "Revise as evidências com a pessoa responsável e registre a decisão no sistema de origem."
    )


def _alerta(c: dict[str, Any], leitor: str = "Leitura da mensagem") -> str:
    alto = c["nivel"] == "alto"
    selo = _selo(
        "gc-selo--retirado" if alto else "gc-selo--humano",
        "Risco alto" if alto else "Atenção",
        "!" if alto else "•",
    )
    pedido = next((v for k, v in c["ia_leu"] if k == "Pedido"), "Mensagem recebida")
    motivos = "".join(f"<li>{e(m)}</li>" for m in c["regra_decidiu"])
    campos = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in c["ia_leu"])
    trecho = (
        f"<blockquote>“{e(_corta(c['trecho'], 240))}”</blockquote>"
        if c["trecho"]
        else '<p class="sx-leg">Sem trecho extraído com segurança. Consulte a mensagem original.</p>'
    )
    acionados = c.get("pessoas_acionadas", [])
    retirados = c.get("retirados", 0)
    execucao = (
        f"{retirados} pagamento{'s' if retirados != 1 else ''} retirado{'s' if retirados != 1 else ''} do lote."
        if retirados
        else "Nenhuma retirada confirmada para esta mensagem."
    )
    chamado = (
        "; ".join(acionados) if acionados else "Nenhum acionamento confirmado para esta mensagem."
    )
    degradada = c.get("status_extracao") in ("degraded", "DEGRADED", "indisponivel")
    aviso = (
        '<p class="sx-aviso" role="status">Leitura incompleta. Este caso precisa de revisão manual.</p>'
        if degradada
        else ""
    )
    return (
        f'<article class="sx-caso sx-caso--{c["nivel"]}"><header class="sx-caso-topo"><div class="sx-caso-identidade">'
        f'<h3 class="sx-caso-titulo">{e(c.get("fornecedor_nome") or pedido)}</h3><span class="sx-pedido">{e(pedido)}</span></div>{selo}</header>'
        f'<p class="sx-quem">{e(c["remetente"])}<span class="sx-hora">{e(_hora_br(c["data_hora"]))}</span></p>'
        f'<p class="sx-assunto">{e(c["assunto"])}</p>{aviso}'
        f'<div class="sx-duas"><section class="sx-evidencia"><h4>{e(leitor)}</h4>{trecho}'
        '<p class="sx-leg">Trecho da mensagem original, com dados sensíveis mascarados.</p></section>'
        f'<section class="sx-execucao"><h4>O que o agente fez</h4><p class="sx-execucao-principal">{e(execucao)}</p>'
        f'<span class="sx-label">Encaminhamento confirmado</span><p>{e(chamado)}</p></section></div>'
        f'<div class="sx-proximo"><span class="sx-proximo-icone" aria-hidden="true">↳</span><div><h4>Próximo passo humano</h4><p>{e(_o_que_fazer(c))}</p></div></div>'
        f'<details class="sx-mais"><summary>Ver evidências</summary><div class="sx-detalhes"><h4>Regra decidiu</h4><ul class="sx-motivos">{motivos}</ul>'
        f'<h4>Trecho completo de origem</h4><blockquote class="sx-trecho-completo">{e(c["trecho"]) if c["trecho"] else "Nenhum trecho extraído com segurança."}</blockquote>'
        f'<h4>Conteúdo extraído</h4><dl class="sx-campos">{campos}</dl>'
        f'<p class="sx-leg">Referência: {e(c["id"])}</p></div></details></article>'
    )


def html_alertas(s: vm.Sessao) -> str:
    cartoes, sem_alerta = vm.cartoes_comunicacao(s)
    altos = [c for c in cartoes if c["nivel"] == "alto"]
    atencao = [c for c in cartoes if c["nivel"] != "alto"]
    p = [
        (
            '<section class="sx-fila" aria-labelledby="h-fila"><div class="sx-section-head"><div><h2 class="sx-h2" id="h-fila">Fila do analista</h2>'
            f'<p class="sx-leg">{len(altos)} mensagens de risco alto. {sem_alerta} mensagens lidas sem alerta.</p></div></div>'
        )
    ]
    if not altos:
        p.append(
            '<div class="sx-vazio"><strong>Nenhuma mensagem de risco alto nesta análise.</strong><p>Continue a conferência para acompanhar novas evidências.</p></div>'
        )
    for i, c in enumerate(altos):
        pedido = next((v for k, v in c["ia_leu"] if k == "Pedido"), "Mensagem recebida")
        p.append(
            f'<details class="sx-fila-item"{" open" if i == 0 else ""}><summary>'
            f'<span class="sx-fila-identidade"><strong>{e(c["fornecedor_nome"])}</strong><span>{e(pedido)}</span></span>'
            f"<time>{e(_hora_br(c['data_hora']))}</time>{_selo('gc-selo--retirado', 'Risco alto', '!')}"
            f"</summary>{_alerta(c, _leitor(s))}</details>"
        )
    if atencao:
        p.append(
            f'<details class="sx-mais sx-atencao"><summary>{len(atencao)} mensagens para revisão, sem risco alto</summary>{"".join(_alerta(c, _leitor(s)) for c in atencao)}</details>'
        )
    return "".join(p) + "</section>"


def html_lote(s: vm.Sessao, section_id: str = "h-lote", compacto: bool = False) -> str:
    ad = vm.lote_antes_depois(s)
    fornecedor = s.laco.catalogo.por_id(s.cenario.foco)
    nome = (fornecedor.nome_fantasia if fornecedor else None) or s.cenario.foco
    prot = sum(x["protegido"] for x in ad)
    total = len(ad)
    p = [
        f'<section class="sx-lote" aria-labelledby="{section_id}"><div class="sx-section-head"><div><h2 class="sx-h2" id="{section_id}">Lote em acompanhamento</h2><p class="sx-leg">{e(nome)}</p></div>{_selo("gc-selo--neutro", "Fornecedor em foco")}</div>'
    ]
    if not ad:
        return (
            "".join(p)
            + '<p class="sx-vazio">Nenhum título em lote aberto no início deste cenário.</p></section>'
        )
    percentual = int(prot / total * 100)
    p.append(
        f'<div class="sx-lote-numeros"><div><strong>{total - prot}</strong><span>Ainda no lote</span></div><div><strong>{prot}</strong><span>Retirados do lote</span></div></div>'
        f'<div class="sx-lote-barra" role="img" aria-label="{prot} de {total} títulos retirados do lote"><span style="width:{percentual}%"></span></div>'
        f'<p class="sx-leg">{prot} de {total} títulos retirados. Estado consultado após a execução.</p>'
        f'<dl class="sx-ficha"><div><dt>Corte acompanhado</dt><dd>{s.corte_instante:%d/%m às %H:%M}</dd></div>'
        f"<div><dt>Lote</dt><dd>{e(s.corte_lote)}</dd></div></dl>"
    )
    if not compacto:
        linhas = "".join(
            f'<tr><th scope="row">{e(x["titulo"])}</th><td class="num">{e(formatar_brl(x["valor"]))}</td><td>{e(x["forma"].upper())}</td><td>{e(x["lote_antes"])}</td><td>{selo_decisao("retirar_do_lote") if x["protegido"] else _selo("gc-selo--segue", "No lote", "✓")}</td></tr>'
            for x in ad
        )
        p.append(
            '<details class="sx-mais" open><summary>Ver a lista dos títulos</summary><div class="sx-rolagem" tabindex="0" role="region" aria-label="Títulos do fornecedor, rolável"><table class="sx-tabela"><caption class="sx-so-leitor">Antes e depois dos títulos em acompanhamento</caption>'
            f'<thead><tr><th scope="col">Título</th><th scope="col">Valor</th><th scope="col">Forma</th><th scope="col">Lote anterior</th><th scope="col">Estado atual</th></tr></thead><tbody>{linhas}</tbody></table></div></details>'
        )
    return "".join(p) + "</section>"


def _svg_tempo(t: dict[str, Any]) -> str:
    total = max((t["fim"] - t["inicio"]).total_seconds(), 1)

    def x(dt):
        return 12 + 676 * max(0, min(1, (dt - t["inicio"]).total_seconds() / total))

    pontos = "".join(
        f'<circle cx="{x(m["t"]):.1f}" cy="18" r="5" fill="{TOKENS["azul"]}"/>' for m in t["marcos"]
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 36" aria-hidden="true" class="sx-svg"><path d="M12 18H688" stroke="{TOKENS["linha"]}" stroke-width="3"/><path d="M12 18H{x(t["agora"]):.1f}" stroke="{TOKENS["azul"]}" stroke-width="3"/>{pontos}</svg>'


def html_tempo(s: vm.Sessao, svg_embutido: bool = True) -> str:
    t = vm.linha_do_tempo(s)
    svg = _svg_tempo(t)
    figura = (
        svg
        if svg_embutido
        else f'<img class="sx-svg" alt="" aria-hidden="true" src="data:image/svg+xml;charset=utf-8,{quote(svg, safe="")}">'
    )
    marcos = [
        {"t": t["inicio"], "rotulo": "Início da simulação"},
        *t["marcos"],
        {"t": t["fim"], "rotulo": "Fechamento do lote acompanhado"},
    ]
    itens = "".join(
        f'<li><time datetime="{m["t"]:%Y-%m-%dT%H:%M}">{m["t"]:%d/%m %H:%M}</time><span>{e(m["rotulo"])}</span></li>'
        for m in marcos
    )
    return f'<section class="sx-tempo" aria-labelledby="h-tempo"><h2 class="sx-h2" id="h-tempo">Linha do tempo</h2>{figura}<ol class="sx-marcos">{itens}</ol></section>'


def html_resumo(s: vm.Sessao) -> str:
    return '<section class="sx-explicacao"><h2 class="sx-h2">Como o agente trabalha</h2><ol class="sx-processo"><li><strong>Reúne as evidências</strong><span>Pagamento, nota, parcela, pedido de compra e mensagens.</span></li><li><strong>Interpreta o pedido</strong><span>Extrai o conteúdo da mensagem e preserva o trecho de origem.</span></li><li><strong>Aplica a política</strong><span>Regras controlam permissões, valores e execução.</span></li><li><strong>Age ou encaminha</strong><span>Executa dentro da alçada e leva as exceções à pessoa responsável.</span></li></ol></section>'


def html_chamados(s: vm.Sessao) -> str:
    ch = vm.chamados(s)
    grupos: dict[str, list] = {}
    for a in ch["acionamentos"]:
        grupos.setdefault(a["pessoa"], []).append(a)
    itens = []
    for pessoa, lista in grupos.items():
        nome = pessoa.split(" (")[0]
        cargo = lista[0]["cargo"].split(", ", 1)[-1]
        dossies = "".join(
            f'<li><div class="sx-chamado-meta"><time>{a["quando"]:%d/%m às %H:%M}</time><span>{e(a["id"])}</span></div><p>{e(a["dossie"])}</p></li>'
            for a in lista
        )
        itens.append(
            f'<article class="sx-contato"><header><span class="sx-avatar" aria-hidden="true">{e(nome[0])}</span><div><h3>{e(nome)}</h3><p>{e(cargo)}</p></div>{_selo("gc-selo--neutro", str(len(lista)) + " acionamentos")}</header><details class="sx-mais"><summary>Ver dossiês</summary><ul class="sx-dossies">{dossies}</ul></details></article>'
        )
    p = [
        '<section aria-labelledby="h-chamados"><h2 class="sx-h2" id="h-chamados">Quem foi chamado</h2><p class="sx-leg">Acionamentos confirmados no replay. Encaminhar não substitui a aprovação.</p>'
    ]
    p.append(
        f'<div class="sx-contatos">{"".join(itens)}</div>'
        if itens
        else '<div class="sx-vazio"><strong>Nenhum acionamento registrado.</strong><p>Os encaminhamentos aparecerão aqui quando forem executados.</p></div>'
    )
    if ch["solicitacoes"]:
        linhas = "".join(
            f'<tr><td>{a["quando"]:%d/%m %H:%M}</td><td>{e(ROTULOS_ACAO.get(a["acao"], a["acao"]))}</td><td>{e(a["aprovador"])}</td><td class="num">{a["titulos"]}</td></tr>'
            for a in ch["solicitacoes"]
        )
        p.append(
            '<div class="sx-rolagem" tabindex="0" role="region" aria-label="Pedidos de aprovação, rolável"><table class="sx-tabela"><caption>Solicitações de aprovação</caption>'
            f'<thead><tr><th scope="col">Quando</th><th scope="col">Ação</th><th scope="col">Aprovador</th><th scope="col">Títulos</th></tr></thead><tbody>{linhas}</tbody></table></div>'
        )
    return "".join(p) + "</section>"


ROTULOS_ACAO = {
    "retirar_do_lote": "Retirada do lote",
    "corrigir_lancamento": "Correção de lançamento",
    "acionar_pessoa": "Acionamento humano",
    "solicitar_aprovacao": "Solicitação de aprovação",
    "agendar_titulo": "Agendamento",
    "cancelar_titulo": "Cancelamento",
}
RESULTADOS = {
    "ok": ("Confirmada", "gc-selo--segue"),
    "incerta": ("A confirmar", "gc-selo--degradado"),
    "recusada": ("Recusada", "gc-selo--retirado"),
    "erro": ("Falhou", "gc-selo--retirado"),
    "nao_executada": ("Não executada", "gc-selo--neutro"),
    "escalada": ("Revisão manual", "gc-selo--degradado"),
}


def html_acoes(s: vm.Sessao) -> str:
    linhas = list(reversed(vm.execucoes(s)))
    p = [
        '<section aria-labelledby="h-acoes"><h2 class="sx-h2" id="h-acoes">Histórico de ações</h2><p class="sx-leg">Execuções do cenário, da mais recente para a mais antiga. Repetições suprimidas não aparecem como novas ações.</p>'
    ]
    if not linhas:
        return (
            "".join(p)
            + '<div class="sx-vazio"><strong>Nenhuma execução registrada.</strong><p>As ações e seus resultados aparecerão aqui após a conferência.</p></div></section>'
        )
    corpo = []
    for linha in linhas:
        rotulo, classe = RESULTADOS.get(linha["resultado"], (linha["resultado"], "gc-selo--neutro"))
        corpo.append(
            f'<tr><td class="sx-nowrap">{linha["quando"]:%d/%m %H:%M}</td><td>{e(linha["referencia"])}</td><td>{e(ROTULOS_ACAO.get(linha["acao"], linha["acao"]))}</td><td>{_selo(classe, rotulo)}</td></tr>'
        )
    p.append(
        '<div class="sx-rolagem" tabindex="0" role="region" aria-label="Histórico de ações, rolável"><table class="sx-tabela"><caption class="sx-so-leitor">Execuções e resultados confirmados ou pendentes</caption>'
        f'<thead><tr><th scope="col">Quando</th><th scope="col">Referência</th><th scope="col">Ação</th><th scope="col">Resultado</th></tr></thead><tbody>{"".join(corpo)}</tbody></table></div></section>'
    )
    return "".join(p)


def html_rodape() -> str:
    return f'<footer class="sx-rodape"><span>Sentinela CP</span><p>{e(RODAPE)}</p></footer>'


def abas(s: vm.Sessao, svg_embutido: bool = True) -> list[tuple[str, str, str]]:
    cartoes, _ = vm.cartoes_comunicacao(s)
    altos = [c for c in cartoes if c["nivel"] == "alto"]
    titulo, sub = vm.manchete(s)
    if not s.registros:
        principal = '<div class="sx-vazio sx-vazio--inicio"><span class="sx-inicio-icone" aria-hidden="true">✓</span><h3>Pronto para conferir os pagamentos</h3><p>Avance uma hora para analisar os documentos disponíveis. Novas mensagens podem mudar o risco de um pagamento já conferido.</p><span>As ações são executadas apenas no ambiente simulado.</span></div>'
    elif altos:
        principal = (
            '<div class="sx-section-head"><h2 class="sx-h2">Caso em destaque</h2><span class="sx-leg">Risco alto mais recente</span></div>'
            + _alerta(altos[0], _leitor(s))
        )
    else:
        principal = '<div class="sx-vazio"><strong>Nenhuma mensagem de risco alto nesta análise.</strong><p>Consulte o histórico para acompanhar correções e outros encaminhamentos.</p></div>'
    resultado = (
        f'<div class="sx-resultado"><span class="sx-resultado-icone" aria-hidden="true">✓</span><div><p>{e(titulo)}</p><span>{e(sub)}</span></div></div>'
        if s.registros
        else ""
    )
    fim = (
        '<div class="sx-aviso" role="status">Simulação concluída. Consulte os resultados ou use Recomeçar o cenário.</div>'
        if s.clock.terminou
        else ""
    )
    geral = (
        fim
        + resultado
        + '<div class="sx-grade"><div class="sx-col">'
        + principal
        + '</div><aside class="sx-col sx-col--lateral">'
        + html_lote(s, "h-lote-resumo", compacto=True)
        + html_tempo(s, svg_embutido)
        + "</aside></div>"
    )
    geral += f'<details class="sx-mais sx-sobre"><summary>Como o agente trabalha</summary>{html_resumo(s)}</details>'
    conteudo = {
        "geral": geral,
        "fila": html_alertas(s),
        "lote": html_lote(s),
        "chamados": html_chamados(s),
        "registro": html_acoes(s),
    }
    return [(i, rot, conteudo[i]) for i, rot in ABAS]


def pagina(s: vm.Sessao, svg_embutido: bool = True) -> str:
    secoes = "".join(
        f'<div class="sx-secao" data-aba="{i}">{h}</div>' for i, _, h in abas(s, svg_embutido)
    )
    return f'<div class="sx-pagina">{html_hero(s)}{secoes}{html_rodape()}</div>'
