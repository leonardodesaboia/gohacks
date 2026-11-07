# Revisão da interface — mesa de contas a pagar

## Direção

O usuário precisa saber qual pagamento exige atenção, o que foi executado e qual decisão continua humana. A interface será uma mesa de trabalho financeira, com dados reais do replay e leitura rápida para a demonstração.

Paleta: azul `#005BAA` para navegação e ação principal; texto `#0B1F33`; texto secundário `#3C566E`; branco `#FFFFFF`; superfície `#F6F9FC`; coral `#F37053` para sinais de risco. Cores de estado aparecem em pequenas áreas, acompanhadas de texto. Figtree para toda a interface, sem tipografia manuscrita; valores usam números tabulares.

Estrutura, alinhada à esquerda:

```text
Marca / Contas a pagar                         Replay / Leitor
Conferência de pagamentos                  Última análise / Corte
Mensagens lidas | Risco alto | Retiradas | Pessoas acionadas
Controles compactos da simulação
Resumo | Fila do analista | Lote | Encaminhamentos | Registro
Caso em destaque (evidência / execução)    Lote em acompanhamento
Próximo passo humano                      Histórico da conferência
```

O destaque visual será o caso e sua evidência, em vez de uma frase promocional grande. A área lateral serve ao prazo do lote e ao estado confirmado dos títulos. No celular, as colunas se empilham e cada campo extraído ocupa toda a largura.

## Princípios aplicados

- `frontend-design`: hierarquia própria de contas a pagar, tipografia consistente e conteúdo operacional.
- `make-interfaces-feel-better`: espaçamento, alinhamento, raios menores, alvos de 44 px, foco e estados de interação.
- `frontend-a11y`: HTML semântico, navegação por teclado, contraste e comunicação textual dos estados.

## Correções funcionais de apresentação

- Remover o pseudo-elemento da legenda que interceptava cliques.
- Diferenciar leitura determinística e leitura com LLM.
- Contar pessoas únicas separadamente de acionamentos.
- Mostrar última análise e próximo passo do relógio, sem sugerir que uma hora ainda não processada já foi conferida.
- Exibir execução confirmada separadamente de decisão ou sugestão.
- Nunca orientar liberação de token, credencial ou anexo suspeito.
- Preservar evidências completas em detalhes expansíveis, com dados sensíveis mascarados.

## Verificação

Validar os dois cenários, navegação, reinício, fim do replay, evidências abertas em 320/390/768/1440 px, versão Streamlit e exportação estática. Conferir o antes/depois do lote e os testes de interface e de ponta a ponta. Não usar correções CSS injetadas pelo teste na validação final.

## Resultado implementado

| Aspecto | Antes | Depois |
| --- | --- | --- |
| Hierarquia | Manchete promocional ocupava a abertura | Cabeçalho operacional, indicadores, controles e conteúdo |
| Navegação | Seções misturadas à narração da demo | Visão geral, fila, lote, encaminhamentos e histórico |
| Fila | Vários cartões longos abertos | Lista de casos expansíveis com remetente, assunto, data e risco |
| Layout | Blocos grandes e repetição de informações | Caso à esquerda; lote e cronologia à direita |
| Cores e forma | Grandes áreas de azul e rosa, selos e botões em pílula | Superfícies neutras, controles compactos e estados com cor discreta |
| Tipografia | Fonte manuscrita e títulos grandes | Uma família, escala consistente e números tabulares |
| Celular | Campos extraídos em colunas de cerca de 45 px | Rótulo e valor empilhados, sem rolagem lateral da página |
| Confiança | Sugestão de pessoa exibida como acionamento | Destinatários e retiradas obtidos das execuções registradas |
| Relógio | Horário seguinte parecia já analisado | Última análise identificada separadamente do relógio do replay |
| Histórico | Decisões tratadas como ações e lista limitada ao último tique | Execuções de todo o cenário com resultado confirmado, pendente ou recusado |

Verificação automatizada inicial: **26 testes de interface e de ponta a ponta passaram**. O fluxo foi exercitado em Chromium nas larguras 320, 390, 768, 1024 e 1440 px, incluindo troca de abas, dois cenários, fim, reinício, evidências e navegação por teclado. A exportação estática foi regenerada. Evidências visuais e dados da verificação ficam em `reports/ux-ui/after-*.png` e `reports/ux-ui/redesign-verification.json`.

Não houve publicação nem integração com sistemas bancários reais nesta revisão. A aplicação permanece identificada como replay local e informa qual leitor processa as mensagens.
