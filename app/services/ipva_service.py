"""
Serviço de parcelamento e quitação de IPVA.

Regras de negócio:
- tipo_pagamento='avista'    → quitar o registro inteiro de uma vez via quitar_avista()
- tipo_pagamento='parcelado' → somente quitar parcela a parcela via quitar_parcela()
- A troca de modo (avista ↔ parcelado) ao gerar/remover parcelas é controlada aqui.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.ipva import Ipva
from app.models.ipva_parcela import IpvaParcela


class IpvaService:
    # DETRAN-SP: máximo 5 parcelas
    MAX_PARCELAS = 5

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Parcelas ──────────────────────────────────────────────────────────────

    def listar_parcelas(self, ipva_id: int) -> list[IpvaParcela]:
        """Retorna parcelas com status de vencimento atualizado antes de retornar."""
        self._atualizar_status_vencidos(ipva_id)
        return (
            self._session.query(IpvaParcela)
            .filter_by(ipva_id=ipva_id)
            .order_by(IpvaParcela.numero)
            .all()
        )

    def gerar_parcelas(
        self,
        ipva_id: int,
        num_parcelas: int,
        valor_total: float,
        data_primeira: str,
    ) -> tuple[bool, str]:
        """
        Gera (ou regenera) as parcelas de um IPVA e marca o registro como 'parcelado'.

        - Remove parcelas existentes antes de criar as novas (regeneração segura).
        - Divide o valor igualmente; centavos de arredondamento vão na última parcela.
        - Vencimentos são mensais a partir de data_primeira.
        - Muda tipo_pagamento para 'parcelado' e limpa pago/data_pagamento do pai.
        """
        if not 1 <= num_parcelas <= self.MAX_PARCELAS:
            return False, f"Número de parcelas deve ser entre 1 e {self.MAX_PARCELAS}."

        ipva = self._session.get(Ipva, ipva_id)
        if not ipva:
            return False, "IPVA não encontrado."

        try:
            data_base = date.fromisoformat(data_primeira)
        except (ValueError, TypeError):
            return False, "Data da primeira parcela inválida."

        if valor_total is None or float(valor_total) <= 0:
            return False, "Valor do IPVA deve ser maior que zero para parcelar."

        # Remove parcelas existentes para permitir regeneração
        self._session.query(IpvaParcela).filter_by(ipva_id=ipva_id).delete()

        total = Decimal(str(valor_total))
        valor_parcela = (total / num_parcelas).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        soma_parcelas = valor_parcela * (num_parcelas - 1)
        valor_ultima = total - soma_parcelas  # absorve diferença de centavos

        for i in range(num_parcelas):
            venc = self._avancar_meses(data_base, i)
            valor = valor_ultima if i == num_parcelas - 1 else valor_parcela
            self._session.add(IpvaParcela(
                ipva_id=ipva_id,
                numero=i + 1,
                valor=valor,
                vencimento=venc.isoformat(),
                status="pendente",
            ))

        # Marca o IPVA como parcelado e limpa estado de quitação anterior
        ipva.tipo_pagamento = "parcelado"
        ipva.pago = False
        ipva.data_pagamento = None

        self._session.commit()
        return True, ""

    def quitar_parcela(self, parcela_id: int) -> tuple[bool, str]:
        """
        Marca uma parcela como paga e registra a data de quitação.
        Se todas as parcelas ficarem pagas, sincroniza ipva.pago = True.
        """
        parcela = self._session.get(IpvaParcela, parcela_id)
        if not parcela:
            return False, "Parcela não encontrada."
        if parcela.status == "pago":
            return False, "Parcela já está quitada."

        parcela.status = "pago"
        parcela.pago_em = date.today().isoformat()
        self._session.flush()

        self._sincronizar_status_ipva(parcela.ipva_id)
        self._session.commit()
        return True, ""

    def quitar_avista(self, ipva_id: int) -> tuple[bool, str]:
        """
        Quita o IPVA integralmente (modo à vista).
        Retorna erro 400 se o IPVA estiver configurado como parcelado —
        nesse caso o pagamento deve ser feito parcela a parcela.
        """
        ipva = self._session.get(Ipva, ipva_id)
        if not ipva:
            return False, "IPVA não encontrado."

        if ipva.tipo_pagamento == "parcelado":
            return False, (
                "Este IPVA está configurado como parcelado. "
                "Quite cada parcela individualmente."
            )

        if ipva.pago:
            return False, "Este IPVA já está quitado."

        ipva.pago = True
        ipva.data_pagamento = date.today().isoformat()
        self._session.commit()
        return True, ""

    def desfazer_parcelamento(self, ipva_id: int) -> tuple[bool, str]:
        """
        Remove todas as parcelas e volta o IPVA para modo à vista.
        Útil quando o usuário quer trocar o modo de pagamento.
        """
        ipva = self._session.get(Ipva, ipva_id)
        if not ipva:
            return False, "IPVA não encontrado."

        self._session.query(IpvaParcela).filter_by(ipva_id=ipva_id).delete()
        ipva.tipo_pagamento = "avista"
        ipva.pago = False
        ipva.data_pagamento = None
        self._session.commit()
        return True, ""

    def status_geral(self, ipva_id: int) -> str:
        """
        Calcula o status derivado das parcelas:
        quitado | parcialmente_pago | vencido | pendente | sem_parcelas
        """
        parcelas = (
            self._session.query(IpvaParcela)
            .filter_by(ipva_id=ipva_id)
            .all()
        )
        if not parcelas:
            return "sem_parcelas"

        total   = len(parcelas)
        pagas   = sum(1 for p in parcelas if p.status == "pago")
        vencidas = sum(1 for p in parcelas if p.status == "vencido")

        if pagas == total:
            return "quitado"
        if pagas > 0:
            return "parcialmente_pago"
        if vencidas > 0:
            return "vencido"
        return "pendente"

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _atualizar_status_vencidos(self, ipva_id: int) -> None:
        """Marca como 'vencido' parcelas pendentes cujo vencimento já passou."""
        hoje = date.today().isoformat()
        vencidas = (
            self._session.query(IpvaParcela)
            .filter(
                IpvaParcela.ipva_id == ipva_id,
                IpvaParcela.status == "pendente",
                IpvaParcela.vencimento < hoje,
            )
            .all()
        )
        for p in vencidas:
            p.status = "vencido"
        if vencidas:
            self._session.commit()

    def _sincronizar_status_ipva(self, ipva_id: int) -> None:
        """Atualiza ipva.pago com base no status consolidado das parcelas."""
        ipva = self._session.get(Ipva, ipva_id)
        if not ipva:
            return
        status = self.status_geral(ipva_id)
        ipva.pago = (status == "quitado")
        if ipva.pago:
            ipva.data_pagamento = date.today().isoformat()

    @staticmethod
    def _avancar_meses(data: date, meses: int) -> date:
        """Avança N meses ajustando para o último dia do mês quando necessário."""
        mes_alvo = data.month + meses
        ano_alvo = data.year + (mes_alvo - 1) // 12
        mes_alvo = ((mes_alvo - 1) % 12) + 1
        ultimo_dia = calendar.monthrange(ano_alvo, mes_alvo)[1]
        return date(ano_alvo, mes_alvo, min(data.day, ultimo_dia))
