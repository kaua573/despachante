"""
Serviço de clientes e documentos anexados.
Toda lógica de negócio relacionada a clientes passa por aqui.
"""
import os
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from app.models.cliente import Cliente
from app.models.documento import Documento
from app.services.base import TenantService


class ClienteService(TenantService):
    def __init__(self, session: Session, upload_dir: str, escritorio_id: int) -> None:
        super().__init__(session, escritorio_id)
        self._upload_dir = upload_dir

    def listar(self, busca: str = "") -> list[Cliente]:
        q = self.scoped(Cliente)
        if busca:
            termo = f"%{busca}%"
            q = q.filter(
                Cliente.nome.ilike(termo)
                | Cliente.cpf.ilike(termo)
                | Cliente.cnpj.ilike(termo)
                | Cliente.telefone.ilike(termo)
            )
        return q.order_by(Cliente.nome).all()

    def obter(self, cliente_id: int) -> Optional[Cliente]:
        return self.scoped(Cliente).filter_by(id=cliente_id).first()

    def cpf_em_uso(self, cpf: str, ignorar_id: Optional[int] = None) -> bool:
        if not cpf:
            return False
        q = self.scoped(Cliente).filter(Cliente.cpf == cpf)
        if ignorar_id:
            q = q.filter(Cliente.id != ignorar_id)
        return self._s.query(q.exists()).scalar()

    def cnpj_em_uso(self, cnpj: str, ignorar_id: Optional[int] = None) -> bool:
        if not cnpj:
            return False
        q = self.scoped(Cliente).filter(Cliente.cnpj == cnpj)
        if ignorar_id:
            q = q.filter(Cliente.id != ignorar_id)
        return self._s.query(q.exists()).scalar()

    def criar(self, dados: dict) -> tuple[Optional[Cliente], str]:
        tipo_pessoa = (dados.get("tipo_pessoa") or "PF").upper()
        # Guarda None (não string vazia) para o campo que não se aplica,
        # senão dois clientes PJ sem CPF colidiriam na constraint UNIQUE.
        cpf = dados.get("cpf") or None if tipo_pessoa == "PF" else None
        cnpj = dados.get("cnpj") or None if tipo_pessoa == "PJ" else None
        if tipo_pessoa == "PF" and self.cpf_em_uso(cpf):
            return None, "Já existe um cliente cadastrado com esse CPF."
        if tipo_pessoa == "PJ" and self.cnpj_em_uso(cnpj):
            return None, "Já existe um cliente cadastrado com esse CNPJ."
        cliente = Cliente(
            escritorio_id=self.escritorio_id,
            nome=dados["nome"],
            tipo_pessoa=tipo_pessoa,
            cpf=cpf,
            cnpj=cnpj,
            telefone=dados.get("telefone", ""),
            email=dados.get("email", ""),
            observacao=dados.get("observacao", ""),
        )
        self._s.add(cliente)
        try:
            self._s.commit()
        except IntegrityError:
            self._s.rollback()
            msg = "Já existe um cliente cadastrado com esse CNPJ." if tipo_pessoa == "PJ" \
                else "Já existe um cliente cadastrado com esse CPF."
            return None, msg
        return cliente, ""

    def atualizar(self, cliente_id: int, dados: dict) -> tuple[bool, str]:
        cliente = self.obter(cliente_id)
        if not cliente:
            return False, "Cliente não encontrado."
        tipo_pessoa = (dados.get("tipo_pessoa") or "PF").upper()
        cpf = dados.get("cpf") or None if tipo_pessoa == "PF" else None
        cnpj = dados.get("cnpj") or None if tipo_pessoa == "PJ" else None
        if tipo_pessoa == "PF" and self.cpf_em_uso(cpf, ignorar_id=cliente_id):
            return False, "Já existe um cliente cadastrado com esse CPF."
        if tipo_pessoa == "PJ" and self.cnpj_em_uso(cnpj, ignorar_id=cliente_id):
            return False, "Já existe um cliente cadastrado com esse CNPJ."
        cliente.nome = dados["nome"]
        cliente.tipo_pessoa = tipo_pessoa
        cliente.cpf = cpf
        cliente.cnpj = cnpj
        cliente.telefone = dados.get("telefone", "")
        cliente.email = dados.get("email", "")
        cliente.observacao = dados.get("observacao", "")
        try:
            self._s.commit()
        except IntegrityError:
            self._s.rollback()
            msg = "Já existe um cliente cadastrado com esse CNPJ." if tipo_pessoa == "PJ" \
                else "Já existe um cliente cadastrado com esse CPF."
            return False, msg
        return True, ""

    def excluir(self, cliente_id: int) -> tuple[bool, str]:
        cliente = self.obter(cliente_id)
        if not cliente:
            return False, "Cliente não encontrado."
        # Remove arquivos de documentos do disco antes de deletar do banco
        for doc in cliente.documentos:
            self._remover_arquivo_disco(doc.arquivo)
        self._s.delete(cliente)
        self._s.commit()
        return True, ""

    # ── Documentos ──────────────────────────────────────────────────────────
    # Documento não tem escritorio_id próprio — pertence a um Cliente, que já
    # é escopado. `obter()` acima já garante que o cliente_id usado abaixo só
    # chega aqui depois de confirmado como do escritório atual.

    def listar_documentos(self, cliente_id: int) -> list[Documento]:
        return (
            self._s.query(Documento)
            .filter_by(cliente_id=cliente_id)
            .order_by(Documento.data_documento.desc())
            .all()
        )

    def criar_documento(
        self,
        cliente_id: int,
        dados: dict,
        arquivo: Optional[FileStorage],
        extensoes_permitidas: set,
    ) -> tuple[bool, str]:
        arquivo_nome = None
        if arquivo and arquivo.filename:
            ok, resultado = self._salvar_arquivo(arquivo, extensoes_permitidas)
            if not ok:
                return False, resultado
            arquivo_nome = resultado

        doc = Documento(
            cliente_id=cliente_id,
            nome=dados["nome"],
            data_documento=dados["data_documento"],
            categoria=dados["categoria"],
            observacao=dados.get("observacao", ""),
            arquivo=arquivo_nome,
        )
        self._s.add(doc)
        self._s.commit()
        return True, ""

    def excluir_documento(self, doc_id: int) -> tuple[bool, str]:
        doc = self._s.get(Documento, doc_id)
        if not doc:
            return False, "Documento não encontrado."
        self._remover_arquivo_disco(doc.arquivo)
        self._s.delete(doc)
        self._s.commit()
        return True, ""

    # ── Helpers privados ────────────────────────────────────────────────────

    def _salvar_arquivo(self, arquivo: FileStorage, extensoes_permitidas: set) -> tuple[bool, str]:
        ext = os.path.splitext(arquivo.filename)[1].lower()
        if ext not in extensoes_permitidas:
            return False, f"Formato não permitido. Use: {', '.join(extensoes_permitidas)}"
        nome = f"{uuid.uuid4().hex}{ext}"
        arquivo.save(os.path.join(self._upload_dir, nome))
        return True, nome

    def _remover_arquivo_disco(self, nome_arquivo: Optional[str]) -> None:
        if not nome_arquivo:
            return
        caminho = os.path.join(self._upload_dir, nome_arquivo)
        try:
            if os.path.exists(caminho):
                os.remove(caminho)
        except OSError:
            pass
