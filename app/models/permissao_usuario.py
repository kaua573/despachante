from app import db


# Códigos válidos de permissão — usados para validação e exibição no admin
PERMISSOES_DISPONIVEIS = [
    ("visualizar_veiculos",      "Consultar lista e detalhes de veículos"),
    ("cadastrar_veiculos",       "Criar e editar veículos"),
    ("excluir_veiculos",         "Excluir veículos"),
    ("visualizar_ipva",          "Consultar IPVA"),
    ("gerenciar_ipva",           "Criar, editar e quitar IPVA e parcelas"),
    ("visualizar_licenciamento", "Consultar licenciamentos"),
    ("gerenciar_licenciamento",  "Criar, editar e quitar licenciamentos"),
    ("visualizar_multas",        "Consultar multas"),
    ("gerenciar_multas",         "Criar, editar e quitar multas"),
    ("visualizar_clientes",      "Consultar clientes e proprietários"),
    ("gerenciar_clientes",       "Criar e editar clientes e proprietários"),
    ("excluir_clientes",         "Excluir clientes e proprietários"),
    ("gerar_relatorios",         "Gerar e exportar relatórios"),
    ("gerenciar_seeds",          "Executar seed de dados de teste"),
]

CODIGOS_PERMISSAO = {cod for cod, _ in PERMISSOES_DISPONIVEIS}


class PermissaoUsuario(db.Model):
    __tablename__ = "permissao_usuario"

    id         = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    permissao  = db.Column(db.String(50), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("usuario_id", "permissao", name="uq_usuario_permissao"),
    )
