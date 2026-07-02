from app import db


class Licenciamento(db.Model):
    __tablename__ = "licenciamento"

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculos.id"), nullable=False)
    ano_referencia = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Numeric(10, 2))
    vencimento = db.Column(db.String(10))
    pago = db.Column(db.Boolean, default=False)
    data_pagamento = db.Column(db.String(10))
    observacao = db.Column(db.Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "veiculo_id": self.veiculo_id,
            "ano_referencia": self.ano_referencia,
            "valor": float(self.valor) if self.valor is not None else None,
            "vencimento": self.vencimento or "",
            "pago": bool(self.pago),
            "data_pagamento": self.data_pagamento or "",
            "observacao": self.observacao or "",
        }
