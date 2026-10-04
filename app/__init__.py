import os
import sqlite3
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from markupsafe import Markup
from sqlalchemy import event
from sqlalchemy.engine import Engine
from config import config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


@event.listens_for(Engine, "connect")
def _ativar_wal_sqlite(dbapi_connection, connection_record):
    """
    Liga o modo WAL (Write-Ahead Logging) do SQLite em toda conexão nova.

    Isso ajuda em duas frentes: reduz bastante o erro "database is locked"
    quando mais de uma pessoa usa o sistema ao mesmo tempo (acesso pela rede
    local), e deixa leituras concorrentes (como o backup automático) mais
    seguras enquanto o banco está sendo escrito. Não tem efeito nenhum se o
    banco for PostgreSQL — o filtro isinstance abaixo garante isso.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    db.init_app(app)
    migrate.init_app(app, db)

    # Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = None  # sem flash — o redirect já é suficiente

    @login_manager.user_loader
    def load_user(user_id: str):
        from app.models.usuario import Usuario
        return db.session.get(Usuario, int(user_id))

    _registrar_escopo_tenant(app)

    _registrar_helpers_jinja(app)
    _registrar_blueprints(app)
    _registrar_handlers_erro(app)
    _registrar_favicon(app)
    _iniciar_backup_automatico(app)

    return app


def _registrar_helpers_jinja(app: Flask) -> None:
    def icon_svg(nome: str, classe: str = "icon") -> Markup:
        caminho = os.path.join(app.static_folder, "icons", f"{nome}.svg")
        if not os.path.exists(caminho):
            return Markup("")
        with open(caminho, "r", encoding="utf-8") as f:
            svg = f.read()
        import re
        if 'class="' in svg.split(">", 1)[0]:
            svg = re.sub(r'class="[^"]*"', f'class="{classe}"', svg, count=1)
        else:
            svg = svg.replace("<svg ", f'<svg class="{classe}" ', 1)

        svg = re.sub(r'(<svg[^>]*?)\s+fill="(?!none)[^"]*"', r'\1', svg, count=1)
        return Markup(svg)

    app.jinja_env.globals["icon"] = icon_svg

    from app.services.validacao_service import formatar_cpf, formatar_telefone, normalizar_placa

    app.jinja_env.filters["formatar_cpf"] = formatar_cpf
    app.jinja_env.filters["formatar_telefone"] = formatar_telefone

    def formatar_placa_exibicao(placa: str) -> str:
        return normalizar_placa(placa)

    app.jinja_env.filters["formatar_placa"] = formatar_placa_exibicao

    def fromjson(texto):
        """Usado na tela de log para tentar interpretar `detalhe` como JSON
        estruturado (antes/depois). Se não for JSON válido, retorna None e o
        template cai de volta para exibir o texto puro."""
        import json
        if not texto:
            return None
        try:
            return json.loads(texto)
        except (TypeError, ValueError):
            return None

    app.jinja_env.filters["fromjson"] = fromjson

    @app.context_processor
    def inject_tema():
        from flask import g
        from app.services.configuracao_service import ConfiguracaoService
        from app.services.base import escritorio_padrao_id
        from flask_login import current_user
        try:
            # Ordem de resolução: usuário logado > escritório já resolvido
            # nesta request pela rota de login por slug (g.escritorio_id
            # setado em auth.py antes de chamar render_template) > fallback
            # pro escritório "principal" (páginas sem usuário e sem slug,
            # como o seletor de escritório em /login).
            if current_user.is_authenticated:
                eid = current_user.escritorio_id
            elif getattr(g, "escritorio_id", None) is not None:
                eid = g.escritorio_id
            else:
                eid = escritorio_padrao_id(db.session)
            cfg = ConfiguracaoService(db.session, eid)
            modo = cfg.get("tema_modo", "claro")
            cor_chave = cfg.get("tema_cor", "azul")
            esc_nome = cfg.get("escritorio_nome", "")
            esc_logo = cfg.get("escritorio_logo", "")
        except Exception:
            modo, cor_chave, esc_nome, esc_logo = "claro", "azul", "", ""

        from app.services.configuracao_service import resolver_cor
        cor = resolver_cor(cor_chave)
        logo_url = ""
        if esc_logo:
            logo_url = f"/static/uploads/logo/{esc_logo}"
            try:
                caminho = os.path.join(app.config["LOGO_DIR"], esc_logo)
                logo_url += f"?v={int(os.path.getmtime(caminho))}"
            except OSError:
                pass
        return {
            "tema_modo": modo,
            "tema_cor_chave": cor_chave,
            "tema_cor": cor,
            "escritorio_nome": esc_nome,
            "escritorio_logo_url": logo_url,
        }


def aplicar_migracoes_leves(app: Flask) -> None:
    """
    Aplica migrações leves e idempotentes de schema (adicionar colunas que
    ainda não existem) diretamente via SQLite, sem depender do Flask-Migrate/
    Alembic estar configurado com `flask db init`.

    Motivo de existir: a instalação empacotada (.exe) não tem Python nem
    Flask CLI disponíveis na máquina do cliente, então `flask db upgrade`
    não é uma opção lá. Chamando esta função a cada start-up (logo após
    `db.create_all()`), a correção de schema vem embutida no próprio
    executável — o usuário só precisa instalar a versão nova por cima.

    Seguro de rodar repetidas vezes: cada bloco só altera a tabela se a
    coluna ainda não existir.
    """
    from sqlalchemy import inspect, text

    with app.app_context():
        inspector = inspect(db.engine)
        if "clientes" not in inspector.get_table_names():
            return  # instalação nova — create_all() já cria com o schema atual

        colunas = {c["name"] for c in inspector.get_columns("clientes")}

        with db.engine.begin() as conn:
            if "tipo_pessoa" not in colunas:
                conn.execute(text(
                    "ALTER TABLE clientes ADD COLUMN tipo_pessoa VARCHAR(2) NOT NULL DEFAULT 'PF'"
                ))
            if "cnpj" not in colunas:
                conn.execute(text("ALTER TABLE clientes ADD COLUMN cnpj VARCHAR(20)"))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_clientes_cnpj ON clientes (cnpj)"
                ))

        if "log_acao" in inspector.get_table_names():
            colunas_log = {c["name"] for c in inspector.get_columns("log_acao")}
            with db.engine.begin() as conn:
                if "usuario_nome" not in colunas_log:
                    conn.execute(text("ALTER TABLE log_acao ADD COLUMN usuario_nome VARCHAR(100)"))
                if "hash_anterior" not in colunas_log:
                    conn.execute(text("ALTER TABLE log_acao ADD COLUMN hash_anterior VARCHAR(64)"))
                    conn.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_log_acao_hash_anterior ON log_acao (hash_anterior)"
                    ))
                if "hash_atual" not in colunas_log:
                    conn.execute(text("ALTER TABLE log_acao ADD COLUMN hash_atual VARCHAR(64)"))
                    conn.execute(text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS uq_log_acao_hash_atual ON log_acao (hash_atual)"
                    ))

        _aplicar_migracao_multi_tenant(app, inspector)


def _aplicar_migracao_multi_tenant(app: Flask, inspector) -> None:
    """
    Introduz o suporte a múltiplos escritórios (tenants) em uma instalação
    que já existia como single-tenant.

    Estratégia: `db.create_all()` (chamado antes desta função) já criou a
    tabela `escritorios` nova, porque ela não existia. O que falta é: (1)
    garantir que existe um registro nela representando o escritório atual —
    quem já usava o sistema antes dessa mudança — e (2) adicionar a coluna
    `escritorio_id` em cada tabela que passou a exigi-la, preenchendo com o
    id desse escritório "herdado" nas linhas que já existiam.

    Sem isso, `escritorio_id NOT NULL` nos models quebraria toda leitura
    das linhas antigas, que não têm valor nenhum nessa coluna.

    Deliberadamente NÃO mexe ainda nas constraints únicas antigas (cpf/cnpj
    globais, nome_usuario global, hash do log global) — isso exige
    reconstruir a tabela inteira no SQLite (não dá pra fazer com ALTER
    TABLE simples) e não é bloqueante enquanto só um escritório estiver
    ativo. Ver observação de acompanhamento nesta função quando isso for
    implementado.
    """
    from sqlalchemy import text

    if "escritorios" not in inspector.get_table_names():
        return  # db.create_all() deveria ter criado — nada a fazer aqui

    with db.engine.begin() as conn:
        existe_algum = conn.execute(text("SELECT COUNT(*) FROM escritorios")).scalar()
        if existe_algum:
            escritorio_id = conn.execute(
                text("SELECT id FROM escritorios ORDER BY id LIMIT 1")
            ).scalar()
        else:
            # Instalação que já tinha dados antes do multi-tenant existir:
            # cria o escritório "herdado" que vai ser dono de tudo que já
            # existe. O nome/slug reais podem ser ajustados depois em
            # Configurações — o que importa aqui é o id existir.
            if db.engine.dialect.name == "postgresql":
                escritorio_id = conn.execute(text(
                    "INSERT INTO escritorios (slug, nome, ativo) "
                    "VALUES ('principal', 'Escritório principal', true) "
                    "RETURNING id"
                )).scalar()
            else:
                conn.execute(text(
                    "INSERT INTO escritorios (slug, nome, ativo) "
                    "VALUES ('principal', 'Escritório principal', 1)"
                ))
                escritorio_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()

    tabelas_para_migrar = {
        "usuarios": "INTEGER",
        "clientes": "INTEGER",
        "veiculos": "INTEGER",
        "regra_vencimento": "INTEGER",
        "templates_relatorio": "INTEGER",
        "log_acao": "INTEGER",
    }

    for tabela, tipo_coluna in tabelas_para_migrar.items():
        if tabela not in inspector.get_table_names():
            continue
        colunas = {c["name"] for c in inspector.get_columns(tabela)}
        if "escritorio_id" in colunas:
            continue
        with db.engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN escritorio_id {tipo_coluna}"))
            conn.execute(
                text(f"UPDATE {tabela} SET escritorio_id = :eid WHERE escritorio_id IS NULL"),
                {"eid": escritorio_id},
            )
        app.logger.info(f"[multi-tenant] escritorio_id adicionado e preenchido em '{tabela}'")

    # `configuracoes` é especial: a chave primária deixa de ser só `chave` e
    # passa a ser composta (escritorio_id, chave). Mudar a PK de uma tabela
    # existente não dá pra fazer com ALTER TABLE ADD COLUMN simples em
    # nenhum dos dois bancos — mas como o volume de linhas é pequeno
    # (algumas dezenas de chaves de config), reconstruir a tabela aqui é
    # seguro e rápido.
    if "configuracoes" in inspector.get_table_names():
        colunas_config = {c["name"] for c in inspector.get_columns("configuracoes")}
        if "escritorio_id" not in colunas_config:
            with db.engine.begin() as conn:
                conn.execute(text(
                    "CREATE TABLE configuracoes_novo ("
                    "escritorio_id INTEGER NOT NULL, "
                    "chave VARCHAR(100) NOT NULL, "
                    "valor TEXT, "
                    "PRIMARY KEY (escritorio_id, chave))"
                ))
                conn.execute(
                    text(
                        "INSERT INTO configuracoes_novo (escritorio_id, chave, valor) "
                        "SELECT :eid, chave, valor FROM configuracoes"
                    ),
                    {"eid": escritorio_id},
                )
                conn.execute(text("DROP TABLE configuracoes"))
                conn.execute(text("ALTER TABLE configuracoes_novo RENAME TO configuracoes"))
            app.logger.info("[multi-tenant] tabela 'configuracoes' migrada para chave composta")


def _registrar_blueprints(app: Flask) -> None:
    from app.routes.main import bp as main_bp
    from app.routes.clientes import bp as clientes_bp
    from app.routes.veiculos import bp as veiculos_bp
    from app.routes.veiculos_geral import bp as veiculos_geral_bp
    from app.routes.painel import bp as painel_bp
    from app.routes.configuracoes import bp as config_bp
    from app.routes.relatorios import bp as relatorios_bp
    from app.routes.ipva import bp as ipva_bp
    from app.routes.pendencias import bp as pendencias_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.super_admin import bp as super_admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(super_admin_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(veiculos_bp)
    app.register_blueprint(veiculos_geral_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(ipva_bp)
    app.register_blueprint(pendencias_bp)


def _registrar_favicon(app: Flask) -> None:
    @app.route("/favicon.ico")
    def favicon():
        from flask import redirect, Response
        from app.services.configuracao_service import ConfiguracaoService
        from app.services.base import escritorio_padrao_id
        try:
            logo = ConfiguracaoService(db.session, escritorio_padrao_id(db.session)).get("escritorio_logo", "")
        except Exception:
            logo = ""
        if not logo:
            return Response(status=204)
        return redirect(f"/static/uploads/logo/{logo}", code=302)


def _registrar_escopo_tenant(app: Flask) -> None:
    """
    Fixa `g.escritorio_id` uma vez por request, a partir do usuário logado.
    Todo service que lida com dado de escritório usa esse valor — nenhuma
    rota resolve "de qual escritório é isso" por conta própria, evitando
    que cada uma decida (ou esqueça de decidir) isso do seu próprio jeito.

    Fica `None` em rotas sem usuário logado (ex.: a própria tela de login) —
    por ora essas rotas não tocam dado de escritório nenhum, então não tem
    problema. Se isso mudar, o valor `None` já faz `TenantService.scoped()`
    estourar erro na hora, em vez de vazar dado silenciosamente.
    """
    from flask import g
    from flask_login import current_user

    @app.before_request
    def _definir_escritorio_atual():
        g.escritorio_id = current_user.escritorio_id if current_user.is_authenticated else None


def _registrar_handlers_erro(app: Flask) -> None:
    @app.errorhandler(403)
    def acesso_negado(e):
        return render_template("errors/403.html"), 403


def _iniciar_backup_automatico(app: Flask) -> None:
    import threading

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and app.debug:
        return

    from app.services.backup_service import BackupService

    def _loop():
        import time
        from app.services.configuracao_service import ConfiguracaoService

        evento = BackupService.evento_reagendamento

        while True:
            with app.app_context():
                try:
                    from app.services.base import escritorio_padrao_id
                    # O backup é do banco inteiro (todos os escritórios), então
                    # o intervalo configurado não é por tenant de verdade — lê
                    # do escritório "principal" como configuração efetivamente
                    # global do sistema.
                    minutos = int(ConfiguracaoService(db.session, escritorio_padrao_id(db.session)).get("backup_intervalo_min", "30"))
                except Exception:
                    minutos = 30

            segundos = max(60, minutos * 60)
            evento.wait(timeout=segundos)
            evento.clear()

            with app.app_context():
                try:
                    BackupService(app.config["BACKUP_DIR"]).fazer_backup()
                except Exception as e:
                    app.logger.error(f"[backup] Erro no backup automático: {e}")

    t = threading.Thread(target=_loop, daemon=True, name="backup-auto")
    t.start()
