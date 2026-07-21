"""Adiciona colunas valor_integral e desconto_percentual na tabela ipva

Revision ID: b7c8d9e0f1a2
Revises:
Create Date: 2026-07-21

Sem revisão anterior — este projeto não usa Flask-Migrate/Alembic
diretamente (não há env.py configurado). Para aplicar num banco já
existente, use o script migrar_ipva_desconto.py na raiz do projeto,
ou execute o SQL abaixo manualmente:

    ALTER TABLE ipva ADD COLUMN valor_integral NUMERIC(10, 2);
    ALTER TABLE ipva ADD COLUMN desconto_percentual NUMERIC(5, 2);

Bancos novos (criados do zero pelo launcher/run.py via db.create_all())
já saem com essas colunas, por já estarem declaradas no model.
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ipva', schema=None) as batch_op:
        batch_op.add_column(sa.Column('valor_integral', sa.Numeric(10, 2)))
        batch_op.add_column(sa.Column('desconto_percentual', sa.Numeric(5, 2)))


def downgrade():
    with op.batch_alter_table('ipva', schema=None) as batch_op:
        batch_op.drop_column('desconto_percentual')
        batch_op.drop_column('valor_integral')
