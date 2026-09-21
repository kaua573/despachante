"""
Serviço de visão geral de veículos — cruza TODOS os clientes do sistema.

Cobre dois pedidos (set/2026):
  1) Veículos sem licenciamento lançado no ano corrente (geral ou filtrado).
  2) Veículos agrupados por espécie (carga/passeio/reboque), geral ou por
     cliente.

Diferente do VeiculoService (que sempre trabalha a partir de um cliente),
este serviço consulta a tabela de veículos inteira, então fica separado
para não misturar responsabilidades.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.licenciamento import Licenciamento
from app.models.veiculo import Veiculo

ESPECIES_VALIDAS = ("carga", "passeio", "reboque")
ESPECIE_LABEL = {"passeio": "Passeio", "carga": "Carga", "reboque": "Reboque"}


class VeiculoGeralService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Listagem geral com filtros ───────────────────────────────────────────

    def listar(
        self,
        cliente_id: Optional[int] = None,
        especie: Optional[str] = None,
        situacao: Optional[str] = None,
        sem_licenciamento_ano: Optional[int] = None,
    ) -> list[dict]:
        """
        Lista veículos (com nome do cliente) aplicando os filtros informados.
        `sem_licenciamento_ano`: se informado, só retorna veículos que NÃO
        têm nenhum registro de Licenciamento para aquele ano.
        """
        q = self._session.query(Veiculo, Cliente).join(Cliente, Veiculo.cliente_id == Cliente.id)

        if cliente_id:
            q = q.filter(Veiculo.cliente_id == cliente_id)
        if especie:
            q = q.filter(Veiculo.especie == especie)
        if situacao:
            if isinstance(situacao, (list, tuple, set)):
                q = q.filter(Veiculo.situacao.in_(situacao))
            else:
                q = q.filter(Veiculo.situacao == situacao)

        if sem_licenciamento_ano:
            sub = (
                self._session.query(Licenciamento.veiculo_id)
                .filter(Licenciamento.ano_referencia == sem_licenciamento_ano)
            )
            q = q.filter(~Veiculo.id.in_(sub))

        rows = q.order_by(Cliente.nome, Veiculo.placa).all()
        resultado = []
        for v, c in rows:
            d = v.to_dict()
            d["cliente_nome"] = c.nome
            resultado.append(d)
        return resultado

    def sem_licenciamento_ano(
        self,
        ano: Optional[int] = None,
        cliente_id: Optional[int] = None,
        especie: Optional[str] = None,
    ) -> list[dict]:
        """Atalho: veículos ativos (Veiculo.SITUACOES_ATIVAS) sem licenciamento lançado para `ano` (padrão: ano corrente)."""
        ano = ano or date.today().year
        return self.listar(
            cliente_id=cliente_id, especie=especie, situacao=Veiculo.SITUACOES_ATIVAS,
            sem_licenciamento_ano=ano,
        )

    # ── Agrupamento por espécie ──────────────────────────────────────────────

    def resumo_por_especie(self, cliente_id: Optional[int] = None) -> list[dict]:
        """Contagem de veículos ativos por espécie, geral ou de um cliente."""
        from sqlalchemy import func
        q = self._session.query(Veiculo.especie, func.count(Veiculo.id)).filter(Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS))
        if cliente_id:
            q = q.filter(Veiculo.cliente_id == cliente_id)
        contagens = dict(q.group_by(Veiculo.especie).all())
        return [
            {"especie": esp, "label": ESPECIE_LABEL[esp], "total": contagens.get(esp, 0)}
            for esp in ESPECIES_VALIDAS
        ]

    def listar_por_especie(self, especie: str, cliente_id: Optional[int] = None) -> list[dict]:
        return self.listar(cliente_id=cliente_id, especie=especie, situacao=Veiculo.SITUACOES_ATIVAS)
