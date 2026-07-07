"""
Serviço de veículos e seus registros associados (IPVA, licenciamento, multas).
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.models.veiculo import Veiculo
from app.models.ipva import Ipva
from app.models.licenciamento import Licenciamento
from app.models.multa import Multa


class VeiculoService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Veículos ────────────────────────────────────────────────────────────

    def listar_por_cliente(self, cliente_id: int) -> list[Veiculo]:
        return (
            self._session.query(Veiculo)
            .filter_by(cliente_id=cliente_id)
            .order_by(Veiculo.placa)
            .all()
        )

    def obter(self, veiculo_id: int) -> Optional[Veiculo]:
        return self._session.get(Veiculo, veiculo_id)

    def criar(self, dados: dict) -> Veiculo:
        v = Veiculo(
            cliente_id=dados["cliente_id"],
            placa=dados["placa"].upper(),
            renavam=dados.get("renavam", ""),
            proprietario=dados.get("proprietario", ""),
            marca_modelo=dados.get("marca_modelo", ""),
            situacao=dados.get("situacao", "ativo"),
            especie=dados.get("especie", "passeio"),
            observacao=dados.get("observacao", ""),
        )
        self._session.add(v)
        self._session.commit()
        return v

    def atualizar(self, veiculo_id: int, dados: dict) -> tuple[bool, str]:
        v = self.obter(veiculo_id)
        if not v:
            return False, "Veículo não encontrado."
        v.placa = dados["placa"].upper()
        v.renavam = dados.get("renavam", "")
        v.proprietario = dados.get("proprietario", "")
        v.marca_modelo = dados.get("marca_modelo", "")
        v.situacao = dados.get("situacao", "ativo")
        v.especie = dados.get("especie", "passeio")
        v.observacao = dados.get("observacao", "")
        self._session.commit()
        return True, ""

    def excluir(self, veiculo_id: int) -> tuple[bool, str]:
        v = self.obter(veiculo_id)
        if not v:
            return False, "Veículo não encontrado."
        self._session.delete(v)
        self._session.commit()
        return True, ""

    # ── IPVA ────────────────────────────────────────────────────────────────

    def listar_ipva(self, veiculo_id: int) -> list[Ipva]:
        return (
            self._session.query(Ipva)
            .filter_by(veiculo_id=veiculo_id)
            .order_by(Ipva.ano_referencia.desc())
            .all()
        )

    def criar_ipva(self, dados: dict) -> Ipva:
        return self._criar_registro(Ipva, dados)

    def atualizar_ipva(self, ipva_id: int, dados: dict) -> tuple[bool, str]:
        return self._atualizar_registro(Ipva, ipva_id, dados)

    def excluir_ipva(self, ipva_id: int) -> tuple[bool, str]:
        return self._excluir_registro(Ipva, ipva_id)

    # ── Licenciamento ───────────────────────────────────────────────────────

    def listar_licenciamento(self, veiculo_id: int) -> list[Licenciamento]:
        return (
            self._session.query(Licenciamento)
            .filter_by(veiculo_id=veiculo_id)
            .order_by(Licenciamento.ano_referencia.desc())
            .all()
        )

    def criar_licenciamento(self, dados: dict) -> Licenciamento:
        return self._criar_registro(Licenciamento, dados)

    def atualizar_licenciamento(self, lid: int, dados: dict) -> tuple[bool, str]:
        return self._atualizar_registro(Licenciamento, lid, dados)

    def excluir_licenciamento(self, lid: int) -> tuple[bool, str]:
        return self._excluir_registro(Licenciamento, lid)

    # ── Multas ──────────────────────────────────────────────────────────────

    def listar_multas(self, veiculo_id: int) -> list[Multa]:
        return (
            self._session.query(Multa)
            .filter_by(veiculo_id=veiculo_id)
            .order_by(Multa.data_infracao.desc())
            .all()
        )

    def criar_multa(self, dados: dict) -> Multa:
        return self._criar_registro(Multa, dados)

    def atualizar_multa(self, mid: int, dados: dict) -> tuple[bool, str]:
        return self._atualizar_registro(Multa, mid, dados)

    def excluir_multa(self, mid: int) -> tuple[bool, str]:
        return self._excluir_registro(Multa, mid)

    # ── Helpers internos (DRY para os três tipos de registro) ───────────────

    def _criar_registro(self, modelo, dados: dict):
        campos_comuns = {
            "veiculo_id": dados["veiculo_id"],
            "valor": dados.get("valor") or None,
            "vencimento": dados.get("vencimento") or None,
            "pago": bool(int(dados.get("pago", 0))),
            "data_pagamento": dados.get("data_pagamento") or None,
            "observacao": dados.get("observacao", ""),
        }
        if modelo in (Ipva, Licenciamento):
            campos_comuns["ano_referencia"] = dados["ano_referencia"]
        if modelo is Ipva:
            campos_comuns["tipo_pagamento"] = dados.get("tipo_pagamento") or "avista"
        elif modelo is Multa:
            campos_comuns.update({
                "auto_infracao": dados.get("auto_infracao", ""),
                "data_infracao": dados.get("data_infracao") or None,
                "descricao": dados.get("descricao", ""),
            })
        obj = modelo(**campos_comuns)
        self._session.add(obj)
        self._session.commit()
        return obj

    def _atualizar_registro(self, modelo, obj_id: int, dados: dict) -> tuple[bool, str]:
        obj = self._session.get(modelo, obj_id)
        if not obj:
            return False, "Registro não encontrado."

        # IPVA parcelado: pago/data_pagamento são controlados pela quitação de
        # parcelas (IpvaService), não pelo formulário básico de edição.
        eh_ipva_parcelado = modelo is Ipva and (dados.get("tipo_pagamento") or obj.tipo_pagamento) == "parcelado"

        obj.valor = dados.get("valor") or None
        obj.vencimento = dados.get("vencimento") or None
        if not eh_ipva_parcelado:
            obj.pago = bool(int(dados.get("pago", 0)))
            obj.data_pagamento = dados.get("data_pagamento") or None
        obj.observacao = dados.get("observacao", "")
        if modelo in (Ipva, Licenciamento):
            obj.ano_referencia = dados["ano_referencia"]
        if modelo is Ipva:
            obj.tipo_pagamento = dados.get("tipo_pagamento") or obj.tipo_pagamento or "avista"
        elif modelo is Multa:
            obj.auto_infracao = dados.get("auto_infracao", "")
            obj.data_infracao = dados.get("data_infracao") or None
            obj.descricao = dados.get("descricao", "")
        self._session.commit()
        return True, ""

    def _excluir_registro(self, modelo, obj_id: int) -> tuple[bool, str]:
        obj = self._session.get(modelo, obj_id)
        if not obj:
            return False, "Registro não encontrado."
        self._session.delete(obj)
        self._session.commit()
        return True, ""
