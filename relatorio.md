# Relatório individual — onde a IA errou e como corrigi

Parte da avaliação (Modelagem 40% e "Como usou IA"): mostrar que conferi o que a IA entregou. **1 linha por erro, no momento em que acontece**, não reconstruído no fim.

| # | Quando | Tarefa | O que a IA fez/afirmou | Por que estava errado | Como corrigi |
|---|---|---|---|---|---|
| 0 | 2026-11-07 | desenho (pré-código) | O desenho usava `consultar_historico_cadastro` e `consultar_extrato` na rota do analista_cp | São ferramentas de `auditor`/`aprovador` (`ferramentas.csv`); o RegistroPapeis bloquearia a própria demo | Rota trocada para `listar_comunicacoes` + `consultar_fornecedor`; histórico/extrato retirados do P0 |
| 1 | 2026-11-07 | desenho (pré-código) | Citou métricas (34 divergentes, R$316k, R$354k, concentração em usuario_07) como resultado | Junção só por número de NF, sem emitente/série/parcela; contracálculo contraditório | Métricas suspensas; protocolo de reprodução em `docs/03-DADOS.md` |
| 2 | 2026-11-07 | desenho (pré-código) | Idempotência marcando só `titulo_id` | Impede reavaliar título que ficou arriscado depois | Três chaves: evento, versão das evidências, ação pretendida |

| 3 | 2026-11-07 | T0 | `tests/test_dados.py` importou o script por `importlib` sem registrar o módulo | `@dataclass` do script quebrou na coleta (`sys.modules` sem o módulo) | Registrei `sys.modules["validar_dados"]` antes do `exec_module`; 36 testes passam |

| 4 | 2026-11-07 | T2 (plano) | O plano da T2 assumia que o relógio libera comunicações/títulos "futuros" ao avançar | Os CSVs são foto de 02/11 08:00; nada chega depois (última comunicação 07:24, último título 30/10) | Replay retroativo: relógio inicia antes e o adaptador reconstrói status e cadastro no instante; documentado em `docs/03-DADOS.md` |
| 5 | 2026-11-07 | T2 (plano) | O plano mandava usar os feriados de `feriados_bancarios.csv` sem distinguir abrangência | Estaduais/municipais têm `sem_expediente_bancario=sim` mas `afeta_remessa=não` (compensação nacional funciona); tratar todas as linhas como não úteis erraria dias de remessa | `clock.py` só considera `sem_expediente_bancario=sim` **e** `afeta_remessa=sim`; teste com São José (CE) |

| 6 | 2026-11-07 | T3 | Deixei no `vincular_comunicacao` uma expressão morta e confusa (`... if False else ...`) ao extrair CNPJs do texto | Código ilegível que parecia fazer duas coisas; pegaria na revisão, mas não deve entrar | Reescrito como `{raiz_cnpj(m.group(0)) for m in ...}` antes de rodar |
| 7 | 2026-11-07 | T3 (plano) | O prompt da T3 pedia "5 casos ambíguos" de fornecedor | Medido: não existe ambiguidade de fornecedor (raízes únicas, OCs 1:1); inventar casos seria falso | Relatório declara 0 ambíguos e redireciona a ambiguidade real (NF) para a T4; os casos não-ok reais são 3 títulos divergentes |

_(acrescentar linhas a partir daqui durante o build)_

## Prompts que funcionaram

_(colar aqui os melhores prompts, com a tarefa)_

## Casos testados

_(listar títulos/comunicações reais usados nos testes, por `titulo_id` / `comunicacao_id`)_
