"""
Gerenciamento de escritórios (tenants).

Diferente de todo outro service deste projeto, este NÃO herda de
TenantService — ele opera ACIMA dos escritórios (cria, lista, ativa/
desativa), não dentro de um. É por isso que só é acessível pela tela
/super-admin, protegida por um segredo à parte do login normal (ver
app/routes/super_admin.py e config.py:SUPER_ADMIN_TOKEN).
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.configuracao import Configuracao
from app.models.contato_pendencia import ContatoPendencia
from app.models.documento import Documento
from app.models.escritorio import Escritorio
from app.models.ipva import Ipva
from app.models.ipva_parcela import IpvaParcela
from app.models.licenciamento import Licenciamento
from app.models.log_acao import LogAcao
from app.models.multa import Multa
from app.models.permissao_usuario import PermissaoUsuario
from app.models.regra_vencimento import RegraVencimento
from app.models.template_relatorio import TemplateRelatorio
from app.models.usuario import Usuario
from app.models.veiculo import Veiculo
from app.services.auth_service import AuthService
from app.services.configuracao_service import ConfiguracaoService, remover_logo_se_orfa


log = logging.getLogger(__name__)

# Limites das colunas em escritorios (String(50) / String(200)). No Postgres,
# passar disso estoura DataError; aqui vira mensagem amigável.
_MAX_SLUG = 50
_MAX_NOME = 200


def normalizar_slug(texto: str) -> str:
    """'Despachante do Zé' -> 'despachante-do-ze'."""
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-")


class EscritorioService:
    def __init__(self, session: Session) -> None:
        self._s = session

    def listar(self) -> list[Escritorio]:
        return self._s.query(Escritorio).order_by(Escritorio.criado_em.desc()).all()

    def obter(self, escritorio_id: int) -> Optional[Escritorio]:
        return self._s.get(Escritorio, escritorio_id)

    def criar(self, nome: str, slug: Optional[str] = None) -> tuple[Optional[Escritorio], str]:
        nome = (nome or "").strip()
        if not nome:
            return None, "Nome é obrigatório."

        slug = normalizar_slug(slug or nome)
        if not slug:
            return None, "Não foi possível gerar um identificador de URL válido a partir do nome."
        if len(nome) > _MAX_NOME or len(slug) > _MAX_SLUG:
            return None, f"Nome (até {_MAX_NOME}) ou identificador (até {_MAX_SLUG}) muito longo."
        if self._s.query(Escritorio).filter_by(slug=slug).first():
            return None, f"Já existe um escritório com o identificador '{slug}'."

        escritorio = Escritorio(slug=slug, nome=nome, ativo=True)
        self._s.add(escritorio)
        self._s.commit()

        # Semeia o que o escritório precisa pra já nascer funcional: valores
        # padrão de configuração (tema, etc.) e o usuário admin inicial —
        # mesma lógica usada no bootstrap do escritório "principal"
        # (wsgi.py), reaproveitada aqui pra um escritório novo.
        ConfiguracaoService(self._s, escritorio.id).seed_defaults()
        AuthService(self._s).seed_admin(escritorio.id)

        return escritorio, ""

    def toggle_ativo(self, escritorio_id: int) -> tuple[bool, str]:
        escritorio = self.obter(escritorio_id)
        if not escritorio:
            return False, "Escritório não encontrado."
        escritorio.ativo = not escritorio.ativo
        self._s.commit()
        return True, ""

    def editar(self, escritorio_id: int, nome: str, slug: str) -> tuple[bool, str]:
        """
        Altera nome e identificador de URL. Mudar o identificador muda o link
        de login (/e/<slug>/login): links salvos com o valor antigo deixam de
        funcionar. Sessões já abertas continuam valendo (a sessão guarda o
        id do usuário, não o slug).
        """
        escritorio = self.obter(escritorio_id)
        if not escritorio:
            return False, "Escritório não encontrado."

        nome = (nome or "").strip()
        if not nome:
            return False, "Nome é obrigatório."
        slug = normalizar_slug(slug or "")
        if not slug:
            return False, "Identificador de URL inválido (use letras, números e hífen)."
        if len(nome) > _MAX_NOME or len(slug) > _MAX_SLUG:
            return False, f"Nome (até {_MAX_NOME}) ou identificador (até {_MAX_SLUG}) muito longo."

        outro = (
            self._s.query(Escritorio)
            .filter(Escritorio.slug == slug, Escritorio.id != escritorio_id)
            .first()
        )
        if outro:
            return False, f"Já existe um escritório com o identificador '{slug}'."

        escritorio.nome = nome
        escritorio.slug = slug
        try:
            self._s.commit()
        except IntegrityError:  # corrida: outro pedido pegou o slug entre a checagem e o commit
            self._s.rollback()
            return False, f"Já existe um escritório com o identificador '{slug}'."
        return True, ""

    def excluir_definitivamente(
        self, escritorio_id: int, upload_dir: str, logo_dir: str
    ) -> tuple[bool, str, dict]:
        """
        Apaga o escritório e TODOS os dados dele: usuários, clientes,
        veículos, IPVA, licenciamento, multas, pendências, documentos, regras,
        templates, configurações e o log de auditoria. Não há como desfazer.

        Tudo no banco acontece em UMA transação: se algo falhar, nada é
        apagado. Os arquivos em disco só são removidos depois do commit, e
        só os que nenhum outro escritório referencia (a logo, por exemplo, é
        gravada como `logo.<ext>` — nome igual para todos os escritórios).

        Recusa apagar o último escritório existente: o start-up recriaria um
        "principal" vazio, e ficar sem nenhum deixaria o sistema inacessível.

        Retorna (ok, mensagem_de_erro, contagens_apagadas).
        """
        escritorio = self.obter(escritorio_id)
        if not escritorio:
            return False, "Escritório não encontrado.", {}
        if self._s.query(Escritorio).count() <= 1:
            return False, "Não é possível excluir o único escritório existente.", {}

        slug, nome = escritorio.slug, escritorio.nome
        s = self._s

        ids_clientes = select(Cliente.id).where(Cliente.escritorio_id == escritorio_id)
        ids_veiculos = select(Veiculo.id).where(Veiculo.escritorio_id == escritorio_id)
        ids_usuarios = select(Usuario.id).where(Usuario.escritorio_id == escritorio_id)
        ids_ipva = select(Ipva.id).where(Ipva.veiculo_id.in_(ids_veiculos))

        try:
            # Nomes de arquivo coletados ANTES de apagar as linhas.
            docs = [
                a for (a,) in s.execute(
                    select(Documento.arquivo).where(
                        Documento.cliente_id.in_(ids_clientes), Documento.arquivo.isnot(None)
                    )
                )
            ]
            logo = s.execute(
                select(Configuracao.valor).where(
                    Configuracao.escritorio_id == escritorio_id,
                    Configuracao.chave == "escritorio_logo",
                )
            ).scalar()

            # Ordem: filhos antes dos pais (respeita as FKs nos dois bancos).
            passos = [
                ("pendencias_contato", delete(ContatoPendencia).where(
                    ContatoPendencia.cliente_id.in_(ids_clientes)
                    | ContatoPendencia.veiculo_id.in_(ids_veiculos)
                    | ContatoPendencia.marcado_por_id.in_(ids_usuarios))),
                ("ipva_parcelas", delete(IpvaParcela).where(IpvaParcela.ipva_id.in_(ids_ipva))),
                ("ipva", delete(Ipva).where(Ipva.veiculo_id.in_(ids_veiculos))),
                ("licenciamentos", delete(Licenciamento).where(Licenciamento.veiculo_id.in_(ids_veiculos))),
                ("multas", delete(Multa).where(Multa.veiculo_id.in_(ids_veiculos))),
                ("documentos", delete(Documento).where(Documento.cliente_id.in_(ids_clientes))),
                ("veiculos", delete(Veiculo).where(Veiculo.escritorio_id == escritorio_id)),
                ("clientes", delete(Cliente).where(Cliente.escritorio_id == escritorio_id)),
                ("log", delete(LogAcao).where(LogAcao.escritorio_id == escritorio_id)),
                ("permissoes", delete(PermissaoUsuario).where(PermissaoUsuario.usuario_id.in_(ids_usuarios))),
                ("usuarios", delete(Usuario).where(Usuario.escritorio_id == escritorio_id)),
                ("regras_vencimento", delete(RegraVencimento).where(RegraVencimento.escritorio_id == escritorio_id)),
                ("templates_relatorio", delete(TemplateRelatorio).where(TemplateRelatorio.escritorio_id == escritorio_id)),
                ("configuracoes", delete(Configuracao).where(Configuracao.escritorio_id == escritorio_id)),
                ("escritorio", delete(Escritorio).where(Escritorio.id == escritorio_id)),
            ]
            contagens = {}
            for rotulo, stmt in passos:
                contagens[rotulo] = s.execute(stmt).rowcount
            s.commit()
        except Exception:
            s.rollback()
            log.exception("Falha ao excluir escritório id=%s slug=%s — nada foi apagado", escritorio_id, slug)
            return False, "Erro ao excluir. Nada foi apagado — veja o log do servidor.", {}

        s.expire_all()
        log.warning(
            "ESCRITÓRIO EXCLUÍDO id=%s slug=%s nome=%r apagado=%s",
            escritorio_id, slug, nome, contagens,
        )

        # Arquivos em disco — falha aqui não desfaz nada (o banco já está certo).
        for arquivo in docs:
            self._remover_arquivo_orfao(upload_dir, arquivo, Documento.arquivo)
        if logo:
            remover_logo_se_orfa(self._s, logo_dir, logo)
        return True, "", contagens

    def _remover_arquivo_orfao(self, pasta, nome, coluna) -> None:
        """Remove o documento do disco só se nenhuma outra linha ainda o referencia."""
        if not nome or os.path.basename(nome) != nome:  # nunca sai da pasta
            return
        if self._s.query(Documento).filter(coluna == nome).first():
            return
        try:
            caminho = os.path.join(pasta, nome)
            if os.path.exists(caminho):
                os.remove(caminho)
        except OSError:
            log.warning("Não foi possível remover o arquivo %s", nome)
