"""
Ponto de entrada da aplicacao quando rodando em container (Cloud Run).

Diferente de run.py (dev) e launcher.py (executavel Windows), este script:
  - Nao abre navegador nem MessageBox (nao faz sentido em um container).
  - Usa FLASK_ENV=production por padrao, que exige DATABASE_URL definida
    (ver ProductionConfig em config.py).
  - Expoe `app` para o Waitress servir via `waitress-serve --call wsgi:app`.

O `db.create_all()` roda a cada start do container: e idempotente (so cria
tabelas que ainda nao existem), igual ja acontece em run.py e launcher.py.
"""
import os

from app import create_app, db
from app.services.configuracao_service import ConfiguracaoService
from app.services.auth_service import AuthService

app = create_app(os.environ.get("FLASK_ENV", "production"))

with app.app_context():
    db.create_all()
    ConfiguracaoService(db.session).seed_defaults()
    AuthService(db.session).seed_admin()
