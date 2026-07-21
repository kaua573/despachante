from app import db


class Ipva(db.Model):
    __tablename__ = "ipva"

    id             = db.Column(db.Integer, primary_key=True)
    veiculo_id     = db.Column(db.Integer, db.ForeignKey("veiculos.id"), nullable=False)
    ano_referencia = db.Column(db.Integer, nullable=False)
    valor          = db.Column(db.Numeric(10, 2))   # valor final a pagar (já com desconto, se houver)
    vencimento     = db.Column(db.String(10))       # ISO: YYYY-MM-DD
    pago           = db.Column(db.Boolean, default=False)
    data_pagamento = db.Column(db.String(10))
    observacao     = db.Column(db.Text)

    # Só usados no modo 'avista'. Guardados separadamente do 'valor' final
    # para que o cadastro (valor integral + % de desconto) fique visível
    # depois, em vez de se perder ao reabrir o registro.
    valor_integral      = db.Column(db.Numeric(10, 2))
    desconto_percentual = db.Column(db.Numeric(5, 2))

    # 'avista' → quitação única; 'parcelado' → apenas via parcelas individuais
    tipo_pagamento = db.Column(db.String(10), nullable=False, default="avista")

    parcelas = db.relationship(
        "IpvaParcela",
        backref="ipva",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="IpvaParcela.numero",
    )

    def to_dict(self) -> dict:
        return {
            "id":                  self.id,
            "veiculo_id":          self.veiculo_id,
            "ano_referencia":      self.ano_referencia,
            "valor":               float(self.valor) if self.valor is not None else None,
            "valor_integral":      float(self.valor_integral) if self.valor_integral is not None else None,
            "desconto_percentual": float(self.desconto_percentual) if self.desconto_percentual is not None else None,
            "vencimento":          self.vencimento or "",
            "pago":                bool(self.pago),
            "data_pagamento":      self.data_pagamento or "",
            "observacao":          self.observacao or "",
            "tipo_pagamento":      self.tipo_pagamento or "avista",
            "num_parcelas":        len(self.parcelas),
        }
