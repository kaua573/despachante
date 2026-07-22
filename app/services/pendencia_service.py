"""
Serviço de pendências consolidadas.

Junta IPVA (à vista e por parcela), licenciamento e multas de TODOS os
veículos de um cliente numa lista só, independente de status — usado pela
tela de quitação em lote (/clientes/<id>/pendencias).

As operações de quitação em si continuam vivendo nos serviços de origem
(IpvaService para IPVA); licenciamento e multa ganham aqui seus próprios
métodos de quitação de um único registro, espelhando o quitar_avista do
IPVA.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.veiculo import Veiculo
from app.models.licenciamento import Licenciamento
from app.models.multa import Multa
from app.services.ipva_service import IpvaService

# Cada tipo de item mapeia para a permissão necessária para quitá-lo.
PERMISSAO_POR_TIPO = {
    "ipva_avista":  "gerenciar_ipva",
    "ipva_parcela": "gerenciar_ipva",
    "licenciamento": "gerenciar_licenciamento",
    "multa":         "gerenciar_multas",
}


class PendenciaService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._ipva_svc = IpvaService(session)

    # ── Listagem consolidada ────────────────────────────────────────────────

    def listar(self, cliente_id: int) -> list[dict]:
        veiculos = (
            self._session.query(Veiculo)
            .filter_by(cliente_id=cliente_id)
            .order_by(Veiculo.placa)
            .all()
        )
        itens: list[dict] = []
        for v in veiculos:
            itens.extend(self._itens_ipva(v))
            itens.extend(self._itens_licenciamento(v))
            itens.extend(self._itens_multa(v))
        return itens

    def _itens_ipva(self, v: Veiculo) -> list[dict]:
        itens = []
        for ipva in v.ipva_list:
            if ipva.tipo_pagamento == "parcelado":
                for p in ipva.parcelas:
                    itens.append({
                        "tipo":           "ipva_parcela",
                        "id":             p.id,
                        "veiculo_id":     v.id,
                        "placa":          v.placa,
                        "descricao":      f"IPVA {ipva.ano_referencia} — {p.numero}ª parcela",
                        "valor":          float(p.valor) if p.valor is not None else None,
                        "vencimento":     p.vencimento or "",
                        "pago":           p.status == "pago",
                        "data_pagamento": p.pago_em or "",
                    })
            else:
                itens.append({
                    "tipo":           "ipva_avista",
                    "id":             ipva.id,
                    "veiculo_id":     v.id,
                    "placa":          v.placa,
                    "descricao":      f"IPVA {ipva.ano_referencia}",
                    "valor":          float(ipva.valor) if ipva.valor is not None else None,
                    "vencimento":     ipva.vencimento or "",
                    "pago":           bool(ipva.pago),
                    "data_pagamento": ipva.data_pagamento or "",
                })
        return itens

    def _itens_licenciamento(self, v: Veiculo) -> list[dict]:
        return [{
            "tipo":           "licenciamento",
            "id":             lic.id,
            "veiculo_id":     v.id,
            "placa":          v.placa,
            "descricao":      f"Licenciamento {lic.ano_referencia}",
            "valor":          float(lic.valor) if lic.valor is not None else None,
            "vencimento":     lic.vencimento or "",
            "pago":           bool(lic.pago),
            "data_pagamento": lic.data_pagamento or "",
        } for lic in v.licenciamentos]

    def _itens_multa(self, v: Veiculo) -> list[dict]:
        return [{
            "tipo":           "multa",
            "id":             m.id,
            "veiculo_id":     v.id,
            "placa":          v.placa,
            "descricao":      f"Multa — {m.auto_infracao or 'sem auto de infração'}",
            "valor":          float(m.valor) if m.valor is not None else None,
            "vencimento":     m.vencimento or "",
            "pago":           bool(m.pago),
            "data_pagamento": m.data_pagamento or "",
        } for m in v.multas]

    # ── Quitação individual (licenciamento / multa) ─────────────────────────
    # IPVA (à vista e parcela) já tem os métodos equivalentes em IpvaService.

    def quitar_licenciamento(self, lid: int) -> tuple[bool, str]:
        obj = self._session.get(Licenciamento, lid)
        if not obj:
            return False, "Licenciamento não encontrado."
        if obj.pago:
            return False, "Licenciamento já está quitado."
        obj.pago = True
        obj.data_pagamento = date.today().isoformat()
        self._session.commit()
        return True, ""

    def quitar_multa(self, mid: int) -> tuple[bool, str]:
        obj = self._session.get(Multa, mid)
        if not obj:
            return False, "Multa não encontrada."
        if obj.pago:
            return False, "Multa já está quitada."
        obj.pago = True
        obj.data_pagamento = date.today().isoformat()
        self._session.commit()
        return True, ""

    # ── Quitação em lote ─────────────────────────────────────────────────────

    def quitar_lote(self, itens: list[dict]) -> dict:
        """
        Recebe [{"tipo": "...", "id": N}, ...] (já filtrados por permissão
        pela rota) e tenta quitar cada um, continuando mesmo se algum falhar.
        Retorna {"sucesso": N, "falhas": [{"tipo","id","erro"}, ...]}.
        """
        sucesso = 0
        falhas: list[dict] = []

        for item in itens:
            tipo = item.get("tipo")
            item_id = item.get("id")
            try:
                if tipo == "ipva_avista":
                    ok, msg = self._ipva_svc.quitar_avista(item_id)
                elif tipo == "ipva_parcela":
                    ok, msg = self._ipva_svc.quitar_parcela(item_id)
                elif tipo == "licenciamento":
                    ok, msg = self.quitar_licenciamento(item_id)
                elif tipo == "multa":
                    ok, msg = self.quitar_multa(item_id)
                else:
                    ok, msg = False, "Tipo de item desconhecido."
            except Exception as exc:  # nunca deixa um item derrubar o lote inteiro
                self._session.rollback()
                ok, msg = False, str(exc)

            if ok:
                sucesso += 1
            else:
                falhas.append({"tipo": tipo, "id": item_id, "erro": msg})

        return {"sucesso": sucesso, "falhas": falhas}
