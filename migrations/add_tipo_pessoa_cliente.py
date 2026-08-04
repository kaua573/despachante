"""Adiciona colunas tipo_pessoa e cnpj na tabela clientes

Revision ID: c3d4e5f6a7b8
Revises:
Create Date: 2026-08-03

Todos os clientes já cadastrados são marcados automaticamente como
tipo_pessoa='PF' (já que só era possível cadastrar CPF até então).

Aplique com: flask db upgrade
Se não usar Flask-Migrate, execute o SQL abaixo diretamente:

    ALTER TABLE clientes ADD COLUMN tipo_pessoa VARCHAR(2) NOT NULL DEFAULT 'PF';
    ALTER TABLE clientes ADD COLUMN cnpj VARCHAR(20);
    CREATE UNIQUE INDEX ix_clientes_cnpj ON clientes (cnpj);
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'tipo_pessoa',
                sa.String(length=2),
                nullable=False,
                server_default='PF',
            )
        )
        batch_op.add_column(sa.Column('cnpj', sa.String(length=20), nullable=True))
        batch_op.create_unique_constraint('uq_clientes_cnpj', ['cnpj'])


def downgrade():
    with op.batch_alter_table('clientes', schema=None) as batch_op:
        batch_op.drop_constraint('uq_clientes_cnpj', type_='unique')
        batch_op.drop_column('cnpj')
        batch_op.drop_column('tipo_pessoa')
