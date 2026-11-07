# Sentinela CP

**Cada pagamento conferido antes de o dinheiro sair.**

Agente de IA que joga o papel de analista de contas a pagar no Gogroup: confere título × NF × pedido de compra, lê comunicações de fornecedores, executa o que está dentro da alçada e chama a pessoa certa, com dossiê, quando encontra risco. Projeto individual para o **GoHacks Talent 2026**.

> A IA lê o que não é tabela; o código decide.

## Status

Em construção. Plano em [`docs/04-PLANO-DE-BUILD.md`](docs/04-PLANO-DE-BUILD.md). Nenhuma métrica de impacto foi publicada ainda: só entram números reproduzidos (ver [`docs/03-DADOS.md`](docs/03-DADOS.md)).

## Como rodar

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows (Git Bash); no Linux/macOS: .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # preencher ANTHROPIC_API_KEY (opcional: sem chave usa o extrator mock)
python scripts/validar_dados.py
pytest
streamlit run src/sentinela/ui/app.py
```

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
