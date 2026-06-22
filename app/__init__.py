import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from markupsafe import Markup
from config import config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    db.init_app(app)
    migrate.init_app(app, db)

    _registrar_helpers_jinja(app)
    _registrar_blueprints(app)
    _iniciar_backup_automatico(app)

    return app


def _registrar_helpers_jinja(app: Flask) -> None:
    """Registra funções e filtros globais nos templates Jinja2."""

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
        return Markup(svg)

    app.jinja_env.globals["icon"] = icon_svg

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

    app.register_blueprint(main_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(veiculos_bp)
    app.register_blueprint(painel_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(relatorios_bp)


def _iniciar_backup_automatico(app: Flask) -> None:
    import threading
    import os

    # Evita duplicar a thread quando Flask usa o reloader em modo debug
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
