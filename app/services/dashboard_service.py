"""
Serviço do dashboard: totais e vencimentos próximos.
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session

from app.models.ipva import Ipva
from app.models.ipva_parcela import IpvaParcela
from app.models.licenciamento import Licenciamento
from app.models.multa import Multa
from app.models.veiculo import Veiculo
from app.models.cliente import Cliente
from app.services.base import TenantService


class DashboardService(TenantService):
    JANELA_DIAS = 30  # exibe vencimentos nos próximos X dias

    def __init__(self, session: Session, escritorio_id: int) -> None:
        super().__init__(session, escritorio_id)

    def resumo(self) -> dict:
        hoje = date.today().isoformat()
        limite = (date.today() + timedelta(days=self.JANELA_DIAS)).isoformat()

        total_clientes = self.scoped(Cliente).count()
        total_veiculos = self.scoped(Veiculo).filter(Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS)).count()
        ipva_vencidos = (
            self._s.query(Ipva)
            .join(Veiculo, Ipva.veiculo_id == Veiculo.id)
            .filter(
                Veiculo.escritorio_id == self.escritorio_id,
                Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS),
                Ipva.tipo_pagamento == "avista",
                Ipva.pago == False, Ipva.vencimento != None, Ipva.vencimento < hoje,
            )
            .count()
            + self._s.query(IpvaParcela)
            .join(Ipva, IpvaParcela.ipva_id == Ipva.id)
            .join(Veiculo, Ipva.veiculo_id == Veiculo.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id, Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS), IpvaParcela.status != "pago", IpvaParcela.vencimento < hoje)
            .count()
        )
        lic_vencidos = (
            self._s.query(Licenciamento)
            .join(Veiculo, Licenciamento.veiculo_id == Veiculo.id)
            .filter(
                Veiculo.escritorio_id == self.escritorio_id,
                Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS),
                Licenciamento.pago == False, Licenciamento.vencimento != None, Licenciamento.vencimento < hoje,
            )
            .count()
        )
        multas_pendentes = (
            self._s.query(Multa)
            .join(Veiculo, Multa.veiculo_id == Veiculo.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id, Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS), Multa.pago == False)
            .count()
        )

        ipva_vencendo = self._buscar_vencimentos(Ipva, limite) + self._buscar_parcelas_vencendo(limite)
        ipva_vencendo.sort(key=lambda d: d["vencimento"])
        lic_vencendo = self._buscar_vencimentos(Licenciamento, limite)

        return {
            "totais": {
                "total_clientes": total_clientes,
                "total_veiculos": total_veiculos,
                "ipva_vencidos": ipva_vencidos,
                "lic_vencidos": lic_vencidos,
                "multas_pendentes": multas_pendentes,
            },
            "ipva": ipva_vencendo,
            "licenciamento": lic_vencendo,
        }

    def resumo_geral(self) -> dict:
        """
        Dados da segunda página do dashboard ("Visão Geral"): contagem de
        veículos por espécie, quantos estão sem licenciamento lançado no ano
        corrente, e os clientes com mais pendências em aberto (top 5).
        """
        from app.services.veiculo_geral_service import VeiculoGeralService

        ano = date.today().year
        geral = VeiculoGeralService(self._s, self.escritorio_id)
        por_especie = geral.resumo_por_especie()
        sem_licenciamento = geral.sem_licenciamento_ano(ano)

        # Conta pendências (IPVA à vista + licenciamento não pagos, e multas não pagas) por cliente.
        from sqlalchemy import func

        contagem_ipva = (
            self._s.query(Veiculo.cliente_id.label("cid"), func.count(Ipva.id).label("qtd"))
            .join(Ipva, Ipva.veiculo_id == Veiculo.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id, Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS), Ipva.tipo_pagamento == "avista", Ipva.pago == False)
            .group_by(Veiculo.cliente_id)
            .subquery()
        )
        contagem_lic = (
            self._s.query(Veiculo.cliente_id.label("cid"), func.count(Licenciamento.id).label("qtd"))
            .join(Licenciamento, Licenciamento.veiculo_id == Veiculo.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id, Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS), Licenciamento.pago == False)
            .group_by(Veiculo.cliente_id)
            .subquery()
        )
        contagem_multa = (
            self._s.query(Veiculo.cliente_id.label("cid"), func.count(Multa.id).label("qtd"))
            .join(Multa, Multa.veiculo_id == Veiculo.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id, Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS), Multa.pago == False)
            .group_by(Veiculo.cliente_id)
            .subquery()
        )

        clientes = self.scoped(Cliente).with_entities(Cliente.id, Cliente.nome).all()
        mapa_ipva = dict(self._s.query(contagem_ipva.c.cid, contagem_ipva.c.qtd).all())
        mapa_lic = dict(self._s.query(contagem_lic.c.cid, contagem_lic.c.qtd).all())
        mapa_multa = dict(self._s.query(contagem_multa.c.cid, contagem_multa.c.qtd).all())

        ranking = []
        for cid, nome in clientes:
            total = mapa_ipva.get(cid, 0) + mapa_lic.get(cid, 0) + mapa_multa.get(cid, 0)
            if total:
                ranking.append({"cliente_id": cid, "cliente_nome": nome, "total_pendencias": total})
        ranking.sort(key=lambda r: r["total_pendencias"], reverse=True)

        return {
            "ano": ano,
            "por_especie": por_especie,
            "sem_licenciamento_total": len(sem_licenciamento),
            "top_pendencias": ranking[:5],
        }

    def _buscar_vencimentos(self, modelo, limite: str) -> list[dict]:
        """
        Busca registros não pagos com vencimento até `limite`, com dados do
        veículo e cliente. Só considera veículos com situacao='ativo' — um
        veículo desativado ou vendido não deve mais gerar notificação de
        vencimento, embora seu histórico continue disponível na tela dele.
        """
        rows = (
            self._s.query(modelo, Veiculo, Cliente)
            .join(Veiculo, modelo.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(
                Veiculo.escritorio_id == self.escritorio_id,
                Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS),
                modelo.pago == False,
                modelo.vencimento != None,
                modelo.vencimento <= limite,
            )
            .order_by(modelo.vencimento.asc())
            .all()
        )
        resultado = []
        for registro, veiculo, cliente in rows:
            d = registro.to_dict()
            d["placa"] = veiculo.placa
            d["especie"] = veiculo.especie
            d["situacao"] = veiculo.situacao
            d["cliente_nome"] = cliente.nome
            d["cliente_id"] = cliente.id
            d["vid"] = veiculo.id
            resultado.append(d)
        return resultado

    def _buscar_parcelas_vencendo(self, limite: str) -> list[dict]:
        """Parcelas de IPVA não quitadas com vencimento até `limite` (o vencimento do
        Ipva pai fica nulo quando parcelado, então elas precisam de busca própria).
        Mesma regra: só veículo com situacao='ativo' gera notificação."""
        rows = (
            self._s.query(IpvaParcela, Ipva, Veiculo, Cliente)
            .join(Ipva, IpvaParcela.ipva_id == Ipva.id)
            .join(Veiculo, Ipva.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id, Veiculo.situacao.in_(Veiculo.SITUACOES_ATIVAS), IpvaParcela.status != "pago", IpvaParcela.vencimento <= limite)
            .order_by(IpvaParcela.vencimento.asc())
            .all()
        )
        resultado = []
        for parcela, ipva, veiculo, cliente in rows:
            resultado.append({
                "id":             ipva.id,
                "ano_referencia": f"{ipva.ano_referencia} ({parcela.numero}ª parc.)",
                "valor":          float(parcela.valor) if parcela.valor is not None else None,
                "vencimento":     parcela.vencimento,
                "placa":          veiculo.placa,
                "especie":        veiculo.especie,
                "situacao":       veiculo.situacao,
                "cliente_nome":   cliente.nome,
                "cliente_id":     cliente.id,
                "vid":            veiculo.id,
            })
        return resultado
