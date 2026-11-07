# Relatório individual — onde a IA errou e como corrigi

Parte da avaliação (Modelagem 40% e "Como usou IA"): mostrar que conferi o que a IA entregou. **1 linha por erro, no momento em que acontece**, não reconstruído no fim.

| # | Quando | Tarefa | O que a IA fez/afirmou | Por que estava errado | Como corrigi |
|---|---|---|---|---|---|
| 0 | 2026-11-07 | desenho (pré-código) | O desenho usava `consultar_historico_cadastro` e `consultar_extrato` na rota do analista_cp | São ferramentas de `auditor`/`aprovador` (`ferramentas.csv`); o RegistroPapeis bloquearia a própria demo | Rota trocada para `listar_comunicacoes` + `consultar_fornecedor`; histórico/extrato retirados do P0 |
| 1 | 2026-11-07 | desenho (pré-código) | Citou métricas (34 divergentes, R$316k, R$354k, concentração em usuario_07) como resultado | Junção só por número de NF, sem emitente/série/parcela; contracálculo contraditório | Métricas suspensas; protocolo de reprodução em `docs/03-DADOS.md` |
| 2 | 2026-11-07 | desenho (pré-código) | Idempotência marcando só `titulo_id` | Impede reavaliar título que ficou arriscado depois | Três chaves: evento, versão das evidências, ação pretendida |

_(acrescentar linhas a partir daqui durante o build)_

## Prompts que funcionaram

_(colar aqui os melhores prompts, com a tarefa)_

## Casos testados

_(listar títulos/comunicações reais usados nos testes, por `titulo_id` / `comunicacao_id`)_
