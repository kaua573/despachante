"""
Importação e exportação em massa via Excel.

- exportar()/importar(): todos os clientes + veículos do sistema, ligados
  pelo CPF ou CNPJ do cliente (usado na tela de Clientes).
- exportar_veiculos_cliente()/importar_veiculos_cliente(): só os veículos de
  UM cliente específico, sem precisar da coluna de documento (usado na tela
  de Veículos de um cliente — útil pra quem tem uma frota grande).
- pre_visualizar()/pre_visualizar_veiculos_cliente(): mesma leitura e
  validação dos métodos acima, mas SEM gravar nada no banco — só relata
  linha a linha o que aconteceria (criar/atualizar/erro). Usado para
  mostrar uma prévia antes do usuário confirmar a importação de verdade.

Os fluxos reais reaproveitam ClienteService/VeiculoService para criar/
atualizar registros, ou seja, passam pelas mesmas validações e regras de
duplicidade (CPF/CNPJ, placa) que já valem para o cadastro manual. A prévia
reaproveita as mesmas funções de validação e os mesmos checadores de
duplicidade (cpf_em_uso/cnpj_em_uso/placa_em_uso) para nunca divergir do que
a importação real de fato faria.
"""
from __future__ import annotations

import io
import re
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.veiculo import Veiculo
from app.services.cliente_service import ClienteService
from app.services.veiculo_service import VeiculoService
from app.services.validacao_service import (
    validar_campos_cliente, validar_campos_veiculo,
    normalizar_cpf, normalizar_cnpj, normalizar_telefone,
)

COLUNAS_CLIENTES = ["Nome/Razão Social*", "Tipo (PF/PJ)*", "CPF", "CNPJ", "Telefone*", "Email", "Observação"]
COLUNAS_VEICULOS = [
    "CPF/CNPJ do Cliente*", "Placa*", "RENAVAM*", "Proprietário*",
    "Marca/Modelo*", "Situação", "Espécie", "Observação",
]
COLUNAS_VEICULOS_CLIENTE = [
    "Placa*", "RENAVAM*", "Proprietário*",
    "Marca/Modelo*", "Situação", "Espécie", "Observação",
]

SITUACOES_VALIDAS = {"ativo", "desativado", "vendido", "pendente"}
ESPECIES_VALIDAS = {"passeio", "carga", "reboque"}

COR_CABECALHO = "1A4F8A"


class ImportacaoService:
    def __init__(self, session: Session, upload_dir: str = "") -> None:
        self._session = session
        self._cliente_svc = ClienteService(session, upload_dir)
        self._veiculo_svc = VeiculoService(session)

    # ── Exportação — todos os clientes ──────────────────────────────────────

    def exportar(self) -> bytes:
        """Gera um .xlsx com duas abas: Clientes e Veículos (ligados pelo CPF)."""
        wb = Workbook()
        fill_header, font_header = self._estilo_cabecalho()

        ws_clientes = wb.active
        ws_clientes.title = "Clientes"
        self._escrever_cabecalho(ws_clientes, COLUNAS_CLIENTES, fill_header, font_header)

        clientes = self._session.query(Cliente).order_by(Cliente.nome).all()
        for row_idx, c in enumerate(clientes, start=2):
            ws_clientes.cell(row=row_idx, column=1, value=c.nome)
            ws_clientes.cell(row=row_idx, column=2, value=c.tipo_pessoa or "PF")
            ws_clientes.cell(row=row_idx, column=3, value=c.cpf or "")
            ws_clientes.cell(row=row_idx, column=4, value=c.cnpj or "")
            ws_clientes.cell(row=row_idx, column=5, value=c.telefone or "")
            ws_clientes.cell(row=row_idx, column=6, value=c.email or "")
            ws_clientes.cell(row=row_idx, column=7, value=c.observacao or "")

        ws_veiculos = wb.create_sheet("Veiculos")
        self._escrever_cabecalho(ws_veiculos, COLUNAS_VEICULOS, fill_header, font_header)

        row_idx = 2
        for c in clientes:
            documento = c.cnpj if c.tipo_pessoa == "PJ" else c.cpf
            for v in sorted(c.veiculos, key=lambda x: x.placa):
                ws_veiculos.cell(row=row_idx, column=1, value=documento or "")
                ws_veiculos.cell(row=row_idx, column=2, value=v.placa)
                ws_veiculos.cell(row=row_idx, column=3, value=v.renavam or "")
                ws_veiculos.cell(row=row_idx, column=4, value=v.proprietario or "")
                ws_veiculos.cell(row=row_idx, column=5, value=v.marca_modelo or "")
                ws_veiculos.cell(row=row_idx, column=6, value=v.situacao or "ativo")
                ws_veiculos.cell(row=row_idx, column=7, value=v.especie or "passeio")
                ws_veiculos.cell(row=row_idx, column=8, value=v.observacao or "")
                row_idx += 1

        self._ajustar_largura(ws_clientes, COLUNAS_CLIENTES)
        self._ajustar_largura(ws_veiculos, COLUNAS_VEICULOS)
        return self._salvar(wb)

    def gerar_modelo(self) -> bytes:
        """Planilha vazia (Clientes + Veículos), só com os cabeçalhos."""
        wb = Workbook()
        fill_header, font_header = self._estilo_cabecalho()

        ws_clientes = wb.active
        ws_clientes.title = "Clientes"
        self._escrever_cabecalho(ws_clientes, COLUNAS_CLIENTES, fill_header, font_header)

        ws_veiculos = wb.create_sheet("Veiculos")
        self._escrever_cabecalho(ws_veiculos, COLUNAS_VEICULOS, fill_header, font_header)

        return self._salvar(wb)

    def importar(self, conteudo_arquivo: bytes) -> dict:
        """
        Lê um .xlsx no mesmo formato do exportar() e cria/atualiza clientes e
        veículos de verdade. Cliente é identificado pelo CPF; veículo, pela
        placa dentro do mesmo cliente. Continua processando mesmo se uma
        linha falhar — cada erro é reportado, sem travar o restante do
        arquivo.
        """
        resultado = {
            "clientes_criados": 0, "clientes_atualizados": 0,
            "veiculos_criados": 0, "veiculos_atualizados": 0,
            "erros": [],
        }

        wb, erro_abertura = self._abrir_planilha(conteudo_arquivo)
        if wb is None:
            resultado["erros"].append({"linha": "-", "erro": erro_abertura})
            return resultado

        if "Clientes" not in wb.sheetnames:
            resultado["erros"].append({"linha": "-", "erro": 'Aba "Clientes" não encontrada na planilha.'})
            return resultado

        documento_para_cliente_id: dict[str, int] = {}
        self._importar_clientes(wb["Clientes"], resultado, documento_para_cliente_id)

        if "Veiculos" in wb.sheetnames:
            self._importar_veiculos(wb["Veiculos"], resultado, documento_para_cliente_id)

        return resultado

    # ── Prévia — todos os clientes (dry-run, não grava nada) ────────────────

    def pre_visualizar(self, conteudo_arquivo: bytes) -> dict:
        preview = {"itens": [], "contagem": {"criar": 0, "atualizar": 0, "erro": 0}}

        wb, erro_abertura = self._abrir_planilha(conteudo_arquivo)
        if wb is None:
            self._add_item(preview, "-", "erro", erro=erro_abertura)
            return preview

        if "Clientes" not in wb.sheetnames:
            self._add_item(preview, "-", "erro", erro='Aba "Clientes" não encontrada na planilha.')
            return preview

        documentos_no_arquivo: set = set()
        self._pre_visualizar_clientes(wb["Clientes"], preview, documentos_no_arquivo)

        if "Veiculos" in wb.sheetnames:
            self._pre_visualizar_veiculos(wb["Veiculos"], preview, documentos_no_arquivo)

        return preview

    def _pre_visualizar_clientes(self, ws, preview: dict, documentos_no_arquivo: set) -> None:
        linhas = ws.iter_rows(min_row=2, values_only=True)
        for numero_linha, linha in enumerate(linhas, start=2):
            if linha is None or not any(linha):
                continue
            nome, tipo_pessoa, cpf, cnpj, telefone, email, observacao = (list(linha) + [None] * 7)[:7]

            dados = self._montar_dados_cliente(nome, tipo_pessoa, cpf, cnpj, telefone, email, observacao)

            erro = validar_campos_cliente(dados)
            if erro:
                self._add_item(preview, numero_linha, "erro", erro=f"[Clientes] {erro}")
                continue

            documento = dados["cpf"] if dados["tipo_pessoa"] == "PF" else dados["cnpj"]
            campo = Cliente.cpf if dados["tipo_pessoa"] == "PF" else Cliente.cnpj
            existente = self._session.query(Cliente).filter(campo == documento).first()
            acao = "atualizar" if existente else "criar"
            documentos_no_arquivo.add(documento)
            rotulo_doc = "CNPJ" if dados["tipo_pessoa"] == "PJ" else "CPF"
            self._add_item(preview, numero_linha, acao, resumo=f"{dados['nome']} — {rotulo_doc} {documento}")

    def _pre_visualizar_veiculos(self, ws, preview: dict, documentos_no_arquivo: set) -> None:
        linhas = ws.iter_rows(min_row=2, values_only=True)
        for numero_linha, linha in enumerate(linhas, start=2):
            if linha is None or not any(linha):
                continue
            documento, placa, renavam, proprietario, marca_modelo, situacao, especie, observacao = (
                list(linha) + [None] * 8
            )[:8]

            documento_normalizado = self._normalizar_documento(documento)
            cliente = self._localizar_cliente_por_documento(documento_normalizado)
            if not cliente and documento_normalizado not in documentos_no_arquivo:
                self._add_item(preview, numero_linha, "erro",
                                erro=f"[Veículos] Nenhum cliente encontrado com o CPF/CNPJ '{documento}'.")
                continue

            erro, dados = self._preparar_linha_veiculo(placa, renavam, proprietario, marca_modelo, situacao, especie, observacao)
            if erro:
                self._add_item(preview, numero_linha, "erro", erro=f"[Veículos] {erro}")
                continue

            cliente_id = cliente.id if cliente else None
            acao, erro_duplicidade = self._determinar_acao_veiculo(cliente_id, dados)
            if erro_duplicidade:
                self._add_item(preview, numero_linha, "erro", erro=f"[Veículos] {erro_duplicidade}")
                continue

            self._add_item(preview, numero_linha, acao,
                            resumo=f"{dados['placa']} — {dados['marca_modelo'] or 'sem marca/modelo informada'}")

    # ── Exportação — veículos de UM cliente ─────────────────────────────────

    def exportar_veiculos_cliente(self, cliente_id: int) -> bytes:
        """Só os veículos do cliente indicado — sem coluna de CPF, já que o escopo é um só cliente."""
        wb = Workbook()
        fill_header, font_header = self._estilo_cabecalho()

        ws = wb.active
        ws.title = "Veiculos"
        self._escrever_cabecalho(ws, COLUNAS_VEICULOS_CLIENTE, fill_header, font_header)

        veiculos = (
            self._session.query(Veiculo)
            .filter_by(cliente_id=cliente_id)
            .order_by(Veiculo.placa)
            .all()
        )
        for row_idx, v in enumerate(veiculos, start=2):
            ws.cell(row=row_idx, column=1, value=v.placa)
            ws.cell(row=row_idx, column=2, value=v.renavam or "")
            ws.cell(row=row_idx, column=3, value=v.proprietario or "")
            ws.cell(row=row_idx, column=4, value=v.marca_modelo or "")
            ws.cell(row=row_idx, column=5, value=v.situacao or "ativo")
            ws.cell(row=row_idx, column=6, value=v.especie or "passeio")
            ws.cell(row=row_idx, column=7, value=v.observacao or "")

        self._ajustar_largura(ws, COLUNAS_VEICULOS_CLIENTE)
        return self._salvar(wb)

    def gerar_modelo_veiculos_cliente(self) -> bytes:
        """Planilha vazia, só com os cabeçalhos dos veículos (sem coluna de CPF)."""
        wb = Workbook()
        fill_header, font_header = self._estilo_cabecalho()
        ws = wb.active
        ws.title = "Veiculos"
        self._escrever_cabecalho(ws, COLUNAS_VEICULOS_CLIENTE, fill_header, font_header)
        return self._salvar(wb)

    def importar_veiculos_cliente(self, cliente_id: int, conteudo_arquivo: bytes) -> dict:
        """
        Lê um .xlsx no formato do exportar_veiculos_cliente() e cria/atualiza
        veículos DESSE cliente de verdade. Identificado pela placa (dentro do
        escopo desse cliente só). Não mexe em veículos de outros clientes.
        """
        resultado = {"veiculos_criados": 0, "veiculos_atualizados": 0, "erros": []}

        wb, erro_abertura = self._abrir_planilha(conteudo_arquivo)
        if wb is None:
            resultado["erros"].append({"linha": "-", "erro": erro_abertura})
            return resultado

        nome_aba = "Veiculos" if "Veiculos" in wb.sheetnames else wb.sheetnames[0]
        self._importar_veiculos_de_um_cliente(wb[nome_aba], cliente_id, resultado)
        return resultado

    # ── Prévia — veículos de UM cliente (dry-run, não grava nada) ────────────

    def pre_visualizar_veiculos_cliente(self, cliente_id: int, conteudo_arquivo: bytes) -> dict:
        preview = {"itens": [], "contagem": {"criar": 0, "atualizar": 0, "erro": 0}}

        wb, erro_abertura = self._abrir_planilha(conteudo_arquivo)
        if wb is None:
            self._add_item(preview, "-", "erro", erro=erro_abertura)
            return preview

        nome_aba = "Veiculos" if "Veiculos" in wb.sheetnames else wb.sheetnames[0]
        linhas = wb[nome_aba].iter_rows(min_row=2, values_only=True)
        for numero_linha, linha in enumerate(linhas, start=2):
            if linha is None or not any(linha):
                continue
            placa, renavam, proprietario, marca_modelo, situacao, especie, observacao = (
                list(linha) + [None] * 7
            )[:7]

            erro, dados = self._preparar_linha_veiculo(placa, renavam, proprietario, marca_modelo, situacao, especie, observacao)
            if erro:
                self._add_item(preview, numero_linha, "erro", erro=f"[Veículos] {erro}")
                continue

            acao, erro_duplicidade = self._determinar_acao_veiculo(cliente_id, dados)
            if erro_duplicidade:
                self._add_item(preview, numero_linha, "erro", erro=f"[Veículos] {erro_duplicidade}")
                continue

            self._add_item(preview, numero_linha, acao,
                            resumo=f"{dados['placa']} — {dados['marca_modelo'] or 'sem marca/modelo informada'}")

        return preview

    # ── Helpers de planilha ──────────────────────────────────────────────────

    @staticmethod
    def _estilo_cabecalho():
        return (
            PatternFill(start_color=COR_CABECALHO, end_color=COR_CABECALHO, fill_type="solid"),
            Font(bold=True, color="FFFFFF", size=11),
        )

    @staticmethod
    def _escrever_cabecalho(ws, colunas, fill, font) -> None:
        for col_idx, titulo in enumerate(colunas, start=1):
            cell = ws.cell(row=1, column=col_idx, value=titulo)
            cell.fill = fill
            cell.font = font

    @staticmethod
    def _ajustar_largura(ws, colunas) -> None:
        for col_idx, titulo in enumerate(colunas, start=1):
            ws.column_dimensions[chr(64 + col_idx)].width = max(14, len(titulo) + 4)

    @staticmethod
    def _salvar(wb: Workbook) -> bytes:
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _abrir_planilha(conteudo_arquivo: bytes):
        """Retorna (workbook, None) em caso de sucesso, ou (None, mensagem_de_erro)."""
        try:
            return load_workbook(io.BytesIO(conteudo_arquivo), read_only=True, data_only=True), None
        except Exception:
            return None, "Arquivo inválido. Envie um .xlsx no formato do modelo."

    @staticmethod
    def _normalizar_documento(v) -> str:
        """Só dígitos — serve tanto pra CPF (11) quanto CNPJ (14), usados como chave de junção."""
        return re.sub(r"\D", "", str(v or ""))

    @staticmethod
    def _montar_dados_cliente(nome, tipo_pessoa, cpf, cnpj, telefone, email, observacao) -> dict:
        tipo_pessoa = str(tipo_pessoa or "PF").strip().upper()
        if tipo_pessoa not in ("PF", "PJ"):
            tipo_pessoa = "PF"
        return {
            "nome": str(nome or "").strip(),
            "tipo_pessoa": tipo_pessoa,
            "cpf": normalizar_cpf(str(cpf or "")) if tipo_pessoa == "PF" else "",
            "cnpj": normalizar_cnpj(str(cnpj or "")) if tipo_pessoa == "PJ" else "",
            "telefone": normalizar_telefone(str(telefone or "")),
            "email": str(email or "").strip(),
            "observacao": str(observacao or "").strip(),
        }

    def _localizar_cliente_por_documento(self, documento_normalizado: str) -> Optional[Cliente]:
        if not documento_normalizado:
            return None
        return (
            self._session.query(Cliente)
            .filter((Cliente.cpf == documento_normalizado) | (Cliente.cnpj == documento_normalizado))
            .first()
        )

    @staticmethod
    def _add_item(preview: dict, linha, acao: str, resumo: str = "", erro: str = "") -> None:
        item = {"linha": linha, "acao": acao}
        if acao == "erro":
            item["erro"] = erro
        else:
            item["resumo"] = resumo
        preview["itens"].append(item)
        preview["contagem"][acao] += 1

    # ── Importação — clientes ────────────────────────────────────────────────

    def _importar_clientes(self, ws, resultado: dict, documento_para_cliente_id: dict) -> None:
        linhas = ws.iter_rows(min_row=2, values_only=True)
        for numero_linha, linha in enumerate(linhas, start=2):
            if linha is None or not any(linha):
                continue
            nome, tipo_pessoa, cpf, cnpj, telefone, email, observacao = (list(linha) + [None] * 7)[:7]

            dados = self._montar_dados_cliente(nome, tipo_pessoa, cpf, cnpj, telefone, email, observacao)

            erro = validar_campos_cliente(dados)
            if erro:
                resultado["erros"].append({"linha": numero_linha, "erro": f"[Clientes] {erro}"})
                continue

            documento = dados["cpf"] if dados["tipo_pessoa"] == "PF" else dados["cnpj"]
            campo = Cliente.cpf if dados["tipo_pessoa"] == "PF" else Cliente.cnpj
            existente = self._session.query(Cliente).filter(campo == documento).first()
            if existente:
                ok, erro = self._cliente_svc.atualizar(existente.id, dados)
                if not ok:
                    resultado["erros"].append({"linha": numero_linha, "erro": f"[Clientes] {erro}"})
                    continue
                documento_para_cliente_id[documento] = existente.id
                resultado["clientes_atualizados"] += 1
            else:
                cliente, erro = self._cliente_svc.criar(dados)
                if not cliente:
                    resultado["erros"].append({"linha": numero_linha, "erro": f"[Clientes] {erro}"})
                    continue
                documento_para_cliente_id[documento] = cliente.id
                resultado["clientes_criados"] += 1

    # ── Importação — veículos ────────────────────────────────────────────────

    def _importar_veiculos(self, ws, resultado: dict, documento_para_cliente_id: dict) -> None:
        """Planilha com coluna de CPF/CNPJ (usada na importação global de clientes)."""
        linhas = ws.iter_rows(min_row=2, values_only=True)
        for numero_linha, linha in enumerate(linhas, start=2):
            if linha is None or not any(linha):
                continue
            documento, placa, renavam, proprietario, marca_modelo, situacao, especie, observacao = (
                list(linha) + [None] * 8
            )[:8]

            documento_normalizado = self._normalizar_documento(documento)
            cliente_id = documento_para_cliente_id.get(documento_normalizado)
            if not cliente_id:
                cliente = self._localizar_cliente_por_documento(documento_normalizado)
                cliente_id = cliente.id if cliente else None

            if not cliente_id:
                resultado["erros"].append({
                    "linha": numero_linha,
                    "erro": f"[Veículos] Nenhum cliente encontrado com o CPF/CNPJ '{documento}'. "
                            f"Cadastre o cliente antes (ou inclua-o na aba Clientes desta planilha).",
                })
                continue

            self._upsert_veiculo(
                cliente_id, placa, renavam, proprietario, marca_modelo,
                situacao, especie, observacao, numero_linha, resultado,
            )

    def _importar_veiculos_de_um_cliente(self, ws, cliente_id: int, resultado: dict) -> None:
        """Planilha sem coluna de CPF — todo mundo pertence ao mesmo cliente_id."""
        linhas = ws.iter_rows(min_row=2, values_only=True)
        for numero_linha, linha in enumerate(linhas, start=2):
            if linha is None or not any(linha):
                continue
            placa, renavam, proprietario, marca_modelo, situacao, especie, observacao = (
                list(linha) + [None] * 7
            )[:7]

            self._upsert_veiculo(
                cliente_id, placa, renavam, proprietario, marca_modelo,
                situacao, especie, observacao, numero_linha, resultado,
            )

    def _preparar_linha_veiculo(self, placa, renavam, proprietario, marca_modelo, situacao, especie, observacao):
        """Normaliza e valida uma linha de veículo (sem cliente_id ainda). Retorna (erro_ou_None, dados)."""
        situacao = str(situacao or "ativo").strip().lower() or "ativo"
        especie = str(especie or "passeio").strip().lower() or "passeio"
        if situacao not in SITUACOES_VALIDAS:
            situacao = "ativo"
        if especie not in ESPECIES_VALIDAS:
            especie = "passeio"

        dados = {
            "placa": str(placa or "").strip(),
            "renavam": str(renavam or "").strip(),
            "proprietario": str(proprietario or "").strip(),
            "marca_modelo": str(marca_modelo or "").strip(),
            "situacao": situacao,
            "especie": especie,
            "observacao": str(observacao or "").strip(),
        }
        erro = validar_campos_veiculo(dados)
        return erro, dados

    def _determinar_acao_veiculo(self, cliente_id: Optional[int], dados: dict):
        """
        Decide se a linha seria 'criar' ou 'atualizar', e detecta conflito de
        placa duplicada — usando exatamente a mesma regra (placa_em_uso) que
        VeiculoService.criar()/atualizar() usam de verdade. Retorna
        (acao, erro_ou_None).
        """
        placa_normalizada = dados["placa"].upper()
        existente = None
        if cliente_id:
            existente = (
                self._session.query(Veiculo)
                .filter(Veiculo.cliente_id == cliente_id, Veiculo.placa == placa_normalizada)
                .first()
            )

        if existente:
            if dados["situacao"] != "vendido" and self._veiculo_svc.placa_em_uso(placa_normalizada, ignorar_id=existente.id):
                return "erro", "Já existe outro veículo ativo cadastrado com esta placa."
            return "atualizar", None

        if dados["situacao"] != "vendido" and self._veiculo_svc.placa_em_uso(placa_normalizada):
            return "erro", "Já existe um veículo ativo cadastrado com esta placa."
        return "criar", None

    def _upsert_veiculo(
        self, cliente_id: int, placa, renavam, proprietario, marca_modelo,
        situacao, especie, observacao, numero_linha: int, resultado: dict,
    ) -> None:
        erro, dados = self._preparar_linha_veiculo(placa, renavam, proprietario, marca_modelo, situacao, especie, observacao)
        if erro:
            resultado["erros"].append({"linha": numero_linha, "erro": f"[Veículos] {erro}"})
            return
        dados["cliente_id"] = cliente_id

        existente = (
            self._session.query(Veiculo)
            .filter(Veiculo.cliente_id == cliente_id, Veiculo.placa == dados["placa"].upper())
            .first()
        )
        if existente:
            ok, erro = self._veiculo_svc.atualizar(existente.id, dados)
            if not ok:
                resultado["erros"].append({"linha": numero_linha, "erro": f"[Veículos] {erro}"})
                return
            resultado["veiculos_atualizados"] += 1
        else:
            veiculo, erro = self._veiculo_svc.criar(dados)
            if not veiculo:
                resultado["erros"].append({"linha": numero_linha, "erro": f"[Veículos] {erro}"})
                return
            resultado["veiculos_criados"] += 1
