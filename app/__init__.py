import os
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from markupsafe import Markup
from config import config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


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

    _registrar_helpers_jinja(app)
    _registrar_blueprints(app)
    _registrar_handlers_erro(app)
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

    @app.context_processor
    def inject_tema():
        from app.services.configuracao_service import ConfiguracaoService
        try:
            cfg = ConfiguracaoService(db.session)
            modo = cfg.get("tema_modo", "claro")
            cor_chave = cfg.get("tema_cor", "azul")
            esc_nome = cfg.get("escritorio_nome", "")
            esc_logo = cfg.get("escritorio_logo", "")
        except Exception:
            modo, cor_chave, esc_nome, esc_logo = "claro", "azul", "", ""

        from app.services.configuracao_service import PALETA_CORES
        cor = PALETA_CORES.get(cor_chave, PALETA_CORES["azul"])
        logo_url = f"/static/uploads/logo/{esc_logo}" if esc_logo else ""
        return {
            "tema_modo": modo,
            "tema_cor_chave": cor_chave,
            "tema_cor": cor,
            "escritorio_nome": esc_nome,
            "escritorio_logo_url": logo_url,
        }


def _registrar_blueprints(app: Flask) -> None:
    from app.routes.main import bp as main_bp
    from app.routes.clientes import bp as clientes_bp
    from app.routes.veiculos import bp as veiculos_bp
    from app.routes.painel import bp as painel_bp
    from app.routes.configuracoes import bp as config_bp
    from app.routes.relatorios import bp as relatorios_bp
    from app.routes.ipva import bp as ipva_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(veiculos_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(ipva_bp)


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
                    minutos = int(ConfiguracaoService(db.session).get("backup_intervalo_min", "30"))
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
