"""T0: valida os CSVs de data/raw contra o dicionário oficial.

Uso:  python scripts/validar_dados.py [--data-dir data/raw]
Sai com código 1 se faltar coluna, arquivo ou houver data fora do formato esperado.
Também confirma que comunicacoes_fornecedores é CSV (os dicionários dizem .jsonl)
e mostra quais arquivos o papel analista_cp pode ou não ler.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

LEGIVEL, BLOQUEADO, APOIO, CONFIG = "legivel", "bloqueado", "apoio", "config"

# nome -> (delimitador, colunas esperadas, acesso do analista_cp)
ESPERADO: dict[str, tuple[str, tuple[str, ...], str]] = {
    "fornecedores": (",", ("fornecedor_id", "razao_social", "nome_fantasia", "cnpj", "categoria", "uf", "banco", "agencia", "conta", "chave_pix", "forma_pagamento_padrao", "email_cadastrado", "telefone_cadastrado", "data_cadastro", "cadastrado_por", "inscricao_estadual", "endereco", "cidade", "cep", "contato_financeiro", "prazo_pagamento_padrao", "responsavel_interno", "contrato_id", "status_cadastro", "data_ultima_alteracao", "ultima_alteracao_por"), LEGIVEL),
    "contas_a_pagar": (",", ("titulo_id", "fornecedor_id", "numero_nf_digitado", "oc_id", "parcela", "valor", "vencimento", "forma_pagamento", "linha_digitavel", "cnpj_beneficiario_boleto", "origem_lancamento", "lancado_por", "data_lancamento", "status", "data_pagamento", "banco_pagador", "lote_remessa", "centro_custo", "conta_contabil", "historico", "nivel_aprovacao", "aprovado_por", "data_aprovacao", "baixado_por", "data_baixa", "cancelado_por", "data_cancelamento"), LEGIVEL),
    "agenda_remessa": (",", ("lote_remessa", "banco_pagador", "data_prevista", "horario_fechamento", "titulo_id", "fornecedor_id", "valor", "vencimento", "forma_pagamento", "destino_pagamento"), LEGIVEL),
    "pedidos_compra": (",", ("oc_id", "cod_fornecedor_compras", "cnpj_fornecedor", "nome_fornecedor", "data_emissao", "descricao", "tipo", "valor_total", "valor_mensal", "condicao_pagamento", "centro_custo", "aprovado_por", "data_aprovacao", "status", "quantidade", "unidade", "valor_unitario", "solicitante", "comprador", "local_entrega", "data_entrega_prevista"), LEGIVEL),
    "notas_fiscais": (",", ("chave_acesso", "modelo", "numero_nf", "serie", "cnpj_emitente", "razao_social_emitente", "data_emissao", "valor_total", "oc_informada", "informacoes_complementares", "data_recebimento_portal", "cnpj_destinatario", "razao_social_destinatario", "natureza_operacao", "cfop", "valor_produtos_servicos", "valor_ipi", "valor_icms", "valor_iss", "situacao_sefaz", "manifestacao_destinatario", "data_manifestacao"), LEGIVEL),
    "nf_duplicatas": (",", ("chave_acesso", "n_dup", "vencimento", "valor"), LEGIVEL),
    "comunicacoes_fornecedores": (",", ("comunicacao_id", "data_hora", "canal", "remetente", "nome_remetente", "destinatario", "assunto", "texto", "anexos"), LEGIVEL),
    "feriados_bancarios": (",", ("data", "dia_semana", "descricao", "abrangencia", "sem_expediente_bancario", "afeta_remessa"), CONFIG),
    "politicas": (",", ("secao", "regra", "valor"), CONFIG),
    "ferramentas": (",", ("ferramenta", "tipo", "papeis_permitidos", "descricao", "parametros", "limites", "custo_rs"), CONFIG),
    "alteracoes_cadastro": (",", ("alteracao_id", "data_hora", "fornecedor_id", "campo", "valor_anterior", "valor_novo", "alterado_por", "origem", "confirmacao_registrada", "confirmacao_como"), BLOQUEADO),
    "extrato_banco_meridiano": (",", ("data", "tipo", "descricao", "documento", "valor", "saldo"), BLOQUEADO),
    "extrato_banco_litoral": (";", ("Data", "Histórico", "Docto", "Valor (R$)", "Saldo (R$)"), BLOQUEADO),
    "log_auditoria_erp": (",", ("log_id", "data_hora", "usuario", "estacao", "modulo", "acao", "entidade", "entidade_id", "detalhe"), BLOQUEADO),
    "aprovacoes": (",", ("aprovacao_id", "titulo_id", "data_hora", "aprovador", "perfil_aprovador", "nivel_exigido", "valor_titulo", "decisao", "origem", "lote_remessa"), BLOQUEADO),
    "usuarios_sistema": (",", ("login", "nome", "email", "sistema", "cargo", "area", "perfil", "alcada_rs", "pode_alterar_dados_bancarios", "data_admissao", "data_desligamento", "status", "gestor", "pessoa_id", "estacao_trabalho"), BLOQUEADO),
    "lotes_remessa": (",", ("lote_remessa", "banco_pagador", "conta_debito", "data_pagamento", "horario_fechamento", "arquivo_remessa", "qtd_titulos", "valor_total", "gerado_por", "data_hora_geracao", "assinado_por", "data_hora_assinatura", "data_hora_envio", "arquivo_retorno", "data_hora_retorno", "qtd_pagos", "valor_pago", "qtd_rejeitados", "valor_rejeitado", "situacao"), BLOQUEADO),
    "retorno_remessa": (",", ("lote_remessa", "arquivo_retorno", "sequencial", "titulo_id", "favorecido", "forma_pagamento", "banco_favorecido", "valor_nominal", "valor_pago", "data_pagamento", "codigo_ocorrencia", "descricao_ocorrencia", "autenticacao"), BLOQUEADO),
    "dda_boletos": (",", ("dda_id", "data_registro", "cnpj_pagador", "banco_cobrador", "nome_banco_cobrador", "beneficiario", "cnpj_beneficiario", "numero_documento", "nosso_numero", "valor", "vencimento", "linha_digitavel", "situacao", "data_situacao"), BLOQUEADO),
    "centros_custo": (",", ("codigo", "nome", "empresa", "area", "responsavel", "responsavel_pessoa_id", "orcamento_mensal_rs", "ativo"), APOIO),
    "plano_contas": (",", ("conta", "descricao", "tipo", "grupo", "natureza", "conta_pai", "aceita_lancamento", "categorias_fornecedor"), APOIO),
    "contratos_fornecedores": (",", ("contrato_id", "fornecedor_id", "oc_id", "tipo", "objeto", "valor_mensal", "valor_variavel", "condicao_pagamento", "dia_vencimento", "forma_pagamento", "inicio_vigencia", "prazo", "fim_vigencia_atual", "indice_reajuste", "mes_reajuste", "data_ultimo_reajuste", "aviso_previo_dias", "multa_rescisoria", "gestor_contrato", "gestor_pessoa_id", "status"), APOIO),
    "recebimentos_mercadoria": (",", ("recebimento_id", "data_hora_recebimento", "local_recebimento", "cnpj_destinatario", "chave_acesso", "numero_nf", "cnpj_emitente", "oc_id", "descricao_item", "quantidade_recebida", "unidade", "volumes", "conferente", "situacao", "observacao", "entrada_estoque"), APOIO),
    "contas_bancarias_empresa": (",", ("conta_id", "banco_codigo", "banco", "agencia", "conta", "tipo", "finalidade", "conta_contabil", "convenio_pagamentos", "layout_remessa", "horario_corte_remessa", "saldo_em", "saldo_rs", "limite_cheque_especial_rs", "limite_diario_pagamentos_rs", "limite_por_transacao_avulsa_rs", "assinatura_remessa", "dupla_assinatura_acima_de_rs", "gerente_conta", "data_abertura", "situacao"), APOIO),
}

# contagens documentadas (dicionário/parâmetros); divergência vira aviso
LINHAS_DOCUMENTADAS = {"fornecedores": 131}

ISO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATAHORA = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?$")
BR_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
# (arquivo, coluna) -> (regex, aceita vazio)
FORMATO_DATAS = {
    ("contas_a_pagar", "vencimento"): (ISO_DATA, False),
    ("contas_a_pagar", "data_lancamento"): (ISO_DATAHORA, False),
    ("contas_a_pagar", "data_pagamento"): (ISO_DATA, True),
    ("agenda_remessa", "data_prevista"): (ISO_DATA, False),
    ("agenda_remessa", "vencimento"): (ISO_DATA, False),
    ("nf_duplicatas", "vencimento"): (ISO_DATA, False),
    ("notas_fiscais", "data_emissao"): (ISO_DATA, False),
    ("comunicacoes_fornecedores", "data_hora"): (ISO_DATAHORA, False),
    ("pedidos_compra", "data_emissao"): (ISO_DATA, False),
    ("extrato_banco_litoral", "Data"): (BR_DATA, False),
    ("extrato_banco_meridiano", "data"): (ISO_DATA, False),
}


@dataclass
class ResultadoArquivo:
    nome: str
    acesso: str
    linhas: int = 0
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def validar_arquivo(data_dir: Path, nome: str) -> ResultadoArquivo:
    delimitador, esperadas, acesso = ESPERADO[nome]
    res = ResultadoArquivo(nome=nome, acesso=acesso)
    caminho = data_dir / f"{nome}.csv"
    if not caminho.exists():
        res.erros.append("arquivo ausente")
        return res
    contadores_data: dict[str, int] = {}
    with caminho.open(encoding="utf-8", newline="") as f:
        leitor = csv.DictReader(f, delimiter=delimitador)
        cabecalho = tuple(leitor.fieldnames or ())
        faltando = [c for c in esperadas if c not in cabecalho]
        extras = [c for c in cabecalho if c not in esperadas]
        if faltando:
            res.erros.append(f"colunas ausentes: {faltando}")
        if extras:
            res.avisos.append(f"colunas não documentadas: {extras}")
        monitoradas = {c: FORMATO_DATAS[(nome, c)] for (n, c) in FORMATO_DATAS if n == nome and c in cabecalho}
        for linha in leitor:
            res.linhas += 1
            for coluna, (padrao, aceita_vazio) in monitoradas.items():
                valor = (linha.get(coluna) or "").strip()
                if not valor and aceita_vazio:
                    continue
                if not padrao.match(valor):
                    contadores_data[coluna] = contadores_data.get(coluna, 0) + 1
    for coluna, n in contadores_data.items():
        res.erros.append(f"{n} valores de '{coluna}' fora do formato de data esperado")
    esperado_linhas = LINHAS_DOCUMENTADAS.get(nome)
    if esperado_linhas is not None and res.linhas != esperado_linhas:
        res.avisos.append(f"{res.linhas} linhas, documentação cita {esperado_linhas}")
    if res.linhas == 0:
        res.erros.append("arquivo sem linhas de dados")
    return res


def validar(data_dir: Path) -> tuple[list[ResultadoArquivo], list[str]]:
    globais: list[str] = []
    if (data_dir / "comunicacoes_fornecedores.jsonl").exists():
        globais.append("existe comunicacoes_fornecedores.jsonl além do .csv: definir qual é a fonte")
    if not (data_dir / "comunicacoes_fornecedores.csv").exists():
        globais.append("comunicacoes_fornecedores.csv ausente (os dicionários dizem .jsonl, o arquivo distribuído é .csv)")
    return [validar_arquivo(data_dir, n) for n in ESPERADO], globais


def imprimir(resultados: list[ResultadoArquivo], globais: list[str]) -> int:
    rotulo = {LEGIVEL: "LÊ (ferramenta do analista_cp)", BLOQUEADO: "NÃO EXPOR ao analista_cp", APOIO: "apoio (validar na T2)", CONFIG: "config/calendário"}
    total_erros = len(globais)
    for grupo in (LEGIVEL, BLOQUEADO, APOIO, CONFIG):
        print(f"\n== {rotulo[grupo]}")
        for r in (x for x in resultados if x.acesso == grupo):
            status = "ERRO" if r.erros else ("aviso" if r.avisos else "ok")
            print(f"  [{status:5}] {r.nome:30} {r.linhas:>7} linhas")
            for e in r.erros:
                print(f"           ERRO: {e}")
            for a in r.avisos:
                print(f"           aviso: {a}")
            total_erros += len(r.erros)
    for g in globais:
        print(f"\nERRO GLOBAL: {g}")
    print(f"\n{'FALHOU' if total_erros else 'OK'}: {total_erros} erro(s)")
    return 1 if total_erros else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=os.environ.get("SENTINELA_DATA_DIR", "data/raw"))
    args = ap.parse_args(argv)
    resultados, globais = validar(Path(args.data_dir))
    return imprimir(resultados, globais)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
