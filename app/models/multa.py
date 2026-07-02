from app import db


class Multa(db.Model):
    __tablename__ = "multas"

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculos.id"), nullable=False)
    auto_infracao = db.Column(db.String(50))
    data_infracao = db.Column(db.String(10))
    descricao = db.Column(db.Text)
    valor = db.Column(db.Numeric(10, 2))
    vencimento = db.Column(db.String(10))
    pago = db.Column(db.Boolean, default=False)
    data_pagamento = db.Column(db.String(10))
    observacao = db.Column(db.Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "veiculo_id": self.veiculo_id,
            "auto_infracao": self.auto_infracao or "",
            "data_infracao": self.data_infracao or "",
            "descricao": self.descricao or "",
            "valor": float(self.valor) if self.valor is not None else None,
            "vencimento": self.vencimento or "",
            "pago": bool(self.pago),
            "data_pagamento": self.data_pagamento or "",
            "observacao": self.observacao or "",
        }
