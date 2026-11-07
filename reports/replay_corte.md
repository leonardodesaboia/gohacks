# Execução em replay local — Sentinela CP

**REPLAY LOCAL** (dados sintéticos; foto de 02/11/2026 08:00). Janela simulada: 02/11 08:00 → 03/11 10:00 (26 tiques). Extrator: `mock`. Escopo: todos os fornecedores.

## Decisões por regra

| Regra | Decisões |
|---|---:|
| R7_limpo_sem_lote | 1391 |
| R7_limpo_manter | 962 |
| R4_troca_bancaria_recente | 139 |
| R1_fraude_ou_identidade | 61 |
| R6_boleto_diverge_da_duplicata | 12 |
| R6_valor_acima_da_alcada | 9 |
| R6_corrigir_valor | 9 |
| C1_comunicacao_alto_risco | 5 |
| R6_corrigir_vencimento | 2 |
| R5_divergencia_oc_nf | 2 |

## Ações executadas (resultado verificado pelo estado do ambiente quando possível)

| Ação | Resultado | Quantidade |
|---|---|---:|
| acionar_pessoa | duplicada | 65 |
| acionar_pessoa | ok | 16 |
| corrigir_lancamento | ok | 11 |
| retirar_do_lote | ok | 31 |
| solicitar_aprovacao | ok | 14 |

## Estado do ambiente ao final

- Acionamentos de pessoas: {'PS08': 3, 'PS02': 1, 'PS01': 4, 'PS05': 4, 'PS04': 4}
- Solicitações de aprovação (agrupadas por incidente): 14
- Ações persistidas por estado: {'aplicada': 72, 'reservada': 65}
