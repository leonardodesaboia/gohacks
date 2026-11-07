# Demo, pitch e submissão

Base: rascunho completo no vault (`03 Pitch/(C) Pitch - Sentinela CP - Rascunho 01.md`). Aqui, o que o código precisa suportar e os campos de submissão.

**Mensagem central:** Sentinela CP acompanha os pagamentos até o fechamento do lote, executa o que está dentro da sua alçada e chama a pessoa certa quando encontra risco. Capa: **Cada pagamento conferido antes de o dinheiro sair.**

**Persona:** Alex, analista de contas a pagar do Gogroup (fictícia). Nunca "Marcos" (é o tesoureiro).

## Regra de honestidade da demo

- Dizer em tela se é **integração operacional** ou **replay local** (selo na UI). A API pública do evento não prova integração com as ferramentas.
- Só falar no passado ("o título foi retirado do lote") depois de **consultar o estado** e mostrar o antes/depois. Se não executou, dizer "esta é a ação proposta".
- Não apresentar domínio divergente como prova de fraude; é sinal de risco.
- Nenhuma métrica não reproduzida (ver `docs/03-DADOS.md`). Sem número, falar do critério de avaliação (os três custos do placar).

## Os 3 cenários (precisam rodar de ponta a ponta antes de ensaiar)

1. **Caso limpo.** Título que bate com NF/duplicata/OC, ≤R$5k, sem sinal de risco → agenda sozinho; log em segundos. Escolher um título real com `status=aberto` e vínculo único.
2. **Erro operacional validado.** Título com **uma** divergência comprovável (ex.: valor exatamente 10× a duplicata da sua parcela, ou nº de NF digitado errado) dentro da alçada → `corrigir_lancamento` com evidência e log. **Só usar caso aprovado pela reprodução de T4** (match único).
3. **Comunicação suspeita (estrela).** Pedido de troca de conta bancária por remetente divergente do cadastro (candidato: Embalarte, EM571119) → IA lê a thread e extrai conta e trechos → regras comparam → título do fornecedor **retirado do lote antes do corte** → **PS01 (Renata Paiva)** acionada com dossiê. Mostrar o trecho hostil dirigido ao "robô" e o agente tratando-o como **dado, não instrução**; mostrar que a alegação de confirmação não conta.

Cenários auxiliares (para ensaio e sabatina, não precisam estar no pitch): mensagem legítima de cobrança (sem acionamento), ambiguidade (escala com limitação registrada), fracionamento (soma por fornecedor+NF+dia).

## Roteiro 5 min (marcas de ensaio)

| Tempo | Conteúdo |
|---|---|
| 0:00 | Abertura: às 10h o lote vai ao banco; dentro dele pode estar um zero a mais ou uma conta de golpista. O Sentinela age nessa janela. |
| 0:20 | Alex: títulos, NFs, OCs e mensagens de fornecedores em sistemas separados, ~131 fornecedores, 2 bancos (10h e 14h). |
| 0:55 | Conferir na chegada não basta: uma mensagem posterior muda o risco de um pagamento já agendado. Acompanhar até o corte e revalidar. |
| 1:20 | Solução: papel analista_cp com as permissões desse papel; **a IA lê a linguagem, as regras controlam o que executa**. |
| 2:10 | **Demo (90 s)**: situar ambiente → comunicação e leitura da IA → risco e decisão → ação e acionamento → pré-fechamento. |
| 3:40 | Métrica: os três custos do placar; resultado medido com e sem agente **se reproduzido**. |
| 4:10 | Implantação: um lote, permissões limitadas, acompanhar decisões antes de ampliar autonomia. Aprendizado: duas consultas previstas eram de outros papéis; corrigimos o desenho. Deixamos fora números não reproduzidos. |
| 5:00 | Fecho. |

Se faltar tempo: cortar arquitetura e implantação; **preservar a demo** e a explicação de onde a IA trabalhou. Plano B: gravação/GIF da execução validada, identificando se foi sandbox ou replay.

## Slides (7, limite 10)

1 Abertura (horário do lote) · 2 Problema (título, NF, OC, comunicação → lote) · 3 Solução (reunir evidências → conferir → agir ou escalar → revalidar) · 4 Demo (pedido de troca → evidências → ação preventiva, antes/depois) · 5 Impacto (os três custos; placar se medido) · 6 Implantação (conector → regras → execução auditável) · 7 Fechamento (agir com evidência, respeitar a alçada, chamar a pessoa certa; link do repo).

Visual dos slides: usar `docs/06-DESIGN-SYSTEM.md` (azul Gocase como base, color blocking, máx. 3 cores por slide).

## Sabatina — respostas curtas

- **"Isso não é só comparar dois domínios?"** Comparar domínio é uma regra. A IA interpreta a thread, identifica o pedido de alteração, extrai os dados e aponta os trechos que sustentam o dossiê. As regras usam essas evidências para controlar a ação.
- **"Por que eventos?"** Um pagamento já conferido pode ficar arriscado depois de uma nova mensagem. Precisa ser reavaliado antes do lote fechar; pode ser polling simples, sem infraestrutura complexa.
- **"E se a IA errar?"** Saída estruturada com evidência de origem; limites e permissões em código; faltou dado ou houve ambiguidade, vai para revisão. A extração nunca autoriza pagamento sozinha. Mostrar `relatorio.md` com erros reais corrigidos.
- **"Quem aprova?"** A política define a instância por valor e tipo de risco. Para suspeita de fraude: PS01. Acionar não substitui a aprovação para liberar.
- **"Como evita travar tudo?"** O placar pune também atraso e acionamento desnecessário (R$60). Casos regulares seguem; alertas do mesmo incidente são agrupados.
- **"Qual o impacto?"** Sem medição: "ainda não apresentamos economia validada; temos o critério e estamos reproduzindo o mesmo cenário com e sem o agente." Com medição: número + execução que o sustenta.
- **"O que significa agnóstico?"** Conectores traduzem cada fonte para um formato interno; as regras seguem explícitas. Trocar de sistema exige adaptar e testar o conector.
- **"O que falta para usar na empresa?"** Validar integrações e permissões reais, testar falhas com a equipe, operar acompanhado antes de ampliar autonomia.
- **"Por que o analista não consulta o histórico de cadastro?"** Porque a ferramenta é de auditor/aprovador; o agente respeita o papel. Sem acesso, a confirmação é "não verificável por ele", e o caso sobe para quem pode verificar.

## Campos de submissão (preencher ao final; limites em `docs/00-EVENTO-E-CRITERIOS.md`)

- **Nome:** Sentinela CP — cada pagamento conferido antes de o dinheiro sair
- **Problema (≤600):** _a preencher com persona Alex e números oficiais do ambiente (131 fornecedores, 2 bancos, alçadas)_
- **Solução (≤800):** _resumo do fluxo: evidências → IA lê comunicações → regras → decisão → ação ou dossiê → revalidação antes do corte_
- **Como usou IA (≤800):** _Claude como extrator estruturado (Pydantic) e como assistente de código; motor de decisão determinístico separado do LLM; testes com vários casos reais; erros da IA e correções em `relatorio.md`_ **(citar 2–3 erros reais)**
- **Impacto (≤500):** _critério de placar em R$; número só se reproduzido_
- **Slides PDF, GitHub, declaração:** pendentes.
