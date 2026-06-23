from datetime import datetime
from app import db


class IpvaParcela(db.Model):
    __tablename__ = "ipva_parcela"

    id            = db.Column(db.Integer, primary_key=True)
    ipva_id       = db.Column(db.Integer, db.ForeignKey("ipva.id", ondelete="CASCADE"), nullable=False)
    numero        = db.Column(db.Integer, nullable=False)   # 1, 2, 3...
    valor         = db.Column(db.Numeric(10, 2), nullable=False)
    vencimento    = db.Column(db.String(10), nullable=False)  # ISO YYYY-MM-DD
    status        = db.Column(db.String(20), default="pendente")  # pendente | pago | vencido
    pago_em       = db.Column(db.String(10))                  # ISO YYYY-MM-DD, nullable
    criado_em     = db.Column(db.DateTime, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "ipva_id":    self.ipva_id,
            "numero":     self.numero,
            "valor":      float(self.valor) if self.valor is not None else None,
            "vencimento": self.vencimento or "",
            "status":     self.status or "pendente",
            "pago_em":    self.pago_em or "",
        }
