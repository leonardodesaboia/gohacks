"""Persistência T7: idempotência de eventos, evidências, decisões e ações.

Não chama ferramentas. O chamador consulta o estado externo após timeout e passa
o resultado a `reconciliar_acao`; estado incerto nunca autoriza retry cego.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping

from pydantic import BaseModel

from .contracts import Decisao, Evidencia


def _normalizar(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ValueError("Decimal não finito")
        normalizado = valor.normalize()
        return {"$decimal": "0" if normalizado == 0 else format(normalizado, "f")}
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, BaseModel):
        return _normalizar(valor.model_dump(mode="python"))
    if is_dataclass(valor) and not isinstance(valor, type):
        return _normalizar(asdict(valor))
    if isinstance(valor, Mapping):
        return {str(k): _normalizar(v) for k, v in sorted(valor.items(), key=lambda item: str(item[0]))}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    if isinstance(valor, (set, frozenset)):
        return sorted((_normalizar(v) for v in valor), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(valor, (str, int, bool)) or valor is None:
        return valor
    if isinstance(valor, float):
        raise TypeError("float proibido na persistência de domínio; use Decimal")
    raise TypeError(f"tipo não serializável: {type(valor).__name__}")


def serializar(valor: Any) -> str:
    return json.dumps(_normalizar(valor), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _restaurar(valor: Any) -> Any:
    if isinstance(valor, dict):
        if set(valor) == {"$decimal"}:
            return Decimal(valor["$decimal"])
        return {k: _restaurar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_restaurar(v) for v in valor]
    return valor


def hash_payload(valor: Any) -> str:
    return hashlib.sha256(serializar(valor).encode("utf-8")).hexdigest()


def chave_acao(titulo_id: str, acao: str, parametros: Mapping[str, Any], versao_evidencias: int) -> str:
    """Chave estável distinta da chave da decisão e do id de evento."""
    return hash_payload((titulo_id, acao, parametros, versao_evidencias))


class ConflitoIdempotencia(ValueError):
    """Uma mesma chave foi reutilizada com conteúdo diferente."""


class ReconciliacaoPendente(RuntimeError):
    """Uma ação incerta pode ter sido aplicada; não repetir sem conferir o sistema."""


@dataclass(frozen=True)
class AcaoPersistida:
    chave: str
    estado: str
    tentativas: int
    resultado: Any | None


class Store:
    def __init__(self, caminho: Path | str) -> None:
        self.db = sqlite3.connect(str(caminho), timeout=30, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS eventos (
                id TEXT PRIMARY KEY, tipo TEXT NOT NULL, instante TEXT NOT NULL,
                payload_hash TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS versoes_evidencias (
                titulo_id TEXT PRIMARY KEY, versao INTEGER NOT NULL CHECK(versao > 0),
                fingerprint TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidencias (
                id TEXT PRIMARY KEY, titulo_id TEXT NOT NULL, fonte TEXT NOT NULL,
                registro TEXT NOT NULL, versao INTEGER NOT NULL,
                instante_disponibilidade TEXT NOT NULL, payload_hash TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisoes (
                chave_idempotencia TEXT PRIMARY KEY, titulo_id TEXT NOT NULL,
                versao_evidencias INTEGER NOT NULL, acao TEXT NOT NULL, regra TEXT NOT NULL,
                payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
                UNIQUE(titulo_id, versao_evidencias)
            );
            CREATE TABLE IF NOT EXISTS acoes (
                chave TEXT PRIMARY KEY, titulo_id TEXT NOT NULL, versao_evidencias INTEGER NOT NULL,
                acao TEXT NOT NULL, parametros_hash TEXT NOT NULL, estado TEXT NOT NULL
                    CHECK(estado IN ('reservada','em_execucao','incerta','aplicada','nao_aplicada','falha')),
                resultado TEXT, tentativas INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS incidentes (
                id TEXT PRIMARY KEY, fornecedor_id TEXT NOT NULL, motivo TEXT NOT NULL,
                pessoas_acionadas TEXT NOT NULL DEFAULT '[]',
                UNIQUE(fornecedor_id, motivo)
            );
            CREATE TABLE IF NOT EXISTS alertas (
                incidente_id TEXT NOT NULL REFERENCES incidentes(id), pessoa_id TEXT NOT NULL,
                estado TEXT NOT NULL CHECK(estado IN ('reservado','enviado','incerto')),
                PRIMARY KEY(incidente_id, pessoa_id)
            );
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT, instante TEXT NOT NULL,
                tipo TEXT NOT NULL, referencia TEXT NOT NULL, payload TEXT NOT NULL
            );
        """)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _inicio(self) -> None:
        self.db.execute("BEGIN IMMEDIATE")

    def _fim(self, erro: BaseException | None = None) -> None:
        self.db.execute("ROLLBACK" if erro else "COMMIT")

    def _auditar(self, tipo: str, referencia: str, payload: Any, instante: datetime) -> None:
        self.db.execute("INSERT INTO auditoria(instante,tipo,referencia,payload) VALUES(?,?,?,?)",
                        (instante.isoformat(), tipo, referencia, serializar(payload)))

    def registrar_evento(self, evento_id: str, tipo: str, instante: datetime, payload: Any) -> bool:
        digest = hash_payload(payload)
        self._inicio()
        try:
            row = self.db.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
            if row:
                if (row["tipo"], row["instante"], row["payload_hash"]) != (tipo, instante.isoformat(), digest):
                    raise ConflitoIdempotencia(f"evento {evento_id} com conteúdo diferente")
                self._fim()
                return False
            self.db.execute("INSERT INTO eventos VALUES(?,?,?,?,?)",
                            (evento_id, tipo, instante.isoformat(), digest, serializar(payload)))
            self._auditar("evento", evento_id, {"tipo": tipo, "hash": digest}, instante)
            self._fim()
            return True
        except BaseException as exc:
            self._fim(exc)
            raise

    def registrar_evidencia(self, titulo_id: str, evidencia_id: str, evidencia: Evidencia) -> int:
        """Mesmo ID+conteúdo é no-op; evidência nova ou alterada sobe a versão do título."""
        digest = hash_payload(evidencia)
        self._inicio()
        try:
            anterior = self.db.execute("SELECT titulo_id,payload_hash,versao FROM evidencias WHERE id=?", (evidencia_id,)).fetchone()
            if anterior:
                if anterior["payload_hash"] != digest or anterior["titulo_id"] != titulo_id:
                    raise ConflitoIdempotencia(f"evidência {evidencia_id} mudou de conteúdo/título; use novo id")
                versao = self.versao_evidencias(titulo_id)
                self._fim()
                return versao
            estado = self.db.execute("SELECT versao, fingerprint FROM versoes_evidencias WHERE titulo_id=?", (titulo_id,)).fetchone()
            versao = (estado["versao"] if estado else 0) + 1
            self.db.execute("INSERT INTO evidencias VALUES(?,?,?,?,?,?,?,?)",
                            (evidencia_id, titulo_id, evidencia.fonte, evidencia.registro, versao,
                             evidencia.instante_disponibilidade.isoformat(), digest, serializar(evidencia)))
            fingerprint = hash_payload((estado["fingerprint"] if estado else "", evidencia_id, digest))
            self.db.execute("INSERT INTO versoes_evidencias VALUES(?,?,?) ON CONFLICT(titulo_id) DO UPDATE SET versao=excluded.versao, fingerprint=excluded.fingerprint",
                            (titulo_id, versao, fingerprint))
            self._auditar("evidencia", evidencia_id, {"titulo_id": titulo_id, "versao": versao}, evidencia.instante_disponibilidade)
            self._fim()
            return versao
        except BaseException as exc:
            self._fim(exc)
            raise

    def versao_evidencias(self, titulo_id: str) -> int:
        row = self.db.execute("SELECT versao FROM versoes_evidencias WHERE titulo_id=?", (titulo_id,)).fetchone()
        return row["versao"] if row else 0

    def registrar_decisao(self, titulo_id: str, decisao: Decisao, instante: datetime | None = None) -> bool:
        payload = serializar(decisao)
        self._inicio()
        try:
            if decisao.versao_evidencias != self.versao_evidencias(titulo_id):
                raise ConflitoIdempotencia("decisão baseada em evidência obsoleta")
            row = self.db.execute("SELECT * FROM decisoes WHERE titulo_id=? AND versao_evidencias=?",
                                  (titulo_id, decisao.versao_evidencias)).fetchone()
            if row:
                if row["chave_idempotencia"] != decisao.chave_idempotencia or row["payload_hash"] != hash_payload(decisao):
                    raise ConflitoIdempotencia("decisão diferente para a mesma versão de evidências")
                self._fim()
                return False
            ocupada = self.db.execute("SELECT titulo_id FROM decisoes WHERE chave_idempotencia=?",
                                      (decisao.chave_idempotencia,)).fetchone()
            if ocupada:
                raise ConflitoIdempotencia("chave de decisão já usada para outro título ou versão")
            self.db.execute("INSERT INTO decisoes VALUES(?,?,?,?,?,?,?)",
                            (decisao.chave_idempotencia, titulo_id, decisao.versao_evidencias,
                             decisao.acao.value, decisao.regra_aplicada, hash_payload(decisao), payload))
            self._auditar("decisao", decisao.chave_idempotencia, {"titulo_id": titulo_id, "versao": decisao.versao_evidencias}, instante or datetime.now())
            self._fim()
            return True
        except BaseException as exc:
            self._fim(exc)
            raise

    def reservar_acao(self, titulo_id: str, acao: str, parametros: Mapping[str, Any], versao_evidencias: int) -> AcaoPersistida:
        """Retorna estado existente; o executor só inicia se `estado == reservada`."""
        chave = chave_acao(titulo_id, acao, parametros, versao_evidencias)
        self._inicio()
        try:
            if versao_evidencias != self.versao_evidencias(titulo_id):
                raise ConflitoIdempotencia("ação baseada em evidência obsoleta")
            row = self.db.execute("SELECT * FROM acoes WHERE chave=?", (chave,)).fetchone()
            if row is None:
                self.db.execute("INSERT INTO acoes(chave,titulo_id,versao_evidencias,acao,parametros_hash,estado) VALUES(?,?,?,?,?,?)",
                                (chave, titulo_id, versao_evidencias, acao, hash_payload(parametros), "reservada"))
            self._fim()
            return self.obter_acao(chave)
        except BaseException as exc:
            self._fim(exc)
            raise

    def obter_acao(self, chave: str) -> AcaoPersistida | None:
        row = self.db.execute("SELECT * FROM acoes WHERE chave=?", (chave,)).fetchone()
        return AcaoPersistida(chave, row["estado"], row["tentativas"], _restaurar(json.loads(row["resultado"])) if row["resultado"] else None) if row else None

    def iniciar_acao(self, chave: str) -> AcaoPersistida:
        """Transição atômica reservada/não_aplicada → em_execucao; incerta exige reconciliação."""
        self._inicio()
        try:
            row = self.db.execute("SELECT * FROM acoes WHERE chave=?", (chave,)).fetchone()
            if row is None:
                raise KeyError(chave)
            if row["estado"] == "incerta":
                raise ReconciliacaoPendente(chave)
            if row["estado"] not in ("reservada", "nao_aplicada"):
                raise ConflitoIdempotencia(f"ação {chave} já está {row['estado']}")
            if row["versao_evidencias"] != self.versao_evidencias(row["titulo_id"]):
                raise ConflitoIdempotencia("evidências mudaram antes da execução; reavalie")
            self.db.execute("UPDATE acoes SET estado='em_execucao',tentativas=tentativas+1 WHERE chave=?", (chave,))
            self._fim()
            return self.obter_acao(chave)
        except BaseException as exc:
            self._fim(exc)
            raise

    def marcar_resultado(self, chave: str, estado: str, resultado: Any = None,
                        instante: datetime | None = None) -> AcaoPersistida:
        if estado not in ("aplicada", "falha", "incerta"):
            raise ValueError("estado final inválido")
        self._inicio()
        try:
            row = self.db.execute("SELECT * FROM acoes WHERE chave=?", (chave,)).fetchone()
            if row is None:
                raise KeyError(chave)
            if row["estado"] != "em_execucao":
                raise ConflitoIdempotencia("resultado só pode seguir execução iniciada")
            self.db.execute("UPDATE acoes SET estado=?,resultado=? WHERE chave=?",
                            (estado, serializar(resultado) if resultado is not None else None, chave))
            self._auditar("resultado_acao", chave, {"estado": estado, "resultado_hash": hash_payload(resultado)}, instante or datetime.now())
            self._fim()
            return self.obter_acao(chave)
        except BaseException as exc:
            self._fim(exc)
            raise

    def reconciliar_acao(self, chave: str, consulta_estado: Callable[[], bool | None], resultado: Any = None,
                         instante: datetime | None = None) -> AcaoPersistida:
        """Consulta externa: True=aplicada, False=ausência comprovada, None=incerto.

        Não faz I/O externo dentro de transação. `False` habilita retry em outra chamada
        a iniciar_acao; erro/None preserva estado incerto. Não executa ação.
        """
        acao = self.obter_acao(chave)
        if acao is None:
            raise KeyError(chave)
        if acao.estado not in ("em_execucao", "incerta"):
            return acao
        try:
            observado = consulta_estado()
        except Exception:
            observado = None
        if observado not in (True, False, None):
            raise TypeError("consulta_estado deve devolver True, False ou None")
        estado = "aplicada" if observado is True else "nao_aplicada" if observado is False else "incerta"
        self._inicio()
        try:
            row = self.db.execute("SELECT estado FROM acoes WHERE chave=?", (chave,)).fetchone()
            if row["estado"] not in ("em_execucao", "incerta"):
                raise ConflitoIdempotencia("ação mudou durante reconciliação")
            self.db.execute("UPDATE acoes SET estado=?,resultado=? WHERE chave=?",
                            (estado, serializar(resultado) if observado is True and resultado is not None else None, chave))
            self._auditar("reconciliacao", chave, {"estado": estado}, instante or datetime.now())
            self._fim()
            return self.obter_acao(chave)
        except BaseException as exc:
            self._fim(exc)
            raise

    def reservar_alerta(self, fornecedor_id: str, motivo: str, pessoa_id: str) -> bool:
        """Reserva único alerta por fornecedor+motivo+pessoa, inclusive entre títulos."""
        incidente_id = hash_payload((fornecedor_id, motivo))
        self._inicio()
        try:
            self.db.execute("INSERT OR IGNORE INTO incidentes(id,fornecedor_id,motivo) VALUES(?,?,?)",
                            (incidente_id, fornecedor_id, motivo))
            cursor = self.db.execute("INSERT OR IGNORE INTO alertas VALUES(?,?,?)",
                                     (incidente_id, pessoa_id, "reservado"))
            self._fim()
            return cursor.rowcount == 1
        except BaseException as exc:
            self._fim(exc)
            raise

    def marcar_alerta(self, fornecedor_id: str, motivo: str, pessoa_id: str, estado: str,
                     instante: datetime | None = None) -> None:
        if estado not in ("enviado", "incerto"):
            raise ValueError(estado)
        incidente_id = hash_payload((fornecedor_id, motivo))
        self._inicio()
        try:
            row = self.db.execute("SELECT estado FROM alertas WHERE incidente_id=? AND pessoa_id=?",
                                  (incidente_id, pessoa_id)).fetchone()
            if row is None or row["estado"] not in ("reservado", "incerto"):
                raise ConflitoIdempotencia("alerta não reservado ou já enviado")
            self.db.execute("UPDATE alertas SET estado=? WHERE incidente_id=? AND pessoa_id=?",
                            (estado, incidente_id, pessoa_id))
            if estado == "enviado":
                pessoas = [r[0] for r in self.db.execute("SELECT pessoa_id FROM alertas WHERE incidente_id=? AND estado='enviado' ORDER BY pessoa_id", (incidente_id,))]
                self.db.execute("UPDATE incidentes SET pessoas_acionadas=? WHERE id=?", (serializar(pessoas), incidente_id))
            self._auditar("alerta", incidente_id, {"pessoa": pessoa_id, "estado": estado}, instante or datetime.now())
            self._fim()
        except BaseException as exc:
            self._fim(exc)
            raise

    def auditar(self, tipo: str, referencia: str, payload: Any, instante: datetime) -> None:
        self._inicio()
        try:
            self._auditar(tipo, referencia, payload, instante)
            self._fim()
        except BaseException as exc:
            self._fim(exc)
            raise
