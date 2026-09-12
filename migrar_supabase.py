"""
Copia todos os dados do SQLite (banco antigo, trazido do computador local)
colocar os 3 arquivos do banco de dados na pasta "dados_reais"
para o Postgres do Supabase. Roda uma vez só.
"""
from sqlalchemy import create_engine, text

from app import create_app, db
import app.models  # noqa: garante que todas as tabelas sejam registradas no metadata

# Caminho do banco que você copiou do computador antigo
SQLITE_PATH = r"dados_reais/despachante.db"

# A mesma DATABASE_URL do seu env.yaml
import os
POSTGRES_URL = os.environ["POSTGRES_URL"]

app = create_app("development")

with app.app_context():
    tabelas = db.metadata.sorted_tables  # ordem correta, respeitando dependências

sqlite_engine = create_engine(f"sqlite:///{SQLITE_PATH}")
postgres_engine = create_engine(POSTGRES_URL)

with sqlite_engine.connect() as origem, postgres_engine.begin() as destino:
    for tabela in reversed(tabelas):
        destino.execute(tabela.delete())

    for tabela in tabelas:
        linhas = origem.execute(tabela.select()).mappings().all()
        if not linhas:
            continue
        destino.execute(tabela.insert(), [dict(linha) for linha in linhas])

        if "id" in tabela.c:
            destino.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{tabela.name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {tabela.name}), 1))"
            ))

print("Migração concluída!")