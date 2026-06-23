"""
Serviço de parcelamento de IPVA.
Separado do VeiculoService porque a lógica de parcelas é complexa o suficiente
para merecer sua própria unidade de responsabilidade.
"""
from __future__ import annotations

import math
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
        """Retorna parcelas com status atualizado antes de retornar."""
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
        Gera (ou regenera) as parcelas de um IPVA.

        - Divide o valor igualmente; centavos do arredondamento vão na última parcela.
        - Vencimentos são mensais a partir de data_primeira.
        - Remove parcelas existentes antes de criar as novas (regeneração segura).

        Args:
            ipva_id: ID do registro de IPVA pai.
            num_parcelas: de 1 a MAX_PARCELAS.
            valor_total: valor total do IPVA em reais.
            data_primeira: ISO YYYY-MM-DD da primeira parcela.

        Returns:
            (True, "") em sucesso, (False, mensagem) em erro.
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
        # Diferença de centavos vai na última parcela
        soma_parcelas = valor_parcela * (num_parcelas - 1)
        valor_ultima = total - soma_parcelas

        for i in range(num_parcelas):
            venc = self._avancar_meses(data_base, i)
            valor = valor_ultima if i == num_parcelas - 1 else valor_parcela
            parcela = IpvaParcela(
                ipva_id=ipva_id,
                numero=i + 1,
                valor=valor,
                vencimento=venc.isoformat(),
                status="pendente",
            )
            self._session.add(parcela)

        self._session.commit()
        return True, ""

    def quitar_parcela(self, parcela_id: int) -> tuple[bool, str]:
        """
        Marca uma parcela como paga e registra a data de quitação.
        Se todas as parcelas do IPVA ficarem pagas, sincroniza ipva.pago = True.
        """
        parcela = self._session.get(IpvaParcela, parcela_id)
        if not parcela:
            return False, "Parcela não encontrada."
        if parcela.status == "pago":
            return False, "Parcela já está quitada."

        parcela.status = "pago"
        parcela.pago_em = date.today().isoformat()
        self._session.flush()

        # Sincroniza o status do IPVA pai
        self._sincronizar_status_ipva(parcela.ipva_id)
        self._session.commit()
        return True, ""

    def status_geral(self, ipva_id: int) -> str:
        """
        Calcula o status derivado das parcelas:
        quitado | parcialmente_pago | vencido | pendente
        """
        parcelas = (
            self._session.query(IpvaParcela)
            .filter_by(ipva_id=ipva_id)
            .all()
        )
        if not parcelas:
            return "sem_parcelas"

        total = len(parcelas)
        pagas = sum(1 for p in parcelas if p.status == "pago")
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
        """
        Marca como 'vencido' as parcelas pendentes com vencimento anterior a hoje.
        Chamado sempre antes de listar, evitando inconsistência na exibição.
        """
        hoje = date.today().isoformat()
        atualizadas = (
            self._session.query(IpvaParcela)
            .filter(
                IpvaParcela.ipva_id == ipva_id,
                IpvaParcela.status == "pendente",
                IpvaParcela.vencimento < hoje,
            )
            .all()
        )
        for p in atualizadas:
            p.status = "vencido"
        if atualizadas:
            self._session.commit()

    def _sincronizar_status_ipva(self, ipva_id: int) -> None:
        """Atualiza ipva.pago baseado nas parcelas para manter consistência."""
        ipva = self._session.get(Ipva, ipva_id)
        if not ipva:
            return
        status = self.status_geral(ipva_id)
        ipva.pago = status == "quitado"

    @staticmethod
    def _avancar_meses(data: date, meses: int) -> date:
        """Avança N meses na data, ajustando para o último dia do mês se necessário."""
        mes_alvo = data.month + meses
        ano_alvo = data.year + (mes_alvo - 1) // 12
        mes_alvo = ((mes_alvo - 1) % 12) + 1

        # Garante que o dia não ultrapasse o último do mês destino
        import calendar
        ultimo_dia = calendar.monthrange(ano_alvo, mes_alvo)[1]
        dia_alvo = min(data.day, ultimo_dia)
        return date(ano_alvo, mes_alvo, dia_alvo)
