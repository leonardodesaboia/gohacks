# Execução em replay local — Sentinela CP

**REPLAY LOCAL** (dados sintéticos; foto de 02/11/2026 08:00). Janela simulada: 29/10 14:00 → 29/10 17:00 (3 tiques). Extrator: `mock`. Escopo: FP4615.

## Decisões por regra

| Regra | Decisões |
|---|---:|
| R1_fraude_ou_identidade | 61 |
| R7_limpo_sem_lote | 33 |
| R7_limpo_manter | 28 |
| C1_comunicacao_alto_risco | 5 |

## Ações executadas (resultado verificado pelo estado do ambiente quando possível)

| Ação | Resultado | Quantidade |
|---|---|---:|
| acionar_pessoa | duplicada | 61 |
| acionar_pessoa | ok | 6 |
| retirar_do_lote | ok | 28 |

## Estado do ambiente ao final

- Acionamentos de pessoas: {'PS08': 3, 'PS02': 1, 'PS01': 2}
- Solicitações de aprovação (agrupadas por incidente): 0
- Ações persistidas por estado: {'aplicada': 34, 'reservada': 61}
