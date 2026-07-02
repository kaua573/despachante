from datetime import datetime
from app import db


class LogAcao(db.Model):
    __tablename__ = "log_acao"

    id          = db.Column(db.Integer, primary_key=True)
    usuario_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    acao        = db.Column(db.String(100), nullable=False)
    entidade    = db.Column(db.String(50), nullable=True)
    entidade_id = db.Column(db.Integer, nullable=True)
    detalhe     = db.Column(db.Text, nullable=True)
    ip          = db.Column(db.String(45), nullable=True)
    criado_em   = db.Column(db.DateTime, default=datetime.now)
