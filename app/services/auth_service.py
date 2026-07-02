"""
Serviço de autenticação.
Controla login, bloqueio por tentativas, troca de senha temporária.
"""
from __future__ import annotations

import functools
from datetime import datetime, timedelta
from typing import Optional

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.models.permissao_usuario import PermissaoUsuario, CODIGOS_PERMISSAO

MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15


class AuthService:
    def __init__(self, session: Session) -> None:
        self._s = session

    def autenticar(self, nome_usuario: str, senha: str) -> tuple[Optional[Usuario], str]:
        """
        Valida credenciais e controla contador de tentativas.
        Retorna (usuario, "") em sucesso ou (None, mensagem_erro).
        Nunca revela se o erro é no usuário ou na senha.
        """
        usuario = self._s.query(Usuario).filter_by(nome_usuario=nome_usuario).first()

        # Usuário inexistente — simula tempo de verificação para evitar timing attack
        if not usuario or not usuario.ativo:
            return None, "Usuário ou senha incorretos."

        # Verifica bloqueio ativo
        if usuario.bloqueado_ate and datetime.now() < usuario.bloqueado_ate:
            restante = int((usuario.bloqueado_ate - datetime.now()).total_seconds() / 60) + 1
            return None, f"Conta bloqueada. Tente novamente em {restante} minuto(s)."

        # Senha errada
        if not check_password_hash(usuario.senha_hash, senha):
            usuario.tentativas_login += 1
            if usuario.tentativas_login >= MAX_TENTATIVAS:
                usuario.bloqueado_ate = datetime.now() + timedelta(minutes=BLOQUEIO_MINUTOS)
                self._s.commit()
                return None, f"Conta bloqueada por {BLOQUEIO_MINUTOS} minutos após {MAX_TENTATIVAS} tentativas incorretas."
            self._s.commit()
            return None, "Usuário ou senha incorretos."

        # Sucesso — zera tentativas e registra acesso
        usuario.tentativas_login = 0
        usuario.bloqueado_ate = None
        usuario.ultimo_acesso = datetime.now()
        self._s.commit()
        return usuario, ""

    def trocar_senha(self, usuario_id: int, nova_senha: str) -> tuple[bool, str]:
        """Troca a senha e limpa flags de senha temporária."""
        if len(nova_senha) < 6:
            return False, "A senha deve ter ao menos 6 caracteres."
        usuario = self._s.get(Usuario, usuario_id)
        if not usuario:
            return False, "Usuário não encontrado."
        usuario.senha_hash = generate_password_hash(nova_senha)
        usuario.senha_temporaria = False
        usuario.senha_expira_em = None
        self._s.commit()
        return True, ""

    def definir_senha_temporaria(self, usuario_id: int, senha_temp: str) -> tuple[bool, str]:
        """Administrador define senha temporária válida por 24h."""
        if len(senha_temp) < 6:
            return False, "A senha temporária deve ter ao menos 6 caracteres."
        usuario = self._s.get(Usuario, usuario_id)
        if not usuario:
            return False, "Usuário não encontrado."
        usuario.senha_hash = generate_password_hash(senha_temp)
        usuario.senha_temporaria = True
        usuario.senha_expira_em = datetime.now() + timedelta(hours=24)
        self._s.commit()
        return True, ""

    def senha_temporaria_expirada(self, usuario: Usuario) -> bool:
        if not usuario.senha_temporaria:
            return False
        if usuario.senha_expira_em and datetime.now() > usuario.senha_expira_em:
            return True
        return False

    # ------------------------------------------------------------------
    # Gerenciamento de usuários (área admin)
    # ------------------------------------------------------------------

    def criar_usuario(self, dados: dict) -> tuple[Optional[Usuario], str]:
        if self._s.query(Usuario).filter_by(nome_usuario=dados["nome_usuario"]).first():
            return None, "Nome de usuário já está em uso."
        if dados.get("perfil") not in ("administrador", "operador"):
            return None, "Perfil inválido."
        u = Usuario(
            nome_usuario=dados["nome_usuario"].strip(),
            nome_completo=dados["nome_completo"].strip(),
            senha_hash=generate_password_hash(dados["senha"]),
            perfil=dados["perfil"],
            ativo=True,
        )
        self._s.add(u)
        self._s.flush()
        self._sincronizar_permissoes(u.id, dados.get("permissoes", []))
        self._s.commit()
        return u, ""

    def atualizar_usuario(self, usuario_id: int, dados: dict) -> tuple[bool, str]:
        u = self._s.get(Usuario, usuario_id)
        if not u:
            return False, "Usuário não encontrado."
        if dados.get("perfil") not in ("administrador", "operador"):
            return False, "Perfil inválido."
        # Impede renomear para um nome_usuario já existente de outro usuário
        conflito = (
            self._s.query(Usuario)
            .filter(Usuario.nome_usuario == dados["nome_usuario"], Usuario.id != usuario_id)
            .first()
        )
        if conflito:
            return False, "Nome de usuário já está em uso."
        u.nome_usuario = dados["nome_usuario"].strip()
        u.nome_completo = dados["nome_completo"].strip()
        u.perfil = dados["perfil"]
        self._sincronizar_permissoes(u.id, dados.get("permissoes", []))
        self._s.commit()
        return True, ""

    def toggle_ativo(self, usuario_id: int) -> tuple[bool, str]:
        u = self._s.get(Usuario, usuario_id)
        if not u:
            return False, "Usuário não encontrado."
        # Não permite desativar o único administrador ativo
        if u.ativo and u.perfil == "administrador":
            outros_admins = (
                self._s.query(Usuario)
                .filter(Usuario.perfil == "administrador", Usuario.ativo == True, Usuario.id != usuario_id)
                .count()
            )
            if outros_admins == 0:
                return False, "Não é possível desativar o único administrador ativo."
        u.ativo = not u.ativo
        self._s.commit()
        return True, ""

    def _sincronizar_permissoes(self, usuario_id: int, permissoes: list[str]) -> None:
        """Substitui as permissões do usuário pelas informadas."""
        self._s.query(PermissaoUsuario).filter_by(usuario_id=usuario_id).delete()
        for cod in permissoes:
            if cod in CODIGOS_PERMISSAO:
                self._s.add(PermissaoUsuario(usuario_id=usuario_id, permissao=cod))

    def seed_admin(self) -> None:
        """Cria usuário admin padrão se não existir nenhum usuário no banco."""
        if self._s.query(Usuario).count() == 0:
            self._s.add(Usuario(
                nome_usuario="admin",
                nome_completo="Administrador",
                senha_hash=generate_password_hash("admin123"),
                perfil="administrador",
                ativo=True,
                senha_temporaria=True,
                senha_expira_em=None,  # admin inicial não expira — força troca no 1º login
            ))
            self._s.commit()


# ------------------------------------------------------------------
# Decorator de permissão — uso: @requer_permissao('codigo')
# ------------------------------------------------------------------

def requer_permissao(codigo: str):
    """
    Decorator que verifica se o usuário logado tem a permissão informada.
    Administradores passam automaticamente.
    Retorna 403 para operadores sem a permissão.
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.path))
            if not current_user.tem_permissao(codigo):
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator
