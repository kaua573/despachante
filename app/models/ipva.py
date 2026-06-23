from app import db


class Ipva(db.Model):
    __tablename__ = "ipva"

    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculos.id"), nullable=False)
    ano_referencia = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Float)
    vencimento = db.Column(db.String(10))  # ISO: YYYY-MM-DD
    pago = db.Column(db.Boolean, default=False)
    data_pagamento = db.Column(db.String(10))
    observacao = db.Column(db.Text)

    # Parcelas do IPVA (opcional — só existem se o usuário parcelar)
    parcelas = db.relationship(
        "IpvaParcela",
        backref="ipva",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="IpvaParcela.numero",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "veiculo_id": self.veiculo_id,
            "ano_referencia": self.ano_referencia,
            "valor": self.valor,
            "vencimento": self.vencimento or "",
            "pago": bool(self.pago),
            "data_pagamento": self.data_pagamento or "",
            "observacao": self.observacao or "",
            "num_parcelas": len(self.parcelas),
        }
