"""
Gerenciamento de escritórios (tenants).

Diferente de todo outro service deste projeto, este NÃO herda de
TenantService — ele opera ACIMA dos escritórios (cria, lista, ativa/
desativa), não dentro de um. É por isso que só é acessível pela tela
/super-admin, protegida por um segredo à parte do login normal (ver
app/routes/super_admin.py e config.py:SUPER_ADMIN_TOKEN).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session

from app.models.escritorio import Escritorio
from app.services.auth_service import AuthService
from app.services.configuracao_service import ConfiguracaoService


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
