from datetime import datetime
from flask_login import UserMixin
from app import db


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id               = db.Column(db.Integer, primary_key=True)
    nome_usuario     = db.Column(db.String(50), unique=True, nullable=False)
    nome_completo    = db.Column(db.String(100), nullable=False)
    senha_hash       = db.Column(db.String(255), nullable=False)
    perfil           = db.Column(db.String(20), nullable=False)  # 'administrador' | 'operador'
    ativo            = db.Column(db.Boolean, default=True, nullable=False)
    tentativas_login = db.Column(db.Integer, default=0, nullable=False)
    bloqueado_ate    = db.Column(db.DateTime, nullable=True)
    senha_temporaria = db.Column(db.Boolean, default=False, nullable=False)
    senha_expira_em  = db.Column(db.DateTime, nullable=True)
    criado_em        = db.Column(db.DateTime, default=datetime.now)
    atualizado_em    = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    ultimo_acesso    = db.Column(db.DateTime, nullable=True)

    permissoes = db.relationship(
        "PermissaoUsuario",
        backref="usuario",
        lazy=True,
        cascade="all, delete-orphan",
    )
    logs = db.relationship("LogAcao", backref="usuario", lazy=True)

    # ------------------------------------------------------------------
    # Administrador tem acesso total; operador verifica tabela de permissões
    # ------------------------------------------------------------------
    def tem_permissao(self, codigo: str) -> bool:
        if self.perfil == "administrador":
            return True
        return any(p.permissao == codigo for p in self.permissoes)

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "nome_usuario":  self.nome_usuario,
            "nome_completo": self.nome_completo,
            "perfil":        self.perfil,
            "ativo":         self.ativo,
            "ultimo_acesso": self.ultimo_acesso.strftime("%d/%m/%Y %H:%M") if self.ultimo_acesso else "",
        }
