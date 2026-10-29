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


def test_super_admin_cria_escritorio_funcional(app, monkeypatch):
    monkeypatch.setattr("app.routes.super_admin.secrets.token_urlsafe", lambda n: "SenhaInicial-9x")
    app.config["SUPER_ADMIN_TOKEN"] = "segredo-de-teste"
    try:
        client = app.test_client()

        r = client.post("/super-admin/escritorios", data={"nome": "Novo"})
        assert r.status_code == 302, "sem logar no token ainda, deve redirecionar pro login, nunca criar nada"

        client.post("/super-admin/", data={"token": "segredo-de-teste"})
        r = client.post("/super-admin/escritorios", data={"nome": "Escritorio Novo", "slug": ""})
        assert r.status_code == 200
        assert b"escritorio-novo" in r.data

        # A senha inicial é aleatória e aparece na tela só nessa hora; a antiga
        # "admin123" (pública no README) não pode abrir o escritório novo.
        assert b"SenhaInicial-9x" in r.data
        novo_cliente = app.test_client()
        r = novo_cliente.post("/e/escritorio-novo/login", data={"nome_usuario": "admin", "senha": "admin123"})
        assert r.status_code == 200, "admin123 não deve funcionar em escritório novo"
        r = novo_cliente.post("/e/escritorio-novo/login", data={"nome_usuario": "admin", "senha": "SenhaInicial-9x"})
        assert r.status_code == 302 and "/trocar-senha" in r.headers["Location"]
    finally:
        app.config["SUPER_ADMIN_TOKEN"] = None


def test_escritorio_novo_nasce_com_admin_mesmo_com_admin_em_outro(app):
    """Regressão: criar um escritório novo falhava com UniqueViolation em
    `usuarios_nome_usuario_key` porque o `admin` inicial colidia com o de
    outro escritório (constraint global antiga). Nome de usuário só pode ser
    único DENTRO do escritório."""
    from sqlalchemy.exc import IntegrityError
    from app import db
    from app.models.usuario import Usuario
    from app.services.escritorio_service import EscritorioService

    with app.app_context():
        # Escritório A (id 1) já tem um "admin" criado pelo fixture.
        novo, erro = EscritorioService(db.session).criar("Escritório C")
        assert novo is not None, erro

        admins = db.session.query(Usuario).filter_by(nome_usuario="admin").all()
        assert {u.escritorio_id for u in admins} >= {1, novo.id}

        # ...mas continua proibido repetir o nome DENTRO do mesmo escritório.
        db.session.add(Usuario(
            escritorio_id=novo.id, nome_usuario="admin", nome_completo="Dup",
            senha_hash="x", perfil="operador",
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_busca_global_nao_mistura_escritorios(app, cliente_logado_a, cliente_logado_b):
    """Regressão: a caixa de pesquisa do topo devolvia clientes e veículos de outro escritório."""
    from app import db
    from app.models.veiculo import Veiculo

    assert _criar_cliente(cliente_logado_a, "Maria Silva", CPF_A).status_code == 200
    assert _criar_cliente(cliente_logado_b, "Maria Souza", CPF_B).status_code == 200
    cid_a = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]

    with app.app_context():
        db.session.add(Veiculo(escritorio_id=1, cliente_id=cid_a, placa="ABC1D23"))
        db.session.commit()

    r_a = cliente_logado_a.get("/api/busca-global?q=Maria").get_json()
    r_b = cliente_logado_b.get("/api/busca-global?q=Maria").get_json()
    assert [c["nome"] for c in r_a["clientes"]] == ["Maria Silva"], r_a
    assert [c["nome"] for c in r_b["clientes"]] == ["Maria Souza"], r_b

    assert len(cliente_logado_a.get("/api/busca-global?q=ABC1").get_json()["veiculos"]) == 1
    assert cliente_logado_b.get("/api/busca-global?q=ABC1").get_json()["veiculos"] == []


def test_paginas_por_id_nao_abrem_dado_de_outro_escritorio(app, cliente_logado_a, cliente_logado_b):
    from app import db
    from app.models.veiculo import Veiculo

    assert _criar_cliente(cliente_logado_a, "Cliente do A", CPF_A).status_code == 200
    cid_a = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]
    with app.app_context():
        v = Veiculo(escritorio_id=1, cliente_id=cid_a, placa="XYZ9K88")
        db.session.add(v)
        db.session.commit()
        vid_a = v.id

    for url in (f"/clientes/{cid_a}/veiculos", f"/clientes/{cid_a}/pendencias",
                f"/veiculos/{vid_a}/painel", f"/api/clientes/{cid_a}/proprietarios"):
        assert cliente_logado_a.get(url).status_code == 200, url
        r = cliente_logado_b.get(url)
        assert r.status_code in (302, 404), f"B acessou {url}: {r.status_code}"


def test_relatorio_filtra_por_cliente_e_proprietario_sem_acento(app, cliente_logado_a):
    """Regressão: filtro de cliente ignorava acentos e o de proprietário não existia."""
    from app import db
    from app.models.veiculo import Veiculo
    from app.models.ipva import Ipva

    assert _criar_cliente(cliente_logado_a, "João da Silva", CPF_A).status_code == 200
    cid = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]
    with app.app_context():
        v = Veiculo(escritorio_id=1, cliente_id=cid, placa="ABC1D23", proprietario="Maria Souza")
        db.session.add(v)
        db.session.commit()
        db.session.add(Ipva(veiculo_id=v.id, ano_referencia=2026, valor=100,
                            vencimento="2026-11-10", pago=False))
        db.session.commit()

    def total(filtros):
        cfg = {"tipos": ["ipva"], "filtros": filtros, "agrupar_por": "nenhum"}
        return len(cliente_logado_a.post("/api/relatorios/dados", json=cfg).get_json()["dados"])

    assert total({}) == 1
    for termo in ("Jo", "joao", "JOÃO", "silva"):
        assert total({"cliente_nome": termo}) == 1, termo
    assert total({"cliente_nome": "Pedro"}) == 0
    for termo in ("maria", "MARIA SOUZA", "souza"):
        assert total({"proprietario": termo}) == 1, termo
    assert total({"proprietario": "Pedro"}) == 0
    assert total({"cliente_nome": "joao", "proprietario": "maria"}) == 1
    assert total({"cliente_nome": "joao", "proprietario": "pedro"}) == 0


def test_exportar_pdf_com_caracteres_especiais_e_agrupamento(app, cliente_logado_a):
    """O PDF não pode quebrar com '&' ou '<' em nomes, nem com agrupamento e resumo."""
    from app import db
    from app.models.veiculo import Veiculo
    from app.models.ipva import Ipva

    assert _criar_cliente(cliente_logado_a, "Silva & Filhos <Ltda>", CPF_A).status_code == 200
    cid = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]
    with app.app_context():
        v = Veiculo(escritorio_id=1, cliente_id=cid, placa="ABC1D23", proprietario="A & B")
        db.session.add(v)
        db.session.commit()
        db.session.add(Ipva(veiculo_id=v.id, ano_referencia=2026, valor=100,
                            vencimento="2020-01-10", pago=False))
        db.session.commit()

    campos = [{"id": "cliente_nome", "label": "Cliente"}, {"id": "valor", "label": "Valor"},
              {"id": "status_pag", "label": "Status"}]
    for extra in ({}, {"agrupar_por": "cliente_nome", "mostrar_resumo": True,
                       "mostrar_totais": True, "quebra_pagina_grupo": True}):
        config = {"tipos": ["ipva"], "filtros": {"cliente_nome": "silva"}, **extra}
        r = cliente_logado_a.post("/api/relatorios/exportar/pdf",
                                  json={"config": config, "campos_visiveis": campos})
        assert r.status_code == 200 and r.data.startswith(b"%PDF"), extra


def test_pagina_relatorios_renderiza(cliente_logado_a):
    r = cliente_logado_a.get("/relatorios")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for marcador in ("relatorio-acoes", "aplicarAtalho", "cfg-proprietario", "busca-cliente", "arvore-escopo"):
        assert marcador in html, marcador


def _montar_cliente_com_veiculos(app, cliente_http, nome, cpf, veiculos, escritorio_id):
    """Cria um cliente e veículos (placa, proprietário, valor do IPVA); devolve (cliente_id, [veiculo_id])."""
    from app import db
    from app.models.veiculo import Veiculo
    from app.models.ipva import Ipva

    assert _criar_cliente(cliente_http, nome, cpf).status_code == 200
    cid = [c["id"] for c in cliente_http.get("/api/clientes").get_json() if c["nome"] == nome][0]
    ids = []
    with app.app_context():
        for placa, prop, valor in veiculos:
            v = Veiculo(escritorio_id=escritorio_id, cliente_id=cid, placa=placa, proprietario=prop)
            db.session.add(v)
            db.session.flush()
            db.session.add(Ipva(veiculo_id=v.id, ano_referencia=2026, valor=valor,
                                vencimento="2020-01-10", pago=False))
            ids.append(v.id)
        db.session.commit()
    return cid, ids


def test_busca_de_clientes_para_relatorio_e_isolada_e_ignora_acentos(app, cliente_logado_a, cliente_logado_b):
    _montar_cliente_com_veiculos(app, cliente_logado_a, "João da Silva", CPF_A, [], 1)
    _montar_cliente_com_veiculos(app, cliente_logado_b, "João Souza", CPF_B, [], 2)

    nomes = lambda r: [c["nome"] for c in r.get_json()]
    assert nomes(cliente_logado_a.get("/api/relatorios/clientes?q=joao")) == ["João da Silva"]
    assert nomes(cliente_logado_b.get("/api/relatorios/clientes?q=JOAO")) == ["João Souza"]
    assert nomes(cliente_logado_a.get("/api/relatorios/clientes?q=silva joao")) == ["João da Silva"]
    assert nomes(cliente_logado_a.get("/api/relatorios/clientes?q=souza")) == []
    assert cliente_logado_a.get("/api/relatorios/clientes?q=j").get_json() == []


def test_escopo_do_cliente_agrupa_por_proprietario_e_nao_vaza(app, cliente_logado_a, cliente_logado_b):
    cid, ids = _montar_cliente_com_veiculos(
        app, cliente_logado_a, "Cliente Frota", CPF_A,
        [("AAA1A11", "Maria Souza", 100), ("BBB2B22", "maria souza", 200), ("CCC3C33", "José Souza", 300)], 1)

    escopo = cliente_logado_a.get(f"/api/relatorios/clientes/{cid}/escopo").get_json()
    assert escopo["total_veiculos"] == 3
    assert [(p["nome"], len(p["veiculos"])) for p in escopo["proprietarios"]] == [("José Souza", 1), ("Maria Souza", 2)]
    assert cliente_logado_b.get(f"/api/relatorios/clientes/{cid}/escopo").status_code == 404


def test_relatorio_por_cliente_e_veiculos_escolhidos(app, cliente_logado_a, cliente_logado_b):
    cid, ids = _montar_cliente_com_veiculos(
        app, cliente_logado_a, "Cliente Frota", CPF_A,
        [("AAA1A11", "Maria Souza", 100), ("BBB2B22", "Maria Souza", 200), ("CCC3C33", "José Souza", 300)], 1)
    _montar_cliente_com_veiculos(app, cliente_logado_a, "Outro Cliente", "52998224725", [("ZZZ9Z99", "X", 999)], 1)

    def valores(http, filtros):
        cfg = {"tipos": ["ipva"], "filtros": filtros, "agrupar_por": "nenhum"}
        return sorted(l["valor"] for l in http.post("/api/relatorios/dados", json=cfg).get_json()["dados"])

    assert valores(cliente_logado_a, {"cliente_id": cid}) == [100, 200, 300]
    assert valores(cliente_logado_a, {"cliente_id": cid, "veiculo_ids": ids[:2]}) == [100, 200]
    assert valores(cliente_logado_a, {"cliente_id": cid, "veiculo_ids": [ids[2]]}) == [300]
    assert valores(cliente_logado_a, {"cliente_id": cid, "veiculo_ids": []}) == []
    assert valores(cliente_logado_a, {"cliente_id": "abc"}) == [100, 200, 300, 999]  # id inválido é ignorado
    # o outro escritório não enxerga nada, mesmo conhecendo os ids
    assert valores(cliente_logado_b, {"cliente_id": cid}) == []
    assert valores(cliente_logado_b, {"veiculo_ids": ids}) == []


def test_pdf_descreve_cliente_e_veiculos_escolhidos(app, cliente_logado_a):
    from app.services.relatorio_service import RelatorioService
    from app import db

    cid, ids = _montar_cliente_com_veiculos(
        app, cliente_logado_a, "Cliente Frota", CPF_A,
        [("AAA1A11", "Maria", 100), ("BBB2B22", "José", 200)], 1)
    with app.app_context():
        texto = RelatorioService(db.session, 1)._descrever_filtros(
            {"filtros": {"cliente_id": cid, "veiculo_ids": [ids[0]]}})[0]
    assert "Cliente: Cliente Frota" in texto and "AAA1A11" in texto and "BBB2B22" not in texto



# ── Segurança ────────────────────────────────────────────────────────────────

def test_login_nao_redireciona_para_outro_site(app):
    from app import db
    from app.models.usuario import Usuario
    with app.app_context():  # senha temporária redirecionaria antes de olhar o "next"
        db.session.query(Usuario).filter_by(nome_usuario="admin").update({"senha_temporaria": False})
        db.session.commit()
    for next_url, esperado_externo in (("//evil.com/x", True), ("/\\evil.com", True),
                                       ("https://evil.com", True), ("/clientes", False)):
        c = app.test_client()
        r = c.post(f"/e/escritorio-a/login?next={next_url}", data={"nome_usuario": "admin", "senha": "admin123"})
        destino = r.headers["Location"]
        if esperado_externo:
            assert "evil.com" not in destino, (next_url, destino)
        else:
            assert destino.endswith(next_url), destino


def test_requisicao_de_outro_site_e_recusada(cliente_logado_a):
    ok = cliente_logado_a.post("/api/clientes", json={}, headers={"Origin": "http://localhost"})
    assert ok.status_code != 403
    for origem in ("https://evil.com", "null"):
        r = cliente_logado_a.post("/api/clientes", json={}, headers={"Origin": origem})
        assert r.status_code == 403, origem
    r = cliente_logado_a.post("/api/clientes", json={}, headers={"Referer": "https://evil.com/pagina"})
    assert r.status_code == 403


def test_cabecalhos_de_seguranca(cliente_logado_a):
    r = cliente_logado_a.get("/api/clientes")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_documento_de_um_escritorio_nao_baixa_no_outro(app, cliente_logado_a, cliente_logado_b):
    from app import db
    from app.models.documento import Documento

    assert _criar_cliente(cliente_logado_a, "Dono do Documento", CPF_A).status_code == 200
    cid = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]
    nome = "a" * 32 + ".pdf"
    with open(os.path.join(app.config["UPLOAD_DIR"], nome), "wb") as f:
        f.write(b"%PDF-1.4 teste")
    with app.app_context():
        db.session.add(Documento(cliente_id=cid, nome="Doc", data_documento="2026-01-01",
                                 categoria="outros", arquivo=nome))
        db.session.commit()
    try:
        assert cliente_logado_a.get(f"/static/uploads/documentos/{nome}").status_code == 200
        assert cliente_logado_b.get(f"/static/uploads/documentos/{nome}").status_code == 404
    finally:
        os.remove(os.path.join(app.config["UPLOAD_DIR"], nome))


def test_logo_svg_nao_executa_script_quando_aberta_direto(app, cliente_logado_a):
    nome = "logo_teste.svg"
    with open(os.path.join(app.config["LOGO_DIR"], nome), "w") as f:
        f.write("<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
    try:
        r = cliente_logado_a.get(f"/static/uploads/logo/{nome}")
        assert "sandbox" in r.headers["Content-Security-Policy"]
    finally:
        os.remove(os.path.join(app.config["LOGO_DIR"], nome))


def test_super_admin_bloqueia_tentativas_em_excesso(app):
    from app.routes import super_admin
    super_admin._falhas.clear()
    app.config["SUPER_ADMIN_TOKEN"] = "token-certo-123456"
    try:
        c = app.test_client()
        for _ in range(5):
            assert b"Token inv" in c.post("/super-admin/", data={"token": "errado"}).data
        # depois do limite, nem o token certo entra
        r = c.post("/super-admin/", data={"token": "token-certo-123456"})
        assert r.status_code == 200 and b"Muitas tentativas" in r.data
    finally:
        app.config["SUPER_ADMIN_TOKEN"] = None
        super_admin._falhas.clear()


def test_senha_nova_precisa_ter_oito_caracteres(app):
    from app import db
    from app.models.usuario import Usuario
    from app.services.auth_service import AuthService
    with app.app_context():
        uid = db.session.query(Usuario).filter_by(nome_usuario="admin").first().id
        svc = AuthService(db.session)
        assert svc.trocar_senha(uid, "curta1")[0] is False
        assert svc.trocar_senha(uid, "admin123")[0] is False
        assert svc.trocar_senha(uid, "Senha-bem-melhor-1")[0] is True


def test_excel_nao_transforma_nome_em_formula(app, cliente_logado_a):
    import io
    from openpyxl import load_workbook
    assert _criar_cliente(cliente_logado_a, "=1+1", CPF_A).status_code == 200
    cid = cliente_logado_a.get("/api/clientes").get_json()[0]["id"]
    _montar_cliente_com_veiculos(app, cliente_logado_a, "+Cliente Teste", "52998224725", [("QQQ1Q11", "@x", 10)], 1)
    r = cliente_logado_a.post("/api/relatorios/exportar/excel", json={
        "config": {"tipos": ["ipva"], "filtros": {}},
        "campos_visiveis": [{"id": "cliente_nome", "label": "Cliente"}, {"id": "proprietario", "label": "Prop"}]})
    ws = load_workbook(io.BytesIO(r.data)).active
    valores = [str(c.value) for row in ws.iter_rows(min_row=2) for c in row]
    assert not any(v.startswith(("=", "+", "@")) for v in valores), valores


def test_indices_de_chave_estrangeira_existem(app):
    from sqlalchemy import inspect
    from app import db
    with app.app_context():
        nomes = {i["name"] for t in ("ipva", "multas", "veiculos") for i in inspect(db.engine).get_indexes(t)}
    assert {"ix_ipva_veiculo_id", "ix_multas_veiculo_id", "ix_veiculos_cliente_id"} <= nomes


def test_dashboard_nao_faz_uma_consulta_por_ipva(app, cliente_logado_a):
    """Regressão: to_dict() do IPVA lia as parcelas registro a registro (N+1)."""
    from sqlalchemy import event
    from app import db

    veiculos = [(f"DD{i:02d}A00", "Prop", 10 + i) for i in range(25)]
    _montar_cliente_com_veiculos(app, cliente_logado_a, "Cliente Dashboard", CPF_A, veiculos, 1)
    total = {"n": 0}
    with app.app_context():
        def contar(*a, **k):
            total["n"] += 1
        event.listen(db.engine, "before_cursor_execute", contar)
        try:
            r = cliente_logado_a.get("/api/dashboard")
        finally:
            event.remove(db.engine, "before_cursor_execute", contar)
    assert r.status_code == 200 and len(r.get_json()["ipva"]) == 25
    assert total["n"] < 20, f"{total['n']} consultas para 25 IPVAs"
