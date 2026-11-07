# Design system — Sentinela CP (identidade Gocase)

Aplicação da linguagem visual da **Gocase** (marca do Gogroup, host do evento) à UI de narração e aos slides.

> **Revisão de 07/11/2026:** a pedido do usuário, a aplicação passou a priorizar a aparência de um sistema operacional de contas a pagar. A direção vigente da interface está em [07-REVISAO-UX-UI.md](07-REVISAO-UX-UI.md): superfícies claras, cabeçalho compacto, uma única família tipográfica, fila organizada e cores discretas de estado. As referências de marca abaixo continuam como origem da paleta e referência para os slides; os antigos blocos grandes e a tipografia manuscrita não são mais usados na aplicação.

> **Ressalva de precisão:** não existe design system público completo da Gogroup. A paleta e a tipografia abaixo vêm do brandbook e playbook da Gocase de 2022 (materiais de terceiros e da marca). São cores históricas documentadas, **não** confirmação da paleta institucional atual da holding. O rosa-claro aparece como `#FFD6DC` (playbook) e `#FBD4DA` (brandbook); usamos `#FFD6DC`. Tokens, neutros derivados e mapeamento semântico abaixo são **proposta deste projeto**, não componentes oficiais. Não usar logotipo da Gocase/Gogroup.

## Direção

Criatividade, personalidade, autenticidade, autoexpressão. Formas geométricas simples, cores marcantes, **color blocking**, tipografia de forte presença, tom divertido porém organizado. Para um produto de controle financeiro: mantemos a energia da marca nos **blocos de cor e nos títulos**, mas a **leitura de dados é sóbria** (fundo claro, texto escuro, cor só onde informa). Regra de ouro: a cor da marca acompanha **estado** (decisão, risco), não decoração.

## Paleta

| Token | Nome | Hex | Uso |
|---|---|---|---|
| `--gc-azul` | Azul | `#005BAA` | cor principal: cabeçalho, botão primário, links, títulos de seção |
| `--gc-coral` | Coral | `#F37053` | **risco / ação preventiva** (retirado do lote), destaques de alerta |
| `--gc-rosa` | Rosa | `#EC3FAA` | acento da marca: selos, stickers, números em destaque, só em texto grande |
| `--gc-turquesa` | Turquesa | `#94D6DA` | **seguiu sozinho / OK**, superfícies calmas |
| `--gc-lima` | Verde-lima | `#E9ED9A` | **corrigido automaticamente**, destaque suave |
| `--gc-rosa-claro` | Rosa claro | `#FFD6DC` | **escalado para humano**, fundo de aviso |

Neutros derivados (não são da marca): `--gc-ink #0B1F33` (texto), `--gc-ink-2 #3C566E` (texto secundário), `--gc-linha #D9E3EC` (bordas), `--gc-fundo #FFFFFF`, `--gc-fundo-2 #F6F9FC` (superfície), `--gc-azul-900 #003D73` (hover/pressed).

Regras do playbook adotadas: **no máximo 3 cores de marca por composição**; contraste legível; degradês só entre duas cores da própria paleta (ex.: azul→turquesa no cabeçalho).

## Contraste (obrigatório)

- Texto sobre **azul**: branco `#FFFFFF` (≈7:1, ok).
- Texto sobre **coral, rosa, turquesa, lima, rosa-claro**: sempre `--gc-ink`. **Nunca branco sobre coral/rosa** (≈3:1, reprova). Coral e rosa como **cor de texto** só em corpo ≥24px ou negrito ≥19px.
- Estado nunca depende só de cor: sempre ícone + rótulo textual.
- Foco visível: contorno 3px `--gc-azul` com offset 2px.

## Mapeamento semântico (decisão do agente → visual)

| Decisão | Rótulo na UI | Fundo | Texto | Ícone |
|---|---|---|---|---|
| Segue sozinho (`agendar_titulo`) | SEGUE SOZINHO | turquesa | ink | ✓ |
| Corrigido (`corrigir_lancamento`) | CORRIGIDO | lima | ink | ✎ |
| Retirado do lote (`retirar_do_lote`) | RETIRADO DO LOTE | coral | ink | ⏸ |
| Escalado a humano (`acionar_pessoa`/`solicitar_aprovacao`) | CHAMEI ALGUÉM | rosa-claro com borda rosa | ink | ✋ |
| Cancelado (`cancelar_titulo`) | CANCELADO | ink-2 claro (`#E4EBF2`) | ink | ✕ |
| Degradado (IA falhou, fail-closed) | REVISÃO MANUAL | branco com borda coral tracejada | ink | ⚠ |

**Quem fez o quê** (crítico para a banca): em todo card de decisão, duas linhas fixas — `IA leu:` (dados extraídos + trecho citado) e `Regra decidiu:` (nome da regra + alçada). Nunca fundir.

## Tipografia

- **Principal documentada:** Averta (títulos e texto). É fonte comercial; **não embutir**. Fallback livre equivalente: **Figtree** (Google Fonts) com `system-ui` de reserva.
- **Secundária documentada:** Felt That (manuscrita, destaques expressivos). Fallback livre: **Caveat**. Uso restrito a 1 frase de destaque por tela (ex.: "Cada pagamento conferido antes de o dinheiro sair."), nunca em dados.
- Escala: título de tela 40/48 peso 800 · seção 24/32 peso 700 · corpo 16/24 peso 400 · rótulo/legenda 13/18 peso 600 caixa alta com tracking 0.04em · números de valor em `font-variant-numeric: tabular-nums`, peso 700.
- Valores em R$ sempre com separador pt-BR (`R$ 1.234,56`).

## Forma e componentes

- Raio: 16px cartões, 999px selos/botões. Sombra suave `0 2px 0 rgba(11,31,51,.06)`; sem sombras pesadas.
- Espaçamento base 8px (4/8/12/16/24/32/48). Gutter lateral mínimo 16px em telas estreitas.
- **Color blocking**: cada seção principal pode ter um bloco sólido de cor da marca (cabeçalho azul, painel de risco coral). Formas geométricas simples (círculo, quadrado, triângulo) só como ornamento de cabeçalho/capa, sem competir com dados.
- **Sticker** (selo inclinado -3°, rosa, texto ink): usar para "REPLAY LOCAL" / "INTEGRAÇÃO", "NOVO" em evidência recém-chegada. Um por tela.
- **Botão primário:** azul, texto branco, pílula; secundário: contorno azul 2px, texto azul; perigo/ação irreversível: contorno coral + texto ink.
- **Tabela:** cabeçalho `--gc-fundo-2`, linhas com borda `--gc-linha`, valores à direita, coluna de estado com o selo semântico.
- **Contagem regressiva do lote:** bloco azul com número grande; vira coral quando faltam < 30 min. Só exibição.
- **Mascaramento:** CNPJ `85.***.***/0001-00`, conta `****-7`, Pix `****…c83bc`. Nunca mostrar valores completos.

## Estados e movimento

- Vazio, carregando, erro e `DEGRADED` têm tela própria com texto claro (nunca spinner infinito).
- Movimento curto (150–200ms), respeitar `prefers-reduced-motion`.
- Tema escuro: **não** é requisito; manter fundo claro (projeção em telão). Se implementar, trocar `--gc-fundo` por `#0B1F33` e inverter ink, mantendo as cores de estado.

## Slides

Fundo branco ou azul (`#005BAA`) em abertura/fechamento; título peso 800; **máx. 3 cores de marca por slide**; um bloco de cor por slide; mesma semântica de estado dos cards. Fontes do PDF: Figtree.

## Implementação

Tokens em `assets/tokens.css` (variáveis CSS) e `.streamlit/config.toml` (tema Streamlit). `src/sentinela/ui/theme.py` expõe `TOKENS`, `COR_DECISAO`, `injetar_css()` e `selo_decisao()`. **Nenhuma cor literal fora desses arquivos.**
