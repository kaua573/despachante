"""
Launcher de produção do Sistema Despachante.

Usado como ponto de entrada do executável empacotado (PyInstaller). Diferente
de run.py (usado em desenvolvimento), este script:

  - Sobe o servidor com Waitress em vez do servidor de desenvolvimento do
    Flask (sem debug, sem reloader, sem avisos de "não use em produção").
  - Roda sem janela de console (o .spec constrói o .exe com console=False).
  - Abre o navegador padrão automaticamente em http://127.0.0.1:5000.
  - Garante que só existe uma instância do sistema rodando por vez.

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

# Config usada quando congelado (.exe): debug desligado, dados em %APPDATA%
os.environ.setdefault("FLASK_ENV", "desktop" if getattr(sys, "frozen", False) else "development")

HOST = "127.0.0.1"
PORT = 5000


def _porta_em_uso(host: str, port: int) -> bool:
    """Verifica se já existe uma instância do sistema rodando nesta porta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _abrir_navegador() -> None:
    webbrowser.open(f"http://{HOST}:{PORT}")


def main() -> None:
    if _porta_em_uso(HOST, PORT):
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

    from waitress import serve
    serve(app, host=HOST, port=PORT, _quiet=True)


if __name__ == "__main__":
    main()
