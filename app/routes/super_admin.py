"""
Tela de gerenciamento de escritórios (tenants) — fora do login normal de
propósito, já que criar um escritório é uma ação de quem é DONO do sistema
(Kauã), não de nenhum escritório em si. Ver app/services/escritorio_service.py
e config.py:SUPER_ADMIN_TOKEN pro raciocínio completo.
"""
import functools

from flask import Blueprint, render_template, request, redirect, url_for, session, abort, current_app, flash

from app import db
from app.services.escritorio_service import EscritorioService

bp = Blueprint("super_admin", __name__, url_prefix="/super-admin")

_SESSION_KEY = "super_admin_ok"


def _token_configurado() -> str | None:
    return current_app.config.get("SUPER_ADMIN_TOKEN")


def requer_super_admin(view):
    """
    Sem token configurado nesta instalação, a tela inteira não existe —
    404, não 403, pra não nem revelar que essa área existe numa instalação
    de escritório cliente (só a instalação que o dono do sistema controla
    deve ter SUPER_ADMIN_TOKEN definida).
    """
    @functools.wraps(view)
    def decorado(*args, **kwargs):
        if not _token_configurado():
            abort(404)
        if not session.get(_SESSION_KEY):
            return redirect(url_for("super_admin.entrar"))
        return view(*args, **kwargs)
    return decorado


@bp.route("/", methods=["GET", "POST"])
def entrar():
    if not _token_configurado():
        abort(404)
    if session.get(_SESSION_KEY):
        return redirect(url_for("super_admin.escritorios"))

    erro = None
    if request.method == "POST":
        token = request.form.get("token", "")
        # Comparação simples — este token não é uma senha de usuário
        # (não há tentativas/bloqueio aqui), é um segredo de operador único
        # que só Kauã tem, guardado como variável de ambiente.
        if token and token == _token_configurado():
            session[_SESSION_KEY] = True
            return redirect(url_for("super_admin.escritorios"))
        erro = "Token inválido."

    return render_template("super_admin/entrar.html", erro=erro)


@bp.route("/sair")
def sair():
    session.pop(_SESSION_KEY, None)
    return redirect(url_for("super_admin.entrar"))


@bp.route("/escritorios", methods=["GET", "POST"])
@requer_super_admin
def escritorios():
    svc = EscritorioService(db.session)

    credenciais_criadas = None
    erro = None
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        slug_informado = request.form.get("slug", "").strip()
        escritorio, msg = svc.criar(nome, slug_informado or None)
        if not escritorio:
            erro = msg
        else:
            flash(f"Escritório '{escritorio.nome}' criado com sucesso.")
            # Credenciais iniciais — mesmas do bootstrap de qualquer
            # escritório novo (ver AuthService.seed_admin): usuário "admin",
            # senha temporária "admin123", troca obrigatória no 1º login.
            credenciais_criadas = {
                "nome": escritorio.nome,
                "slug": escritorio.slug,
                "url_login": url_for("auth.login_escritorio", slug=escritorio.slug, _external=True),
                "usuario": "admin",
                "senha": "admin123",
            }

    return render_template(
        "super_admin/escritorios.html",
        escritorios=svc.listar(),
        erro=erro,
        credenciais_criadas=credenciais_criadas,
    )


@bp.route("/escritorios/<int:escritorio_id>/toggle-ativo", methods=["POST"])
@requer_super_admin
def toggle_ativo(escritorio_id):
    ok, msg = EscritorioService(db.session).toggle_ativo(escritorio_id)
    if not ok:
        flash(msg)
    return redirect(url_for("super_admin.escritorios"))
