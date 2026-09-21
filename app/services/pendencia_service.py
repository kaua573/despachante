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

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.veiculo import Veiculo
from app.models.cliente import Cliente
from app.models.ipva import Ipva
from app.models.ipva_parcela import IpvaParcela
from app.models.licenciamento import Licenciamento
from app.models.multa import Multa
from app.models.contato_pendencia import ContatoPendencia
from app.services.ipva_service import IpvaService

# Cada tipo de item mapeia para a permissão necessária para quitá-lo.
PERMISSAO_POR_TIPO = {
    "ipva_avista":  "gerenciar_ipva",
    "ipva_parcela": "gerenciar_ipva",
    "licenciamento": "gerenciar_licenciamento",
    "multa":         "gerenciar_multas",
}

TIPOS_VALIDOS = set(PERMISSAO_POR_TIPO.keys())


class PendenciaService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._ipva_svc = IpvaService(session)

    # ── Listagem consolidada (um cliente) ───────────────────────────────────

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

    # ── Listagem consolidada (TODOS os clientes — Central de pendências) ────

    def listar_todas(self, apenas_ativos: bool = True) -> list[dict]:
        """
        Mesma ideia de `listar()`, mas cruzando a carteira inteira — usado
        pela Central de pendências (/pendencias). Usa eager loading porque
        aqui, diferente do `listar()` de um cliente só, o volume de veículos
        pode ser grande e uma consulta por relação evitaria N+1 em cada um.

        Por padrão só considera veículos com situação "ativa" (Veiculo.
        SITUACOES_ATIVAS — inclui "pendente"; exclui "desativado"/"vendido"),
        mesma regra já usada no dashboard e na previsão de vencimentos (um
        veículo vendido/desativado não deve gerar pendência para ninguém
        contatar).
        """
        q = (
            self._session.query(Veiculo)
            .options(
                joinedload(Veiculo.cliente),
                joinedload(Veiculo.ipva_list).joinedload(Ipva.parcelas),
                joinedload(Veiculo.licenciamentos),
                joinedload(Veiculo.multas),
            )
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
        )
        if apenas_ativos:
            q = q.filter(Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS))
        veiculos = q.order_by(Cliente.nome, Veiculo.placa).all()

        contatos = self._mapa_contatos()

        itens: list[dict] = []
        for v in veiculos:
            itens_veiculo = self._itens_ipva(v) + self._itens_licenciamento(v) + self._itens_multa(v)
            for item in itens_veiculo:
                item["cliente_id"] = v.cliente_id
                item["cliente_nome"] = v.cliente.nome if v.cliente else ""
                item["cliente_telefone"] = (v.cliente.telefone or "") if v.cliente else ""
                item["contato"] = contatos.get((item["tipo"], item["id"]))
            itens.extend(itens_veiculo)
        return itens

    def _mapa_contatos(self) -> dict[tuple[str, int], dict]:
        """(tipo, pendencia_id) -> dict do ContatoPendencia mais recente."""
        registros = self._session.query(ContatoPendencia).all()
        return {(c.tipo, c.pendencia_id): c.to_dict() for c in registros}

    # ── Marcar/desmarcar contato feito com o cliente ────────────────────────
    # Nunca confia em cliente_id/veiculo_id vindos do front — sempre resolve
    # o item de origem (Ipva/IpvaParcela/Licenciamento/Multa) no banco antes
    # de gravar, pra não deixar o registro de contato associado a um
    # veículo/cliente errado.

    def _resolver_origem(self, tipo: str, pendencia_id: int) -> Optional[dict]:
        if tipo not in TIPOS_VALIDOS:
            return None

        modelo = {
            "ipva_avista":   Ipva,
            "ipva_parcela":  IpvaParcela,
            "licenciamento": Licenciamento,
            "multa":         Multa,
        }[tipo]
        obj = self._session.get(modelo, pendencia_id)
        if not obj:
            return None

        if tipo == "ipva_parcela":
            veiculo_id = obj.ipva.veiculo_id
        else:
            veiculo_id = obj.veiculo_id
        veiculo = self._session.get(Veiculo, veiculo_id)
        if not veiculo:
            return None
        return {"veiculo_id": veiculo_id, "cliente_id": veiculo.cliente_id}

    def marcar_contato(
        self, tipo: str, pendencia_id: int, usuario_id: int, observacao: Optional[str] = None,
    ) -> tuple[bool, str]:
        origem = self._resolver_origem(tipo, pendencia_id)
        if not origem:
            return False, "Pendência não encontrada."

        obs = (observacao or "").strip()[:280] or None
        existente = (
            self._session.query(ContatoPendencia)
            .filter_by(tipo=tipo, pendencia_id=pendencia_id)
            .first()
        )
        if existente:
            existente.marcado_por_id = usuario_id
            existente.marcado_em = datetime.now()
            existente.observacao = obs
        else:
            self._session.add(ContatoPendencia(
                tipo=tipo, pendencia_id=pendencia_id,
                cliente_id=origem["cliente_id"], veiculo_id=origem["veiculo_id"],
                marcado_por_id=usuario_id, observacao=obs,
            ))
        self._session.commit()
        return True, ""

    def desmarcar_contato(self, tipo: str, pendencia_id: int) -> bool:
        existente = (
            self._session.query(ContatoPendencia)
            .filter_by(tipo=tipo, pendencia_id=pendencia_id)
            .first()
        )
        if not existente:
            return False
        self._session.delete(existente)
        self._session.commit()
        return True

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
