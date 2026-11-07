# Sentinela CP

**Cada pagamento conferido antes de o dinheiro sair.**

Agente de IA que joga o papel de analista de contas a pagar no Gogroup: confere título × NF × pedido de compra, lê comunicações de fornecedores, executa o que está dentro da alçada e chama a pessoa certa, com dossiê, quando encontra risco. Projeto individual para o **GoHacks Talent 2026**.

> A IA lê o que não é tabela; o código decide.

## Status

Em construção. Plano em [`docs/04-PLANO-DE-BUILD.md`](docs/04-PLANO-DE-BUILD.md). Nenhuma métrica de impacto foi publicada ainda: só entram números reproduzidos (ver [`docs/03-DADOS.md`](docs/03-DADOS.md)).

## Como rodar

Python 3.11+. Os CSVs de Pagamentos do evento devem estar em `data/raw/` (não versionados).

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows (PowerShell/cmd); no Git Bash: source .venv/Scripts/activate
pip install -e ".[dev]"           # + pip install openai  se for usar GPT
set PYTHONUTF8=1                  # Windows: evita erro de acentos no console (PowerShell: $env:PYTHONUTF8=1)

python scripts/validar_dados.py   # confere os 25 CSVs contra o dicionário
pytest                            # toda a suíte (usa extrator mock, sem rede)
```

**Demo (replay local; os CSVs são uma foto de 02/11/2026 08:00):**

```bash
# fila inicial no corte até o primeiro fechamento de lote (03/11 10:00): confere, corrige, retira, aciona
python scripts/rodar_replay.py --ate 2026-11-03T10:00

# a mensagem do Embalarte chega entre dois tiques (replay retroativo) e o lote é protegido antes do corte
python scripts/rodar_replay.py --inicio 2026-10-29T14:00 --ate 2026-10-29T17:00 --fornecedores FP4615
```

Cada execução escreve um resumo em `reports/replay*.md`. O extrator padrão é o `mock` (determinístico). Para usar um LLM de verdade:

```bash
# chave no ambiente ou em .env (nunca commitar). Provedor: claude (ANTHROPIC_API_KEY) ou openai (OPENAI_API_KEY)
python scripts/validar_claude.py --extrator openai            # casos críticos + amostra; compara com o mock
SENTINELA_EXTRATOR=openai python scripts/rodar_replay.py ...   # roda a demo com o LLM
```

Status: **não há tela ainda** (a UI de narração da T10 está pendente); a demo hoje é por linha de comando e relatórios em `reports/`.

## Dados

Dados sintéticos fornecidos pelo evento. Coloque os CSVs de Pagamentos em `data/raw/` (não versionados). Só são usados dados fornecidos.

## Estrutura

```
CLAUDE.md                contexto mestre para a IA de código
docs/                    evento, domínio, arquitetura, dados, plano, demo, design, prompts
docs/fonte-oficial/      regras oficiais (fonte da verdade)
src/sentinela/           pacote: contratos, papéis, gateway, adaptadores, regras, decisão, UI
tests/                   testes (papéis, dados, regras, e2e)
assets/tokens.css        tokens visuais (identidade Gocase)
relatorio.md             erros da IA e correções
```

## Princípios

Papel `analista_cp` aplicado em código · texto de terceiros é dado, nunca instrução · fail-closed · alçada por soma · idempotência por evento/versão/ação · sem acesso ao futuro no replay · sem manutenção cadastral · sem métricas não reproduzidas.

## Licença e dados

Código do autor. Os dados do evento pertencem à GoGroup e são sintéticos; a identidade visual referencia a Gocase de forma ilustrativa, sem uso de logotipo.
