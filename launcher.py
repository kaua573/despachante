"""
Launcher de produção do Sistema Despachante.

Usado como ponto de entrada do executável empacotado (PyInstaller). Diferente
de run.py (usado em desenvolvimento), este script:

  - Sobe o servidor com Waitress em vez do servidor de desenvolvimento do
    Flask (sem debug, sem reloader, sem avisos de "não use em produção").
  - Roda sem janela de console (o .spec constrói o .exe com console=False).
  - Abre o navegador padrão automaticamente em http://127.0.0.1:5000.
  - Garante que só existe uma instância do sistema rodando por vez.
  - Por padrão só aceita conexões da própria máquina (127.0.0.1). Se existir
    o arquivo "rede_local.flag" dentro da pasta "dados" (ao lado do
    executável), passa a aceitar conexões de outros computadores da rede
    local também.

Uso normal: não é executado diretamente por quem usa o sistema — é o alvo do
build do PyInstaller (veja despachante.spec) e roda dentro do .exe gerado.
"""
import os
import socket
import sys
import threading
import webbrowser

# Garante que o diretório do próprio script está no path (necessário em
# alguns modos de execução do PyInstaller)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Config usada quando congelado (.exe): debug desligado, dados na pasta "dados"
os.environ.setdefault("FLASK_ENV", "desktop" if getattr(sys, "frozen", False) else "development")

import config as app_config  # usa o mesmo BASE_DIR (dados) que o resto do sistema

PORT = 5000
FLAG_REDE_LOCAL = os.path.join(app_config.BASE_DIR, "rede_local.flag")


def _rede_local_ativada() -> bool:
    """
    Liga/desliga o acesso por outros computadores da rede.

    Controlado por um arquivo simples em vez de variável de ambiente para que
    dê para ativar/desativar sem precisar reinstalar ou mexer em atalhos:
    basta criar ou apagar "rede_local.flag" dentro da pasta "dados" ao lado
    do executável.
    """
    return os.path.exists(FLAG_REDE_LOCAL)


def _ip_local() -> str:
    """Descobre o IP da máquina na rede local (não depende de internet real)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _porta_em_uso(host: str, port: int) -> bool:
    """Verifica se já existe uma instância do sistema rodando nesta porta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _abrir_navegador() -> None:
    # O navegador sempre abre via localhost nesta própria máquina,
    # independente de o servidor também estar escutando na rede (0.0.0.0).
    webbrowser.open(f"http://127.0.0.1:{PORT}")


def _avisar_endereco_rede() -> None:
    """Mostra um aviso nativo do Windows com o endereço para outros PCs acessarem."""
    ip = _ip_local()
    mensagem = (
        f"O Sistema Despachante também está acessível por outros computadores "
        f"da mesma rede local em:\n\nhttp://{ip}:{PORT}\n\n"
        f"Se o Firewall do Windows perguntar, clique em 'Permitir acesso' "
        f"(rede privada)."
    )
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, mensagem, "Sistema Despachante - Acesso pela rede", 0x40)
    except (AttributeError, OSError):
        # Não está no Windows (ex.: testando launcher.py em dev no Linux/mac) — ignora.
        pass


def main() -> None:
    host = "0.0.0.0" if _rede_local_ativada() else "127.0.0.1"

    if _porta_em_uso("127.0.0.1", PORT):
        # Sistema já está rodando (ex.: usuário clicou duas vezes no atalho) —
        # só abre o navegador na instância existente e encerra esta.
        _abrir_navegador()
        return

    from app import create_app, db
    from app.services.configuracao_service import ConfiguracaoService
    from app.services.auth_service import AuthService

    app = create_app(os.environ.get("FLASK_ENV", "default"))

    with app.app_context():
        db.create_all()
        ConfiguracaoService(db.session).seed_defaults()
        AuthService(db.session).seed_admin()

    threading.Timer(1.2, _abrir_navegador).start()
    if host == "0.0.0.0":
        threading.Timer(2.0, _avisar_endereco_rede).start()

    from waitress import serve
    serve(app, host=host, port=PORT, _quiet=True)


if __name__ == "__main__":
    main()
