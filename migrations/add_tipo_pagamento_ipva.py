"""Adiciona coluna tipo_pagamento na tabela ipva

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-06-23

Sem revisão anterior — aplique com: flask db upgrade
Se não usar Flask-Migrate, execute o SQL abaixo diretamente:

    ALTER TABLE ipva ADD COLUMN tipo_pagamento VARCHAR(10) NOT NULL DEFAULT 'avista';
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ipva', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'tipo_pagamento',
                sa.String(length=10),
                nullable=False,
                server_default='avista',
            )
        )


def downgrade():
    with op.batch_alter_table('ipva', schema=None) as batch_op:
        batch_op.drop_column('tipo_pagamento')
