from datetime import datetime

from app import db


class ContatoPendencia(db.Model):
    """
    Registra que algum funcionário do escritório já entrou em contato com o
    cliente sobre uma pendência específica (IPVA à vista/parcela,
    licenciamento ou multa).

    Existe para dar suporte à "Central de pendências" (visão de todos os
    clientes numa tela só): como o sistema roda em rede local para várias
    máquinas do mesmo escritório, isso evita que duas pessoas liguem para o
    mesmo cliente sobre a mesma cobrança. Não dispara nenhum contato
    automático (e-mail/WhatsApp) — só registra que uma pessoa humana já
    tratou daquele item.
    """
    __tablename__ = "contato_pendencia"

    id = db.Column(db.Integer, primary_key=True)

    # Mesmo vocabulário de "tipo" usado em PendenciaService: ipva_avista,
    # ipva_parcela, licenciamento, multa. "pendencia_id" é o id do registro
    # de origem correspondente (Ipva.id, IpvaParcela.id, etc.).
    tipo = db.Column(db.String(20), nullable=False)
    pendencia_id = db.Column(db.Integer, nullable=False)

    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculos.id"), nullable=False)

    marcado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    marcado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)
    observacao = db.Column(db.String(280))

    marcado_por = db.relationship("Usuario")

    __table_args__ = (
        db.UniqueConstraint("tipo", "pendencia_id", name="uq_contato_tipo_pendencia"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tipo": self.tipo,
            "pendencia_id": self.pendencia_id,
            "marcado_por": self.marcado_por.nome_completo if self.marcado_por else None,
            "marcado_em": self.marcado_em.strftime("%d/%m/%Y %H:%M") if self.marcado_em else None,
            "observacao": self.observacao,
        }
