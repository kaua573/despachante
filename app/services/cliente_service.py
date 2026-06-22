"""
Serviço de clientes e documentos anexados.
Toda lógica de negócio relacionada a clientes passa por aqui.
"""
import os
import uuid
from typing import Optional
from sqlalchemy.orm import Session
from werkzeug.datastructures import FileStorage

from app.models.cliente import Cliente
from app.models.documento import Documento


class ClienteService:
    def __init__(self, session: Session, upload_dir: str) -> None:
        self._session = session
        self._upload_dir = upload_dir

    def listar(self, busca: str = "") -> list[Cliente]:
        q = self._session.query(Cliente)
        if busca:
            termo = f"%{busca}%"
            q = q.filter(
                Cliente.nome.ilike(termo)
                | Cliente.cpf.ilike(termo)
                | Cliente.telefone.ilike(termo)
            )
        return q.order_by(Cliente.nome).all()

    def obter(self, cliente_id: int) -> Optional[Cliente]:
        return self._session.get(Cliente, cliente_id)

    def criar(self, dados: dict) -> Cliente:
        cliente = Cliente(
            nome=dados["nome"],
            cpf=dados.get("cpf", ""),
            telefone=dados.get("telefone", ""),
            email=dados.get("email", ""),
            observacao=dados.get("observacao", ""),
        )
        self._session.add(cliente)
        self._session.commit()
        return cliente

    def atualizar(self, cliente_id: int, dados: dict) -> tuple[bool, str]:
        cliente = self.obter(cliente_id)
        if not cliente:
            return False, "Cliente não encontrado."
        cliente.nome = dados["nome"]
        cliente.cpf = dados.get("cpf", "")
        cliente.telefone = dados.get("telefone", "")
        cliente.email = dados.get("email", "")
        cliente.observacao = dados.get("observacao", "")
        self._session.commit()
        return True, ""

    def excluir(self, cliente_id: int) -> tuple[bool, str]:
        cliente = self.obter(cliente_id)
        if not cliente:
            return False, "Cliente não encontrado."
        # Remove arquivos de documentos do disco antes de deletar do banco
        for doc in cliente.documentos:
            self._remover_arquivo_disco(doc.arquivo)
        self._session.delete(cliente)
        self._session.commit()
        return True, ""

    # ── Documentos ──────────────────────────────────────────────────────────

    def listar_documentos(self, cliente_id: int) -> list[Documento]:
        return (
            self._session.query(Documento)
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
        self._session.add(doc)
        self._session.commit()
        return True, ""

    def excluir_documento(self, doc_id: int) -> tuple[bool, str]:
        doc = self._session.get(Documento, doc_id)
        if not doc:
            return False, "Documento não encontrado."
        self._remover_arquivo_disco(doc.arquivo)
        self._session.delete(doc)
        self._session.commit()
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
