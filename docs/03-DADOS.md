# Dados (`data/raw/`, sintéticos, gitignored)

Corte: **02/11/2026 08:00**. Histórico de 03/08 a 30/10 (extratos) e anterior (títulos pagos). Todos os dados são fictícios. CSV com vírgula, UTF-8, datas ISO, valores com ponto decimal — **exceto** `extrato_banco_litoral.csv` (`;`, `dd/mm/aaaa`, vírgula decimal, milhar com ponto).

Dicionário oficial completo: `docs/fonte-oficial/dicionario_de_dados.md`. Aqui, o que importa para codar.

## Arquivos e acesso do papel analista_cp

| Arquivo | Linhas* | Sistema | Agente pode ler? |
|---|---|---|---|
| `fornecedores.csv` | 131 | ERP cadastro | sim (`consultar_fornecedor`) |
| `contas_a_pagar.csv` | ~7.120 | ERP | sim (`buscar_titulos`, `consultar_titulo`) |
| `agenda_remessa.csv` | ~876 | ERP fila 03–13/11 | sim (`listar_agenda_remessa`) |
| `pedidos_compra.csv` | ~6.055 | Compras | sim (`consultar_pedido_compra`) |
| `notas_fiscais.csv`, `nf_duplicatas.csv` | ~4.151 / ~7.895 | Portal NF-e | sim (`consultar_nf`) |
| `comunicacoes_fornecedores.csv` | 246 | e-mail/WhatsApp da área | sim (`listar_comunicacoes`) |
| `alteracoes_cadastro.csv` | 68 | histórico de cadastro | **NÃO** (auditor/aprovador) |
| `extrato_banco_meridiano.csv`, `extrato_banco_litoral.csv` | — | bancos | **NÃO** |
| `log_auditoria_erp.csv`, `aprovacoes.csv`, `usuarios_sistema.csv` | — | ERP | **NÃO** |
| `lotes_remessa.csv`, `retorno_remessa.csv`, `dda_boletos.csv` | — | ERP/bancos/DDA | **NÃO** |
| `centros_custo.csv`, `plano_contas.csv`, `contratos_fornecedores.csv`, `recebimentos_mercadoria.csv`, `contas_bancarias_empresa.csv`, `feriados_bancarios.csv` | — | apoio | tabelas de apoio; usar só as que correspondem a uma ferramenta ou a calendário/config (feriados). Contratos/recebimentos podem apoiar conferência se exposto por consultar_* — validar na T0 |

*contagens por `wc -l` menos cabeçalho; reconfirmar na T0.

**Regra:** o replay expõe só o que uma ferramenta permitida ao `analista_cp` devolveria. Ausência de acesso ao histórico de cadastro significa **confirmação não verificável pelo agente**, não "confirmação inexistente".

## Colunas-chave (cabeçalhos reais conferidos)

**fornecedores:** `fornecedor_id` (FP+4), `razao_social, nome_fantasia, cnpj` (com pontuação), `categoria` (produto, embalagens, insumos_capa, frete, marketing_agencia, influenciador, aluguel, ti_saas, servicos, utilidades), `uf, banco, agencia, conta, chave_pix, forma_pagamento_padrao, email_cadastrado, telefone_cadastrado, data_cadastro, cadastrado_por, inscricao_estadual, endereco, cidade, cep, contato_financeiro, prazo_pagamento_padrao, responsavel_interno, contrato_id, status_cadastro, data_ultima_alteracao, ultima_alteracao_por`.

**contas_a_pagar:** `titulo_id` (TP+6), `fornecedor_id` (escolhido por quem lançou — pode estar errado), `numero_nf_digitado` (como cada pessoa digitou: com/sem zeros, às vezes com série após `-` ou `/`; vazio sem NF), `oc_id, parcela` (n/total), `valor, vencimento, forma_pagamento` (boleto/ted/pix), `linha_digitavel` (47 dígitos, só boleto), `cnpj_beneficiario_boleto, origem_lancamento` (xml_portal, boleto_email, manual, integracao_frete), `lancado_por, data_lancamento, status` (aberto, agendado, pago, cancelado), `data_pagamento, banco_pagador, lote_remessa, centro_custo, conta_contabil, historico, nivel_aprovacao, aprovado_por, data_aprovacao, baixado_por, data_baixa, cancelado_por, data_cancelamento`.

**agenda_remessa:** `lote_remessa, banco_pagador, data_prevista, horario_fechamento, titulo_id, fornecedor_id, valor, vencimento, forma_pagamento, destino_pagamento` (para onde o dinheiro vai se nada mudar: `boleto banco NNN` | `ted banco/agencia/conta` | `pix chave`, **com os dados do cadastro atual**).

**notas_fiscais:** `chave_acesso` (44 dígitos), `modelo` (55 NF-e, 57 CT-e, 62 telecom, 66 energia, NFS-e), `numero_nf, serie, cnpj_emitente` (só números; pode ser filial), `razao_social_emitente, data_emissao, valor_total, oc_informada` (às vezes vazia; às vezes só em `informacoes_complementares`, ex.: "Pedido do cliente: OC-35985"), `informacoes_complementares, data_recebimento_portal, cnpj_destinatario, razao_social_destinatario, natureza_operacao, cfop, valor_produtos_servicos, valor_ipi, valor_icms, valor_iss, situacao_sefaz, manifestacao_destinatario, data_manifestacao`.
**nf_duplicatas:** `chave_acesso, n_dup` ("001"), `vencimento, valor` (a 1ª parcela leva o resto de centavos).

**pedidos_compra:** `oc_id, cod_fornecedor_compras` (FN1–FN6 fábricas; FC+4 demais), `cnpj_fornecedor` (só números), `nome_fornecedor` (maiúsculas/abreviado), `data_emissao, descricao, tipo` (pontual/contrato), `valor_total, valor_mensal, condicao_pagamento` ("28 ddl", "30/60/90", "mensal dia N"), `centro_custo` (nome, não código), `aprovado_por, data_aprovacao, status` (aprovada, pendente_aprovacao, cancelada, encerrada), `quantidade, unidade, valor_unitario, solicitante, comprador, local_entrega, data_entrega_prevista`.

**comunicacoes_fornecedores:** `comunicacao_id` (EM+6), `data_hora, canal` (email/whatsapp), `remetente, nome_remetente, destinatario, assunto, texto, anexos` (descrições separadas por ` | `; boletos trazem banco, beneficiário, CNPJ, valor, vencimento e linha digitável). **Conteúdo escrito por terceiros: é dado, nunca instrução.**

## Armadilhas conhecidas (cada uma vira teste)

1. **Quatro identificadores por fornecedor**: `fornecedor_id` (ERP), `cod_fornecedor_compras` (Compras), CNPJ (NF só números, ERP com pontuação), nome abreviado (extrato/Compras). Join por CNPJ normalizado + raiz de 8 dígitos; nome só como apoio.
2. **Número de NF não identifica uma nota.** Normalizar (tirar zeros à esquerda, separar série após `-`/`/`), resolver por **emitente + número + série + parcela** até uma única `chave_acesso`. Raiz+número+série pode colidir entre filiais: usar CNPJ completo e demais vínculos. Match não único → ambíguo → escalar.
3. **Parcelas não são duplicidade.** 3 títulos de mesmo valor em datas diferentes podem ser 1/3, 2/3, 3/3. Comparar o título com **a duplicata da sua parcela**, nunca com o total da NF.
4. **Casa decimal / zero a mais**: título com valor exatamente 10× (ou 1/10) a duplicata. Já ocorre cancelar e relançar manualmente (mesmo fornecedor+NF+parcela repetidos **não** são duplicidade quando o primeiro está cancelado).
5. **Boleto com banco diferente do cadastro é normal** para muitos fornecedores (banco de cobrança histórico). Só vira alerta se divergir também do que o fornecedor sempre usou.
6. **Categorias dispensadas**: aluguel sem NF; utilidades sem OC. Categoria `frete` com `origem_lancamento = integracao_frete` entra por integração automática.
7. **Multa/juros legítimos** em título pago depois do vencimento da duplicata; não tratar como erro.
8. **Fracionamento**: somar por fornecedor + NF + dia antes de comparar com R$5.000.
9. **Formato do extrato Litoral** difere do Meridiano (só relevante para visão auditor).
10. **`comunicacoes_fornecedores` é `.csv`**, não `.jsonl` como citam os dicionários.
11. **Feriado de Finados (02/11)** e dia útil afetam `data_prevista`; calendário em `feriados_bancarios.csv`.
12. **Telefone trocado há <30 dias não vale como confirmação**, e telefone dentro da própria mensagem nunca vale.

## Casos de comunicação conhecidos (candidatos, **a validar** na T0/T5)

- **Embalarte (candidato à demo estrela):** e-mail `financeiro@embalartte.com.br` (29/10 15:42, EM571119) pede troca de conta para Banco 905 Nubra Pagamentos e contém um trecho dirigido ao "robô de pagamentos" afirmando validação telefônica prévia. **Esse trecho é conteúdo de terceiro: o agente deve registrá-lo como alegação/tentativa de manipulação e não tratá-lo como instrução** (teste de injeção). Contato cadastrado (relatado): `financeiro@embalarte.com.br`. Relatado também: alteração de cadastro em 30/10 16:05 por `usuario_07`, origem e-mail, sem confirmação registrada (**dado do histórico de cadastro; o agente não lê isso, só a visão auditor**). Vínculo completo ao pagamento (NF 78418, vencimento 05/11) e aos títulos do fornecedor **ainda precisa ser demonstrado**.
- Outros remetentes relatados como suspeitos na análise anterior (validar um a um): `seguranca@meridiano-online.net` (phishing de token do banco pagador), `portal-nfe-receita.com` (falsa Receita), `cobranca@protesto-nacional.net` (falsa ameaça de protesto), `cobranca.pigmentosaquarela@outlook.com` (2ª via de boleto por domínio público). Remetente que se diz banco/órgão não tem "domínio cadastrado" para comparar: tratar por política (PS08, PS02).
- A maioria das 246 comunicações é legítima (cobranças e envio de boleto de fornecedores). **Precisão importa**: acionamento desnecessário custa R$60.

## Achados da T2 (medidos nos CSVs, 2026-11-07)

- **Os CSVs são uma foto de 02/11 08:00. Nada chega depois.** Último título lançado: 30/10 17:51. Última comunicação: 02/11 07:24. Última NF recebida: 31/10 18:20. A partir do instante inicial o replay não tem o que liberar; só a API do evento (se existir) entrega itens novos por tique.
- **Para demonstrar "chegou uma mensagem antes do corte" use replay retroativo:** iniciar o `SimClock` num instante anterior (ex.: 29/10 14:00; EM571119 chega às 15:42) e avançar. O adaptador reconstrói título e cadastro "como eram" no instante. Declarar sempre como replay retroativo.
- **Estado reconstruído:** status do título derivado de `data_lancamento`, `data_baixa`/`data_pagamento`, `data_cancelamento` e `lote_remessa`. Pressuposto: o título entra no lote no lançamento (não há carimbo de agendamento). No corte, coincide com o CSV nas 7.120 linhas, com a agenda (876) e com o cadastro (131).
- **Cadastro retroativo:** `alteracoes_cadastro.csv` é lido só dentro do simulador, para reverter alterações posteriores ao instante. O agente continua sem acesso a ele.
- **FP4615 (Embalarte):** conta antiga banco 774 / ag. 7166 / conta 9517944-5; trocada em 30/10 16:05 (`usuario_07`, origem e-mail, sem confirmação registrada) para banco 905 / 0001 / 4471203-9, **a mesma conta pedida por EM571119 em 29/10 15:42**. No corte, a agenda já aponta o destino novo. 192 títulos no total do fornecedor.
- **Pedidos de compra com aprovação posterior ao corte** (3, datas até 03/11): o adaptador mascara aprovação e mostra `pendente_aprovacao` até o instante da aprovação.
- **Feriado de remessa:** só entram feriados com `afeta_remessa = sim` (nacionais). Estaduais/municipais não bloqueiam remessa. 02/11 (Finados) bloqueia; o primeiro fechamento do período é **03/11 10:00 (MER)**.
- **Efeito da alçada na demo:** `corrigir_lancamento` de valor só vale sem aprovação se **|novo − atual| ≤ R$5.000**. Um erro de fator 10× com título grande (ex.: R$90 mil → R$9 mil) exige aprovador. Para a demo 2 escolha um título pequeno (≲ R$5,5 mil).

## Achados da T3 (identidade, medidos no corte; detalhes em `reports/identidade.md`)

- **Fornecedor é chave limpa:** 131 fornecedores, CNPJs válidos, raízes únicas; todas as 6.055 OCs resolvem para exatamente um fornecedor (matriz); `cod_fornecedor_compras` ↔ raiz é 1:1. **Não há ambiguidade de fornecedor**; a ambiguidade real é a da NF (T4).
- **NF:** 4.151 NFs; 3.951 de matriz e **200 de filial** (mesma raiz, outro estabelecimento, razão social diferente). Todas resolvem.
- **Títulos (7.120):** 7.117 coerentes; **3 divergentes, todos já agendados**:
  - `TP431946` (FP5079, R$ 9.870,50, lote RM20261106-MER): a OC OC-40703 pertence ao FP6799. Fornecedor possivelmente errado no lançamento.
  - `TP432337` (FP3614, R$ 12.380,00, lote RM20261110-MER): a OC OC-41231 pertence ao FP3302.
  - `TP431754` (FP4345 Pigmentos Aquarela, R$ 11.740,00, boleto, vence 03/11, **lote RM20261103-MER, primeiro fechamento do período**): o CNPJ do beneficiário do boleto (`61.525.615/0001-26`) não é o do fornecedor (`20.623.234/0001-00`) e é **o mesmo CNPJ do boleto anexado no e-mail EM571116** (29/10 11:05, `cobranca.pigmentosaquarela@outlook.com`, "2ª via... favor desconsiderar o anterior"). A política diz que 2ª via com beneficiário diferente não pode ser paga sem confirmação no canal do cadastro. **Candidato a demo de golpe de boleto**, além do Embalarte. Observação: o título foi lançado em 08/10, antes do e-mail; não afirmar quem inseriu o CNPJ.
- **Comunicações (246):** 241 vêm do e-mail cadastrado do fornecedor. Os 5 que não conferem são exatamente os suspeitos: EM571119 (Embalarte, vincula por CNPJ e nome, remetente `embalartte`), EM571116 (Pigmentos, `outlook.com`, só evidência de nome → ambíguo) e três impersonações de não-fornecedores (EM570977 falsa Receita, EM570998 falso cartório, EM571100 falso Banco Meridiano → sem vínculo).
- **O vínculo é por sinais explícitos** (e-mail exato 4 pts, domínio 3, CNPJ no texto 3, nome 1; ≥3 e único = ok). `remetente_confere` é o sinal determinístico que a T5 usa.

## Achados da T5 (comunicações; extrator mock + risco, medido nas 246 mensagens no corte)

- **Distribuição por tipo (mock):** 196 envio de boleto/NF, 14 cobrança, 13 segunda via, 5 troca bancária, 15 outros (reajuste, pagamento não identificado, duplicidade, programação), 1 phishing, 1 ameaça de protesto, 1 token.
- **Ancoragem:** 0 problemas nas 246 (todo trecho, valor, conta e data extraído existe literalmente na mensagem).
- **Risco (246 mensagens):** 236 sem alerta, 5 em atenção, **exatamente 5 de nível alto** (antes de tratar a 2ª via como informativa eram 224 / 17 / 5): EM571119 (Embalarte), EM571116 (2ª via com beneficiário trocado), EM570977/EM570998/EM571100 (falsa Receita, falso cartório, falso Banco Meridiano; sem vínculo com fornecedor; PS08, e PS02 quando diz ser banco pagador).
- **Troca bancária por remetente legítimo (4):** EM570891 (Cartonart FP5079), EM570954 (Polyfilm FP3614), EM570976 (Evoluir FP4202), EM571033 (Magnetec FP3345). Remetente confere e **o cadastro já contém o banco anunciado**. Nível atenção + `requer_confirmacao_cadastro` (a confirmação por telefone anterior não é verificável pelo analista). **Observação a verificar, sem concluir nada:** FP5079 e FP3614 são justamente dois dos fornecedores dos títulos com OC de outro fornecedor (TP431946, TP432337).
- **2ª via legítima (12 de 13)** com remetente e beneficiário corretos: `segunda_via_boleto` é sinal informativo e não gera atenção sozinho (o ajuste evitou ~12 acionamentos de R$ 60).
- **Instrução plantada em texto de terceiro** (ex.: EM570996, e o trecho dirigido ao "robô" em EM571119): a extração registra em `tentativas_de_instrucao`, o risco sobe para atenção/alto conforme o contexto e **nenhuma decisão muda por causa do texto**. `AnaliseRisco` não tem campo de ação.
- **IA real (GPT-4o, 246 mensagens, `reports/validacao_openai_246.md`):** **0 degradadas**; mesmo nível de risco que o mock em **243/246**, com os **5 de risco alto idênticos** (Embalarte, 2ª via com beneficiário trocado, falsa Receita, falso cartório, falso banco). As 3 divergências são mensagens de "pagamento parcial" em que o GPT marcou urgência ("para evitar multa") numa execução e não na outra: a saída do modelo **não é determinística** mesmo com temperatura 0, mas isso só move "nenhum" para "atenção" e não muda nenhuma decisão de pagamento (que só depende de risco alto e das regras). Tipo de pedido igual em 215/246: 30 são o mock dizendo `envio_boleto_nf` e o GPT `cobranca` (granularidade, mesmo risco) e 1 `cobranca`→`outro`. Por isso os testes e2e usam o mock. O `ExtratorClaude` (Anthropic) continua sem execução real.

## Achados da T8 (laço de eventos; fila inicial completa no corte, conferência 3 vias neutra)

- **Fila inicial** (2.398 títulos abertos/agendados + 246 comunicações) processa em ~1 s. Resultado: **28 títulos retirados do lote** (25 do Embalarte por TED + os 3 divergentes TP431754, TP431946, TP432337), **8 acionamentos** (PS08 ×3 por impersonação, PS02 ×1 pelo falso Banco Meridiano, PS01 ×4) e **4 solicitações de aprovação agrupadas** (131 títulos). Nenhum agendamento, correção ou cancelamento: a conferência de 3 vias real (T4) ainda não está ligada ao laço.
- **Embalarte (FP4615):** 192 títulos, **todos por TED**: 25 agendados (retirados), 33 abertos, 134 pagos. Como todos usam a conta do cadastro, o risco de troca de conta os afeta todos; um fornecedor com títulos por boleto não seria afetado (boleto vai para o beneficiário do próprio boleto).
- **Pigmentos Aquarela (FP4345):** só o título da NF 57551 (TP431754) é retirado; os demais títulos legítimos do fornecedor permanecem agendados. O risco de boleto vale para a NF citada, não para o fornecedor inteiro.
- **Trocas de conta de remetente legítimo (FP3614, FP5079, FP3345, FP4202): as 4 têm confirmação registrada por ligação ao telefone do cadastro.** Só a do FP4615 não tem. O analista **não lê** o histórico (`consultar_historico_cadastro` é de auditor/aprovador), então não consegue distinguir. Por isso a R4 apenas **pede aprovação dupla (agrupada por fornecedor)** e não retira pagamentos no pré-fechamento: retirar 131 títulos legítimos custaria multa, juros e relacionamento (o placar pune atraso).
- **Aprovação acima da alçada:** títulos agendados >R$ 5.000 não trazem `aprovado_por` no cadastro (só os pagos trazem). Pedir aprovação deles seria ~1.500 pedidos de ruído; o agente só pede aprovação do que **ele mesmo** agendaria.
- **Replay retroativo (29/10):** às 14:00 e 15:00 a mensagem do Embalarte (15:42) não existe; no tique das 16:00 ela aparece e os 25 títulos TED em lote aberto são retirados antes do primeiro corte desses títulos.
- **Pré-fechamento:** roda no último tique anterior ao corte (09:00 para o lote das 10:00; 13:00 para o das 14:00), só em dia útil (02/11 é feriado: o primeiro é 03/11 09:00). Uma pendência sem resolução é retirada ali, e não antes.
- **Integração T8↔T9 (laço + Store + Executor), replay retroativo de 29/10, escopo FP4615:** 28 retiradas **confirmadas pelo estado do ambiente** (`consultar_titulo`), 6 acionamentos verificados, 61 acionamentos de títulos reservados e não reenviados por pertencerem a incidente já alertado, nenhuma ação `incerta` ou `falha`. Reiniciar o laço sobre o mesmo banco executa **zero** ações novas. Com o verificador padrão (sem `verificador_replay`), acionar e solicitar ficam `incerta` e **não são reenviados**, que é o comportamento correto sem prova.
- **Não existe `AprovacaoRecebida`:** o ambiente simulado não devolve aprovações, então o laço nunca vê uma pendência ser resolvida; toda pendência com `fallback_no_corte` é executada no pré-fechamento.

## Achados da T11 (laço com a conferência de 3 vias real, fila inicial no corte; `reports/replay_corte.md`)

- **Escala:** 2.403 decisões em ~3 s. **Nenhum "evidência ausente ou ambígua"**: nenhum título legítimo seria retirado por falha de pareamento de NF. Ações: **31 retiradas** (25 Embalarte por TED, 3 de identidade/boleto trocado, 3 excessos de fator 10× agendados), **11 correções** (9 de valor em TED, 2 de vencimento), **12 boletos com tarifa** encaminhados ao comprador **sem reter pagamento**, 2 divergências de OC (PS04/PS05), **11 pedidos de aprovação** (4 troca de conta + 7 valor acima da alçada), 16 acionamentos.
- **Armadilha do boleto:** 12 títulos de boleto ficam R$ 2,90 a R$ 4,50 acima da duplicata e **o valor do título é exatamente o impresso no boleto** (linha digitável, posições 38–47). Corrigir o título para a duplicata o faria divergir do boleto que será pago, então o agente **não corrige**: aciona o comprador (diferença de tarifa) e só retiraria do lote se o excesso passasse de 1% da duplicata (premissa `LIMITE_EXCESSO_RELATIVO`, a calibrar). Outras 95 divergências título × boleto: 92 são ±R$ 0,01 (resto de parcela); 3 são fator 10× com boleto certo e título errado, e aí corrigir o título é o certo.
- **Correção de valor só em TED/PIX (ou boleto que bate com a duplicata):** os 9 erros de fator 10× corrigidos (ex.: TP431634 R$ 240,64 → R$ 2.406,36) estão dentro da alçada de R$ 5.000 de diferença. Os 3 excessos agendados acima disso (TP431459, TP431536, TP431775) são retirados e viram pedido de aprovação.
- **Vencimento:** 2 títulos (TP432123, TP432281) têm vencimento 08/02/2027, que é Carnaval (bancos fechados); a duplicata vence em 06/02/2027 (sábado). A correção usa a data da duplicata, permitida pela política.
- **Não existe título aberto vencendo na janela da agenda (03–13/11):** os 1.522 abertos vencem de 14/11 em diante. O "agendar sozinho" só ocorre com título novo ou programando adiante no lote do próprio vencimento (feito no cenário: 178 títulos ≤ R$ 5.000 até 23/11).
- **Solicitações de aprovação:** só títulos ainda não incluídos em solicitação anterior do incidente são pedidos (o pré-fechamento reavalia o lote e reenviaria subconjuntos; isso gerou 14 pedidos antes do ajuste, 11 depois).
- **Não verificado:** o `ExtratorClaude` (Anthropic) não rodou com a API real (sem chave); o `ExtratorOpenAI` rodou com GPT-4o (ver Achados da T5). Os cenários e2e usam o extrator mock.

## Métricas — SUSPENSAS, reproduzir antes de usar

Não existe número validado. Valores abaixo vêm de auditorias anteriores **não reproduzidas** e **não podem** aparecer em código, UI, slides ou submissão:

| Afirmação anterior | Estado |
|---|---|
| 34 divergentes, 22 de fator 10×, R$316.182,88 de excesso | sem reprodução independente |
| 6 títulos / R$132.245,00 em lote | idem |
| 23 de 34 por `usuario_07` | concentração contestada; **não afirmar causa raiz** |
| 240 divergentes, 9 de fator 10×, R$1,36 mi | contracálculo com junção só por nº de NF; também não validado |
| 58 títulos / R$354.862,86 do FP4615 | exposição, não perda confirmada nem economia |

Confirmado (verificação relatada): typosquat do Embalarte e `ultima_alteracao_por = usuario_07` no FP4615 — sustentam investigação, **não provam autoria de fraude**.

### Protocolo de reprodução (T3/T4, antes dos slides)

1. Fixar instante de referência e universo (títulos abertos e agendados), preservando IDs e status.
2. Normalizar CNPJ e número digitado; separar série quando informada, sem inventar série ausente.
3. Buscar NF por fornecedor/emitente + número + série. Exigir **uma única `chave_acesso`** antes de comparar valores.
4. Vincular a parcela do título à duplicata correta (`n/total` ↔ `n_dup`). Respeitar categorias dispensadas, multa/juros e tolerâncias.
5. Separar matches únicos, ausentes e ambíguos. Somar com `Decimal`. Produzir tabela rastreável: `titulo_id`, chave de acesso, parcela, valor esperado, diferença.
6. Calcular separadamente: excesso, insuficiência e exposição em lote. **Não somar exposições sobrepostas como benefícios distintos.**
7. Só então contar divergências por usuário, com o nº de títulos processados por usuário como denominador. Concentração isolada não prova causa raiz.

Saída esperada: `reports/reproducao_metricas.csv` + `reports/reproducao_metricas.md` com contagens por categoria de resultado (único / ausente / ambíguo / divergente / ok).
