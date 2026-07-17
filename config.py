import os
import sys


def _resolver_base_dir() -> str:
    """
    Diretório onde ficam o banco de dados, uploads e backups (dados do usuário).

    - Em desenvolvimento (`python run.py`): raiz do projeto, como sempre foi.
    - Empacotado como .exe (PyInstaller, modo --onedir): o instalador (Inno
      Setup) pergunta na tela de instalação onde salvar os dados e grava a
      resposta em "local_dados.cfg", ao lado do executável. Se esse arquivo
      existir, o caminho salvo nele é usado. Se não existir (ex.: instalação
      antiga, ou o .exe rodando fora do instalador), cai no padrão: subpasta
      "dados" ao lado do executável.
      Em qualquer um dos dois casos, fica fora da pasta que o instalador
      sobrescreve em atualizações — os dados nunca são apagados ao atualizar
      ou desinstalar o programa.
    """
    if getattr(sys, "frozen", False):
        pasta_do_programa = os.path.dirname(sys.executable)
        arquivo_config = os.path.join(pasta_do_programa, "local_dados.cfg")
        base = None
        if os.path.isfile(arquivo_config):
            try:
                with open(arquivo_config, "r", encoding="utf-8") as f:
                    caminho_salvo = f.read().strip()
                if caminho_salvo:
                    base = caminho_salvo
            except OSError:
                base = None
        if not base:
            base = os.path.join(pasta_do_programa, "dados")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    return base


BASE_DIR = _resolver_base_dir()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "despachante-local-dev-key-troque-em-producao")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_DIR = os.path.join(BASE_DIR, "app", "static", "uploads", "documentos")
    LOGO_DIR = os.path.join(BASE_DIR, "app", "static", "uploads", "logo")
    BACKUP_DIR = os.path.join(BASE_DIR, "backups")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Extensões permitidas para upload de documentos
    EXTENSOES_DOCUMENTO = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}
    # Extensões permitidas para logo
    EXTENSOES_LOGO = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

    @staticmethod
    def init_app(app):
        os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
        os.makedirs(Config.LOGO_DIR, exist_ok=True)
        os.makedirs(Config.BACKUP_DIR, exist_ok=True)


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'despachante.db')}"
    )


class DesktopConfig(Config):
    """
    Config usada pelo executável empacotado (launcher.py + Waitress).
    Mesma base SQLite da DevelopmentConfig, porém com DEBUG desligado —
    não expõe o debugger interativo do Werkzeug para o usuário final.
    """
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'despachante.db')}"
    )


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    @staticmethod
    def init_app(app):
        Config.init_app(app)
        if not ProductionConfig.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL não configurada para produção.")


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "desktop": DesktopConfig,
    "default": DevelopmentConfig,
}
