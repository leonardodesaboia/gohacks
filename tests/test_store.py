from datetime import datetime
from decimal import Decimal

import pytest

from sentinela.contracts import Acao, Decisao, Evidencia
from sentinela.store import (
    ConflitoIdempotencia, ReconciliacaoPendente, Store, chave_acao, hash_payload,
)

AGORA = datetime(2026, 11, 2, 8)
TITULO = "TP431754"


def evidencia(registro="EM571116"):
    return Evidencia(fonte="comunicacoes_fornecedores", registro=registro,
                     trecho="2a via boleto", instante_disponibilidade=AGORA)


def decisao(versao, chave="dec-1"):
    return Decisao(acao=Acao.RETIRAR, regra_aplicada="identidade_boleto", alcada="analista_cp",
                   versao_evidencias=versao, chave_idempotencia=chave,
                   motivo="beneficiário divergente")


def test_evento_duplicado_e_conflito_rollback(tmp_path):
    with Store(tmp_path / "store.db") as s:
        assert s.registrar_evento("EV1", "ComunicacaoRecebida", AGORA, {"titulo": TITULO})
        assert not s.registrar_evento("EV1", "ComunicacaoRecebida", AGORA, {"titulo": TITULO})
        with pytest.raises(ConflitoIdempotencia):
            s.registrar_evento("EV1", "ComunicacaoRecebida", AGORA, {"titulo": "outro"})
        assert s.db.execute("SELECT count(*) FROM eventos").fetchone()[0] == 1
        assert s.db.execute("SELECT count(*) FROM auditoria").fetchone()[0] == 1


def test_evidencia_nova_reavalia_mesmo_titulo_sem_repetir_acao(tmp_path):
    with Store(tmp_path / "store.db") as s:
        assert s.registrar_evidencia(TITULO, "E1", evidencia()) == 1
        assert s.registrar_evidencia(TITULO, "E1", evidencia()) == 1
        assert s.registrar_decisao(TITULO, decisao(1))
        assert not s.registrar_decisao(TITULO, decisao(1))
        parametros = {"valor": Decimal("11740.00"), "motivo": "identidade"}
        a = s.reservar_acao(TITULO, Acao.RETIRAR.value, parametros, 1)
        assert a.estado == "reservada"
        assert s.iniciar_acao(a.chave).tentativas == 1
        assert s.marcar_resultado(a.chave, "aplicada", {"estado": "aberto"}).estado == "aplicada"
        assert s.reservar_acao(TITULO, Acao.RETIRAR.value, dict(reversed(list(parametros.items()))), 1).estado == "aplicada"
        with pytest.raises(ConflitoIdempotencia):
            s.iniciar_acao(a.chave)
        assert s.registrar_evidencia(TITULO, "E2", evidencia("EM571119")) == 2
        with pytest.raises(ConflitoIdempotencia):
            s.registrar_evidencia("TP431459", "E1", evidencia())
        with pytest.raises(ConflitoIdempotencia):
            s.registrar_decisao(TITULO, decisao(1))
        assert s.registrar_decisao(TITULO, decisao(2, "dec-2"))
        with pytest.raises(ConflitoIdempotencia):
            s.registrar_decisao(TITULO, decisao(2, "dec-1"))
        assert s.reservar_acao(TITULO, Acao.RETIRAR.value, parametros, 2).chave != a.chave
        assert s.db.execute("SELECT count(*) FROM decisoes").fetchone()[0] == 2


def test_timeout_consulta_antes_de_nova_tentativa(tmp_path):
    with Store(tmp_path / "s.db") as s:
        s.registrar_evidencia(TITULO, "E1", evidencia())
        a = s.reservar_acao(TITULO, Acao.RETIRAR.value, {"titulo_id": TITULO}, 1)
        s.iniciar_acao(a.chave)
        assert s.reconciliar_acao(a.chave, lambda: None).estado == "incerta"
        with pytest.raises(ReconciliacaoPendente):
            s.iniciar_acao(a.chave)
        assert s.reconciliar_acao(a.chave, lambda: True, {"status": "aberto"}).estado == "aplicada"
        assert s.obter_acao(a.chave).tentativas == 1


def test_ausencia_comprovada_permita_retry_e_erro_de_consulta_nao(tmp_path):
    with Store(tmp_path / "s.db") as s:
        s.registrar_evidencia(TITULO, "E1", evidencia())
        a = s.reservar_acao(TITULO, Acao.RETIRAR.value, {}, 1)
        s.iniciar_acao(a.chave)

        def falha():
            raise TimeoutError("consulta indisponível")

        assert s.reconciliar_acao(a.chave, falha).estado == "incerta"
        assert s.reconciliar_acao(a.chave, lambda: False).estado == "nao_aplicada"
        assert s.iniciar_acao(a.chave).tentativas == 2
        s.marcar_resultado(a.chave, "aplicada")


def test_reabertura_sqlite_acao_em_execucao_exige_reconciliacao(tmp_path):
    caminho = tmp_path / "s.db"
    with Store(caminho) as s:
        s.registrar_evidencia(TITULO, "E1", evidencia())
        a = s.reservar_acao(TITULO, Acao.RETIRAR.value, {}, 1)
        s.iniciar_acao(a.chave)
    with Store(caminho) as s:
        assert s.obter_acao(a.chave).estado == "em_execucao"
        with pytest.raises(ConflitoIdempotencia):
            s.iniciar_acao(a.chave)
        assert s.reconciliar_acao(a.chave, lambda: True).estado == "aplicada"


def test_alertas_agrupados_por_incidente_e_pessoa(tmp_path):
    with Store(tmp_path / "s.db") as s:
        assert s.reservar_alerta("FP4615", "troca_bancaria", "PS01")
        assert not s.reservar_alerta("FP4615", "troca_bancaria", "PS01")
        s.marcar_alerta("FP4615", "troca_bancaria", "PS01", "enviado")
        assert not s.reservar_alerta("FP4615", "troca_bancaria", "PS01")
        assert s.reservar_alerta("FP4615", "troca_bancaria", "PS08")
        assert s.db.execute("SELECT count(*) FROM incidentes").fetchone()[0] == 1
        assert s.db.execute("SELECT count(*) FROM alertas").fetchone()[0] == 2


def test_serializacao_decimal_estavel_e_float_recusado():
    assert chave_acao(TITULO, "retirar", {"a": Decimal("1.20"), "b": 1}, 2) == chave_acao(
        TITULO, "retirar", {"b": 1, "a": Decimal("1.20")}, 2)
    assert hash_payload({"a": Decimal("1.20")}) != hash_payload({"a": "1.20"})
    assert hash_payload({"a": Decimal("1.20")}) == hash_payload({"a": Decimal("1.2")})
    with pytest.raises(TypeError, match="float"):
        hash_payload({"valor": 1.2})
    with pytest.raises(ValueError, match="não finito"):
        hash_payload({"valor": Decimal("NaN")})


def test_resultado_decimal_reabre_sem_float(tmp_path):
    caminho = tmp_path / "store.db"
    with Store(caminho) as s:
        s.registrar_evidencia(TITULO, "E1", evidencia())
        a = s.reservar_acao(TITULO, Acao.RETIRAR.value, {}, 1)
        s.iniciar_acao(a.chave)
        s.marcar_resultado(a.chave, "aplicada", {"valor": Decimal("11.70")})
    with Store(caminho) as s:
        assert s.obter_acao(a.chave).resultado["valor"] == Decimal("11.7")
        assert isinstance(s.obter_acao(a.chave).resultado["valor"], Decimal)
