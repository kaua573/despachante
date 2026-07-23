from datetime import datetime
from app import db


class Veiculo(db.Model):
    __tablename__ = "veiculos"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    placa = db.Column(db.String(10), nullable=False, index=True)
    renavam = db.Column(db.String(20))
    proprietario = db.Column(db.String(200))
    marca_modelo = db.Column(db.String(100))
    situacao = db.Column(db.String(20), default="ativo")
    especie = db.Column(db.String(20), default="passeio")
    observacao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.now)

    ipva_list = db.relationship("Ipva", backref="veiculo", lazy=True, cascade="all, delete-orphan")
    licenciamentos = db.relationship("Licenciamento", backref="veiculo", lazy=True, cascade="all, delete-orphan")
    multas = db.relationship("Multa", backref="veiculo", lazy=True, cascade="all, delete-orphan")

    __table_args__ = (
        # Único só ENTRE veículos não vendidos — uma placa não pode estar
        # cadastrada duas vezes como ativa/desativada ao mesmo tempo, mas o
        # sistema permite marcar um veículo como "vendido" e cadastrar a
        # mesma placa de novo depois (revenda), sem que a placa antiga
        # (histórico) bloqueie o cadastro novo.
        db.Index(
            "uq_veiculo_placa_ativo", "placa", unique=True,
            sqlite_where=db.text("situacao != 'vendido'"),
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cliente_id": self.cliente_id,
            "placa": self.placa,
            "renavam": self.renavam or "",
            "proprietario": self.proprietario or "",
            "marca_modelo": self.marca_modelo or "",
            "situacao": self.situacao or "ativo",
            "especie": self.especie or "passeio",
            "observacao": self.observacao or "",
        }
