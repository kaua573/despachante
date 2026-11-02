import os
import secrets


def _resolver_base_dir() -> str:
    """
    Diretório onde ficam o banco de dados SQLite local, uploads e backups.
    É a raiz do projeto (em produção o banco vem de DATABASE_URL).
    """
    base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    return base


BASE_DIR = _resolver_base_dir()


def _resolver_secret_key() -> str:
    """
    Chave usada para assinar o cookie de sessão do login.

    Se a variável de ambiente SECRET_KEY estiver definida, usa ela (cobre
    deploys tipo Render/Postgres, onde isso já é configurado à parte). Caso
    contrário, gera uma chave aleatória na primeira execução e persiste em
    "secret.key" dentro da pasta de dados — assim cada instalação tem sua
    própria chave, em vez de todas compartilharem um valor fixo publicado
    junto do código-fonte.
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key

    caminho = os.path.join(BASE_DIR, "secret.key")
    if os.path.isfile(caminho):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                chave_salva = f.read().strip()
            if chave_salva:
                return chave_salva
        except OSError:
            pass

    chave = secrets.token_hex(32)
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(chave)
    except OSError:
        pass  # sem permissão de escrita: segue com a chave só nesta execução
    return chave


class Config:
    SECRET_KEY = _resolver_secret_key()
    # Senha de acesso à tela /super-admin (gerenciar escritórios/tenants —
    # ver app/routes/super_admin.py). Só faz sentido na instalação que o
    # dono do sistema controla (hoje, o Cloud Run); nunca deve ser definida
    # em instalações locais (.exe) de um escritório cliente. Sem essa env
    # var definida, a tela inteira responde 404 — nem revela que existe.
    SUPER_ADMIN_TOKEN = os.environ.get("SUPER_ADMIN_TOKEN")
    # Segundo segredo, exigido SÓ para excluir um escritório em definitivo
    # (apaga todos os dados dele, sem volta). Diferente do token de acesso à
    # tela de propósito: quem está com a sessão aberta não consegue apagar
    # nada sem digitar este também. Sem essa env var, a exclusão fica
    # desativada (a tela de escritórios continua funcionando normalmente).
    SUPER_ADMIN_DELETE_TOKEN = os.environ.get("SUPER_ADMIN_DELETE_TOKEN")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Cookie de sessão: inacessível ao JavaScript e não enviado em requisições
    # que partem de outros sites (reforça a proteção contra CSRF).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
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
    # Só trafega o cookie por HTTPS (o Cloud Run já serve tudo em HTTPS)
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    # Conexões com o Postgres (Supabase) que ficam ociosas são derrubadas pelo
    # servidor: pre_ping testa a conexão antes de usar e recycle a renova.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 5,
    }

    @staticmethod
    def init_app(app):
        Config.init_app(app)
        if not ProductionConfig.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL não configurada para produção.")
        if not os.environ.get("SECRET_KEY"):
            # Sem SECRET_KEY fixa, cada instância/reinício gera uma chave nova e
            # derruba as sessões de quem está logado. Defina no Cloud Run.
            app.logger.warning("SECRET_KEY não definida: defina a variável de ambiente em produção.")


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
