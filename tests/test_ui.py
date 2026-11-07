from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("sentinela.store")
pytest.importorskip("sentinela.executor")
pytest.importorskip("sentinela.threeway")
pytest.importorskip("streamlit")

from sentinela.loop import TipoEvento  # noqa: E402
from sentinela.ui import viewmodel as vm  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (RAIZ / "data" / "raw").exists(), reason="data/raw ausente")
APP = RAIZ / "src" / "sentinela" / "ui" / "app.py"


# ------------------------------------------------------------------ viewmodel
def test_cenario_embalarte_a_mensagem_chega_entre_dois_tiques():
    s = vm.criar_sessao("embalarte")
    assert len(s.antes) == 28 and all(x["forma"] in ("ted", "pix") for x in s.antes.values())
    vm.avancar(s)
    vm.avancar(s)  # 14:00 e 15:00: a mensagem ainda não existe
    assert not any(x["protegido"] for x in vm.lote_antes_depois(s))
    assert s.clock.agora == datetime(2026, 10, 29, 16, 0)
    vm.avancar(s)  # 16:00: a mensagem aparece
    depois = vm.lote_antes_depois(s)
    assert all(x["protegido"] and x["lote_agora"] == "—" for x in depois)
    assert any(e.tipo is TipoEvento.COMUNICACAO and e.referencia == "EM571119" for e in s.registros[-1].eventos)


def test_cartoes_alto_primeiro_e_dados_sensiveis_mascarados():
    s = vm.criar_sessao("embalarte")
    for _ in range(3):
        vm.avancar(s)
    cartoes, sem_alerta = vm.cartoes_comunicacao(s)
    altos = [c["id"] for c in cartoes if c["nivel"] == "alto"]
    assert altos == sorted(altos, key=lambda i: next(c["data_hora"] for c in cartoes if c["id"] == i)) and {"EM571119", "EM571116", "EM570977", "EM570998", "EM571100"} == set(altos)
    assert [c["nivel"] for c in cartoes][:5] == ["alto"] * 5 and sem_alerta > 200
    emb = next(c for c in cartoes if c["id"] == "EM571119")
    texto = str(emb["ia_leu"])
    assert "4471203-9" not in texto and "****-9" in texto  # conta mascarada
    assert "85.990.602/0001-96" not in texto and "85.***.***/0001-96" in texto  # CNPJ mascarado
    assert any("instrução dirigida ao sistema" in k for k, _ in emb["ia_leu"])  # a instrução plantada aparece como ignorada
    assert emb["pessoas"] == ["PS01"] and emb["trecho"]


def test_chamados_e_totais_batem_com_o_replay():
    s = vm.criar_sessao("embalarte")
    for _ in range(3):
        vm.avancar(s)
    t, ch = vm.totais(s), vm.chamados(s)
    assert t["tiques"] == 3 and t["retirados"] == 29 and t["pessoas"] == len(ch["acionamentos"]) == 6
    assert {"Renata Paiva (PS01)", "Lívia Campos (PS08)", "Marcos Teles (PS02)"} == {a["pessoa"] for a in ch["acionamentos"]}
    assert all(a["dossie"] for a in ch["acionamentos"])


def test_contagem_regressiva_e_pre_fechamento_no_cenario_do_corte():
    s = vm.criar_sessao("corte")
    c = vm.contagem(s)
    assert (c["lote"], c["restante"], c["urgente"]) == ("RM20261103-MER", "26h00", False)  # 02/11 é feriado: primeiro corte em 03/11 10:00
    n = vm.avancar_ate_pre_fechamento(s)
    assert n == 26 and s.clock.agora == datetime(2026, 11, 3, 10, 0)
    assert any(e.tipo is TipoEvento.PRE_FECHAMENTO for e in s.registros[-1].eventos)
    depois = vm.contagem(s)
    assert (depois["lote"], depois["restante"]) == ("RM20261103-LIT", "4h00")  # próximo corte: Banco Litoral às 14:00 do mesmo dia
    assert vm.totais(s)["corrigidos"] == 11 and vm.totais(s)["retirados"] == 31


def test_sessao_criada_em_uma_thread_pode_ser_usada_em_outra():
    # o Streamlit roda cada interação numa thread diferente: sem isso o primeiro clique daria ProgrammingError do SQLite
    import threading

    s = vm.criar_sessao("embalarte")
    erros = []

    def usar():
        try:
            vm.avancar(s)
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    t = threading.Thread(target=usar)
    t.start()
    t.join()
    assert not erros and len(s.registros) == 1


def test_avancar_para_no_fim_do_periodo():
    s = vm.criar_sessao("embalarte")
    while vm.avancar(s) is not None:
        pass
    assert s.clock.terminou and vm.avancar(s) is None


def test_mascarar_texto_cobre_cnpj_conta_linha_digitavel_e_pix_e_preserva_o_resto():
    from sentinela.ui.theme import mascarar_texto

    m = mascarar_texto("Banco 905, Ag. 0001, C/C 4471203-9, CNPJ 85.990.602/0001-96 ou 85990602000196, Pix 244c83bc-a736-4fff-afa2-6e12fdcf5242")
    assert "4471203-9" not in m and "C/C ****-9" in m
    assert "85.990.602" not in m and "85990602000196" not in m and m.count("85.***.***/0001-96") == 2
    assert "244c83bc-a736" not in m and "****…f5242" in m
    assert "28995217401010503090100000967141715440002124941" not in mascarar_texto("linha 28995217401010503090100000967141715440002124941")
    neutro = "Segue a segunda via da NF 57551, valor R$ 11.740,00, vencimento 03/11/2026."
    assert mascarar_texto(neutro) == neutro and mascarar_texto(None) == "" and mascarar_texto("") == ""


# ------------------------------------------------------------------ app (Streamlit AppTest)
def _app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(APP), default_timeout=240)


def _markdown(at):
    return "\n".join(m.value for m in at.markdown)


def test_app_abre_sem_erro_e_declara_replay_local():
    at = _app().run()
    assert not at.exception
    texto = _markdown(at)
    assert "REPLAY LOCAL" in texto and "Cada pagamento conferido antes de o dinheiro sair." in texto
    assert [b.label for b in at.sidebar.button][:2] == ["Executar tique e avançar 1 hora", "Avançar até o pré-fechamento"]


def test_app_mostra_o_risco_alto_depois_de_tres_tiques():
    at = _app().run()
    for _ in range(3):
        at.sidebar.button(key="avancar").click().run()
    assert not at.exception
    texto = _markdown(at)
    assert "RISCO ALTO" in texto and "EM571119" in texto and "gc-ia" in texto and "gc-regra" in texto  # "IA leu"/"Regra decidiu" vêm por CSS
    assert "4471203-9" not in texto  # a conta pedida pelo golpista não aparece em claro
    assert "RETIRADO DO LOTE" in texto and "29" in texto


def test_app_escapa_html_de_mensagem_hostil():
    from sentinela.ui import viewmodel as vm2

    s = vm2.criar_sessao("embalarte")
    s.adapter._comunicacoes.append({
        "comunicacao_id": "EMX001", "data_hora": "2026-10-29 10:00:00", "canal": "email", "remetente": "seguranca@falso-banco.net",
        "nome_remetente": "Banco <b>Falso</b>", "destinatario": "contasapagar@gogroup.com.br",
        "assunto": "<script>alert(1)</script> token urgente", "texto": "Informe o código do token hoje <img src=x onerror=alert(2)>", "anexos": "",
    })
    s.adapter._comunicacoes.sort(key=lambda r: r["data_hora"])
    at = _app()
    at.session_state["sessao"] = s
    at.session_state["config"] = ("embalarte", "mock")
    at.run()
    at.sidebar.button(key="avancar").click().run()
    assert not at.exception
    texto = _markdown(at)
    assert "&lt;script&gt;" in texto and "<script>" not in texto
    assert "<img src=x" not in texto and "<b>Falso</b>" not in texto
