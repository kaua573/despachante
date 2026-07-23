import os
import secrets
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
