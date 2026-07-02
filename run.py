"""
Ponto de entrada do Sistema Despachante.
Uso: python run.py
"""
import os
from app import create_app, db
from app.models import (
    Cliente, Veiculo, Ipva, Licenciamento,
    Multa, Documento, Configuracao, TemplateRelatorio,
    Usuario, PermissaoUsuario, LogAcao,
)
from app.services.configuracao_service import ConfiguracaoService
from app.services.auth_service import AuthService

app = create_app(os.environ.get("FLASK_ENV", "default"))


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db, "Cliente": Cliente, "Veiculo": Veiculo,
        "Ipva": Ipva, "Licenciamento": Licenciamento,
        "Multa": Multa, "Documento": Documento,
        "Usuario": Usuario,
    }


def init_db():
    """Cria tabelas, aplica valores padrão de configuração e cria admin padrão."""
    with app.app_context():
        db.create_all()
        ConfiguracaoService(db.session).seed_defaults()
        AuthService(db.session).seed_admin()


if __name__ == "__main__":
    init_db()
    print("\n✅  Sistema Despachante iniciado!")
    print("🌐  Abra no navegador: http://localhost:5000")
    print("👤  Login inicial: admin / admin123  (troque a senha no primeiro acesso)\n")
    app.run(debug=True, port=5000)
