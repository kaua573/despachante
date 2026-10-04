from datetime import datetime
from app import db


class Escritorio(db.Model):
    __tablename__ = "escritorios"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "nome": self.nome,
            "ativo": self.ativo,
        }
