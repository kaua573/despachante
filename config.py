import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


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
    "default": DevelopmentConfig,
}
