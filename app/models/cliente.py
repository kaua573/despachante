from datetime import datetime
from app import db


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    tipo_pessoa = db.Column(db.String(2), nullable=False, default="PF", server_default="PF")
    cpf = db.Column(db.String(20), unique=True)
    cnpj = db.Column(db.String(20), unique=True)
    telefone = db.Column(db.String(30))
    email = db.Column(db.String(100))
    observacao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.now)

    veiculos = db.relationship("Veiculo", backref="cliente", lazy=True, cascade="all, delete-orphan")
    documentos = db.relationship("Documento", backref="cliente", lazy=True, cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "tipo_pessoa": self.tipo_pessoa or "PF",
            "cpf": self.cpf or "",
            "cnpj": self.cnpj or "",
            "telefone": self.telefone or "",
            "email": self.email or "",
            "observacao": self.observacao or "",
            "criado_em": self.criado_em.strftime("%Y-%m-%d %H:%M:%S") if self.criado_em else "",
        }
