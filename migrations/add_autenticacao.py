"""Adiciona tabelas de autenticação: usuarios, permissao_usuario, log_acao

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-30

Aplique com: flask db upgrade
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'usuarios',
        sa.Column('id',               sa.Integer(),     primary_key=True),
        sa.Column('nome_usuario',     sa.String(50),    nullable=False, unique=True),
        sa.Column('nome_completo',    sa.String(100),   nullable=False),
        sa.Column('senha_hash',       sa.String(255),   nullable=False),
        sa.Column('perfil',           sa.String(20),    nullable=False),
        sa.Column('ativo',            sa.Boolean(),     nullable=False, server_default='1'),
        sa.Column('tentativas_login', sa.Integer(),     nullable=False, server_default='0'),
        sa.Column('bloqueado_ate',    sa.DateTime(),    nullable=True),
        sa.Column('senha_temporaria', sa.Boolean(),     nullable=False, server_default='0'),
        sa.Column('senha_expira_em',  sa.DateTime(),    nullable=True),
        sa.Column('criado_em',        sa.DateTime(),    nullable=True),
        sa.Column('atualizado_em',    sa.DateTime(),    nullable=True),
        sa.Column('ultimo_acesso',    sa.DateTime(),    nullable=True),
    )

    op.create_table(
        'permissao_usuario',
        sa.Column('id',         sa.Integer(),  primary_key=True),
        sa.Column('usuario_id', sa.Integer(),  sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('permissao',  sa.String(50), nullable=False),
        sa.UniqueConstraint('usuario_id', 'permissao', name='uq_usuario_permissao'),
    )

    op.create_table(
        'log_acao',
        sa.Column('id',          sa.Integer(),  primary_key=True),
        sa.Column('usuario_id',  sa.Integer(),  sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('acao',        sa.String(100), nullable=False),
        sa.Column('entidade',    sa.String(50),  nullable=True),
        sa.Column('entidade_id', sa.Integer(),   nullable=True),
        sa.Column('detalhe',     sa.Text(),      nullable=True),
        sa.Column('ip',          sa.String(45),  nullable=True),
        sa.Column('criado_em',   sa.DateTime(),  nullable=True),
    )


def downgrade():
    op.drop_table('log_acao')
    op.drop_table('permissao_usuario')
    op.drop_table('usuarios')
