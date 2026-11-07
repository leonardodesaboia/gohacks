from datetime import datetime, timedelta

import pytest

from sentinela.contracts import Papel
from sentinela.gateway import (
    FerramentaDesconhecida,
    HandlerNaoRegistrado,
    LimiteDiarioExcedido,
    ToolGateway,
)
from sentinela.roles import (
    FERRAMENTAS_ANALISTA_CP,
    FERRAMENTAS_PROIBIDAS_ANALISTA_CP,
    PermissaoNegada,
)


class Relogio:
    def __init__(self, inicio="2026-11-03T08:00:00"):
        self.t = datetime.fromisoformat(inicio)

    def __call__(self):
        return self.t

    def avancar(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def gw(relogio):
    g = ToolGateway(Papel.ANALISTA_CP, relogio)
    for f in FERRAMENTAS_ANALISTA_CP:
        g.registrar(f, lambda f=f, **kw: {"ferramenta": f, **kw})
    return g


def test_so_analista_cp(relogio):
    with pytest.raises(ValueError):
        ToolGateway(Papel.AUDITOR, relogio)


@pytest.mark.parametrize("ferramenta", sorted(FERRAMENTAS_ANALISTA_CP))
def test_permitida_executa_e_registra_instante_simulado(gw, relogio, ferramenta):
    r = gw.chamar(ferramenta, titulo_id="TP1")
    assert r == {"ferramenta": ferramenta, "titulo_id": "TP1"}
    ultima = gw.historico[-1]
    assert (ultima.ferramenta, ultima.resultado, ultima.instante) == (ferramenta, "ok", relogio.t)


@pytest.mark.parametrize("ferramenta", sorted(FERRAMENTAS_PROIBIDAS_ANALISTA_CP))
def test_proibida_nega_registra_e_nao_chama_handler(relogio, ferramenta):
    chamado = []
    g = ToolGateway(Papel.ANALISTA_CP, relogio, handlers={ferramenta: lambda **kw: chamado.append(kw)})
    with pytest.raises(PermissaoNegada):
        g.chamar(ferramenta, fornecedor_id="FP1")
    assert chamado == []
    assert g.historico[-1].resultado == "negada"
    assert g.historico[-1].instante == relogio.t


def test_nao_registra_handler_de_ferramenta_proibida(relogio):
    g = ToolGateway(Papel.ANALISTA_CP, relogio)
    with pytest.raises(PermissaoNegada):
        g.registrar("consultar_extrato", lambda **kw: None)


def test_ferramenta_desconhecida(gw):
    with pytest.raises(FerramentaDesconhecida):
        gw.chamar("apagar_banco")
    assert gw.historico[-1].resultado == "desconhecida"


def test_sem_handler(relogio):
    g = ToolGateway(Papel.ANALISTA_CP, relogio)
    with pytest.raises(HandlerNaoRegistrado):
        g.chamar("consultar_titulo", titulo_id="TP1")
    assert g.historico[-1].resultado == "sem_handler"


@pytest.mark.parametrize("ferramenta,limite", [("acionar_pessoa", 40), ("contatar_fornecedor", 60)])
def test_limite_diario(gw, relogio, ferramenta, limite):
    for _ in range(limite):
        gw.chamar(ferramenta, x=1)
    with pytest.raises(LimiteDiarioExcedido):
        gw.chamar(ferramenta, x=1)
    assert gw.historico[-1].resultado == "limite"
    assert gw.uso_no_dia(ferramenta) == limite


def test_limite_zera_no_dia_seguinte(gw, relogio):
    for _ in range(40):
        gw.chamar("acionar_pessoa", x=1)
    relogio.avancar(days=1)
    gw.chamar("acionar_pessoa", x=1)
    assert gw.uso_no_dia("acionar_pessoa") == 1


def test_leitura_nao_tem_limite(gw):
    for _ in range(200):
        gw.chamar("consultar_titulo", titulo_id="TP1")


def test_tentativa_negada_nao_consome_limite(gw):
    with pytest.raises(PermissaoNegada):
        gw.chamar("consultar_extrato", banco="meridiano")
    assert gw.uso_no_dia("acionar_pessoa") == 0


def test_erro_do_handler_e_registrado_e_propagado(relogio):
    def falha(**kw):
        raise TimeoutError("sem resposta")

    g = ToolGateway(Papel.ANALISTA_CP, relogio, handlers={"retirar_do_lote": falha})
    with pytest.raises(TimeoutError):
        g.chamar("retirar_do_lote", titulo_id="TP1", motivo="x")
    assert g.historico[-1].resultado == "erro"
    assert "TimeoutError" in g.historico[-1].detalhe
