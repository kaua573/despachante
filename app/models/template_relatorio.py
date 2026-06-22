from datetime import datetime
from app import db


class TemplateRelatorio(db.Model):
    __tablename__ = "templates_relatorio"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    config_json = db.Column(db.Text, nullable=False)  # JSON serializado da configuração
    criado_em = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "nome": self.nome,
            "config_json": self.config_json,
            "criado_em": self.criado_em.strftime("%Y-%m-%d %H:%M:%S") if self.criado_em else "",
            "atualizado_em": self.atualizado_em.strftime("%Y-%m-%d %H:%M:%S") if self.atualizado_em else "",
        }
