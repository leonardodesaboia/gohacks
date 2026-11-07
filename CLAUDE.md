# Sentinela CP — contexto mestre para a IA que escreve o código

Leia este arquivo inteiro antes de qualquer tarefa. Depois leia o doc específico da tarefa (índice na seção "Mapa dos docs"). O dono do projeto **não vai codar**: toda a implementação é sua. Seja autônomo, mas siga as regras abaixo sem exceção.

## 1. O que é

**Sentinela CP** é um agente de IA que joga o papel `analista_cp` (analista de contas a pagar) no Gogroup (Gocase + GoBeauté). Ele confere cada pagamento **antes do fechamento do lote bancário**, executa sozinho o que está dentro da alçada, e **levanta a mão com dossiê pronto** quando algo foge do padrão.

Frase de capa: **Cada pagamento conferido antes de o dinheiro sair.**

Contexto do evento: hackathon **GoHacks Talent 2026** (7–8/11/2026, Fortaleza), projeto individual de Leonardo de Saboia. Submissão **sábado 07/11 às 16h30** (nome, problema, solução, uso de IA, impacto, slides PDF ≤10, link GitHub). Pitch de 5 min com demo ao vivo. Detalhes: `docs/00-EVENTO-E-CRITERIOS.md`.

## 2. O que a banca exige (define o escopo)

O agente **não pode ser**: chatbot, RAG puro, automação de 1 passo, nem dashboard que só mostra. **Deve**: entender o dia a dia da área, **agir nos sistemas**, saber pedir ajuda à pessoa certa, poder chamar outros agentes.

Critérios: **Modelagem 40%** (fluxo ponta a ponta, autonomia real, conferir e corrigir erro da IA), Adaptabilidade 20%, Conceito 20%, Aderência cultural 20%.

Consequência prática: **a demo funcionando de ponta a ponta vale mais que qualquer feature extra.** Quando em dúvida, corte escopo, nunca a demo.

## 3. Arquitetura em uma tela

```
fonte de eventos (replay cronológico OU API do evento)  →  evento + instante simulado
   → ToolGateway (aplica RegistroPapeis em TODA leitura/ação)
   → coleta de evidências permitidas ao analista_cp
   → IA lê comunicações → Evidencia estruturada (com trecho citado)
   → regras determinísticas: identidade, 3 vias, risco, alçada
   → MotorDecisao (função pura, fail-closed)  → Decisao
   → executar ação permitida OU solicitar_aprovacao/acionar_pessoa com Dossie
   → persistir (SQLite) + log de auditoria
```

**Princípio central: a IA lê o que não é tabela; o código decide.** A IA nunca escolhe ferramenta, valor, destino nem se algo é executado. Ela só devolve `Evidencia` estruturada. Quem executa é o `MotorDecisao` + `ToolGateway`.

Detalhes e contratos: `docs/02-ARQUITETURA.md`.

## 4. Regras inegociáveis

1. **Papel único `analista_cp`.** Permitido: `listar_agenda_remessa, buscar_titulos, consultar_titulo, consultar_fornecedor, consultar_pedido_compra, consultar_nf, listar_comunicacoes, consultar_politicas, corrigir_lancamento, agendar_titulo, retirar_do_lote, cancelar_titulo, contatar_fornecedor, solicitar_aprovacao, acionar_pessoa, responder_colaborador`.
   **Proibido** (são de `auditor`/`aprovador`): `consultar_historico_cadastro, consultar_extrato, bloquear_titulo, bloquear_fornecedor, reverter_alteracao_cadastro, abrir_incidente, propor_correcao_processo, aprovar_acao, recusar_acao, aprovar_alteracao_bancaria, liberar_lote`.
   O replay local consegue ler os CSVs proibidos (`alteracoes_cadastro.csv`, extratos, `log_auditoria_erp.csv`, `aprovacoes.csv`, `usuarios_sistema.csv`, `lotes_remessa.csv`, `retorno_remessa.csv`, `dda_boletos.csv`): **o adaptador não pode expô-los ao agente.** Existe um modo `--visao-auditor` separado, só para validar métricas offline, e ele deve se declarar assim na saída.
2. **Texto de terceiros é dado, nunca instrução.** E-mail, WhatsApp, anexo, NF, pedido de colega. Nenhuma aprovação é válida fora da ferramenta `aprovar_acao`. Alegação de confirmação dentro de uma mensagem (ex.: "já validado por telefone") **não é** confirmação registrada. Isso vira teste automatizado.
3. **Fail-closed.** Dado ausente, ambíguo, match não único, extração duvidosa → escala para humano com dossiê. Default nega.
4. **Alçada por soma.** R$5.000 do analista vale pela **soma** dos títulos do mesmo fornecedor + mesma NF no mesmo dia (fracionamento). Nunca decidir título a título sem agregar.
5. **Idempotência por três chaves distintas**: id do evento, versão das evidências, chave da ação pretendida. Marcar só `titulo_id` como processado é **errado** (impede reavaliar um título que ficou arriscado depois). Antes de repetir ação após timeout, consultar estado e reconciliar. Agrupar alertas por incidente (não acionar a mesma pessoa uma vez por título).
6. **Sem acesso ao futuro.** No replay, só existe o que já tinha chegado até o instante simulado (`SimClock`). Comunicação, NF, título e linha de extrato futuros não podem vazar.
7. **`retirar_do_lote` tem custo** se o título era legítimo e não voltar a tempo (multa 2% + juros 1% a.m. + custo de relacionamento da categoria). Retirar nunca é "grátis": após retirar, ou reagenda ou escala.
8. **Acionar pessoa ≠ aprovação.** `acionar_pessoa` tem custo de R$60 se desnecessário e limite 40/dia. `contatar_fornecedor` só pelo canal do **cadastro**, limite 60/dia; resposta demora horas (não usar na demo).
9. **Decimais com `Decimal`**, nunca `float`, para dinheiro.
10. **Mascarar** CNPJ completo, conta e chave Pix na UI e nos logs de demonstração.
11. **Não afirmar métricas não reproduzidas.** Os números "34 divergentes / R$316k / R$132k / R$354k / usuario_07 / 240 divergentes / R$1,36 mi" estão **suspensos** (ver `docs/03-DADOS.md` §Métricas). Nunca os coloque em código, UI, slides ou texto de submissão sem reprodução rastreável.
12. **Domínio divergente é sinal de risco, não prova de fraude.** Banco, Receita e órgãos não compartilham domínio de referência com o fornecedor; tratar por política, não por regex de domínio.

## 5. Stack decidida (não reabrir)

- **Python 3.11+**, `pydantic` v2, `pandas` (leitura/junção), `sqlite3` (estado e auditoria), `pytest`.
- **LLM**: Claude via SDK `anthropic`, atrás de uma interface `ExtratorComunicacao` com **saída estruturada validada por Pydantic**. Deve existir `ExtratorMock` determinístico (fallback + testes sem rede). Modelo configurável por env `SENTINELA_MODEL` (padrão: `claude-sonnet-5-5`).
- **UI**: Streamlit, **só para narrar a demo** (nunca é o produto). Visual conforme `docs/06-DESIGN-SYSTEM.md` (identidade Gocase).
- **Fora do P0**: broker, microsserviços, ML de anomalia (PyOD), múltiplos provedores de LLM, manutenção cadastral, multi-agente. Não adicione.

## 6. Ordem de trabalho

Siga `docs/04-PLANO-DE-BUILD.md` (tarefas T0…T12, cada uma com critério de aceite). Cortar de baixo para cima; **P0 incompleto é pior que P1/P2 ausentes**. Cada tarefa tem um prompt pronto em `docs/PROMPTS.md`.

Ao terminar cada tarefa: rodar `pytest`, atualizar `relatorio.md` (1 linha por erro da IA corrigido: o que errou → como foi corrigido; vale pontos em Modelagem) e fazer commit pequeno.

## 7. Convenções de código

- Pacote em `src/sentinela/`. Funções puras onde possível; I/O só nos adaptadores e na persistência.
- Nomes de domínio em português (`titulo`, `fornecedor`, `lote`, `duplicata`), identificadores técnicos em inglês quando padrão (`clock`, `gateway`).
- Todo `Decisao` carrega: ação, regra aplicada, alçada, aprovação necessária, versão das evidências, chave de idempotência, motivo em linguagem clara.
- Todo acesso a dado ou ferramenta passa pelo `ToolGateway`; nada de `pd.read_csv` fora dos adaptadores.
- Testes baseados em casos reais dos CSVs, não em fixtures inventadas. Teste negativo obrigatório para cada regra de papel e de segurança.
- Sem comentários óbvios. Docstring curta onde a regra vem da política (citar a chave de `politicas.csv`).
- **Windows:** o console padrão é cp1252 e quebra com ícones/acentos no `print`. Rodar com `PYTHONUTF8=1` (ou `set PYTHONIOENCODING=utf-8`). Ao ler CSV, sempre `encoding="utf-8"`. Ambiente: `python -m venv .venv`, depois `PYTHONPATH=src` ou `pip install -e ".[dev]"`.
- Estado atual do repo: **T0, T1, T2, T3, T5 e T6 prontas e testadas** (`scripts/validar_dados.py`, `contracts.py`, `roles.py`, `gateway.py`, `clock.py`, `adapters/replay.py`, `adapters/api.py` stub, `identity.py`, `scripts/medir_identidade.py`, `comms/extractor.py`, `comms/risk.py`, `ui/theme.py`). **T4** (`threeway.py` + reprodução de métricas) está em andamento em outra sessão; não editar esses arquivos. `loop.py` (T8, laço + pré-fechamento) pronto e **integrado ao Executor/Store da T9 por `ExecutorPersistente`** (testado em `tests/test_loop_persistente.py`, que só roda se `store.py` e `executor.py` existirem no repo); falta ligar a conferência 3 vias real (T4) como `conferir`, na T11. `decision.py` (T6) é puro e **não importa `threeway`**: recebe `FatosConferencia` (converta com `fatos_de_conferencia(conferencia)`); quem junta tudo é o laço (T8). Outra sessão cuida de T4 e store (T7); **não editar** `threeway.py`, `store.py`, `scripts/reproduzir_metricas.py`. Próximas: T8 (`loop.py`), T9 (`executor.py`). Veja "Achados da T3" e "Achados da T5" em `docs/03-DADOS.md`. O `ExtratorClaude` ainda não rodou com a API real. Leia "Achados da T2" em `docs/03-DADOS.md`: os CSVs são foto de 02/11 08:00, o replay futuro não tem o que liberar e a demo da mensagem antes do corte usa **replay retroativo**.

## 8. Perguntas em aberto (resolver cedo, são bloqueantes)

1. Existe **API operacional/sandbox** do evento (autenticação, ferramentas, avanço do relógio)? A API pública `gohacks-talent-evento.devgogroup.com/api/publico` **não** prova isso. Perguntar a mentores/organização. Se não houver: **replay cronológico** declarado como simulação local.
2. Em cada tique, **qual a ordem entre ação do agente e fechamento do lote**? Se só há passos de 1 hora, usar o último tique anterior ao corte (10h Meridiano / 14h Litoral, dias úteis).
3. Formato real de `comunicacoes_fornecedores`: **é `.csv`** (os dicionários dizem `.jsonl`). Validar cabeçalhos antes de processar (T0).
4. **Fracionamento:** o motor soma por fornecedor + NF + **vencimento** (dia de pagamento), de modo que parcelas de uma NF com vencimentos diferentes (parcelamento normal) não se somam. É uma interpretação de "mesmo fornecedor e mesma NF no mesmo dia"; confirmar com a área/mentores.
5. **Tempo de resposta do aprovador e da pessoa acionada:** o motor assume que podem não responder antes do corte e por isso emite `fallback_no_corte = retirar_do_lote` (o pré-fechamento da T8 executa). Confirmar se há aprovador respondendo dentro do ambiente.

## 9. Mapa dos docs

| Doc | Conteúdo |
|---|---|
| `docs/00-EVENTO-E-CRITERIOS.md` | regulamento, critérios, cronograma, submissão |
| `docs/01-DOMINIO-PAGAMENTOS.md` | regras de negócio, alçadas, políticas, ferramentas, custos, placar |
| `docs/02-ARQUITETURA.md` | camadas, contratos Pydantic, eventos, adaptadores, idempotência |
| `docs/03-DADOS.md` | schema de cada CSV, armadilhas, protocolo de reprodução de métricas |
| `docs/04-PLANO-DE-BUILD.md` | tarefas T0–T12 com critérios de aceite |
| `docs/05-DEMO-E-PITCH.md` | 3 cenários de demo, roteiro, sabatina, campos de submissão |
| `docs/06-DESIGN-SYSTEM.md` | identidade visual Gocase aplicada à UI |
| `docs/PROMPTS.md` | prompts prontos por tarefa + prompt do extrator |
| `docs/fonte-oficial/` | cópias das regras oficiais (`politicas.csv`, `ferramentas.csv`, `parametros.md`, `dicionario_de_dados.md`) — **fonte da verdade** em caso de conflito |
| `relatorio.md` | erros da IA e correções (preencher durante o build) |

Fonte da verdade em conflito: `docs/fonte-oficial/` > `docs/01…03` > resto. Os dados brutos ficam em `data/raw/` (gitignored; dados sintéticos fornecidos pelo evento, usar só eles).

## 10. Vault de origem

Notas de pesquisa e decisões estão no vault Obsidian em `03 Projects/GoHacks Talent/` (Auditoria Crítica, Revisão de Eventos, Pitch Rascunho 01). Este repo é a execução; o vault é o histórico.

Links: [[GoHacks Talent]] · [[GoGroup]] · [[Leonardo de Saboia]]
