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


class DashboardService:
    JANELA_DIAS = 30  # exibe vencimentos nos próximos X dias

    def __init__(self, session: Session) -> None:
        self._session = session

    def resumo(self) -> dict:
        hoje = date.today().isoformat()
        limite = (date.today() + timedelta(days=self.JANELA_DIAS)).isoformat()

        total_clientes = self._session.query(Cliente).count()
        total_veiculos = self._session.query(Veiculo).filter_by(situacao="ativo").count()
        ipva_vencidos = (
            self._session.query(Ipva)
            .filter(
                Ipva.tipo_pagamento == "avista",
                Ipva.pago == False, Ipva.vencimento != None, Ipva.vencimento < hoje,
            )
            .count()
            + self._session.query(IpvaParcela)
            .filter(IpvaParcela.status != "pago", IpvaParcela.vencimento < hoje)
            .count()
        )
        lic_vencidos = (
            self._session.query(Licenciamento)
            .filter(Licenciamento.pago == False, Licenciamento.vencimento != None, Licenciamento.vencimento < hoje)
            .count()
        )
        multas_pendentes = self._session.query(Multa).filter_by(pago=False).count()

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

    def _buscar_vencimentos(self, modelo, limite: str) -> list[dict]:
        """Busca registros não pagos com vencimento até `limite`, com dados do veículo e cliente."""
        rows = (
            self._session.query(modelo, Veiculo, Cliente)
            .join(Veiculo, modelo.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(
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
        Ipva pai fica nulo quando parcelado, então elas precisam de busca própria)."""
        rows = (
            self._session.query(IpvaParcela, Ipva, Veiculo, Cliente)
            .join(Ipva, IpvaParcela.ipva_id == Ipva.id)
            .join(Veiculo, Ipva.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(IpvaParcela.status != "pago", IpvaParcela.vencimento <= limite)
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
