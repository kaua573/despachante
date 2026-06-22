"""
Ponto de entrada do Sistema Despachante.
Uso: python run.py
"""
import os
from app import create_app, db
from app.models import (
    Cliente, Veiculo, Ipva, Licenciamento,
    Multa, Documento, Configuracao, TemplateRelatorio,
)
from app.services.configuracao_service import ConfiguracaoService

app = create_app(os.environ.get("FLASK_ENV", "default"))


@app.shell_context_processor
def make_shell_context():
    return {
        "db": db, "Cliente": Cliente, "Veiculo": Veiculo,
        "Ipva": Ipva, "Licenciamento": Licenciamento,
        "Multa": Multa, "Documento": Documento,
    }


def init_db():
    """Cria tabelas e aplica valores padrão de configuração."""
    with app.app_context():
        db.create_all()
        ConfiguracaoService(db.session).seed_defaults()


if __name__ == "__main__":
    init_db()
    print("\n✅  Sistema Despachante iniciado!")
    print("🌐  Abra no navegador: http://localhost:5000\n")
    app.run(debug=True, port=5000)
