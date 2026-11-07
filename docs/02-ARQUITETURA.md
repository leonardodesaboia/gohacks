# Arquitetura

Princípio: **a IA lê o que não é tabela; o código decide.** Fluxo orientado a eventos com relógio explícito, cadastro limitado à conferência e contratos internos mínimos. Nada de plataforma genérica.

## Fluxo

```
fonte (ReplayAdapter | ApiAdapter) → Evento + instante simulado
  → ToolGateway(papel=analista_cp)           # RegistroPapeis em toda leitura e ação
  → coletor de evidências                    # só o que o papel pode ler
  → ExtratorComunicacao (LLM ou mock)        # texto livre → Evidencia estruturada + trecho citado
  → regras: identidade · 3 vias · risco · alçada
  → MotorDecisao(dossie) → Decisao           # função pura, fail-closed
  → Executor                                  # ação permitida OU solicitar_aprovacao / acionar_pessoa
  → Store (SQLite) + log de auditoria
```

## Eventos internos

| Evento | Tratamento |
|---|---|
| `TituloDisponivelOuAlterado` | coletar evidências, conferir, decidir dentro da alçada |
| `ComunicacaoRecebida` | interpretar pedido em texto livre, vincular ao fornecedor, reavaliar os títulos afetados |
| `CadastroObservadoAlterado` | invalidar análise que dependia daquele cadastro (só se a fonte permitir observar a mudança) |
| `AprovacaoRecebida` | retomar o caso; revalidar se o contexto mudou |
| `PreFechamentoLote` | reconsultar o lote e revalidar títulos sem análise válida para o estado atual |

`PreFechamentoLote` deve terminar **antes** do corte (Meridiano 10:00, Litoral 14:00, dias úteis). Se só houver passos de 1 hora, usar o último tique anterior ao corte. **A ordem ação × fechamento no ambiente real é pergunta em aberto** (ver `CLAUDE.md` §8).

Ciclo: começar pela fila existente no instante inicial (02/11 08:00) → avançar tique a tique → a cada tique emitir eventos de títulos novos, comunicações novas e, quando aplicável, pré-fechamento. Sem broker: polling/replay produzem os mesmos eventos internos.

## Adaptadores (traduzem fonte → contratos)

- **`ReplayAdapter`** lê `data/raw/*.csv` e simula as ferramentas do analista_cp. Mantém `SimClock`: só devolve registros com `instante_disponibilidade <= agora`. Regras de disponibilidade por tabela em `docs/03-DADOS.md`. **Não expõe** extratos, histórico de cadastro, log de auditoria, aprovações, retorno de remessa, DDA, usuários.
- **`ApiAdapter`**: stub com a mesma interface, para plugar a API do evento se existir.
- Modo `--visao-auditor` (somente validação offline de métricas) é uma classe separada, nunca usada pelo agente, e imprime "VISÃO AUDITOR — NÃO REPRESENTA O PAPEL analista_cp".

## Contratos internos (Pydantic v2, agnósticos de formato)

| Contrato | Campos mínimos |
|---|---|
| `Pagamento` | id e origem, fornecedor, nf/serie/parcela, `valor: Decimal`, moeda, vencimento, estado, lote, versão observada |
| `FornecedorRef` | id de origem, CNPJ completo normalizado, raiz (8 dígitos), contatos disponíveis ao papel |
| `Evidencia` | fonte, registro e trecho de origem, instante do fato, instante de disponibilidade, método de extração |
| `Dossie` | pagamento, evidências, inconsistências, dados ausentes, ação proposta, confiança |
| `Decisao` | ação, regra aplicada, alçada, aprovação necessária, versão das evidências, chave de idempotência, motivo |

Políticas do evento ficam explícitas em config/código (tolerâncias, exceções por categoria, aprovação dupla, limites, horários). O modelo agnóstico preserva particularidades; não as substitui por regra financeira universal.

`confianca` no `Dossie` (alta/média/baixa) é **contagem de regras disparadas**, não ML: 0 flags = alta; 1 flag leve = média; qualquer flag de fraude/duplicidade = baixa.

## Camadas de código (`src/sentinela/`)

| Módulo | Responsabilidade |
|---|---|
| `contracts.py` | contratos acima + enums de ação/papel |
| `roles.py` | `RegistroPapeis` (papel → ferramentas) a partir de `ferramentas.csv` |
| `clock.py` | `SimClock`, calendário de dias úteis e cortes de lote |
| `gateway.py` | `ToolGateway`: valida papel, limites por dia, registra toda chamada |
| `adapters/replay.py`, `adapters/api.py` | fontes de dados e ferramentas simuladas |
| `identity.py` | resolução fornecedor ERP ↔ Compras ↔ NF ↔ CNPJ |
| `threeway.py` | conferência título × duplicata × NF × OC com exceções por categoria |
| `comms/extractor.py` | interface + `ExtratorClaude` + `ExtratorMock` |
| `comms/risk.py` | comparação determinística de remetente/dados com cadastro |
| `decision.py` | `MotorDecisao` puro |
| `executor.py` | executa ação via gateway, reconcilia timeout |
| `store.py` | SQLite: eventos, versões de evidência, ações, incidentes, auditoria |
| `loop.py` | laço de eventos por tique + pré-fechamento |
| `scoreboard.py` | placar (P1) |
| `ui/app.py`, `ui/theme.py` | Streamlit de narração (design system Gocase) |

## MotorDecisao — implementado na T6 (`src/sentinela/decision.py`)

Função pura `decidir(FatosTitulo) -> Decisao` (e `decidir_comunicacao(AnaliseRisco)`). Ordem: **R0** estado final · **R1** fraude/identidade (risco alto em comunicação do fornecedor, identidade divergente, OC de outro fornecedor: retira do lote e aciona PS01; lote já fechado aciona PS02) · **R2** duplicidade comprovada (cancela ≤ alçada, senão retira + solicita aprovação) · **R3** evidência ausente/ambígua (aciona pessoa; nada executa; `fallback_no_corte`) · **R4** troca bancária pedida com cadastro mexido há ≤30 dias (aprovação dupla, agrupada por fornecedor, **sem reter pagamento**: o analista não vê a confirmação) · **R5** divergência OC×NF (aciona o comprador da categoria) · **R6** valor/vencimento (corrige só com causa única e diferença ≤ R$5.000; senão aprovação) · **R7** caso limpo (título já agendado: mantém; aberto com lote alvo: agenda dentro da alçada agregada ou pede aprovação). Risco de comunicação só vale para o título que ele afeta (`risco_relevante`: troca de conta afeta TED/PIX; boleto/2ª via afeta a NF citada).

**Laço (T8, `src/sentinela/loop.py`):** a cada tique processa comunicações novas, títulos novos e cadastro alterado e, no último tique antes de cada corte, faz o **pré-fechamento** (revalida o lote e executa o `fallback_no_corte`). A conferência de 3 vias é injetada (`conferir`). `ExecutorEmMemoria` é provisório; a versão persistente é o `Executor` da T9 (integrar na T11).

`Decisao` carrega `acoes` (lista ordenada de `AcaoPlanejada`), `fallback_no_corte` (o que o pré-fechamento faz se ninguém resolver) e `incidente` (chave para agrupar alertas: comunicação e títulos do mesmo fornecedor compartilham `"<fornecedor>|fraude"`). Verificado por testes: um por regra, uma varredura de ~12 mil combinações (nunca fora do papel ou da alçada, nunca executa sem evidência, sempre retira em risco alto), uma varredura exaustiva da alçada de agendamento e casos reais do evento.

## MotorDecisao (esboço original da lógica, histórico)

Entrada: `Dossie`. Saída: `Decisao`. **Sem I/O, sem LLM.**

1. Se qualquer evidência crítica ausente/ambígua → `ESCALAR` (fail-closed).
2. Sinal de fraude (troca bancária sem confirmação **registrada e verificável**, boleto com banco/beneficiário divergente sem histórico, remetente suspeito pedindo mudança de pagamento) → `retirar_do_lote` + `acionar_pessoa(PS01, urgência alta)`; acima da alçada ou aprovação dupla → também `solicitar_aprovacao`. Fraude por impersonação de banco/Receita/órgão → PS08 (e PS02 se envolver banco pagador).
3. Divergência de valor com **uma única causa comprovável** e dentro da alçada agregada → `corrigir_lancamento` com evidência; senão `ESCALAR`.
4. Duplicidade comprovada (mesmo fornecedor + NF + parcela + valor) e ≤ alçada → `cancelar_titulo`; senão `solicitar_aprovacao`.
5. Divergência OC × NF acima da tolerância → `acionar_pessoa` (PS04/PS05 por categoria) e `retirar_do_lote` se fecha antes de resolver.
6. Tudo bate e soma agregada ≤ R$5.000 e sem gatilho de dupla → `agendar_titulo` (ou manter agendado) automático.
7. Tudo bate mas > R$5.000 → `solicitar_aprovacao` (aprovador até R$50k; PS03 acima).

Ordem de prioridade da fila: **exposição financeira e custo de atraso por categoria**, depois proximidade do fechamento, não ordem de chegada.

## IA: onde entra e onde não entra

Entra: (a) extrair de comunicação em texto livre: tipo de pedido (troca bancária, 2ª via de boleto, cobrança, ameaça/protesto, phishing), identidade alegada, dados bancários citados, número de NF/vencimento/valor citados, **alegações de confirmação** (registradas como alegação, nunca como fato), e **trecho literal de suporte**; (b) escrever o motivo do flag em linguagem clara para o humano. Não entra: escolher ação, valor, destino, alçada, ou executar.

Saída do extrator: JSON validado por Pydantic. Falha de validação ou confiança baixa → `status=DEGRADED` → escalar com a limitação registrada (nunca silenciar). O prompt do extrator está em `docs/PROMPTS.md`. Injeção: o texto da comunicação é passado ao modelo **delimitado como dado**, o modelo não tem ferramentas, e o código ignora qualquer campo fora do schema.

## Persistência e idempotência

SQLite com tabelas: `eventos(id, tipo, instante, payload_hash)`, `evidencias(id, fonte, registro, versao, instante_disponibilidade)`, `decisoes(chave_idempotencia, titulo_id, versao_evidencias, acao, regra, ...)`, `acoes(chave, estado, resultado, tentativas)`, `incidentes(id, fornecedor, motivo, pessoas_acionadas)`, `auditoria(...)`.

- Evento duplicado → ignorado pelo `payload_hash`/id.
- Mudou a versão das evidências do título → reavalia (nova decisão).
- Ação: `chave = hash(titulo_id, acao, parametros, versao_evidencias)`. Antes de executar, ver se já existe; após timeout, **consultar estado** no sistema e reconciliar antes de repetir.
- Alertas por incidente (fornecedor + motivo), não por título.

## Fase 2 (só se sobrar tempo, não é P0)

`Roteador(papel_necessario)` que delega a sub-agentes (auditor) reutilizando `Dossie`, `RegistroPapeis` e `MotorDecisao`. É um acréscimo, não reescrita; não construir antes do P0 testado.
