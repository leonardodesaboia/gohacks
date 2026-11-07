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

from sentinela.loop import TipoEvento  # noqa: E402
from sentinela.ui import render  # noqa: E402
from sentinela.ui import viewmodel as vm  # noqa: E402

SAIDA = RAIZ / "site"

VERCEL = {
    "cleanUrls": True,
    "headers": [{
        "source": "/(.*)",
        "headers": [
            {"key": "X-Content-Type-Options", "value": "nosniff"},
            {"key": "Referrer-Policy", "value": "no-referrer"},
            {"key": "X-Frame-Options", "value": "DENY"},
            {"key": "Content-Security-Policy", "value": (
                "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src https://fonts.gstatic.com; img-src data:; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
            )},
        ],
    }],
}

CSS_EXTRA = """
body { margin: 0; background: var(--gc-fundo-2); font-family: var(--gc-font); color: var(--gc-ink); }
.sx-site { max-width: 1180px; margin: 0 auto; padding: 20px clamp(14px, 3vw, 24px) 48px; }
.sx-controles { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 12px; }
.sx-grupo { display: flex; flex-wrap: wrap; gap: 8px; }
.sx-btn { font: inherit; font-weight: 700; min-height: 44px; padding: 0 20px; border-radius: 999px; border: 2px solid var(--gc-azul); background: var(--gc-fundo); color: var(--gc-azul); cursor: pointer;
  transition-property: background-color, color, transform; transition-duration: 150ms; transition-timing-function: ease-out; }
.sx-btn:active { transform: scale(0.98); }
.sx-btn[aria-pressed="true"], .sx-btn--primario { background: var(--gc-azul); color: #FFFFFF; }
.sx-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.sx-desc { color: var(--gc-ink-2); font-size: 14px; margin: 0 0 14px; max-width: 60em; }
"""


def _rodar(chave: str) -> dict:
    s = vm.criar_sessao(chave)
    paginas = [render.pagina(s, svg_embutido=True)]
    pre = None
    while vm.avancar(s) is not None:
        paginas.append(render.pagina(s, svg_embutido=True))
        if pre is None and any(e.tipo is TipoEvento.PRE_FECHAMENTO for e in s.registros[-1].eventos):
            pre = len(paginas) - 1
    c = vm.CENARIOS[chave]
    return {"chave": chave, "curto": c.curto, "descricao": c.descricao, "paginas": paginas, "pre": pre if pre is not None else len(paginas) - 1}


def montar() -> str:
    dados = [_rodar(k) for k in vm.CENARIOS]
    css = (RAIZ / "assets" / "tokens.css").read_text(encoding="utf-8") + CSS_EXTRA
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
  <div class="sx-controles">
    <div class="sx-grupo" id="cenarios" role="group" aria-label="Cenário"></div>
  </div>
  <p class="sx-desc" id="desc"></p>
  <div class="sx-controles">
    <div class="sx-grupo">
      <button type="button" class="sx-btn sx-btn--primario" id="avancar">Avançar 1 hora</button>
      <button type="button" class="sx-btn" id="pre">Até o pré-fechamento</button>
      <button type="button" class="sx-btn" id="reiniciar">Recomeçar o cenário</button>
    </div>
  </div>
  <div id="pagina"></div>
  <p class="sx-so-leitor" role="status" aria-live="polite" id="aviso"></p>
</main>
<script>
const DADOS = {payload};
let atual = 0, tique = 0;
const $ = (id) => document.getElementById(id);
function desenhar(anuncio) {{
  const c = DADOS[atual], ultimo = c.paginas.length - 1;
  $("pagina").innerHTML = c.paginas[tique];
  $("desc").textContent = c.descricao;
  $("avancar").disabled = tique >= ultimo;
  $("pre").disabled = tique >= ultimo;
  [...$("cenarios").children].forEach((b, i) => b.setAttribute("aria-pressed", String(i === atual)));
  if (anuncio) $("aviso").textContent = anuncio + " Tique " + tique + " de " + ultimo + ".";
}}
DADOS.forEach((c, i) => {{
  const b = document.createElement("button");
  b.type = "button"; b.className = "sx-btn"; b.textContent = c.curto;
  b.onclick = () => {{ atual = i; tique = 0; desenhar("Cenário " + c.curto + "."); }};
  $("cenarios").appendChild(b);
}});
$("avancar").onclick = () => {{ tique = Math.min(tique + 1, DADOS[atual].paginas.length - 1); desenhar("Avançou uma hora."); }};
$("pre").onclick = () => {{ tique = Math.max(tique, DADOS[atual].pre); desenhar("Avançou até o pré-fechamento."); }};
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
