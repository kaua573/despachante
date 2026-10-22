"""
Serviço de relatórios configuráveis.

Responsável por:
- Montar queries dinâmicas com base na configuração do usuário
- Gerar saída em PDF (ReportLab) ou Excel (openpyxl)
- Persistir e recuperar templates de relatório salvos
"""
from __future__ import annotations

import io
import json
import os
import unicodedata
from datetime import date, datetime
from typing import Any, Optional
from xml.sax.saxutils import escape as _xml_escape

from sqlalchemy import false as _sql_false, func
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.ipva import Ipva
from app.models.licenciamento import Licenciamento
from app.models.multa import Multa
from app.models.template_relatorio import TemplateRelatorio
from app.models.veiculo import Veiculo
from app.services.base import TenantService


# ── Definição de campos disponíveis por domínio ───────────────────────────

CAMPOS_IPVA = [
    {"id": "cliente_nome",   "label": "Cliente"},
    {"id": "placa",          "label": "Placa"},
    {"id": "proprietario",   "label": "Proprietário"},
    {"id": "marca_modelo",   "label": "Marca/Modelo"},
    {"id": "especie",        "label": "Espécie"},
    {"id": "situacao",       "label": "Situação do Veículo"},
    {"id": "ano_referencia", "label": "Ano Referência"},
    {"id": "valor",          "label": "Valor"},
    {"id": "vencimento",     "label": "Vencimento"},
    {"id": "status_pag",     "label": "Status"},
    {"id": "data_pagamento", "label": "Data Pagamento"},
    {"id": "observacao",     "label": "Observação"},
]

CAMPOS_LICENCIAMENTO = [
    {"id": "cliente_nome",   "label": "Cliente"},
    {"id": "placa",          "label": "Placa"},
    {"id": "proprietario",   "label": "Proprietário"},
    {"id": "marca_modelo",   "label": "Marca/Modelo"},
    {"id": "especie",        "label": "Espécie"},
    {"id": "situacao",       "label": "Situação do Veículo"},
    {"id": "ano_referencia", "label": "Ano Referência"},
    {"id": "valor",          "label": "Valor"},
    {"id": "vencimento",     "label": "Vencimento"},
    {"id": "status_pag",     "label": "Status"},
    {"id": "data_pagamento", "label": "Data Pagamento"},
    {"id": "observacao",     "label": "Observação"},
]

CAMPOS_MULTAS = [
    {"id": "cliente_nome",   "label": "Cliente"},
    {"id": "placa",          "label": "Placa"},
    {"id": "proprietario",   "label": "Proprietário"},
    {"id": "marca_modelo",   "label": "Marca/Modelo"},
    {"id": "especie",        "label": "Espécie"},
    {"id": "auto_infracao",  "label": "Auto de Infração"},
    {"id": "data_infracao",  "label": "Data da Infração"},
    {"id": "descricao",      "label": "Descrição"},
    {"id": "valor",          "label": "Valor"},
    {"id": "vencimento",     "label": "Vencimento"},
    {"id": "status_pag",     "label": "Status"},
    {"id": "data_pagamento", "label": "Data Pagamento"},
    {"id": "observacao",     "label": "Observação"},
]

CAMPOS_POR_TIPO = {
    "ipva":          CAMPOS_IPVA,
    "licenciamento": CAMPOS_LICENCIAMENTO,
    "multas":        CAMPOS_MULTAS,
}

TIPOS_VALIDOS = ("ipva", "licenciamento", "multas")

TIPO_LABEL = {"ipva": "IPVA", "licenciamento": "Licenciamento", "multas": "Multas"}


def tipos_do_config(config: dict) -> list[str]:
    """
    Normaliza a lista de domínios (ipva/licenciamento/multas) selecionados no
    relatório. Aceita a chave nova 'tipos' (lista, seleção múltipla) e mantém
    compatibilidade com a chave antiga 'tipo' (string, seleção única) usada
    por templates salvos antes da seleção múltipla existir.
    """
    tipos = config.get("tipos")
    if not tipos and config.get("tipo"):
        tipos = [config["tipo"]]
    if not tipos:
        return []
    vistos: list[str] = []
    for t in tipos:
        if t in TIPOS_VALIDOS and t not in vistos:
            vistos.append(t)
    return vistos


def tipos_label(tipos: list[str]) -> str:
    return " + ".join(TIPO_LABEL.get(t, t) for t in tipos) or "Relatório"


class RelatorioService(TenantService):
    def __init__(self, session: Session, escritorio_id: int) -> None:
        super().__init__(session, escritorio_id)

    # ── Templates salvos ────────────────────────────────────────────────────

    def listar_templates(self) -> list[TemplateRelatorio]:
        return self.scoped(TemplateRelatorio).order_by(TemplateRelatorio.nome).all()

    def obter_template(self, template_id: int) -> Optional[TemplateRelatorio]:
        return self.scoped(TemplateRelatorio).filter_by(id=template_id).first()

    def salvar_template(self, nome: str, config: dict, template_id: Optional[int] = None) -> TemplateRelatorio:
        config_json = json.dumps(config, ensure_ascii=False)
        if template_id:
            t = self.obter_template(template_id)
            if t:
                t.nome = nome
                t.config_json = config_json
                t.atualizado_em = datetime.now()
                self._s.commit()
                return t
        t = TemplateRelatorio(escritorio_id=self.escritorio_id, nome=nome, config_json=config_json)
        self._s.add(t)
        self._s.commit()
        return t

    def excluir_template(self, template_id: int) -> tuple[bool, str]:
        t = self.obter_template(template_id)
        if not t:
            return False, "Template não encontrado."
        self._s.delete(t)
        self._s.commit()
        return True, ""

    # ── Busca de dados ──────────────────────────────────────────────────────

    def buscar_dados(self, config: dict) -> list[dict]:
        """
        Executa a query de acordo com a configuração passada.
        Retorna todos os campos — a filtragem de colunas visíveis é feita na renderização.

        Suporta selecionar mais de um domínio (ipva/licenciamento/multas) ao
        mesmo tempo: os resultados de cada domínio são concatenados e, quando
        há mais de um domínio selecionado, cada linha ganha o campo
        'tipo_registro' para identificar de onde ela veio.
        """
        tipos          = tipos_do_config(config)
        filtros        = dict(config.get("filtros", {}))
        ordenar_por    = config.get("ordenar_por", "vencimento")
        ordem_direcao  = config.get("ordem_direcao", "asc")
        multiplos      = len(tipos) > 1

        # Em qual data o período (data início/fim) filtra as MULTAS: pelo
        # vencimento (igual IPVA e licenciamento) ou pela data da infração.
        # Sem a escolha explícita (templates antigos), multas sozinhas
        # mantêm o comportamento antigo (data da infração) e, combinadas
        # com outros domínios, usam o vencimento — senão a multa de uma
        # infração antiga sumia do relatório mesmo com vencimento no período.
        modo_data = config.get("filtro_data_multas")
        if modo_data not in ("vencimento", "infracao"):
            modo_data = "infracao" if tipos == ["multas"] else "vencimento"
        filtros["_data_multas"] = modo_data

        # Cliente e proprietário são filtrados em Python (ignorando acentos e
        # maiúsculas): o ILIKE do banco não casa "Joao" com "João".
        filtros["cliente_id"] = self._inteiro(filtros.get("cliente_id"))
        ids_veiculos = filtros.get("veiculo_ids")
        filtros["veiculo_ids"] = (
            [i for i in map(self._inteiro, ids_veiculos) if i is not None]
            if isinstance(ids_veiculos, list) else None
        )
        filtro_cliente = filtros.pop("cliente_nome", None)
        filtro_proprietario = filtros.pop("proprietario", None)

        dados: list[dict] = []
        for tipo in tipos:
            if tipo == "ipva":
                linhas = self._buscar_ipva(filtros, ordenar_por, ordem_direcao)
            elif tipo == "licenciamento":
                linhas = self._buscar_licenciamento(filtros, ordenar_por, ordem_direcao)
            elif tipo == "multas":
                linhas = self._buscar_multas(filtros, ordenar_por, ordem_direcao)
            else:
                continue
            linhas = self._filtrar_por_texto(
                linhas, filtro_cliente, filtro_proprietario
            )
            if multiplos:
                for linha in linhas:
                    linha["tipo_registro"] = TIPO_LABEL.get(tipo, tipo).upper()
            dados.extend(linhas)

        if multiplos:
            dados = self._ordenar_combinado(dados, ordenar_por, ordem_direcao)
        return dados

    @staticmethod
    def _inteiro(valor: Any) -> Optional[int]:
        try:
            return int(valor)
        except (TypeError, ValueError):
            return None

    # ── Escolha do cliente na tela de relatórios ────────────────────────────

    def buscar_clientes(self, termo: str, limite: int = 8) -> list[dict]:
        """Sugestões de clientes do escritório por nome (sem acento) ou CPF/CNPJ."""
        palavras = self._normalizar_texto(termo).split()
        digitos = "".join(ch for ch in str(termo or "") if ch.isdigit())
        if not palavras or len(" ".join(palavras)) < 2:
            return []

        linhas = (
            self._s.query(Cliente.id, Cliente.nome, Cliente.cpf, Cliente.cnpj)
            .filter(Cliente.escritorio_id == self.escritorio_id)
            .all()
        )
        achados = []
        for cid, nome, cpf, cnpj in linhas:
            nome_n = self._normalizar_texto(nome)
            doc = cpf or cnpj or ""
            doc_digitos = "".join(ch for ch in doc if ch.isdigit())
            if all(p in nome_n for p in palavras):
                relevancia = 0 if nome_n.startswith(palavras[0]) else (
                    1 if any(parte.startswith(palavras[0]) for parte in nome_n.split()) else 2)
            elif len(digitos) >= 3 and digitos in doc_digitos:
                relevancia = 2
            else:
                continue
            achados.append((relevancia, nome_n, cid, nome, doc))
        achados.sort()
        achados = achados[:limite]
        if not achados:
            return []

        contagem = dict(
            self._s.query(Veiculo.cliente_id, func.count(Veiculo.id))
            .filter(Veiculo.escritorio_id == self.escritorio_id,
                    Veiculo.cliente_id.in_([a[2] for a in achados]))
            .group_by(Veiculo.cliente_id)
            .all()
        )
        return [
            {"id": cid, "nome": nome, "documento": doc, "total_veiculos": contagem.get(cid, 0)}
            for _, _, cid, nome, doc in achados
        ]

    def escopo_cliente(self, cliente_id: int) -> Optional[dict]:
        """Proprietários e veículos de um cliente, para escolher o que entra no relatório."""
        cliente = (
            self._s.query(Cliente)
            .filter(Cliente.id == cliente_id, Cliente.escritorio_id == self.escritorio_id)
            .first()
        )
        if not cliente:
            return None
        veiculos = (
            self._s.query(Veiculo)
            .filter(Veiculo.cliente_id == cliente.id, Veiculo.escritorio_id == self.escritorio_id)
            .order_by(Veiculo.placa)
            .all()
        )
        grupos: dict[str, dict] = {}
        for v in veiculos:
            nome = (v.proprietario or "").strip() or "Sem proprietário informado"
            grupo = grupos.setdefault(self._normalizar_texto(nome), {"nome": nome, "veiculos": []})
            grupo["veiculos"].append({
                "id": v.id, "placa": v.placa,
                "marca_modelo": v.marca_modelo or "", "situacao": self._situacao_txt(v),
            })
        return {
            "cliente": {"id": cliente.id, "nome": cliente.nome, "documento": cliente.cpf or cliente.cnpj or ""},
            "total_veiculos": len(veiculos),
            "proprietarios": sorted(grupos.values(), key=lambda g: self._normalizar_texto(g["nome"])),
        }

    @staticmethod
    def _normalizar_texto(valor: Any) -> str:
        """Minúsculas e sem acentos, para comparar 'João' com 'joao'."""
        texto = unicodedata.normalize("NFKD", str(valor or ""))
        return "".join(c for c in texto if not unicodedata.combining(c)).casefold().strip()

    @classmethod
    def _filtrar_por_texto(cls, linhas: list[dict], cliente: Optional[str],
                           proprietario: Optional[str]) -> list[dict]:
        """Mantém só as linhas cujo cliente/proprietário contém o texto buscado."""
        for campo, termo in (("cliente_nome", cliente), ("proprietario", proprietario)):
            termo = cls._normalizar_texto(termo)
            if termo:
                linhas = [l for l in linhas
                          if termo in cls._normalizar_texto(l.get(campo))]
        return linhas

    @staticmethod
    def _ordenar_combinado(dados: list[dict], campo: str, direcao: str) -> list[dict]:
        """
        Reordena a lista já combinada de mais de um domínio, já que cada
        domínio foi ordenado individualmente na consulta ao banco.
        """
        def chave(linha: dict):
            valor = linha.get(campo)
            return (valor is None, valor if valor is not None else "")

        return sorted(dados, key=chave, reverse=(direcao == "desc"))

    def _buscar_ipva(self, filtros: dict, ordenar_por: str, direcao: str) -> list[dict]:
        q = (
            self._s.query(Ipva, Veiculo, Cliente)
            .join(Veiculo, Ipva.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id)
        )
        q = self._aplicar_filtros_comuns(q, Ipva, filtros)
        q = self._aplicar_ordenacao(q, Ipva, Veiculo, Cliente, ordenar_por, direcao)
        return [self._montar_linha_ipva(r, v, c) for r, v, c in q.all()]

    def _buscar_licenciamento(self, filtros: dict, ordenar_por: str, direcao: str) -> list[dict]:
        q = (
            self._s.query(Licenciamento, Veiculo, Cliente)
            .join(Veiculo, Licenciamento.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id)
        )
        q = self._aplicar_filtros_comuns(q, Licenciamento, filtros)
        q = self._aplicar_ordenacao(q, Licenciamento, Veiculo, Cliente, ordenar_por, direcao)
        return [self._montar_linha_licenciamento(r, v, c) for r, v, c in q.all()]

    def _buscar_multas(self, filtros: dict, ordenar_por: str, direcao: str) -> list[dict]:
        q = (
            self._s.query(Multa, Veiculo, Cliente)
            .join(Veiculo, Multa.veiculo_id == Veiculo.id)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(Veiculo.escritorio_id == self.escritorio_id)
        )
        q = self._aplicar_filtros_multas(q, filtros)
        q = self._aplicar_ordenacao(q, Multa, Veiculo, Cliente, ordenar_por, direcao)
        return [self._montar_linha_multa(r, v, c) for r, v, c in q.all()]

    def _aplicar_filtros_comuns(self, q, modelo, filtros: dict):
        if filtros.get("data_inicio"):
            q = q.filter(modelo.vencimento >= filtros["data_inicio"])
        if filtros.get("data_fim"):
            q = q.filter(modelo.vencimento <= filtros["data_fim"])
        if filtros.get("status") == "pago":
            q = q.filter(modelo.pago == True)
        elif filtros.get("status") in ("pendente", "vencido", "a_vencer"):
            q = q.filter(modelo.pago == False)
            hoje = date.today().isoformat()
            if filtros["status"] == "vencido":
                q = q.filter(modelo.vencimento < hoje)
            elif filtros["status"] == "a_vencer":
                q = q.filter(modelo.vencimento >= hoje)
        if filtros.get("placa"):
            q = q.filter(Veiculo.placa.ilike(f"%{filtros['placa']}%"))
        if filtros.get("cliente_nome"):
            q = q.filter(Cliente.nome.ilike(f"%{filtros['cliente_nome']}%"))
        return self._aplicar_filtros_escopo(q, filtros)

    @staticmethod
    def _aplicar_filtros_escopo(q, filtros: dict):
        """Escopo escolhido na tela: um cliente e, dentro dele, só alguns veículos.

        As consultas já são limitadas ao escritório (Veiculo.escritorio_id),
        então um id de outro escritório simplesmente não retorna nada.
        """
        if filtros.get("cliente_id") is not None:
            q = q.filter(Cliente.id == filtros["cliente_id"])
        ids = filtros.get("veiculo_ids")
        if ids is not None:
            q = q.filter(Veiculo.id.in_(ids)) if ids else q.filter(_sql_false())
        return q

    def _aplicar_filtros_multas(self, q, filtros: dict):
        campo_data = Multa.data_infracao if filtros.get("_data_multas") == "infracao" else Multa.vencimento
        if filtros.get("data_inicio"):
            q = q.filter(campo_data >= filtros["data_inicio"])
        if filtros.get("data_fim"):
            q = q.filter(campo_data <= filtros["data_fim"])
        if filtros.get("status") == "pago":
            q = q.filter(Multa.pago == True)
        elif filtros.get("status") in ("pendente", "vencido", "a_vencer"):
            q = q.filter(Multa.pago == False)
            hoje = date.today().isoformat()
            if filtros["status"] == "vencido":
                q = q.filter(Multa.vencimento < hoje)
            elif filtros["status"] == "a_vencer":
                q = q.filter(Multa.vencimento >= hoje)
        if filtros.get("placa"):
            q = q.filter(Veiculo.placa.ilike(f"%{filtros['placa']}%"))
        if filtros.get("cliente_nome"):
            q = q.filter(Cliente.nome.ilike(f"%{filtros['cliente_nome']}%"))
        return self._aplicar_filtros_escopo(q, filtros)

    def _aplicar_ordenacao(self, q, modelo, veiculo_model, cliente_model, campo: str, direcao: str):
        mapa = {
            "cliente_nome":  cliente_model.nome,
            "placa":         veiculo_model.placa,
            "proprietario":  veiculo_model.proprietario,
            "vencimento":    modelo.vencimento,
            "valor":         modelo.valor,
            "status_pag":    modelo.pago,
        }
        if hasattr(modelo, "ano_referencia"):
            mapa["ano_referencia"] = modelo.ano_referencia
        if hasattr(modelo, "data_infracao"):
            mapa["data_infracao"] = modelo.data_infracao

        coluna = mapa.get(campo, modelo.vencimento if hasattr(modelo, "vencimento") else modelo.id)
        if direcao == "desc":
            coluna = coluna.desc()
        return q.order_by(coluna)

    # ── Montagem de linhas ──────────────────────────────────────────────────

    def _montar_linha_ipva(self, r: Ipva, v: Veiculo, c: Cliente) -> dict:
        return {
            "cliente_nome":   c.nome,
            "placa":          v.placa,
            "proprietario":   v.proprietario or "",
            "marca_modelo":   v.marca_modelo or "",
            "especie":        (v.especie or "").upper(),
            "situacao":       self._situacao_txt(v),
            "ano_referencia": r.ano_referencia,
            "valor":          float(r.valor) if r.valor is not None else None,
            "vencimento":     r.vencimento or "",
            "status_pag":     ("Pago" if r.pago else self._status_vencimento(r.vencimento)).upper(),
            "data_pagamento": r.data_pagamento or "",
            "observacao":     r.observacao or "",
        }

    def _montar_linha_licenciamento(self, r: Licenciamento, v: Veiculo, c: Cliente) -> dict:
        return {
            "cliente_nome":   c.nome,
            "placa":          v.placa,
            "proprietario":   v.proprietario or "",
            "marca_modelo":   v.marca_modelo or "",
            "especie":        (v.especie or "").upper(),
            "situacao":       self._situacao_txt(v),
            "ano_referencia": r.ano_referencia,
            "valor":          float(r.valor) if r.valor is not None else None,
            "vencimento":     r.vencimento or "",
            "status_pag":     ("Pago" if r.pago else self._status_vencimento(r.vencimento)).upper(),
            "data_pagamento": r.data_pagamento or "",
            "observacao":     r.observacao or "",
        }

    def _montar_linha_multa(self, r: Multa, v: Veiculo, c: Cliente) -> dict:
        return {
            "cliente_nome":   c.nome,
            "placa":          v.placa,
            "proprietario":   v.proprietario or "",
            "marca_modelo":   v.marca_modelo or "",
            "especie":        (v.especie or "").upper(),
            "situacao":       self._situacao_txt(v),
            "auto_infracao":  r.auto_infracao or "",
            "data_infracao":  r.data_infracao or "",
            "descricao":      r.descricao or "",
            "valor":          float(r.valor) if r.valor is not None else None,
            "vencimento":     r.vencimento or "",
            "status_pag":     ("Pago" if r.pago else self._status_vencimento(r.vencimento)).upper(),
            "data_pagamento": r.data_pagamento or "",
            "observacao":     r.observacao or "",
        }

    @staticmethod
    def _situacao_txt(v: Veiculo) -> str:
        return Veiculo.SITUACAO_LABEL.get(v.situacao or "", v.situacao or "").upper()

    @staticmethod
    def _status_vencimento(vencimento: Optional[str]) -> str:
        if not vencimento:
            return "Pendente"
        return "Vencido" if vencimento < date.today().isoformat() else "A Vencer"

    # ── Agrupamento ─────────────────────────────────────────────────────────

    @staticmethod
    def agrupar(dados: list[dict], campo_grupo: str) -> dict[str, list[dict]]:
        """Agrupa lista de dicts por valor de um campo."""
        grupos: dict[str, list[dict]] = {}
        for linha in dados:
            chave = str(linha.get(campo_grupo, "—") or "—")
            grupos.setdefault(chave, []).append(linha)
        return grupos

    # ── Totalizadores ───────────────────────────────────────────────────────

    @staticmethod
    def calcular_totais(dados: list[dict]) -> dict:
        total_valor     = sum(float(r.get("valor") or 0) for r in dados)
        total_pago      = sum(1 for r in dados if r.get("status_pag") == "PAGO")
        total_pendente  = sum(1 for r in dados if r.get("status_pag") == "PENDENTE")
        total_a_vencer  = sum(1 for r in dados if r.get("status_pag") == "A VENCER")
        total_vencido   = sum(1 for r in dados if r.get("status_pag") == "VENCIDO")
        valor_pago      = sum(float(r.get("valor") or 0) for r in dados if r.get("status_pag") == "PAGO")
        valor_pendente  = sum(float(r.get("valor") or 0) for r in dados if r.get("status_pag") != "PAGO")
        return {
            "total_registros": len(dados),
            "total_valor":     total_valor,
            "total_pago":      total_pago,
            "total_pendente":  total_pendente,
            "total_a_vencer":  total_a_vencer,
            "total_vencido":   total_vencido,
            "valor_pago":      valor_pago,
            "valor_pendente":  valor_pendente,
        }


    # ── Exportação PDF ──────────────────────────────────────────────────────

    # Peso relativo de cada coluna na largura da página: nomes e textos longos
    # ganham mais espaço que placa, ano ou datas.
    _PESOS_COLUNA = {
        "cliente_nome": 2.1, "placa": 1.35, "proprietario": 2.2, "marca_modelo": 2.0,
        "especie": 1.45, "situacao": 1.3, "ano_referencia": 1.3, "valor": 1.5,
        "vencimento": 1.5, "status_pag": 1.5, "data_pagamento": 1.4,
        "observacao": 2.2, "auto_infracao": 1.6, "data_infracao": 1.4,
        "descricao": 2.4, "tipo_registro": 1.4,
    }
    _CORES_STATUS = {
        "VENCIDO": "#B42318", "PAGO": "#067647",
        "A VENCER": "#B54708", "PENDENTE": "#475467",
    }
    _STATUS_LABEL = {"pago": "Pago", "pendente": "Pendente", "vencido": "Vencido", "a_vencer": "A vencer"}

    def _descrever_filtros(self, config: dict) -> list[str]:
        """Texto curto dos filtros/ordenação aplicados, para constar no PDF."""
        f = config.get("filtros") or {}
        filtros: list[str] = []
        cid = self._inteiro(f.get("cliente_id"))
        if cid is not None:
            nome = (self._s.query(Cliente.nome)
                    .filter(Cliente.id == cid, Cliente.escritorio_id == self.escritorio_id)
                    .scalar())
            if nome:
                filtros.append(f"Cliente: {nome}")
        if isinstance(f.get("veiculo_ids"), list):
            ids = [i for i in map(self._inteiro, f["veiculo_ids"]) if i is not None]
            placas = [pl for (pl,) in (self._s.query(Veiculo.placa)
                      .filter(Veiculo.id.in_(ids), Veiculo.escritorio_id == self.escritorio_id)
                      .order_by(Veiculo.placa).all())]
            if placas:
                resto = f" +{len(placas) - 6}" if len(placas) > 6 else ""
                filtros.append(f"Veículos: {', '.join(placas[:6])}{resto}")
        ini, fim = f.get("data_inicio"), f.get("data_fim")
        if ini and fim:
            filtros.append(f"Período: {self._fmt_data(ini)} a {self._fmt_data(fim)}")
        elif ini:
            filtros.append(f"A partir de {self._fmt_data(ini)}")
        elif fim:
            filtros.append(f"Até {self._fmt_data(fim)}")
        if f.get("status"):
            filtros.append(f"Status: {self._STATUS_LABEL.get(f['status'], f['status'])}")
        if f.get("placa"):
            filtros.append(f"Placa: {f['placa']}")
        if f.get("cliente_nome"):
            filtros.append(f"Cliente: {f['cliente_nome']}")
        if f.get("proprietario"):
            filtros.append(f"Proprietário: {f['proprietario']}")

        rotulos = {c["id"]: c["label"] for c in CAMPOS_IPVA + CAMPOS_MULTAS}
        organizacao: list[str] = []
        grupo = config.get("agrupar_por")
        if grupo and grupo != "nenhum":
            organizacao.append(f"Agrupado por {rotulos.get(grupo, grupo)}")
        ordem = config.get("ordenar_por") or "vencimento"
        sentido = "decrescente" if config.get("ordem_direcao") == "desc" else "crescente"
        organizacao.append(f"Ordenado por {rotulos.get(ordem, ordem)} ({sentido})")

        linhas = [" · ".join(filtros) if filtros else "Sem filtros (todos os registros)"]
        linhas.append(" · ".join(organizacao))
        return linhas

    def gerar_pdf(
        self,
        dados: list[dict],
        campos_visiveis: list[dict],
        config: dict,
        cfg_pdf: dict,
    ) -> bytes:
        """
        Gera PDF do relatório.

        Layout: cabeçalho com logo/escritório, barra de título com data de
        geração, filtros aplicados, resumo em cartões (opcional), tabela com
        colunas proporcionais ao conteúdo, valores à direita, status colorido
        e rodapé com numeração "Página X de Y".

        Args:
            dados: linhas do relatório
            campos_visiveis: lista de {id, label} na ordem desejada
            config: configuração do relatório (tipo, filtros, agrupamento etc.)
            cfg_pdf: {nome_escritorio, logo_dir, logo_arquivo}
        """
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors as rl_colors
        from reportlab.lib.units import cm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            Image as RLImage, CondPageBreak, PageBreak,
        )

        nome_escritorio = cfg_pdf.get("nome_escritorio", "") or "Sistema Despachante"
        logo_dir        = cfg_pdf.get("logo_dir", "")
        logo_arquivo    = cfg_pdf.get("logo_arquivo", "")

        PRETO       = rl_colors.HexColor("#16181C")
        CABECALHO   = rl_colors.HexColor("#1F2A37")
        CINZA_BARRA = rl_colors.HexColor("#EDEAE1")
        CINZA_BORDA = rl_colors.HexColor("#D8D4C8")
        CINZA_SUB   = rl_colors.HexColor("#63697A")
        ZEBRA       = rl_colors.HexColor("#F7F6F2")
        BRANCO      = rl_colors.white
        FONTE_BASE, FONTE_BOLD = "Helvetica", "Helvetica-Bold"

        n_colunas = max(len(campos_visiveis), 1)
        compacto  = n_colunas > 8
        t_cell, t_head = (7.5, 7) if compacto else (8.5, 8)

        def estilo(nome, **kw):
            kw.setdefault("fontName", FONTE_BASE)
            kw.setdefault("textColor", PRETO)
            kw.setdefault("fontSize", t_cell)
            kw.setdefault("leading", kw["fontSize"] * 1.25)
            return ParagraphStyle(nome, **kw)

        estilos = {
            "escrit":   estilo("escrit", fontName=FONTE_BOLD, fontSize=14),
            "barra":    estilo("barra", fontName=FONTE_BOLD, fontSize=10.5),
            "barra_d":  estilo("barra_d", fontSize=9.5, alignment=2),
            "secao":    estilo("secao", fontName=FONTE_BOLD, fontSize=9),
            "filtros":  estilo("filtros", fontSize=8, textColor=CINZA_SUB, leading=11),
            "cell":     estilo("cell"),
            "cell_d":   estilo("cell_d", alignment=2),
            "cell_c":   estilo("cell_c", alignment=1),
            "head":     estilo("head", fontName=FONTE_BOLD, fontSize=t_head, textColor=BRANCO),
            "head_d":   estilo("head_d", fontName=FONTE_BOLD, fontSize=t_head, textColor=BRANCO, alignment=2),
            "head_c":   estilo("head_c", fontName=FONTE_BOLD, fontSize=t_head, textColor=BRANCO, alignment=1),
            "total":    estilo("total", fontName=FONTE_BOLD),
            "total_d":  estilo("total_d", fontName=FONTE_BOLD, alignment=2),
            "kpi_rot":  estilo("kpi_rot", fontSize=7.5, textColor=CINZA_SUB),
            "kpi_val":  estilo("kpi_val", fontName=FONTE_BOLD, fontSize=11, leading=14),
            "kpi_sub":  estilo("kpi_sub", fontSize=7.5, textColor=CINZA_SUB),
            "vazio":    estilo("vazio"),
        }

        pagesize = landscape(A4) if len(campos_visiveis) > 6 else A4
        margem   = 1.5 * cm
        largura_util = pagesize[0] - 2 * margem
        data_geracao = datetime.now().strftime("%d/%m/%Y %H:%M")
        texto_rodape = f"{nome_escritorio} — Relatório emitido em {data_geracao}"

        class _CanvasNumerado(rl_canvas.Canvas):
            """Canvas em duas passadas, para poder escrever 'Página X de Y'."""

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._paginas: list[dict] = []

            def showPage(self):
                self._paginas.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total = len(self._paginas)
                for pagina in self._paginas:
                    self.__dict__.update(pagina)
                    self._rodape(total)
                    super().showPage()
                super().save()

            def _rodape(self, total):
                self.setStrokeColor(CINZA_BORDA)
                self.setLineWidth(0.5)
                self.line(margem, 1.15 * cm, pagesize[0] - margem, 1.15 * cm)
                self.setFont(FONTE_BASE, 7.5)
                self.setFillColor(CINZA_SUB)
                self.drawString(margem, 0.7 * cm, texto_rodape)
                self.drawRightString(pagesize[0] - margem, 0.7 * cm,
                                     f"Página {self._pageNumber} de {total}")

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=pagesize,
            leftMargin=margem, rightMargin=margem,
            topMargin=1.5 * cm, bottomMargin=1.8 * cm,
            title=f"Relatório — {tipos_label(tipos_do_config(config))}",
            author=nome_escritorio,
        )
        story: list = []

        def barra_secao(texto: str, texto_direita: str = "") -> Table:
            if texto_direita:
                t = Table(
                    [[Paragraph(_xml_escape(texto.upper()), estilos["secao"]),
                      Paragraph(_xml_escape(texto_direita), estilos["barra_d"])]],
                    colWidths=[largura_util * 0.7, largura_util * 0.3],
                )
            else:
                t = Table([[Paragraph(_xml_escape(texto.upper()), estilos["secao"])]],
                          colWidths=[largura_util])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), CINZA_BARRA),
                ("BOX",        (0, 0), (-1, -1), 0.6, CINZA_BORDA),
                ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING",    (0, 0), (-1, -1), 6),
            ]))
            return t

        # ── Cabeçalho: logo + nome do escritório ─────────────────────────
        nome_par = Paragraph(_xml_escape(nome_escritorio), estilos["escrit"])
        logo_path = os.path.join(logo_dir, logo_arquivo) if logo_dir and logo_arquivo else ""
        cabecalho = nome_par
        if logo_path and os.path.exists(logo_path):
            try:
                logo_img = RLImage(logo_path)
                razao = (1.8 * cm) / logo_img.imageHeight
                largura_final = min(logo_img.imageWidth * razao, 5 * cm)
                altura_final  = largura_final / (logo_img.imageWidth / logo_img.imageHeight)
                logo_cell = RLImage(logo_path, width=largura_final, height=altura_final)
                cabecalho = Table([[logo_cell, nome_par]], colWidths=[largura_final + 0.4 * cm, None])
                cabecalho.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
            except Exception:
                cabecalho = nome_par
        story.append(cabecalho)
        story.append(Spacer(1, 8))

        # ── Barra de título + filtros aplicados ──────────────────────────
        tipo_label = tipos_label(tipos_do_config(config))
        story.append(barra_secao(f"Relatório — {tipo_label}", data_geracao))
        story.append(Spacer(1, 4))
        for linha_filtro in self._descrever_filtros(config):
            story.append(Paragraph(_xml_escape(linha_filtro), estilos["filtros"]))
        story.append(Spacer(1, 8))

        # ── Resumo em cartões (opcional) ─────────────────────────────────
        if config.get("mostrar_resumo"):
            story.append(self._montar_resumo_pdf(dados, estilos, largura_util, ZEBRA, CINZA_BORDA, BRANCO))
            story.append(Spacer(1, 12))

        # ── Tabela(s) de dados ───────────────────────────────────────────
        contexto = {
            "estilos": estilos, "largura": largura_util, "cabecalho": CABECALHO,
            "zebra": ZEBRA, "borda": CINZA_BORDA, "barra": CINZA_BARRA, "branco": BRANCO,
        }
        campo_grupo = config.get("agrupar_por", "")
        if campo_grupo and campo_grupo != "nenhum":
            grupos = self.agrupar(dados, campo_grupo)
            for i, (nome_grupo, linhas) in enumerate(grupos.items()):
                if i and config.get("quebra_pagina_grupo"):
                    story.append(PageBreak())
                else:
                    story.append(CondPageBreak(4 * cm))
                total_grupo = self._fmt_moeda(sum(float(l.get("valor") or 0) for l in linhas))
                n = len(linhas)
                story.append(barra_secao(
                    f"{nome_grupo} — {n} registro{'s' if n != 1 else ''}", total_grupo))
                story.extend(self._montar_tabela_pdf(linhas, campos_visiveis, config, contexto))
                story.append(Spacer(1, 10))
            if len(grupos) > 1:
                story.append(CondPageBreak(2 * cm))
                story.append(barra_secao(
                    f"Total geral — {len(dados)} registros",
                    self._fmt_moeda(sum(float(l.get("valor") or 0) for l in dados))))
        else:
            story.append(barra_secao("Registros"))
            story.extend(self._montar_tabela_pdf(dados, campos_visiveis, config, contexto))

        doc.build(story, canvasmaker=_CanvasNumerado)
        buf.seek(0)
        return buf.read()

    def _montar_resumo_pdf(self, dados, estilos, largura, fundo, borda, branco):
        """Faixa de cartões: registros, valor total, pago, vencido e a vencer."""
        from reportlab.platypus import Paragraph, Table, TableStyle

        def soma(status):
            linhas = [r for r in dados if r.get("status_pag") == status]
            return len(linhas), sum(float(r.get("valor") or 0) for r in linhas)

        totais = self.calcular_totais(dados)
        n_pago, v_pago = soma("PAGO")
        n_venc, v_venc = soma("VENCIDO")
        n_avenc, v_avenc = soma("A VENCER")
        cartoes = [
            ("REGISTROS", str(totais["total_registros"]), ""),
            ("VALOR TOTAL", self._fmt_moeda(totais["total_valor"]), ""),
            ("PAGO", self._fmt_moeda(v_pago), f"{n_pago} registro(s)"),
            ("VENCIDO", self._fmt_moeda(v_venc), f"{n_venc} registro(s)"),
            ("A VENCER", self._fmt_moeda(v_avenc), f"{n_avenc} registro(s)"),
        ]
        celulas = [[
            [Paragraph(rot, estilos["kpi_rot"]), Paragraph(val, estilos["kpi_val"]),
             Paragraph(sub or "&nbsp;", estilos["kpi_sub"])]
            for rot, val, sub in cartoes
        ]]
        t = Table(celulas, colWidths=[largura / len(cartoes)] * len(cartoes))
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), fundo),
            ("BOX",        (0, 0), (-1, -1), 0.6, borda),
            ("LINEAFTER",  (0, 0), (-2, -1), 0.6, borda),
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("PADDING",    (0, 0), (-1, -1), 7),
        ]))
        return t

    def _montar_tabela_pdf(self, dados, campos_visiveis, config, ctx):
        from reportlab.platypus import Table, TableStyle, Paragraph

        estilos = ctx["estilos"]
        if not dados:
            return [Paragraph("Nenhum registro encontrado.", estilos["vazio"])]

        ids = [c["id"] for c in campos_visiveis]
        a_direita = {"valor"}
        centralizados = {"placa", "ano_referencia", "vencimento", "data_pagamento", "data_infracao"}

        def estilo_cel(campo_id, prefixo="cell"):
            if campo_id in a_direita:
                return estilos[f"{prefixo}_d"]
            if campo_id in centralizados and prefixo != "total":
                return estilos[f"{prefixo}_c"]
            return estilos[prefixo]

        linhas = [[Paragraph(_xml_escape(c["label"]), estilo_cel(c["id"], "head")) for c in campos_visiveis]]

        for linha in dados:
            row = []
            for campo in campos_visiveis:
                cid = campo["id"]
                val = linha.get(cid, "")
                if cid == "valor":
                    texto = _xml_escape(self._fmt_moeda(val))
                elif cid in ("vencimento", "data_pagamento", "data_infracao"):
                    texto = _xml_escape(self._fmt_data(str(val or "")))
                elif cid == "status_pag" and str(val) in self._CORES_STATUS:
                    texto = f'<font color="{self._CORES_STATUS[str(val)]}"><b>{_xml_escape(str(val))}</b></font>'
                else:
                    texto = _xml_escape(str(val)) if val not in (None, "") else "—"
                row.append(Paragraph(texto, estilo_cel(cid)))
            linhas.append(row)

        tem_totais = bool(config.get("mostrar_totais"))
        if tem_totais:
            totais = self.calcular_totais(dados)
            linha_tot = [""] * len(ids)
            idx_rotulo = next((i for i, c in enumerate(ids) if c != "valor"), None)
            if idx_rotulo is not None:
                n = totais["total_registros"]
                linha_tot[idx_rotulo] = f"Total: {n} registro{'s' if n != 1 else ''}"
            if "valor" in ids:
                linha_tot[ids.index("valor")] = self._fmt_moeda(totais["total_valor"])
            linhas.append([Paragraph(_xml_escape(v), estilo_cel(cid, "total"))
                           for v, cid in zip(linha_tot, ids)])

        pesos = [self._PESOS_COLUNA.get(cid, 1.4) for cid in ids]
        col_w = [ctx["largura"] * p / sum(pesos) for p in pesos]
        t = Table(linhas, colWidths=col_w, repeatRows=1)
        ultima_dado = len(dados)
        regras = [
            ("BACKGROUND",     (0, 0), (-1, 0), ctx["cabecalho"]),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",    (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
            ("TOPPADDING",     (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, ultima_dado), [ctx["branco"], ctx["zebra"]]),
            ("LINEBELOW",      (0, 1), (-1, ultima_dado), 0.3, ctx["borda"]),
            ("BOX",            (0, 0), (-1, -1), 0.6, ctx["borda"]),
        ]
        if tem_totais:
            regras += [
                ("BACKGROUND", (0, -1), (-1, -1), ctx["barra"]),
                ("LINEABOVE",  (0, -1), (-1, -1), 0.8, ctx["borda"]),
            ]
        t.setStyle(TableStyle(regras))
        return [t]

    # ── Exportação Excel ────────────────────────────────────────────────────

    def gerar_excel(self, dados: list[dict], campos_visiveis: list[dict], config: dict) -> bytes:
        """Gera planilha Excel com os dados do relatório."""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        tipo_label = tipos_label(tipos_do_config(config))
        ws.title = tipo_label[:31]  # Excel limita o nome da aba a 31 caracteres

        fill_header = PatternFill(start_color="16181C", end_color="16181C", fill_type="solid")
        font_header = Font(bold=True, color="FFFFFF", size=11)
        fill_alt    = PatternFill(start_color="EDEAE1", end_color="EDEAE1", fill_type="solid")
        borda = Border(
            left=Side(style="thin", color="D8D4C8"),
            right=Side(style="thin", color="D8D4C8"),
            top=Side(style="thin", color="D8D4C8"),
            bottom=Side(style="thin", color="D8D4C8"),
        )

        for col_idx, campo in enumerate(campos_visiveis, start=1):
            cell            = ws.cell(row=1, column=col_idx, value=campo["label"])
            cell.font       = font_header
            cell.fill       = fill_header
            cell.alignment  = Alignment(horizontal="center", vertical="center")
            cell.border     = borda

        for row_idx, linha in enumerate(dados, start=2):
            fill_row = fill_alt if row_idx % 2 == 0 else None
            for col_idx, campo in enumerate(campos_visiveis, start=1):
                val = linha.get(campo["id"], "")
                if campo["id"] == "valor" and val is not None:
                    try:
                        val = float(val)
                    except (TypeError, ValueError):
                        val = ""
                elif campo["id"] in ("vencimento", "data_pagamento", "data_infracao"):
                    val = self._fmt_data(str(val)) if val else ""
                cell           = ws.cell(row=row_idx, column=col_idx, value=val if val is not None else "")
                if fill_row:
                    cell.fill  = fill_row
                cell.border    = borda
                cell.alignment = Alignment(vertical="center")

        if config.get("mostrar_totais") and dados:
            totais         = self.calcular_totais(dados)
            linha_tot_idx  = len(dados) + 2
            ids            = [c["id"] for c in campos_visiveis]
            fill_total     = PatternFill(start_color="1A4F8A", end_color="1A4F8A", fill_type="solid")
            for col_idx, campo in enumerate(campos_visiveis, start=1):
                val = ""
                if campo["id"] == "valor":
                    val = totais["total_valor"]
                elif campo["id"] == "cliente_nome":
                    val = f"TOTAL: {totais['total_registros']} registros"
                cell           = ws.cell(row=linha_tot_idx, column=col_idx, value=val)
                cell.font      = Font(bold=True, color="FFFFFF", size=11)
                cell.fill      = fill_total
                cell.border    = borda
                cell.alignment = Alignment(vertical="center")

        for col_idx, campo in enumerate(campos_visiveis, start=1):
            max_len = max(
                len(str(campo["label"])),
                *(len(str(linha.get(campo["id"], "") or "")) for linha in dados[:50]),
                10,
            )
            ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 40)

        ws.row_dimensions[1].height = 20

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read()

    # ── Helpers de formatação ───────────────────────────────────────────────

    @staticmethod
    def _fmt_data(valor: str) -> str:
        if not valor or len(valor) < 8:
            return "—"
        try:
            y, m, d = valor[:10].split("-")
            return f"{d}/{m}/{y}"
        except (ValueError, AttributeError):
            return valor

    @staticmethod
    def _fmt_moeda(valor) -> str:
        if valor is None or valor == "":
            return "—"
        try:
            return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return "—"
