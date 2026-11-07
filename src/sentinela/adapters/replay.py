"""ReplayAdapter: simula as ferramentas do analista_cp sobre os CSVs, com relógio (T2).

Princípios
- **Sem futuro:** toda leitura é filtrada pelo instante do SimClock. Comunicação, título,
  NF e pedido de compra só existem a partir da sua data de chegada/emissão; campos de
  aprovação/baixa/cancelamento posteriores ao instante são omitidos.
- **Estado no instante:** o status do título e o cadastro do fornecedor são reconstruídos
  "como eram" no instante. No instante de corte (02/11 08:00) coincidem com os CSVs.
  `alteracoes_cadastro.csv` é lido **apenas aqui dentro** para reconstruir o cadastro; nunca
  é exposto ao agente (consultar_historico_cadastro é de auditor/aprovador).
- **Ações não alteram os CSVs:** viram sobrescritas em memória, visíveis nas leituras seguintes.
- Pressupostos documentados: título agendado no momento do lançamento (não há carimbo de
  quando foi agendado); baixa de pagamento = data_baixa, ou fim do dia de data_pagamento.
"""

from __future__ import annotations

import csv
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..clock import NOME_BANCO, SimClock, parse_lote
from ..roles import FERRAMENTAS_ANALISTA_CP

ALCADA_ANALISTA = Decimal("5000")
CAMPO_PARA_COLUNA = {
    "banco": "banco",
    "agencia": "agencia",
    "conta": "conta",
    "chave_pix": "chave_pix",
    "email": "email_cadastrado",
    "telefone": "telefone_cadastrado",
    "endereco": "endereco",
}
CAMPOS_CORRIGIVEIS = {"valor", "numero_nf_digitado", "vencimento", "forma_pagamento", "linha_digitavel", "fornecedor_id"}
CAMPOS_SO_APROVADOR = {"fornecedor_id", "forma_pagamento", "linha_digitavel"}


class AcaoRecusada(Exception):
    """O sistema recusou a ação (regra do ambiente)."""


class AprovacaoNecessaria(AcaoRecusada):
    """Passa da alçada do analista_cp: usar solicitar_aprovacao."""


class LoteFechado(AcaoRecusada):
    """O lote já fechou: o dinheiro saiu ou está fora do alcance do analista."""


class NaoEncontrado(LookupError):
    """Registro inexistente (ou ainda não disponível no instante simulado)."""


@lru_cache(maxsize=None)
def _ler(caminho: str, delimitador: str = ",") -> tuple[dict[str, str], ...]:
    with open(caminho, encoding="utf-8", newline="") as f:
        return tuple(csv.DictReader(f, delimiter=delimitador))


def _dt(valor: str | None) -> datetime | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    if len(valor) == 10:
        return datetime.combine(date.fromisoformat(valor), time.min)
    return datetime.fromisoformat(valor)


def _digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def _dec(valor: Any) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except InvalidOperation as exc:
        raise AcaoRecusada(f"valor inválido: {valor!r}") from exc


class ReplayAdapter:
    def __init__(self, data_dir: Path | str, clock: SimClock) -> None:
        d = Path(data_dir)
        self.clock = clock
        self._titulos = {r["titulo_id"]: r for r in _ler(str(d / "contas_a_pagar.csv"))}
        self._fornecedores = {r["fornecedor_id"]: r for r in _ler(str(d / "fornecedores.csv"))}
        self._ocs = {r["oc_id"]: r for r in _ler(str(d / "pedidos_compra.csv"))}
        self._nfs = {r["chave_acesso"]: r for r in _ler(str(d / "notas_fiscais.csv"))}
        self._duplicatas: dict[str, list[dict[str, str]]] = {}
        for r in _ler(str(d / "nf_duplicatas.csv")):
            self._duplicatas.setdefault(r["chave_acesso"], []).append(r)
        self._comunicacoes = sorted(_ler(str(d / "comunicacoes_fornecedores.csv")), key=lambda r: r["data_hora"])
        self._politicas = _ler(str(d / "politicas.csv"))
        self._pessoas = self._carregar_pessoas()
        # só para reconstruir o cadastro no instante; NUNCA exposto ao agente
        self._alteracoes: dict[str, list[dict[str, str]]] = {}
        for r in sorted(_ler(str(d / "alteracoes_cadastro.csv")), key=lambda r: (r["data_hora"], r["alteracao_id"])):
            self._alteracoes.setdefault(r["fornecedor_id"], []).append(r)
        # estado mutável
        self._sobrescritas: dict[str, dict[str, Any]] = {}
        self.acoes: list[dict[str, Any]] = []
        self.solicitacoes: list[dict[str, Any]] = []
        self.acionamentos: list[dict[str, Any]] = []
        self.contatos: list[dict[str, Any]] = []
        self.respostas: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ infra
    def registrar_em(self, gateway) -> None:
        for nome in sorted(FERRAMENTAS_ANALISTA_CP):
            gateway.registrar(nome, getattr(self, nome))

    def _carregar_pessoas(self) -> dict[str, dict[str, str]]:
        pessoas: dict[str, dict[str, str]] = {}
        for r in self._politicas:
            m = re.fullmatch(r"pessoas\[(\d+)\]\.(\w+)", r["regra"])
            if r["secao"] == "acionamento_humano" and m:
                pessoas.setdefault(m.group(1), {})[m.group(2)] = r["valor"]
        return {p["pessoa_id"]: p for p in pessoas.values() if "pessoa_id" in p}

    @property
    def _t(self) -> datetime:
        return self.clock.agora

    def _registrar(self, ferramenta: str, parametros: dict[str, Any], resultado: Any) -> None:
        self.acoes.append({"instante": self._t, "ferramenta": ferramenta, "parametros": parametros, "resultado": resultado})

    # ---------------------------------------------------------------- títulos
    @staticmethod
    def _instante_pagamento(base: dict[str, str]) -> datetime | None:
        baixa = _dt(base["data_baixa"])
        if baixa:
            return baixa
        dia = _dt(base["data_pagamento"])
        return datetime.combine(dia.date(), time(23, 59)) if dia else None

    def _titulo_em(self, titulo_id: str) -> dict[str, Any] | None:
        base = self._titulos.get(titulo_id)
        t = self._t
        if base is None or _dt(base["data_lancamento"]) > t:
            return None
        v: dict[str, Any] = dict(base)
        cancelamento = _dt(base["data_cancelamento"])
        pagamento = self._instante_pagamento(base)
        if cancelamento is not None and cancelamento <= t:
            status = "cancelado"
        elif base["status"] == "pago" and pagamento is not None and pagamento <= t:
            status = "pago"
        elif base["lote_remessa"]:
            status = "agendado"
        else:
            status = "aberto"
        v["status"] = status
        if status in ("aberto", "cancelado"):
            v["lote_remessa"] = ""
        if status != "pago":
            v["data_pagamento"] = ""
        for campos, ref in (
            (("aprovado_por", "data_aprovacao"), _dt(base["data_aprovacao"])),
            (("baixado_por", "data_baixa"), _dt(base["data_baixa"])),
            (("cancelado_por", "data_cancelamento"), cancelamento),
        ):
            if ref is not None and ref > t:
                for c in campos:
                    v[c] = ""
        v.update(self._sobrescritas.get(titulo_id, {}))
        v["valor"] = _dec(v["valor"])
        return v

    def _titulo_visivel(self, titulo_id: str) -> dict[str, Any]:
        v = self._titulo_em(titulo_id)
        if v is None:
            raise NaoEncontrado(f"título {titulo_id} não encontrado")
        return v

    def consultar_titulo(self, titulo_id: str) -> dict[str, Any]:
        return self._titulo_visivel(titulo_id)

    def buscar_titulos(
        self,
        fornecedor_id: str | None = None,
        cnpj: str | None = None,
        numero_nf: str | None = None,
        valor_min: Any = None,
        valor_max: Any = None,
        vencimento_de: str | None = None,
        vencimento_ate: str | None = None,
        status: str | None = None,
        lancado_por: str | None = None,
        limite: int = 50,
    ) -> list[dict[str, Any]]:
        ids_cnpj: set[str] | None = None
        if cnpj:
            ids_cnpj = {fid for fid, f in self._fornecedores.items() if _digitos(f["cnpj"]) == _digitos(cnpj)}
        vmin, vmax = _dec(valor_min), _dec(valor_max)
        resultado: list[dict[str, Any]] = []
        for tid in self._titulos:
            v = self._titulo_em(tid)
            if v is None:
                continue
            if fornecedor_id and v["fornecedor_id"] != fornecedor_id:
                continue
            if ids_cnpj is not None and v["fornecedor_id"] not in ids_cnpj:
                continue
            if numero_nf and v["numero_nf_digitado"] != numero_nf:
                continue
            if vmin is not None and v["valor"] < vmin:
                continue
            if vmax is not None and v["valor"] > vmax:
                continue
            if vencimento_de and v["vencimento"] < vencimento_de:
                continue
            if vencimento_ate and v["vencimento"] > vencimento_ate:
                continue
            if status and v["status"] != status:
                continue
            if lancado_por and v["lancado_por"] != lancado_por:
                continue
            resultado.append(v)
            if len(resultado) >= limite:
                break
        return resultado

    # ----------------------------------------------------------- fornecedores
    def _cadastro_em(self, fornecedor_id: str) -> dict[str, str] | None:
        base = self._fornecedores.get(fornecedor_id)
        t = self._t
        if base is None or _dt(base["data_cadastro"]) > t:
            return None
        v = dict(base)
        alteracoes = self._alteracoes.get(fornecedor_id, [])
        for a in reversed(alteracoes):
            if _dt(a["data_hora"]) > t:
                v[CAMPO_PARA_COLUNA[a["campo"]]] = a["valor_anterior"]
        vigentes = [a for a in alteracoes if _dt(a["data_hora"]) <= t]
        if len(vigentes) != len(alteracoes):
            if vigentes:
                v["data_ultima_alteracao"] = vigentes[-1]["data_hora"]
                v["ultima_alteracao_por"] = vigentes[-1]["alterado_por"]
            else:
                v["data_ultima_alteracao"] = f"{base['data_cadastro']} 00:00:00"
                v["ultima_alteracao_por"] = base["cadastrado_por"]
        return v

    def consultar_fornecedor(self, fornecedor_id: str | None = None, cnpj: str | None = None) -> dict[str, str]:
        if not fornecedor_id and not cnpj:
            raise AcaoRecusada("informe fornecedor_id ou cnpj")
        if not fornecedor_id:
            achados = [fid for fid, f in self._fornecedores.items() if _digitos(f["cnpj"]) == _digitos(cnpj)]
            if not achados:
                raise NaoEncontrado(f"CNPJ {cnpj} não encontrado")
            fornecedor_id = achados[0]
        v = self._cadastro_em(fornecedor_id)
        if v is None:
            raise NaoEncontrado(f"fornecedor {fornecedor_id} não encontrado")
        return v

    # ------------------------------------------------------------------ agenda
    @staticmethod
    def _destino(titulo: dict[str, Any], cadastro: dict[str, str]) -> str:
        forma = titulo["forma_pagamento"]
        if forma == "boleto":
            return f"boleto banco {titulo['linha_digitavel'][:3]}"
        if forma == "ted":
            return f"ted {cadastro['banco']}/{cadastro['agencia']}/{cadastro['conta']}"
        return f"pix {cadastro['chave_pix']}"

    def listar_agenda_remessa(self, lote_remessa: str | None = None, data_prevista: str | None = None, banco: str | None = None) -> list[dict[str, Any]]:
        linhas: list[dict[str, Any]] = []
        for tid in self._titulos:
            v = self._titulo_em(tid)
            if v is None or v["status"] != "agendado" or not v["lote_remessa"]:
                continue
            lote = v["lote_remessa"]
            if self.clock.lote_fechado(lote):
                continue
            dia, sufixo = parse_lote(lote)
            if lote_remessa and lote != lote_remessa:
                continue
            if data_prevista and str(dia) != str(data_prevista)[:10]:
                continue
            if banco and banco.lower() not in NOME_BANCO[sufixo].lower() and banco.upper() != sufixo:
                continue
            cadastro = self._cadastro_em(v["fornecedor_id"]) or {}
            linhas.append(
                {
                    "lote_remessa": lote,
                    "banco_pagador": NOME_BANCO[sufixo],
                    "data_prevista": str(dia),
                    "horario_fechamento": self.clock.fechamento(lote).strftime("%H:%M"),
                    "titulo_id": tid,
                    "fornecedor_id": v["fornecedor_id"],
                    "valor": v["valor"],
                    "vencimento": v["vencimento"],
                    "forma_pagamento": v["forma_pagamento"],
                    "destino_pagamento": self._destino(v, cadastro) if cadastro else "",
                }
            )
        return sorted(linhas, key=lambda r: (r["data_prevista"], r["banco_pagador"], r["titulo_id"]))

    # ------------------------------------------------------------ OC, NF, comms
    def _oc_em(self, oc_id: str) -> dict[str, Any] | None:
        base = self._ocs.get(oc_id)
        t = self._t
        if base is None or _dt(base["data_emissao"]) > t:
            return None
        v: dict[str, Any] = dict(base)
        aprovacao = _dt(base["data_aprovacao"])
        if aprovacao is not None and aprovacao > t:
            v["aprovado_por"], v["data_aprovacao"], v["status"] = "", "", "pendente_aprovacao"
        v["valor_total"] = _dec(v["valor_total"])
        v["valor_mensal"] = _dec(v["valor_mensal"])
        return v

    def consultar_pedido_compra(self, oc_id: str | None = None, cnpj: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        if oc_id:
            v = self._oc_em(oc_id)
            if v is None:
                raise NaoEncontrado(f"pedido {oc_id} não encontrado")
            return v
        if cnpj:
            alvo = _digitos(cnpj)
            achados = [v for oid, b in self._ocs.items() if _digitos(b["cnpj_fornecedor"]) == alvo and (v := self._oc_em(oid))]
            if not achados:
                raise NaoEncontrado(f"nenhum pedido para o CNPJ {cnpj}")
            return achados
        raise AcaoRecusada("informe oc_id ou cnpj")

    def _nf_em(self, chave: str) -> dict[str, Any] | None:
        base = self._nfs.get(chave)
        t = self._t
        if base is None or _dt(base["data_recebimento_portal"]) > t:
            return None
        v: dict[str, Any] = dict(base)
        manifestacao = _dt(base["data_manifestacao"])
        if manifestacao is not None and manifestacao > t:
            v["manifestacao_destinatario"], v["data_manifestacao"] = "", ""
        v["valor_total"] = _dec(v["valor_total"])
        v["duplicatas"] = [
            {"n_dup": d["n_dup"], "vencimento": d["vencimento"], "valor": _dec(d["valor"])}
            for d in sorted(self._duplicatas.get(chave, []), key=lambda d: d["n_dup"])
        ]
        return v

    def consultar_nf(self, chave_acesso: str | None = None, cnpj_emitente: str | None = None, numero_nf: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        if chave_acesso:
            v = self._nf_em(chave_acesso)
            if v is None:
                raise NaoEncontrado(f"NF {chave_acesso} não encontrada")
            return v
        if cnpj_emitente and numero_nf:
            alvo = _digitos(cnpj_emitente)
            achados = [
                v for k, b in self._nfs.items() if _digitos(b["cnpj_emitente"]) == alvo and b["numero_nf"] == numero_nf and (v := self._nf_em(k))
            ]
            if not achados:
                raise NaoEncontrado(f"NF {numero_nf} do emitente {cnpj_emitente} não encontrada")
            return achados
        raise AcaoRecusada("informe chave_acesso, ou cnpj_emitente e numero_nf")

    def listar_comunicacoes(self, de: str | None = None, ate: str | None = None, remetente: str | None = None, texto: str | None = None) -> list[dict[str, str]]:
        t = self._t
        inicio = _dt(de)
        fim = _dt(ate)
        if fim is not None and len(str(ate).strip()) == 10:
            fim = datetime.combine(fim.date(), time.max)
        saida = []
        for r in self._comunicacoes:
            quando = _dt(r["data_hora"])
            if quando > t:
                continue
            if inicio and quando < inicio:
                continue
            if fim and quando > fim:
                continue
            if remetente and remetente.lower() not in r["remetente"].lower():
                continue
            if texto and texto.lower() not in f"{r['assunto']} {r['texto']} {r['anexos']}".lower():
                continue
            saida.append(dict(r))
        return saida

    def consultar_politicas(self) -> dict[str, dict[str, str]]:
        saida: dict[str, dict[str, str]] = {}
        for r in self._politicas:
            saida.setdefault(r["secao"], {})[r["regra"]] = r["valor"]
        return saida

    # ------------------------------------------------------------- execuções
    @staticmethod
    def _exigir_texto(valor: Any, nome: str) -> None:
        if not valor or not str(valor).strip():
            raise AcaoRecusada(f"{nome} obrigatório")

    @staticmethod
    def _exigir_evidencias(evidencias: Any) -> None:
        if not evidencias:
            raise AcaoRecusada("evidências obrigatórias")

    def _exigir_titulo_editavel(self, titulo_id: str) -> dict[str, Any]:
        v = self._titulo_visivel(titulo_id)
        if v["status"] in ("pago", "cancelado"):
            raise AcaoRecusada(f"título {titulo_id} está {v['status']}")
        if v["status"] == "agendado" and self.clock.lote_fechado(v["lote_remessa"]):
            raise LoteFechado(v["lote_remessa"])
        return v

    def retirar_do_lote(self, titulo_id: str, motivo: str) -> dict[str, Any]:
        self._exigir_texto(motivo, "motivo")
        v = self._titulo_visivel(titulo_id)
        if v["status"] != "agendado" or not v["lote_remessa"]:
            raise AcaoRecusada(f"título {titulo_id} não está em lote (status {v['status']})")
        lote = v["lote_remessa"]
        if self.clock.lote_fechado(lote):
            raise LoteFechado(lote)
        self._sobrescritas.setdefault(titulo_id, {}).update(status="aberto", lote_remessa="")
        r = {"titulo_id": titulo_id, "estado": "aberto", "lote_anterior": lote}
        self._registrar("retirar_do_lote", {"titulo_id": titulo_id, "motivo": motivo}, r)
        return r

    def agendar_titulo(self, titulo_id: str, lote_remessa: str) -> dict[str, Any]:
        v = self._titulo_visivel(titulo_id)
        if v["status"] != "aberto":
            raise AcaoRecusada(f"título {titulo_id} não está aberto (status {v['status']})")
        try:
            dia, sufixo = parse_lote(lote_remessa)
        except ValueError as exc:
            raise AcaoRecusada(str(exc)) from exc
        if not self.clock.eh_dia_util(dia):
            raise AcaoRecusada(f"{dia} não é dia útil de remessa")
        if self.clock.lote_fechado(lote_remessa):
            raise LoteFechado(lote_remessa)
        if dia < _dt(v["data_lancamento"]).date():
            raise AcaoRecusada("data prevista não pode ser anterior ao lançamento")
        if v["valor"] > ALCADA_ANALISTA:
            raise AprovacaoNecessaria("valor acima de R$ 5.000,00: usar solicitar_aprovacao")
        vencimento = self.clock.proximo_dia_util(date.fromisoformat(v["vencimento"]), inclusive=True)
        if dia < vencimento:
            raise AprovacaoNecessaria("antecipação exige aprovação dupla")
        self._sobrescritas.setdefault(titulo_id, {}).update(status="agendado", lote_remessa=lote_remessa, banco_pagador=NOME_BANCO[sufixo])
        r = {"titulo_id": titulo_id, "estado": "agendado", "lote_remessa": lote_remessa}
        self._registrar("agendar_titulo", {"titulo_id": titulo_id, "lote_remessa": lote_remessa}, r)
        return r

    def cancelar_titulo(self, titulo_id: str, motivo: str, evidencias: Any) -> dict[str, Any]:
        self._exigir_texto(motivo, "motivo")
        self._exigir_evidencias(evidencias)
        v = self._exigir_titulo_editavel(titulo_id)
        if v["valor"] > ALCADA_ANALISTA:
            raise AprovacaoNecessaria("cancelamento acima de R$ 5.000,00: usar solicitar_aprovacao")
        self._sobrescritas.setdefault(titulo_id, {}).update(
            status="cancelado", lote_remessa="", cancelado_por="agente_analista_cp", data_cancelamento=self._t.isoformat(sep=" ")
        )
        r = {"titulo_id": titulo_id, "estado": "cancelado"}
        self._registrar("cancelar_titulo", {"titulo_id": titulo_id, "motivo": motivo, "evidencias": evidencias}, r)
        return r

    def corrigir_lancamento(self, titulo_id: str, campo: str, valor_novo: Any, evidencias: Any, justificativa: str | None = None) -> dict[str, Any]:
        if campo not in CAMPOS_CORRIGIVEIS:
            raise AcaoRecusada(f"campo não corrigível: {campo}")
        self._exigir_evidencias(evidencias)
        v = self._exigir_titulo_editavel(titulo_id)
        if campo in CAMPOS_SO_APROVADOR:
            raise AprovacaoNecessaria(f"corrigir {campo} exige aprovador")
        anterior = v[campo]
        if campo == "valor":
            novo = _dec(valor_novo)
            if novo is None or novo <= 0:
                raise AcaoRecusada("valor deve ser positivo")
            if abs(novo - v["valor"]) > ALCADA_ANALISTA:
                raise AprovacaoNecessaria("mudança de valor acima de R$ 5.000,00: usar solicitar_aprovacao")
        elif campo == "vencimento":
            try:
                novo = date.fromisoformat(str(valor_novo)).isoformat()
            except ValueError as exc:
                raise AcaoRecusada(f"vencimento inválido: {valor_novo!r}") from exc
        else:
            self._exigir_texto(valor_novo, "valor_novo")
            novo = str(valor_novo)
        self._sobrescritas.setdefault(titulo_id, {})[campo] = novo
        r = {"titulo_id": titulo_id, "campo": campo, "valor_anterior": anterior, "valor_novo": novo}
        self._registrar("corrigir_lancamento", {"titulo_id": titulo_id, "campo": campo, "valor_novo": str(novo), "justificativa": justificativa, "evidencias": evidencias}, r)
        return r

    def contatar_fornecedor(self, fornecedor_id: str, canal: str, mensagem: str) -> dict[str, Any]:
        if canal not in ("email", "telefone"):
            raise AcaoRecusada("o ambiente só aceita o canal do cadastro (email ou telefone)")
        self._exigir_texto(mensagem, "mensagem")
        cadastro = self.consultar_fornecedor(fornecedor_id=fornecedor_id)
        destino = cadastro["email_cadastrado"] if canal == "email" else cadastro["telefone_cadastrado"]
        r = {"fornecedor_id": fornecedor_id, "canal": canal, "enviado_para": destino, "resposta": "pendente (chega em algumas horas)"}
        self.contatos.append({"instante": self._t, **r, "mensagem": mensagem})
        self._registrar("contatar_fornecedor", {"fornecedor_id": fornecedor_id, "canal": canal}, r)
        return r

    def solicitar_aprovacao(self, acao: str, parametros: Any, evidencias: Any, aprovador_humano: str | None = None) -> dict[str, Any]:
        self._exigir_texto(acao, "acao")
        self._exigir_evidencias(evidencias)
        sid = f"SOL-{len(self.solicitacoes) + 1:04d}"
        item = {"solicitacao_id": sid, "instante": self._t, "acao": acao, "parametros": parametros, "evidencias": evidencias, "aprovador_humano": aprovador_humano, "estado": "pendente"}
        self.solicitacoes.append(item)
        self._registrar("solicitar_aprovacao", {"acao": acao}, {"solicitacao_id": sid})
        return {"solicitacao_id": sid, "estado": "pendente"}

    def acionar_pessoa(self, pessoa_id: str, motivo: str, urgencia: str = "normal", titulos: Any = ()) -> dict[str, Any]:
        pessoa = self._pessoas.get(pessoa_id)
        if pessoa is None:
            raise AcaoRecusada(f"pessoa desconhecida: {pessoa_id}")
        self._exigir_texto(motivo, "motivo")
        aid = f"ACI-{len(self.acionamentos) + 1:04d}"
        item = {"acionamento_id": aid, "instante": self._t, "pessoa_id": pessoa_id, "nome": pessoa["nome"], "motivo": motivo, "urgencia": urgencia, "titulos": tuple(titulos)}
        self.acionamentos.append(item)
        self._registrar("acionar_pessoa", {"pessoa_id": pessoa_id, "urgencia": urgencia}, {"acionamento_id": aid})
        return {"acionamento_id": aid, "pessoa": pessoa["nome"], "cargo": pessoa.get("cargo", "")}

    def responder_colaborador(self, solicitacao_id: str, mensagem: str) -> dict[str, Any]:
        self._exigir_texto(solicitacao_id, "solicitacao_id")
        self._exigir_texto(mensagem, "mensagem")
        self.respostas.append({"instante": self._t, "solicitacao_id": solicitacao_id, "mensagem": mensagem})
        self._registrar("responder_colaborador", {"solicitacao_id": solicitacao_id}, "enviada")
        return {"solicitacao_id": solicitacao_id, "estado": "respondida"}
