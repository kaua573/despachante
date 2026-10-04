from app import db


class Configuracao(db.Model):
    __tablename__ = "configuracoes"

    escritorio_id = db.Column(db.Integer, db.ForeignKey("escritorios.id"), primary_key=True)
    chave = db.Column(db.String(100), primary_key=True)
    valor = db.Column(db.Text)
