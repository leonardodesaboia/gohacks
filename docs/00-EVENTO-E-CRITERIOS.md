# Evento, critérios e submissão

Fonte: API pública do evento + toolkit oficial (extraído em 2026-11-07).

## Dados

- **GoHacks Talent 2026**, 07 e 08/11/2026, Gogroup Hub, Rua Carolina Sucupira 1368, Fortaleza.
- 26 participantes, 10 finalistas (domingo). **Projeto individual**, prêmio individual: R$5.000 / R$2.000 / R$1.000.
- Só dados sintéticos fornecidos. Proibido dado real da empresa.
- Claude é a ferramenta de IA recomendada (conta paga no notebook do evento).

## O que a GoGroup espera

> Um agente de IA que trabalhe na área **como um colega**: entenda o dia a dia, faça sozinho o que pode e saiba pedir ajuda quando não pode.

Deve: entender a área, agir com autonomia nos sistemas (não só sugerir), levantar a mão com a pessoa certa, poder chamar outros agentes.
Não pode ser: chatbot, RAG puro, automação de um passo, painel que não age.
Bônus: conversar pelos canais que as pessoas usam (Slack, Google Chat, WhatsApp, Telegram) para avisar, pedir aprovação e receber pedidos.

## Critérios

| Critério | Peso | A banca olha |
|---|---|---|
| Modelagem | 40% | fluxo ponta a ponta funciona; orquestração/agentes; autonomia real; **você conferiu o que a IA fez e corrigiu erro** |
| Adaptabilidade | 20% | entendeu tema novo rápido; usou bem os dados fictícios e mostrou como seria com dados reais; mudou de rota quando algo falhou |
| Conceito | 20% | pra quem é; necessidade real; problema+solução claros em poucos minutos |
| Aderência cultural | 20% | assumiu como dono; colaborou com mentores; recebeu feedback e ajustou; energia |

## Cronograma

**Sábado 07/11:** 09:40–12:00 escolha + mão na massa · 13:10–16:30 construção + pitch + submissão · **16:30 fim da submissão** · 16:35–18:10 pré-júri (10 min por pessoa, 3 bancas) · 18:25 Top 10.
**Domingo 08/11 (finalistas):** 09:30–11:30 apresentações (5 min pitch + 5 min sabatina + 1 min troca) · 11:50–12:30 vencedores.

## Submissão (app do evento, até 16h30 de sábado)

| Campo | Limite |
|---|---|
| Nome do projeto | 80 car. |
| Problema resolvido | 600 car. (dor, quem sofre, por que vale) |
| Solução | 800 car. (o que construiu, passo a passo) |
| Como usou IA | 800 car. (ferramentas, agentes, **como conferiu e corrigiu erro da IA**) |
| Impacto esperado | 500 car. (pode ser estimativa) |
| Slides PDF | ≤20 MB, **≤10 slides**: Problema · Solução · Demonstração · Impacto · Próximos passos |
| GitHub | repo público ou com acesso à organização |
| Declaração | só dados fornecidos + leu regulamento |

Opcionais: app publicado (testar em janela anônima), vídeo de demo ≤2 min.

## Toolkit oficial (pontos que viram requisito)

- Entender o problema antes do como; tentar invalidar a própria ideia.
- MVP = menor entrega que valida: fluxo principal funciona (mesmo simples), demonstrável (real ou simulado), resultado mensurável.
- Uso de IA conta na nota: peça pra IA explicar antes de aceitar; teste com **vários casos** dos dados, não um; **anote cada erro da IA e a correção**; guarde prompts que funcionaram; commit a cada avanço.
- Pitch 5 min: abertura 0:15 → dor e usuário-chave 0:50 → fluxo atual 1:20 → solução com IA 2:10 → **demo ao vivo 3:30** → métricas 4:00 → impacto e implantação 5:00. Cortar texto, nunca a demo. **Plano B obrigatório** (print/GIF/vídeo).
- Sabatina: "como funciona" (2 frases + mostrar na tela), "quem usaria" (persona), "o que falta" (ser honesto), "como medir sucesso". Nunca contradizer a banca.

## Padrões técnicos valorizados (starter kit oficial e projetos de outros participantes)

Zero hallucination (saída estruturada Pydantic), human-in-the-loop em decisão crítica, fail-closed com status degradado em vez de falha silenciosa, mascaramento de PII, Python + Streamlit + SQLite + Claude com fallback mock.
