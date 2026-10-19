"""
Testes das melhorias: novas situações de veículo (pendência adm. / baixado),
edição do vencimento das parcelas do IPVA e relatório combinado
(licenciamento + multas).
"""
import io
import os
import tempfile
from datetime import date, timedelta

import pytest

_DB_FILE = os.path.join(tempfile.mkdtemp(prefix="despachante-teste-"), "novas.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ.setdefault("FLASK_ENV", "development")

CPF = "11144477735"


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app("development")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture()
def client(app):
    from app import db, aplicar_migracoes_leves
    from app.models.escritorio import Escritorio
    from app.services.configuracao_service import ConfiguracaoService
    from app.services.auth_service import AuthService

    with app.app_context():
        db.drop_all()
        db.create_all()
        aplicar_migracoes_leves(app)
        esc = db.session.get(Escritorio, 1)
        esc.slug, esc.nome = "escritorio-a", "Escritório A"
        db.session.commit()
        ConfiguracaoService(db.session, esc.id).seed_defaults()
        AuthService(db.session).seed_admin(esc.id)

    c = app.test_client()
    c.post("/e/escritorio-a/login", data={"nome_usuario": "admin", "senha": "admin123"})
    c.post("/trocar-senha", data={"nova_senha": "SenhaA12345", "confirmar_senha": "SenhaA12345"})
    return c


def _cliente(c):
    r = c.post("/api/clientes", json={"nome": "Fulano", "tipo_pessoa": "PF", "cpf": CPF,
                                      "telefone": "11999998888", "email": "", "observacao": ""})
    assert r.status_code == 200, r.get_json()
    return c.get("/api/clientes").get_json()[0]["id"]


def _veiculo(c, cid, placa="ABC1D23", situacao="ativo"):
    r = c.post("/api/veiculos", json={"cliente_id": cid, "placa": placa, "especie": "passeio",
                                      "situacao": situacao, "marca_modelo": "Gol",
                                      "renavam": "12345678901", "proprietario": "Fulano"})
    assert r.status_code == 200, r.get_json()
    return [v for v in c.get(f"/api/clientes/{cid}/veiculos").get_json() if v["placa"] == placa][0]["id"]


# ── 1. Situações de veículo ──────────────────────────────────────────────────

def test_novas_situacoes_de_veiculo(client):
    from app.models.veiculo import Veiculo
    assert "pendencia_adm" in Veiculo.SITUACOES_ATIVAS
    assert "baixado" not in Veiculo.SITUACOES_ATIVAS
    assert Veiculo.SITUACAO_LABEL["pendencia_adm"] == "Pendência adm."

    cid = _cliente(client)
    _veiculo(client, cid, "ABC1D23", "pendencia_adm")
    _veiculo(client, cid, "XYZ9A87", "baixado")
    sit = {v["placa"]: v["situacao"] for v in client.get(f"/api/clientes/{cid}/veiculos").get_json()}
    assert sit == {"ABC1D23": "pendencia_adm", "XYZ9A87": "baixado"}


def test_telas_oferecem_e_destacam_as_novas_situacoes(client):
    cid = _cliente(client)
    _veiculo(client, cid, "ABC1D23", "pendencia_adm")
    pagina = client.get(f"/clientes/{cid}/veiculos").get_data(as_text=True)
    assert 'value="pendencia_adm"' in pagina and 'value="baixado"' in pagina
    assert "badge-pendencia-adm" in pagina and "badge-baixado" in pagina
    geral = client.get("/veiculos").get_data(as_text=True)
    assert 'value="pendencia_adm"' in geral and "badge-pendencia-adm" in geral
    assert ".badge-pendencia-adm" in pagina and "#B84A00" in pagina  # laranja


def test_importacao_aceita_novas_situacoes(app, client):
    from app import db
    from app.services.importacao_service import ImportacaoService
    with app.app_context():
        svc = ImportacaoService(db.session, tempfile.mkdtemp(), 1)
        for texto, esperado in [("pendencia_adm", "pendencia_adm"), ("Pendência adm.", "pendencia_adm"),
                                ("PENDENCIA ADMINISTRATIVA", "pendencia_adm"), ("baixado", "baixado"),
                                ("Baixado", "baixado"), ("qualquer coisa", "ativo")]:
            erro, dados = svc._preparar_linha_veiculo("ABC1D23", "12345678901", "Fulano", "Gol", texto, "passeio", "")
            assert not erro and dados["situacao"] == esperado, (texto, erro, dados)


# ── 2. Editar vencimento das parcelas do IPVA ────────────────────────────────

def _ipva_parcelado(c, parcelas=3, primeira=None):
    cid = _cliente(c)
    vid = _veiculo(c, cid)
    c.post("/api/ipva", json={"veiculo_id": vid, "ano_referencia": 2026, "valor": 300.0,
                              "vencimento": "2026-01-10", "tipo_pagamento": "parcelado"})
    iid = c.get(f"/api/veiculos/{vid}/ipva").get_json()[0]["id"]
    primeira = primeira or (date.today() + timedelta(days=30)).isoformat()
    r = c.post(f"/api/ipva/{iid}/parcelas/gerar",
               json={"num_parcelas": parcelas, "valor_total": 300.0, "data_primeira": primeira})
    assert r.status_code == 200, r.get_json()
    return iid, c.get(f"/api/ipva/{iid}/parcelas").get_json()["parcelas"]


def test_editar_vencimento_de_parcela(client):
    iid, parcelas = _ipva_parcelado(client)
    p2 = parcelas[1]
    nova = (date.today() + timedelta(days=90)).isoformat()
    r = client.put(f"/api/ipva/parcelas/{p2['id']}/vencimento", json={"vencimento": nova})
    assert r.status_code == 200, r.get_json()
    atual = client.get(f"/api/ipva/{iid}/parcelas").get_json()["parcelas"]
    assert [p["vencimento"] for p in atual][1] == nova
    assert atual[0]["vencimento"] == parcelas[0]["vencimento"]  # as outras não mudam
    assert atual[1]["status"] == "pendente"


def test_editar_vencimento_para_data_passada_marca_vencido_e_volta_a_pendente(client):
    iid, parcelas = _ipva_parcelado(client)
    pid = parcelas[0]["id"]
    ontem = (date.today() - timedelta(days=1)).isoformat()
    assert client.put(f"/api/ipva/parcelas/{pid}/vencimento", json={"vencimento": ontem}).status_code == 200
    assert client.get(f"/api/ipva/{iid}/parcelas").get_json()["parcelas"][0]["status"] == "vencido"
    amanha = (date.today() + timedelta(days=1)).isoformat()
    assert client.put(f"/api/ipva/parcelas/{pid}/vencimento", json={"vencimento": amanha}).status_code == 200
    assert client.get(f"/api/ipva/{iid}/parcelas").get_json()["parcelas"][0]["status"] == "pendente"


def test_nao_edita_vencimento_de_parcela_paga_nem_data_invalida(client):
    iid, parcelas = _ipva_parcelado(client)
    pid = parcelas[0]["id"]
    for ruim in ("", "31/12/2026", "2026-13-40", None):
        r = client.put(f"/api/ipva/parcelas/{pid}/vencimento", json={"vencimento": ruim})
        assert r.status_code == 400, ruim
    client.post(f"/api/ipva/parcelas/{pid}/quitar")
    r = client.put(f"/api/ipva/parcelas/{pid}/vencimento", json={"vencimento": "2030-01-01"})
    assert r.status_code == 400
    assert client.get(f"/api/ipva/{iid}/parcelas").get_json()["parcelas"][0]["vencimento"] == parcelas[0]["vencimento"]


def test_edicao_de_vencimento_fica_no_log(app, client):
    from app import db
    from app.models.log_acao import LogAcao
    iid, parcelas = _ipva_parcelado(client)
    client.put(f"/api/ipva/parcelas/{parcelas[0]['id']}/vencimento", json={"vencimento": "2031-05-05"})
    with app.app_context():
        log = db.session.query(LogAcao).filter_by(acao="editar_vencimento_parcela_ipva").first()
        assert log is not None and "2031-05-05" in (log.detalhe or "")


# ── 3. Relatório combinado licenciamento + multas ────────────────────────────

def _dados_relatorio(c):
    cid = _cliente(c)
    vid = _veiculo(c, cid)
    c.post("/api/licenciamento", json={"veiculo_id": vid, "ano_referencia": 2026, "valor": 100,
                                       "vencimento": "2026-10-20", "pago": False})
    # multa com infração antiga (julho) e vencimento em outubro, e outra sem data de infração
    c.post("/api/multas", json={"veiculo_id": vid, "auto_infracao": "A1", "data_infracao": "2026-07-01",
                                "valor": 195, "vencimento": "2026-10-25", "pago": False})
    c.post("/api/multas", json={"veiculo_id": vid, "auto_infracao": "A2", "valor": 130,
                                "vencimento": "2026-10-28", "pago": False})


def _buscar(c, **cfg):
    r = c.post("/api/relatorios/dados", json=cfg)
    assert r.status_code == 200, r.get_json()
    return r.get_json()["dados"]


def test_relatorio_combinado_com_periodo_traz_licenciamento_e_multas(client):
    _dados_relatorio(client)
    periodo = {"data_inicio": "2026-10-01", "data_fim": "2026-10-31"}
    dados = _buscar(client, tipos=["licenciamento", "multas"], filtros=periodo)
    assert sorted(d["tipo_registro"] for d in dados) == ["LICENCIAMENTO", "MULTAS", "MULTAS"]
    assert all(d["situacao"] == "ATIVO" for d in dados)  # situação aparece também nas multas


def test_periodo_das_multas_pela_data_da_infracao_continua_disponivel(client):
    _dados_relatorio(client)
    periodo = {"data_inicio": "2026-06-01", "data_fim": "2026-07-31"}
    dados = _buscar(client, tipos=["multas"], filtros=periodo, filtro_data_multas="infracao")
    assert [d["auto_infracao"] for d in dados] == ["A1"]
    # template antigo (sem a chave) com só multas mantém o comportamento antigo
    dados = _buscar(client, tipos=["multas"], filtros=periodo)
    assert [d["auto_infracao"] for d in dados] == ["A1"]


def test_exportar_excel_do_relatorio_combinado_inclui_multas(client):
    import openpyxl
    _dados_relatorio(client)
    config = {"tipos": ["licenciamento", "multas"],
              "filtros": {"data_inicio": "2026-10-01", "data_fim": "2026-10-31"}, "mostrar_totais": False}
    campos = [{"id": "tipo_registro", "label": "Tipo"}, {"id": "placa", "label": "Placa"},
              {"id": "valor", "label": "Valor"}]
    r = client.post("/api/relatorios/exportar/excel", json={"config": config, "campos_visiveis": campos})
    assert r.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(r.data)).active
    tipos = [ws.cell(row=i, column=1).value for i in range(2, ws.max_row + 1)]
    assert sorted(tipos) == ["LICENCIAMENTO", "MULTAS", "MULTAS"]
    r = client.post("/api/relatorios/exportar/pdf", json={"config": config, "campos_visiveis": campos})
    assert r.status_code == 200 and r.data[:4] == b"%PDF"
