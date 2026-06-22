from datetime import datetime
from app import db


class Documento(db.Model):
    __tablename__ = "documentos"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    data_documento = db.Column(db.String(10), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    observacao = db.Column(db.Text)
    arquivo = db.Column(db.String(200))
    criado_em = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cliente_id": self.cliente_id,
            "nome": self.nome,
            "data_documento": self.data_documento,
            "categoria": self.categoria,
            "observacao": self.observacao or "",
            "arquivo": self.arquivo or "",
            "criado_em": self.criado_em.strftime("%Y-%m-%d %H:%M:%S") if self.criado_em else "",
        }
