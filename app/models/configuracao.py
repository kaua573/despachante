from app import db


class Configuracao(db.Model):
    __tablename__ = "configuracoes"

    chave = db.Column(db.String(100), primary_key=True)
    valor = db.Column(db.Text)
