# Plano de build

**Regra de corte:** se o tempo apertar, corte de baixo para cima. P0 incompleto é pior que P1/P2 ausentes. Prazo de submissão: sábado 07/11 às 16h30; a demo ao vivo é o que mais pesa.

Convenção por tarefa: **Entrega** (arquivos), **Aceite** (como saber que acabou), **Teste** (obrigatório). Rodar `pytest` e commitar ao fim de cada tarefa; registrar erros da IA em `relatorio.md`.

## P0 — sem isso não existe projeto

### T0 — Bootstrap e validação de dados
- Entrega: `pyproject.toml` funcional, `pip install -e .[dev]` ok, `scripts/validar_dados.py`.
- Aceite: o script lê todos os CSVs de `data/raw/`, confere cabeçalhos contra o dicionário, imprime contagem de linhas, formato de datas, e **confirma que `comunicacoes_fornecedores` é CSV**; lista tabelas que o papel analista_cp pode/não pode ver. Falha alto se faltar coluna.
- Teste: `tests/test_dados.py` com os cabeçalhos esperados.

### T1 — Contratos e papéis (já existe esqueleto em `src/sentinela/`)
- Entrega: `contracts.py`, `roles.py` completos; `ToolGateway` em `gateway.py` (valida papel, limites diários `acionar_pessoa` 40, `contatar_fornecedor` 60, registra toda chamada).
- Aceite: chamar `consultar_historico_cadastro` ou `consultar_extrato` com papel analista_cp levanta `PermissaoNegada`; chamada permitida é registrada com instante simulado.
- Teste: um teste negativo para **cada** uma das 11 ferramentas proibidas; um positivo para cada uma das 16 permitidas.

### T2 — Relógio e adaptador de replay
- Entrega: `clock.py` (`SimClock`, dias úteis, feriados de `feriados_bancarios.csv`, cortes 10:00/14:00), `adapters/replay.py` com as 8 leituras e as execuções simuladas (mudam o estado em memória/SQLite, não nos CSVs), `adapters/api.py` stub.
- Aceite: com `agora=2026-11-02 08:00` o adaptador não devolve comunicação, título ou NF com disponibilidade posterior; avançar o relógio libera o que chegou. Retirar/agendar altera `agenda_remessa` simulada e é consultável.
- Teste: nenhum vazamento de futuro (propriedade testada em vários instantes); estado após ação confere.
- Antes: **decidir integração vs replay** (ver `CLAUDE.md` §8). Sem resposta da organização, replay declarado.

### T3 — Identidade do fornecedor
- Entrega: `identity.py`: normaliza CNPJ, raiz de 8 dígitos, resolve ERP ↔ Compras ↔ NF; devolve `FornecedorRef` ou ambiguidade explícita.
- Aceite: 100% dos títulos de `contas_a_pagar` resolvem para um fornecedor ERP com CNPJ válido; casos de filial (outra razão social, mesma raiz) resolvem; ambíguos listados.
- Teste: casos reais de filial; CNPJ com/sem pontuação; fornecedor `FC`/`FN`.

### T4 — Conferência de 3 vias (+ reprodução de métricas)
- Entrega: `threeway.py` e `scripts/reproduzir_metricas.py` seguindo o protocolo de `docs/03-DADOS.md`.
- Aceite: para cada título aberto/agendado devolve `{ok, divergente(tipo, esperado, diferença), ausente, ambíguo}` com a chave de acesso única; exceções por categoria (aluguel sem NF, utilidades sem OC); tolerâncias R$0,10 e 2%/R$50; multa/juros pro rata; vencimento = duplicata ou próximo dia útil. Gera `reports/reproducao_metricas.{csv,md}`.
- Teste: um caso real por regra; parcela ≠ total; fator 10×; cancelado+relançado não é duplicidade; NF ambígua não decide.

### T5 — IA nas comunicações + risco determinístico
- Entrega: `comms/extractor.py` (`ExtratorComunicacao`, `ExtratorClaude`, `ExtratorMock`), `comms/risk.py`.
- Aceite: para cada comunicação devolve `ExtracaoComunicacao` válida (tipo de pedido, identidade alegada, dados bancários citados, NF/valor/vencimento citados, alegações de confirmação, **trecho literal de suporte**, confiança). `risk.py` compara determinísticamente remetente × `email_cadastrado` e dados citados × cadastro; **domínio divergente = sinal, não prova**; alegação de confirmação nunca vira confirmação. Falha/ambiguidade → `DEGRADED` + escalar.
- Teste: Embalarte (troca bancária, remetente divergente, trecho "para o robô" tratado como alegação); mensagem legítima de cobrança → sem flag; ambiguidade; **injeção** (instrução plantada é ignorada e registrada); extrator mock reproduz os resultados sem rede.

### T6 — MotorDecisao
- Entrega: `decision.py` puro conforme `docs/02-ARQUITETURA.md`.
- Aceite: tabela de decisão cobre: limpo→agendar; erro comprovável ≤R$5k→corrigir; duplicidade→cancelar; fraude→retirar+acionar PS01 (+aprovação se couber); >R$5k→solicitar_aprovacao; ausente/ambíguo→escalar; alçada **agregada** por fornecedor+NF+dia; aprovação dupla nos gatilhos da política; trocar fornecedor/forma/linha digitável exige aprovador.
- Teste: propriedade "nenhuma decisão viola alçada ou papel"; um teste por ramo; fracionamento.

### T7 — Persistência e idempotência
- Entrega: `store.py` conforme `docs/02-ARQUITETURA.md`.
- Aceite: reprocessar o mesmo evento não repete ação; mudança de versão das evidências reavalia; timeout simulado → consulta de estado e reconciliação antes de repetir; alertas agrupados por incidente.
- Teste: evento duplicado; ação repetida; evidência nova após decisão.

### T8 — Laço de eventos e pré-fechamento
- Entrega: `loop.py`: fila inicial → tique a tique → `ComunicacaoRecebida`, `TituloDisponivelOuAlterado`, `PreFechamentoLote` antes de 10:00/14:00 em dias úteis.
- Aceite: um título agendado fica arriscado por comunicação nova e é **retirado do lote antes do corte**; no pré-fechamento, títulos sem análise válida são revalidados. Demonstra "antes de o dinheiro sair".
- Teste: cenário cronológico com nova evidência entre dois tiques.

### T9 — Executor, log e relatório
- Entrega: `executor.py`, auditoria no `store`, `relatorio.md` mantido.
- Aceite: toda ação passa pelo gateway; log de **intenção e de resultado** (consultar estado após agir); falha de ação vira escalonamento, não silêncio.
- Teste: ação negada pelo gateway; falha simulada.

## P1 — defensável e diferenciado (só com P0 testado)

### T10 — UI Streamlit de narração
- Entrega: `src/sentinela/ui/app.py` usando `ui/theme.py` e `assets/tokens.css` (ver `docs/06-DESIGN-SYSTEM.md`).
- Aceite: tela única com (1) cabeçalho do lote e contagem regressiva até o corte (**só exibição**), (2) fila priorizada por exposição, (3) card da comunicação com **dados extraídos e trecho citado lado a lado**, (4) decisão com regra aplicada e quem decidiu (IA leu / regra decidiu), (5) estado antes/depois do lote, (6) acionamento de PS01 com dossiê, (7) selo "REPLAY LOCAL" ou "INTEGRAÇÃO". Dados sensíveis mascarados. Botão de avançar relógio.
- Teste: render sem exceção; mascaramento aplicado.

### T11 — Cenários de demo e testes de ponta a ponta
- Entrega: `tests/e2e/` com os 3 cenários de `docs/05-DEMO-E-PITCH.md` (limpo, erro operacional validado, comunicação suspeita) + injeção + mensagem legítima.
- Aceite: executam de ponta a ponta no replay e reproduzem a mesma saída duas vezes (determinismo com `ExtratorMock`); versão com Claude real funciona com `ANTHROPIC_API_KEY`.

### T12 — Placar, prioridade e mascaramento
- Entrega: `scoreboard.py` — placar do mesmo cenário **com e sem agente**; prioridade por custo de atraso; mascaramento global.
- Aceite: `reports/placar.md` com a decomposição (indevido / atraso / acionamentos) e rastreabilidade por título. **Só vira número de slide se reproduzível.** Se o ambiente não der gabarito de "o que seria indevido", declarar a limitação.

## P2 — só se sobrar tempo, nesta ordem

1. Auditoria retroativa sobre os 90 dias fechados (papel auditor, rotulada como visão offline).
2. Contador visual do lote (se T10 não trouxe).
3. `contatar_fornecedor` em ambiguidade resolvível (a história da demo não pode depender dele: resposta em horas).
4. Baseline de valor típico por fornecedor.
5. Fase 2: `Roteador` multi-agente.

## Entrega final (T13, antes das 16h30)

`README.md` com como rodar em 3 comandos; commit do repo público; `docs/05-DEMO-E-PITCH.md` campos preenchidos; slides PDF ≤10; gravação reserva da demo.
