"""Exporta a demo como site estático (site/index.html), pronto para Vercel, Netlify ou GitHub Pages.

Roda o replay de cada cenário uma vez, guarda o HTML de cada tique (o mesmo `render.pagina` do Streamlit) e embute
tudo num único arquivo com CSS inline e um JavaScript mínimo para avançar entre os tiques. Sem servidor, sem chave de API,
sem dados reais além do replay sintético do evento.

Uso:  PYTHONUTF8=1 PYTHONPATH=src python scripts/exportar_site.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sentinela.loop import TipoEvento
from sentinela.ui import render
from sentinela.ui import viewmodel as vm

SAIDA = RAIZ / "site"

VERCEL = {
    "cleanUrls": True,
    "headers": [
        {
            "source": "/(.*)",
            "headers": [
                {"key": "X-Content-Type-Options", "value": "nosniff"},
                {"key": "Referrer-Policy", "value": "no-referrer"},
                {"key": "X-Frame-Options", "value": "DENY"},
                {
                    "key": "Content-Security-Policy",
                    "value": (
                        "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
                        "font-src https://fonts.gstatic.com; img-src data:; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
                    ),
                },
            ],
        }
    ],
}


def _tique(s: vm.Sessao) -> dict:
    return {
        "hero": render.html_hero(s),
        "abas": [h for _, _, h in render.abas(s, svg_embutido=True)],
    }


def _rodar(chave: str) -> dict:
    s = vm.criar_sessao(chave)
    paginas = [_tique(s)]
    pre = None
    while vm.avancar(s) is not None:
        paginas.append(_tique(s))
        if pre is None and any(
            e.tipo is TipoEvento.PRE_FECHAMENTO for e in s.registros[-1].eventos
        ):
            pre = len(paginas) - 1
    c = vm.CENARIOS[chave]
    return {
        "chave": chave,
        "curto": c.curto,
        "descricao": c.descricao,
        "paginas": paginas,
        "tem_pre": pre is not None,
        "pre": pre if pre is not None else len(paginas) - 1,
    }


def montar() -> str:
    dados = [_rodar(k) for k in vm.CENARIOS]
    css = (RAIZ / "assets" / "tokens.css").read_text(encoding="utf-8")
    payload = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinela CP</title>
<meta name="description" content="Replay do agente que confere cada pagamento antes do fechamento do lote. Projeto individual para o GoHacks Talent 2026.">
<meta name="robots" content="noindex">
<style>{css}</style>
</head>
<body>
<main class="sx-site">
  <div id="hero"></div>
  <section class="sx-toolbar" aria-label="Controles da simulação">
    <p class="sx-toolbar-label">Cenário da simulação</p>
    <div class="sx-toolbar-row">
      <div class="sx-grupo" id="cenarios" role="group" aria-label="Cenário"></div>
      <div class="sx-controles">
        <button type="button" class="sx-btn sx-btn--primario" id="avancar">Avançar 1 hora</button>
        <button type="button" class="sx-btn" id="pre">Até o pré-fechamento</button>
        <button type="button" class="sx-btn" id="reiniciar">Recomeçar o cenário</button>
      </div>
    </div>
    <p class="sx-desc" id="desc"></p>
  </section>
  <div class="sx-abas" role="tablist" aria-label="Seções" id="abas"></div>
  <div class="sx-painel sx-pagina" role="tabpanel" id="painel" tabindex="0"></div>
  {render.html_rodape()}
  <p class="sx-so-leitor" role="status" aria-live="polite" id="aviso"></p>
</main>
<script>
const DADOS = {payload};
const ROTULOS = {json.dumps([rot for _, rot in render.ABAS], ensure_ascii=False)};
let atual = 0, tique = 0, aba = 0;
const $ = (id) => document.getElementById(id);
ROTULOS.forEach((rot, i) => {{
  const b = document.createElement("button");
  b.type = "button"; b.className = "sx-aba"; b.id = "aba-" + i; b.setAttribute("role", "tab"); b.setAttribute("aria-controls", "painel"); b.textContent = rot;
  b.onclick = () => {{ aba = i; desenhar(""); }};
  b.onkeydown = (ev) => {{
    const d = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
    if (d) {{ aba = (i + d + ROTULOS.length) % ROTULOS.length; }}
    else if (ev.key === "Home") {{ aba = 0; }} else if (ev.key === "End") {{ aba = ROTULOS.length - 1; }} else {{ return; }}
    desenhar(""); $("aba-" + aba).focus(); ev.preventDefault();
  }};
  $("abas").appendChild(b);
}});
function desenhar(anuncio) {{
  const c = DADOS[atual], ultimo = c.paginas.length - 1;
  $("hero").innerHTML = c.paginas[tique].hero;
  $("painel").innerHTML = c.paginas[tique].abas[aba];
  $("painel").setAttribute("aria-labelledby", "aba-" + aba);
  [...$("abas").children].forEach((b, i) => {{ b.setAttribute("aria-selected", String(i === aba)); b.tabIndex = i === aba ? 0 : -1; }});
  $("desc").textContent = c.descricao;
  $("avancar").disabled = tique >= ultimo;
  $("pre").disabled = tique >= ultimo;
  $("pre").textContent = c.tem_pre ? "Até o pré-fechamento" : "Concluir cenário";
  [...$("cenarios").children].forEach((b, i) => b.setAttribute("aria-pressed", String(i === atual)));
  if (document.activeElement && document.activeElement.disabled) $("painel").focus();
  if (anuncio) {{ $("aviso").textContent = ""; setTimeout(() => {{ $("aviso").textContent = anuncio + " " + ($("hero").querySelector("h1") || {{}}).textContent; }}, 50); }}
}}
DADOS.forEach((c, i) => {{
  const b = document.createElement("button");
  b.type = "button"; b.className = "sx-btn"; b.textContent = c.curto;
  b.onclick = () => {{ atual = i; tique = 0; desenhar("Cenário " + c.curto + "."); }};
  $("cenarios").appendChild(b);
}});
$("avancar").onclick = () => {{ tique = Math.min(tique + 1, DADOS[atual].paginas.length - 1); desenhar("Avançou uma hora."); }};
$("pre").onclick = () => {{ tique = Math.max(tique, DADOS[atual].pre); desenhar(DADOS[atual].tem_pre ? "Avançou até o pré-fechamento." : "Simulação concluída."); }};
$("reiniciar").onclick = () => {{ tique = 0; desenhar("Cenário recomeçado."); }};
desenhar("");
</script>
</body>
</html>
"""


def main() -> None:
    SAIDA.mkdir(exist_ok=True)
    pagina = montar()
    (SAIDA / "index.html").write_text(pagina, encoding="utf-8")
    (SAIDA / "vercel.json").write_text(json.dumps(VERCEL, indent=2), encoding="utf-8")
    print(f"site/index.html: {len(pagina.encode('utf-8')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
