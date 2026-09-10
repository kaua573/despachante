from app import db


class RegraVencimento(db.Model):
    """
    Regra configurável de vencimento de licenciamento por final de placa +
    espécie do veículo (carga/passeio/reboque). Usada para prever a data de
    vencimento de veículos que ainda não têm o licenciamento do ano lançado,
    e para o lançamento em lote (item 3 do pedido de set/2026).

    Uma regra vale para TODOS os anos: o vencimento é sempre calculado como
    `mes_vencimento`/`dia_vencimento` do ano de referência escolhido na tela.
    """
    __tablename__ = "regra_vencimento"

    id             = db.Column(db.Integer, primary_key=True)
    final_placa    = db.Column(db.String(1), nullable=False)   # '0' a '9'
    especie        = db.Column(db.String(20), nullable=False)  # carga | passeio | reboque
    mes_vencimento = db.Column(db.Integer, nullable=False)     # 1-12
    dia_vencimento = db.Column(db.Integer, nullable=True)      # 1-31; nulo = último dia do mês
    ativo          = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("final_placa", "especie", name="uq_regra_final_especie"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "final_placa": self.final_placa,
            "especie": self.especie,
            "mes_vencimento": self.mes_vencimento,
            "dia_vencimento": self.dia_vencimento,
            "ativo": bool(self.ativo),
        }
