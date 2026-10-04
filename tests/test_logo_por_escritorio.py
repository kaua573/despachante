"""
Logo por escritório.

Bug corrigido: o upload gravava sempre `logo.<ext>` — um arquivo só para todos
os escritórios. Quando o B enviava a logo dele, a do A passava a mostrar a do
B (e, ao trocar/remover, um apagava o arquivo do outro).
"""
import io
import os
import tempfile

import pytest

_DB_FILE = os.path.join(tempfile.mkdtemp(prefix="despachante-teste-"), "logo.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ.setdefault("FLASK_ENV", "development")


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app("development")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture(autouse=True)
def ambiente(app, tmp_path):
    from app import db, aplicar_migracoes_leves
    from app.models.escritorio import Escritorio
    from app.services.auth_service import AuthService
    from app.services.configuracao_service import ConfiguracaoService
    app.config["LOGO_DIR"] = str(tmp_path / "logo")
    os.makedirs(app.config["LOGO_DIR"])
    with app.app_context():
        db.drop_all()
        db.create_all()
        aplicar_migracoes_leves(app)
        a = db.session.get(Escritorio, 1)
        a.slug, a.nome = "a", "A"
        b = Escritorio(slug="b", nome="B", ativo=True)
        db.session.add(b)
        db.session.commit()
        for esc in (a, b):
            ConfiguracaoService(db.session, esc.id).seed_defaults()
            AuthService(db.session).seed_admin(esc.id)
    yield


def _logado(app, slug):
    c = app.test_client()
    c.post(f"/e/{slug}/login", data={"nome_usuario": "admin", "senha": "admin123"})
    c.post("/trocar-senha", data={"nova_senha": "SenhaForte12345", "confirmar_senha": "SenhaForte12345"})
    return c


def _enviar(client, nome_arq, conteudo):
    return client.post(
        "/api/configuracoes/escritorio",
        data={"nome": "x", "logo": (io.BytesIO(conteudo), nome_arq)},
        content_type="multipart/form-data",
    )


def _logo_de(app, escritorio_id):
    from app import db
    from app.services.configuracao_service import ConfiguracaoService
    with app.app_context():
        return ConfiguracaoService(db.session, escritorio_id).get("escritorio_logo", "")


def _definir_logo(app, escritorio_id, nome):
    from app import db
    from app.services.configuracao_service import ConfiguracaoService
    with app.app_context():
        ConfiguracaoService(db.session, escritorio_id).set("escritorio_logo", nome)


def _arquivos(app):
    return sorted(os.listdir(app.config["LOGO_DIR"]))


def _ler(app, nome):
    with open(os.path.join(app.config["LOGO_DIR"], nome), "rb") as f:
        return f.read()


def test_dois_escritorios_com_a_mesma_extensao_nao_se_sobrescrevem(app):
    ca, cb = _logado(app, "a"), _logado(app, "b")
    assert _enviar(ca, "minha.png", b"LOGO-DO-A").status_code == 200
    assert _enviar(cb, "outra.png", b"LOGO-DO-B").status_code == 200

    assert _logo_de(app, 1) == "logo-1.png"
    assert _logo_de(app, 2) == "logo-2.png"
    assert _arquivos(app) == ["logo-1.png", "logo-2.png"]
    assert _ler(app, "logo-1.png") == b"LOGO-DO-A"   # a do A continua sendo a do A
    assert _ler(app, "logo-2.png") == b"LOGO-DO-B"


def test_trocar_extensao_remove_so_a_logo_anterior_do_proprio_escritorio(app):
    ca, cb = _logado(app, "a"), _logado(app, "b")
    _enviar(ca, "a.png", b"A-PNG")
    _enviar(cb, "b.png", b"B-PNG")
    _enviar(ca, "a.jpg", b"A-JPG")

    assert _logo_de(app, 1) == "logo-1.jpg"
    assert _arquivos(app) == ["logo-1.jpg", "logo-2.png"]   # logo-1.png saiu; a do B ficou
    assert _ler(app, "logo-2.png") == b"B-PNG"


def test_reenviar_mesma_extensao_substitui_sem_apagar_o_novo(app):
    ca = _logado(app, "a")
    _enviar(ca, "a.png", b"V1")
    _enviar(ca, "a.png", b"V2")
    assert _arquivos(app) == ["logo-1.png"]
    assert _ler(app, "logo-1.png") == b"V2"


def test_remover_logo_nao_afeta_o_outro_escritorio(app):
    ca, cb = _logado(app, "a"), _logado(app, "b")
    _enviar(ca, "a.png", b"A")
    _enviar(cb, "b.png", b"B")
    assert ca.delete("/api/configuracoes/escritorio/logo").status_code == 200
    assert _logo_de(app, 1) == ""
    assert _arquivos(app) == ["logo-2.png"]
    assert _logo_de(app, 2) == "logo-2.png"


def test_legado_logo_compartilhada_nao_e_apagada_enquanto_alguem_usa(app):
    """Banco antigo: os dois escritórios apontam para o mesmo `logo.png`."""
    with open(os.path.join(app.config["LOGO_DIR"], "logo.png"), "wb") as f:
        f.write(b"LEGADA")
    _definir_logo(app, 1, "logo.png")
    _definir_logo(app, 2, "logo.png")
    ca, cb = _logado(app, "a"), _logado(app, "b")

    # A envia uma logo nova: ganha arquivo próprio; a legada fica porque o B ainda usa.
    _enviar(ca, "nova.png", b"NOVA-A")
    assert _logo_de(app, 1) == "logo-1.png"
    assert _logo_de(app, 2) == "logo.png"
    assert _arquivos(app) == ["logo-1.png", "logo.png"]
    assert _ler(app, "logo.png") == b"LEGADA"

    # B remove a dele: agora a legada não tem mais ninguém e pode sair.
    cb.delete("/api/configuracoes/escritorio/logo")
    assert _arquivos(app) == ["logo-1.png"]


def test_formato_invalido_e_recusado_e_nada_muda(app):
    ca = _logado(app, "a")
    _enviar(ca, "a.png", b"OK")
    r = _enviar(ca, "virus.exe", b"MZ")
    assert r.status_code == 400
    assert _logo_de(app, 1) == "logo-1.png"
    assert _arquivos(app) == ["logo-1.png"]


def test_nome_de_arquivo_com_caminho_nao_escapa_da_pasta(app):
    ca = _logado(app, "a")
    _enviar(ca, "../../etc/passwd.png", b"X")
    assert _logo_de(app, 1) == "logo-1.png"          # o nome enviado é ignorado
    assert _arquivos(app) == ["logo-1.png"]


def test_excluir_escritorio_apaga_a_logo_dele_e_preserva_a_do_outro(app):
    from app import db
    from app.services.escritorio_service import EscritorioService
    ca, cb = _logado(app, "a"), _logado(app, "b")
    _enviar(ca, "a.png", b"A")
    _enviar(cb, "b.png", b"B")
    with app.app_context():
        ok, msg, _ = EscritorioService(db.session).excluir_definitivamente(
            2, str(app.config["LOGO_DIR"]), app.config["LOGO_DIR"])
        assert ok, msg
    assert _arquivos(app) == ["logo-1.png"]
