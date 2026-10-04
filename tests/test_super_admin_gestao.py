"""
Super admin: editar nome/identificador e excluir escritório em definitivo.

O teste mais importante aqui é o de exclusão completa: semeia dados em TODAS
as tabelas para dois escritórios, apaga um e confere que (1) não sobrou
nenhuma linha dele em lugar nenhum e (2) o outro ficou intacto. Se alguém
criar uma tabela nova com `escritorio_id` e esquecer de incluí-la na
exclusão, `test_nao_sobra_nada_do_escritorio_excluido` fica vermelho.
"""
import os
import tempfile

import pytest

_DB_FILE = os.path.join(tempfile.mkdtemp(prefix="despachante-teste-"), "gestao.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ.setdefault("FLASK_ENV", "development")


@pytest.fixture(scope="module")
def app():
    from app import create_app
    app = create_app("development")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture(autouse=True)
def banco_limpo(app, tmp_path):
    from app import db, aplicar_migracoes_leves
    app.config["UPLOAD_DIR"] = str(tmp_path / "docs")
    app.config["LOGO_DIR"] = str(tmp_path / "logo")
    os.makedirs(app.config["UPLOAD_DIR"])
    os.makedirs(app.config["LOGO_DIR"])
    with app.app_context():
        db.drop_all()
        db.create_all()
        aplicar_migracoes_leves(app)  # cria o escritório "principal" (id 1)
    yield


def _semear_escritorio(db, escritorio_id, sufixo, upload_dir, logo_dir, logo_nome="logo.png"):
    """Uma linha em CADA tabela que pertence ao escritório. Devolve nomes de arquivos criados."""
    from app.models.cliente import Cliente
    from app.models.configuracao import Configuracao
    from app.models.contato_pendencia import ContatoPendencia
    from app.models.documento import Documento
    from app.models.ipva import Ipva
    from app.models.ipva_parcela import IpvaParcela
    from app.models.licenciamento import Licenciamento
    from app.models.log_acao import LogAcao
    from app.models.multa import Multa
    from app.models.permissao_usuario import PermissaoUsuario
    from app.models.regra_vencimento import RegraVencimento
    from app.models.template_relatorio import TemplateRelatorio
    from app.models.usuario import Usuario
    from app.models.veiculo import Veiculo

    u = Usuario(escritorio_id=escritorio_id, nome_usuario="admin", nome_completo="A",
                senha_hash="x", perfil="administrador")
    c = Cliente(escritorio_id=escritorio_id, nome=f"Cli {sufixo}", cpf=f"cpf-{sufixo}")
    db.session.add_all([u, c])
    db.session.flush()
    v = Veiculo(escritorio_id=escritorio_id, cliente_id=c.id, placa=f"PLC{sufixo}", situacao="ativo")
    db.session.add(v)
    db.session.flush()
    ip = Ipva(veiculo_id=v.id, ano_referencia=2026)
    db.session.add(ip)
    db.session.flush()
    arquivo_doc = f"doc-{sufixo}.pdf"
    open(os.path.join(upload_dir, arquivo_doc), "w").close()
    db.session.add_all([
        IpvaParcela(ipva_id=ip.id, numero=1, valor=10, vencimento="2026-01-10"),
        Licenciamento(veiculo_id=v.id, ano_referencia=2026),
        Multa(veiculo_id=v.id),
        Documento(cliente_id=c.id, nome="d", data_documento="2026-01-01", categoria="x", arquivo=arquivo_doc),
        PermissaoUsuario(usuario_id=u.id, permissao="clientes"),
        ContatoPendencia(tipo="ipva", pendencia_id=ip.id, cliente_id=c.id, veiculo_id=v.id, marcado_por_id=u.id),
        RegraVencimento(escritorio_id=escritorio_id, final_placa="1", especie="passeio", mes_vencimento=3),
        TemplateRelatorio(escritorio_id=escritorio_id, nome="t", config_json="{}"),
        Configuracao(escritorio_id=escritorio_id, chave="escritorio_logo", valor=logo_nome),
        LogAcao(escritorio_id=escritorio_id, usuario_id=u.id, acao="teste", hash_anterior="0" * 64, hash_atual=f"h{sufixo}"),
    ])
    db.session.commit()
    open(os.path.join(logo_dir, logo_nome), "w").close()
    return arquivo_doc


def _contar_tudo(db):
    """{tabela: nº de linhas} para todas as tabelas, exceto escritorios."""
    return {
        nome: db.session.execute(db.text(f'SELECT COUNT(*) FROM "{nome}"')).scalar()
        for nome in db.metadata.tables if nome != "escritorios"
    }


def _dois_escritorios(app, db, logo_a="logo.png", logo_b="logo.png"):
    from app.models.escritorio import Escritorio
    esc_b = Escritorio(slug="b", nome="B", ativo=True)
    db.session.add(esc_b)
    db.session.commit()
    up, lg = app.config["UPLOAD_DIR"], app.config["LOGO_DIR"]
    doc_a = _semear_escritorio(db, 1, "A", up, lg, logo_a)
    doc_b = _semear_escritorio(db, esc_b.id, "B", up, lg, logo_b)
    return esc_b.id, doc_a, doc_b


# ── Edição ───────────────────────────────────────────────────────────────────

def test_editar_nome_e_slug(app):
    from app import db
    from app.models.escritorio import Escritorio
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        ok, msg = EscritorioService(db.session).editar(1, "  Despachante do Zé ", "Despachante do Zé")
        assert ok, msg
        e = db.session.get(Escritorio, 1)
        assert (e.nome, e.slug) == ("Despachante do Zé", "despachante-do-ze")


def test_editar_validacoes(app):
    from app import db
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        svc = EscritorioService(db.session)
        novo, _ = svc.criar("Outro", "outro")
        assert not svc.editar(1, "", "x")[0]                      # nome vazio
        assert not svc.editar(1, "N", "!!!")[0]                   # slug vira vazio
        assert not svc.editar(1, "N", "outro")[0]                 # slug de outro escritório
        assert not svc.editar(1, "N", "a" * 51)[0]                # slug longo demais
        assert not svc.editar(999, "N", "x")[0]                   # não existe
        assert svc.editar(1, "Novo nome", "principal")[0]         # manter o próprio slug é permitido


# ── Exclusão (serviço) ───────────────────────────────────────────────────────

def test_nao_sobra_nada_do_escritorio_excluido(app):
    from app import db
    from app.models.escritorio import Escritorio
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        b_id, _, _ = _dois_escritorios(app, db, logo_b="logo-b.png")
        total_com_ambos = _contar_tudo(db)

        ok, msg, cont = EscritorioService(db.session).excluir_definitivamente(
            b_id, app.config["UPLOAD_DIR"], app.config["LOGO_DIR"])
        assert ok, msg
        assert db.session.get(Escritorio, b_id) is None

        # Cada tabela perdeu exatamente 1 linha (a do escritório B)...
        depois = _contar_tudo(db)
        for tabela, antes in total_com_ambos.items():
            assert depois[tabela] == antes - 1, f"{tabela}: esperava perder só a linha de B"
        # ...e nenhuma tabela com escritorio_id guarda mais o id de B.
        for nome, tb in db.metadata.tables.items():
            if "escritorio_id" in tb.columns:
                n = db.session.execute(
                    db.text(f'SELECT COUNT(*) FROM "{nome}" WHERE escritorio_id = :i'), {"i": b_id}).scalar()
                assert n == 0, f"sobrou dado de {nome}"


def test_outro_escritorio_fica_intacto(app):
    from app import db
    from app.models.cliente import Cliente
    from app.models.usuario import Usuario
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        b_id, doc_a, _ = _dois_escritorios(app, db)
        EscritorioService(db.session).excluir_definitivamente(
            b_id, app.config["UPLOAD_DIR"], app.config["LOGO_DIR"])
        assert db.session.query(Cliente).filter_by(escritorio_id=1).count() == 1
        assert db.session.query(Usuario).filter_by(escritorio_id=1).count() == 1
        assert os.path.exists(os.path.join(app.config["UPLOAD_DIR"], doc_a))


def test_arquivos_do_escritorio_excluido_saem_do_disco(app):
    from app import db
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        b_id, _, doc_b = _dois_escritorios(app, db, logo_a="logo-a.png", logo_b="logo-b.png")
        EscritorioService(db.session).excluir_definitivamente(
            b_id, app.config["UPLOAD_DIR"], app.config["LOGO_DIR"])
        assert not os.path.exists(os.path.join(app.config["UPLOAD_DIR"], doc_b))
        assert not os.path.exists(os.path.join(app.config["LOGO_DIR"], "logo-b.png"))
        assert os.path.exists(os.path.join(app.config["LOGO_DIR"], "logo-a.png"))


def test_logo_compartilhada_com_outro_escritorio_nao_e_apagada(app):
    """A logo é salva como `logo.<ext>` para TODOS os escritórios. Apagar o
    escritório B não pode levar embora o arquivo que o A ainda usa."""
    from app import db
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        b_id, _, _ = _dois_escritorios(app, db, logo_a="logo.png", logo_b="logo.png")
        EscritorioService(db.session).excluir_definitivamente(
            b_id, app.config["UPLOAD_DIR"], app.config["LOGO_DIR"])
        assert os.path.exists(os.path.join(app.config["LOGO_DIR"], "logo.png"))


def test_nao_exclui_o_ultimo_escritorio(app):
    from app import db
    from app.models.escritorio import Escritorio
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        ok, msg, _ = EscritorioService(db.session).excluir_definitivamente(
            1, app.config["UPLOAD_DIR"], app.config["LOGO_DIR"])
        assert not ok and "único" in msg
        assert db.session.get(Escritorio, 1) is not None


def test_falha_no_meio_nao_apaga_nada(app):
    """Se o commit falhar, a transação inteira volta atrás."""
    from app import db
    from app.models.escritorio import Escritorio
    from app.services.escritorio_service import EscritorioService
    with app.app_context():
        b_id, _, doc_b = _dois_escritorios(app, db)
        antes = _contar_tudo(db)

        class SessaoQuebrada:
            def __getattr__(self, nome):
                return getattr(db.session, nome)
            def commit(self):
                raise RuntimeError("falha simulada")

        ok, msg, _ = EscritorioService(SessaoQuebrada()).excluir_definitivamente(
            b_id, app.config["UPLOAD_DIR"], app.config["LOGO_DIR"])
        assert not ok
        assert db.session.get(Escritorio, b_id) is not None
        assert _contar_tudo(db) == antes
        assert os.path.exists(os.path.join(app.config["UPLOAD_DIR"], doc_b))  # arquivo preservado


# ── Rotas ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def admin_client(app):
    app.config.update(SUPER_ADMIN_TOKEN="acesso", SUPER_ADMIN_DELETE_TOKEN="apagar")
    c = app.test_client()
    c.post("/super-admin/", data={"token": "acesso"})
    yield c
    app.config.update(SUPER_ADMIN_TOKEN=None, SUPER_ADMIN_DELETE_TOKEN=None)


def _existe(app, escritorio_id):
    from app import db
    from app.models.escritorio import Escritorio
    with app.app_context():
        return db.session.get(Escritorio, escritorio_id) is not None


def test_rota_editar(app, admin_client):
    from app import db
    from app.models.escritorio import Escritorio
    r = admin_client.post("/super-admin/escritorios/1/editar", data={"nome": "Renomeado", "slug": "novo-slug"})
    assert r.status_code == 302
    with app.app_context():
        e = db.session.get(Escritorio, 1)
        assert (e.nome, e.slug) == ("Renomeado", "novo-slug")
    assert admin_client.get("/e/novo-slug/login").status_code == 200   # link novo funciona
    assert admin_client.get("/e/principal/login").status_code == 404   # link antigo não


def test_rota_excluir_exige_token_e_slug(app, admin_client):
    from app import db
    from app.models.escritorio import Escritorio
    with app.app_context():
        b = Escritorio(slug="b", nome="B", ativo=True)
        db.session.add(b); db.session.commit()
        b_id = b.id
    url = f"/super-admin/escritorios/{b_id}/excluir"

    admin_client.post(url, data={"confirmar_slug": "b", "token_exclusao": "errado"})
    assert _existe(app, b_id), "token errado não pode apagar"
    admin_client.post(url, data={"confirmar_slug": "b", "token_exclusao": "acesso"})
    assert _existe(app, b_id), "o token de ACESSO não vale como token de exclusão"
    admin_client.post(url, data={"confirmar_slug": "outro", "token_exclusao": "apagar"})
    assert _existe(app, b_id), "slug digitado errado não pode apagar"
    admin_client.post(url, data={"token_exclusao": "apagar"})
    assert _existe(app, b_id), "sem confirmar o slug não pode apagar"

    admin_client.post(url, data={"confirmar_slug": "b", "token_exclusao": "apagar"})
    assert not _existe(app, b_id)


def test_rota_excluir_desativada_sem_token_configurado(app, admin_client):
    from app import db
    from app.models.escritorio import Escritorio
    app.config["SUPER_ADMIN_DELETE_TOKEN"] = None
    with app.app_context():
        b = Escritorio(slug="b", nome="B", ativo=True)
        db.session.add(b); db.session.commit()
        b_id = b.id
    admin_client.post(f"/super-admin/escritorios/{b_id}/excluir", data={"confirmar_slug": "b", "token_exclusao": ""})
    assert _existe(app, b_id)
    assert b"Excluir definitivamente" not in admin_client.get("/super-admin/escritorios").data


def test_rotas_exigem_sessao_super_admin(app):
    app.config.update(SUPER_ADMIN_TOKEN="acesso", SUPER_ADMIN_DELETE_TOKEN="apagar")
    try:
        c = app.test_client()  # sem logar
        for rota in ("/editar", "/excluir"):
            r = c.post(f"/super-admin/escritorios/1{rota}", data={"nome": "x", "slug": "x",
                       "confirmar_slug": "principal", "token_exclusao": "apagar"})
            assert r.status_code == 302 and "/super-admin/" in r.headers["Location"]
        assert _existe(app, 1)
    finally:
        app.config.update(SUPER_ADMIN_TOKEN=None, SUPER_ADMIN_DELETE_TOKEN=None)


def test_pagina_renderiza_nome_com_aspas_sem_quebrar(app, admin_client):
    from app import db
    from app.models.escritorio import Escritorio
    with app.app_context():
        db.session.get(Escritorio, 1).nome = "Zé's \"Despachante\" <b>"
        db.session.commit()
    html = admin_client.get("/super-admin/escritorios").get_data(as_text=True)
    assert "<b>" not in html.replace("<b>Não há como desfazer.</b>", "")   # escapado
    assert "onsubmit=\"return confirmarExclusao(this);\"" in html
    assert "confirm('Excluir" not in html.split("<script>")[0]            # nada de nome dentro de JS inline
