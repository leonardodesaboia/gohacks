# Validação do extrator `openai` com a API real

Modelo: `gpt-4o` · mensagens: 19 · gerado em 07/11/2026 14:01. Dados sintéticos do evento.

- Extrações degradadas (falha, saída inválida ou não ancorada): **0/19**
- Mesmo tipo de pedido que o mock: **19/19**
- **Mesmo nível de risco que o mock: 19/19**

| comunicação | caso | tipo (LLM) | tipo (mock) | risco (LLM) | risco (mock) | status |
|---|---|---|---|---|---|---|
| EM571119 | Embalarte: troca de conta + instrução ao robô | troca_dados_bancarios | troca_dados_bancarios | alto | alto | ok |
| EM571116 | 2ª via com beneficiário trocado (outlook.com) | segunda_via_boleto | segunda_via_boleto | alto | alto | ok |
| EM570996 | texto dirigido ao assistente (remetente legítimo) | outro | outro | atencao | atencao | ok |
| EM570977 | falsa Receita (arquivo) | phishing_ou_arquivo_suspeito | phishing_ou_arquivo_suspeito | alto | alto | ok |
| EM570998 | falso cartório (protesto) | ameaca_protesto_ou_cobranca_agressiva | ameaca_protesto_ou_cobranca_agressiva | alto | alto | ok |
| EM571100 | falso Banco Meridiano (token) | solicitacao_seguranca_token | solicitacao_seguranca_token | alto | alto | ok |
| EM570891 | troca de conta de remetente legítimo | troca_dados_bancarios | troca_dados_bancarios | atencao | atencao | ok |
| EM570878 | cobrança rotineira com boleto | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM570948 | 2ª via legítima | segunda_via_boleto | segunda_via_boleto | nenhum | nenhum | ok |
| EM571101 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM570980 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM571078 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM571112 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM570989 |  | cobranca | cobranca | nenhum | nenhum | ok |
| EM570889 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM570946 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM571014 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM571008 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |
| EM570985 |  | envio_boleto_nf | envio_boleto_nf | nenhum | nenhum | ok |

## Leitura

- Todos os casos críticos têm o mesmo nível de risco que o mock.
- Divergências de risco: nenhuma.
