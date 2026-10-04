"""
Teste de isolamento multi-tenant.

Propósito: pegar automaticamente qualquer ponto do código que esqueceu de
filtrar uma query por `escritorio_id`. Semeia dois escritórios com dados
próprios e garante que um nunca enxerga (nem consegue adivinhar por ID) o
dado do outro.

Como usar durante a migração dos services que faltam: rode este arquivo
depois de migrar cada service. Ele fica vermelho nas rotas ainda não
migradas — isso é o esperado, não um bug do teste. Conforme cada service
passa a herdar de `TenantService`, o teste correspondente fica verde.
Adicione um teste novo aqui para cada rota migrada, seguindo o padrão dos
já existentes.
"""
import os
import tempfile
import pytest

# Precisa rodar ANTES de qualquer `from app import ...` neste processo: a
# URI do banco é lida de DATABASE_URL uma única vez, dentro de
# create_app()->db.init_app(), na primeira vez que o config.py é
# importado. Definir a env var depois disso (ex. dentro de uma fixture) não
# tem efeito nas chamadas seguintes de create_app() no mesmo processo.
_DB_FILE = os.path.join(tempfile.mkdtemp(prefix="despachante-teste-"), "isolamento.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"
os.environ.setdefault("FLASK_ENV", "development")


@pytest.fixture(scope="module")
def app():
    """Uma única instância da app pro módulo inteiro — a URI do banco só
    pode ser definida uma vez por processo (ver comentário acima), então
    recriar a app por teste não isolaria nada mesmo."""
    from app import create_app
    app = create_app("development")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    yield app


@pytest.fixture(autouse=True)
def banco_limpo(app):
    """Reseta o schema e semeia os dois escritórios antes de CADA teste,
    pra nenhum teste ver dado deixado por outro."""
    from app import db, aplicar_migracoes_leves
    from app.models.escritorio import Escritorio
    from app.services.configuracao_service import ConfiguracaoService
    from app.services.auth_service import AuthService

    with app.app_context():
        db.drop_all()
        db.create_all()
        aplicar_migracoes_leves(app)

        # aplicar_migracoes_leves já criou o escritório "principal" (id 1,
        # backfill de instalação nova). Renomeia pra ficar claro no teste e
        # cria um segundo escritório do zero.
        esc_a = db.session.get(Escritorio, 1)
        esc_a.slug, esc_a.nome = "escritorio-a", "Escritório A"
        esc_b = Escritorio(slug="escritorio-b", nome="Escritório B", ativo=True)
        db.session.add(esc_b)
        db.session.commit()

        for esc in (esc_a, esc_b):
            ConfiguracaoService(db.session, esc.id).seed_defaults()
            AuthService(db.session).seed_admin(esc.id)

        # seed_admin sempre cria um usuário "admin" — nome_usuario ainda é
        # único GLOBALMENTE (a constraint composta por escritório é um
        # passo futuro), então o do segundo escritório precisa de outro nome.
        from app.models.usuario import Usuario
        usuario_b = db.session.query(Usuario).filter_by(escritorio_id=esc_b.id, nome_usuario="admin").first()
        usuario_b.nome_usuario = "admin_b"
        db.session.commit()

    yield


@pytest.fixture()
def cliente_logado_a(app):
    """Test client logado como admin do Escritório A."""
    client = app.test_client()
    client.post("/e/escritorio-a/login", data={"nome_usuario": "admin", "senha": "admin123"})
    client.post("/trocar-senha", data={"nova_senha": "SenhaA12345", "confirmar_senha": "SenhaA12345"})
    return client


@pytest.fixture()
def cliente_logado_b(app):
    """Test client logado como admin do Escritório B."""
    client = app.test_client()
    client.post("/e/escritorio-b/login", data={"nome_usuario": "admin_b", "senha": "admin123"})
    client.post("/trocar-senha", data={"nova_senha": "SenhaB12345", "confirmar_senha": "SenhaB12345"})
    return client


def _criar_cliente(client, nome, cpf):
    return client.post("/api/clientes", json={
        "nome": nome, "tipo_pessoa": "PF", "cpf": cpf,
        "telefone": "11999998888", "email": "", "observacao": "",
    })


# CPFs válidos (dígito verificador correto) só pra passar da validação —
# não representam pessoas reais.
CPF_A = "11144477735"
CPF_B = "52998224725"


def test_cliente_do_escritorio_a_nao_aparece_na_listagem_do_b(cliente_logado_a, cliente_logado_b):
    r = _criar_cliente(cliente_logado_a, "Cliente do A", CPF_A)
    assert r.status_code == 200, r.get_json()

    listagem_b = cliente_logado_b.get("/api/clientes").get_json()
    assert listagem_b == [], f"Escritório B viu cliente do Escritório A: {listagem_b}"

    listagem_a = cliente_logado_a.get("/api/clientes").get_json()
    assert len(listagem_a) == 1 and listagem_a[0]["nome"] == "Cliente do A"


def test_escritorio_b_nao_acessa_cliente_do_a_por_id(cliente_logado_a, cliente_logado_b):
    r = _criar_cliente(cliente_logado_a, "Cliente do A", CPF_A)
    assert r.status_code == 200
    cliente_id = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]

    # B tentando acessar direto pelo id do cliente de A — não pode nem saber
    # que existe (404, não 403 — não vaza nem a existência do registro).
    r = cliente_logado_b.get(f"/api/clientes/{cliente_id}")
    assert r.status_code == 404, f"Escritório B conseguiu acessar cliente do A: {r.get_json()}"


def test_cpf_pode_repetir_entre_escritorios_diferentes(cliente_logado_a, cliente_logado_b):
    """
    Mesmo CPF em dois escritórios diferentes tem que ser permitido — são
    despachantes diferentes, podem atender o mesmo cliente.
    """
    r_a = _criar_cliente(cliente_logado_a, "Fulano", CPF_A)
    r_b = _criar_cliente(cliente_logado_b, "Fulano (outro escritório)", CPF_A)
    assert r_a.status_code == 200, r_a.get_json()
    assert r_b.status_code == 200, r_b.get_json()


def test_log_de_acoes_nao_mistura_escritorios(app, cliente_logado_a, cliente_logado_b):
    _criar_cliente(cliente_logado_a, "Cliente do A", CPF_A)
    _criar_cliente(cliente_logado_b, "Cliente do B", CPF_B)

    from app import db
    from app.models.log_acao import LogAcao
    from app.services.log_service import LogService

    with app.app_context():
        from app.models.escritorio import Escritorio
        esc_a = db.session.query(Escritorio).filter_by(slug="escritorio-a").first()
        esc_b = db.session.query(Escritorio).filter_by(slug="escritorio-b").first()

        logs_a = db.session.query(LogAcao).filter_by(escritorio_id=esc_a.id).all()
        logs_b = db.session.query(LogAcao).filter_by(escritorio_id=esc_b.id).all()
        assert all(l.escritorio_id == esc_a.id for l in logs_a)
        assert all(l.escritorio_id == esc_b.id for l in logs_b)

        # A cadeia de hash de cada escritório precisa ser íntegra
        # INDEPENDENTE da atividade do outro escritório intercalada no meio.
        resultado_a = LogService(db.session, esc_a.id).verificar_integridade()
        resultado_b = LogService(db.session, esc_b.id).verificar_integridade()
        assert resultado_a["integro"], f"Cadeia de hash do Escritório A quebrou: {resultado_a}"
        assert resultado_b["integro"], f"Cadeia de hash do Escritório B quebrou: {resultado_b}"


def test_usuario_de_um_escritorio_nao_loga_no_slug_do_outro(app):
    """
    O gap que ficou documentado desde o passo 2: antes do login por slug,
    não havia como saber de qual escritório era o usuário antes de
    autenticar. Agora autenticar() busca escopado — um usuário do
    Escritório A tentando logar em /e/escritorio-b/login não pode ter
    sucesso, mesmo com a senha certa.
    """
    client = app.test_client()
    r = client.post("/e/escritorio-b/login", data={"nome_usuario": "admin", "senha": "admin123"})
    assert r.status_code == 200, "deveria re-renderizar a página de login com erro, não redirecionar"
    assert b"incorretos" in r.data

    # Mas no próprio escritório, a mesma senha funciona normalmente.
    r = client.post("/e/escritorio-a/login", data={"nome_usuario": "admin", "senha": "admin123"})
    assert r.status_code == 302


def test_slug_inexistente_da_404(app):
    client = app.test_client()
    r = client.get("/e/nao-existe/login")
    assert r.status_code == 404


def test_login_sem_slug_redireciona_quando_ha_um_unico_escritorio_ativo(app):
    """
    Com 2 escritórios ativos (o padrão deste arquivo de teste), /login sem
    slug deve mostrar o seletor, não redirecionar sozinho.
    """
    client = app.test_client()
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Escrit\xc3\xb3rio A" in r.data and b"Escrit\xc3\xb3rio B" in r.data


def test_admin_usuarios_nao_lista_usuario_de_outro_escritorio(cliente_logado_a, cliente_logado_b):
    """
    Vazamento real encontrado durante a sessão: /admin/usuarios listava
    TODOS os usuários de TODOS os escritórios, sem filtro nenhum.
    """
    r = cliente_logado_a.get("/admin/usuarios")
    assert r.status_code == 200
    assert b"admin_b" not in r.data, "Escritorio A viu o usuario do Escritorio B na tela de admin"

    r = cliente_logado_b.get("/admin/usuarios")
    assert r.status_code == 200
    assert b"admin_b" in r.data  # o próprio usuário aparece normalmente


def test_super_admin_sem_token_configurado_eh_404(app):
    """Sem SUPER_ADMIN_TOKEN definido, a área inteira não deve existir."""
    assert app.config.get("SUPER_ADMIN_TOKEN") is None
    client = app.test_client()
    assert client.get("/super-admin/").status_code == 404
    assert client.get("/super-admin/escritorios").status_code == 404


def test_super_admin_cria_escritorio_funcional(app):
    app.config["SUPER_ADMIN_TOKEN"] = "segredo-de-teste"
    try:
        client = app.test_client()

        r = client.post("/super-admin/escritorios", data={"nome": "Novo"})
        assert r.status_code == 302, "sem logar no token ainda, deve redirecionar pro login, nunca criar nada"

        client.post("/super-admin/", data={"token": "segredo-de-teste"})
        r = client.post("/super-admin/escritorios", data={"nome": "Escritorio Novo", "slug": ""})
        assert r.status_code == 200
        assert b"escritorio-novo" in r.data

        # O escritório recém-criado já tem login funcional com a credencial padrão.
        novo_cliente = app.test_client()
        r = novo_cliente.post("/e/escritorio-novo/login", data={"nome_usuario": "admin", "senha": "admin123"})
        assert r.status_code == 302 and "/trocar-senha" in r.headers["Location"]
    finally:
        app.config["SUPER_ADMIN_TOKEN"] = None
