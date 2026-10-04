"""
Tela de gerenciamento de escritórios (tenants) — fora do login normal de
propósito, já que criar um escritório é uma ação de quem é DONO do sistema
(Kauã), não de nenhum escritório em si. Ver app/services/escritorio_service.py
e config.py:SUPER_ADMIN_TOKEN pro raciocínio completo.
"""
import functools
import hmac

from flask import Blueprint, render_template, request, redirect, url_for, session, abort, current_app, flash

from app import db
from app.services.escritorio_service import EscritorioService

bp = Blueprint("super_admin", __name__, url_prefix="/super-admin")

_SESSION_KEY = "super_admin_ok"


def _token_configurado() -> str | None:
    return current_app.config.get("SUPER_ADMIN_TOKEN")


def _token_exclusao_configurado() -> str | None:
    return current_app.config.get("SUPER_ADMIN_DELETE_TOKEN")


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
        exclusao_habilitada=bool(_token_exclusao_configurado()),
    )


@bp.route("/escritorios/<int:escritorio_id>/toggle-ativo", methods=["POST"])
@requer_super_admin
def toggle_ativo(escritorio_id):
    ok, msg = EscritorioService(db.session).toggle_ativo(escritorio_id)
    if not ok:
        flash(msg)
    return redirect(url_for("super_admin.escritorios"))


@bp.route("/escritorios/<int:escritorio_id>/editar", methods=["POST"])
@requer_super_admin
def editar(escritorio_id):
    ok, msg = EscritorioService(db.session).editar(
        escritorio_id,
        request.form.get("nome", ""),
        request.form.get("slug", ""),
    )
    flash("Escritório atualizado." if ok else msg)
    return redirect(url_for("super_admin.escritorios"))


@bp.route("/escritorios/<int:escritorio_id>/excluir", methods=["POST"])
@requer_super_admin
def excluir(escritorio_id):
    """
    Exclusão DEFINITIVA. Exige, além da sessão de super admin: (1) o segundo
    token (SUPER_ADMIN_DELETE_TOKEN) e (2) digitar o identificador do
    escritório, pra não apagar a linha errada por engano.
    """
    token_ok = _token_exclusao_configurado()
    if not token_ok:
        flash("Exclusão desativada: defina SUPER_ADMIN_DELETE_TOKEN no servidor.")
        return redirect(url_for("super_admin.escritorios"))

    svc = EscritorioService(db.session)
    escritorio = svc.obter(escritorio_id)
    if not escritorio:
        flash("Escritório não encontrado.")
        return redirect(url_for("super_admin.escritorios"))

    token_informado = request.form.get("token_exclusao", "")
    if not token_informado or not hmac.compare_digest(
        token_informado.encode("utf-8"), token_ok.encode("utf-8")
    ):
        flash("Token de exclusão inválido. Nada foi apagado.")
        return redirect(url_for("super_admin.escritorios"))

    if request.form.get("confirmar_slug", "").strip() != escritorio.slug:
        flash("O identificador digitado não confere. Nada foi apagado.")
        return redirect(url_for("super_admin.escritorios"))

    nome = escritorio.nome
    ok, msg, contagens = svc.excluir_definitivamente(
        escritorio_id,
        upload_dir=current_app.config["UPLOAD_DIR"],
        logo_dir=current_app.config["LOGO_DIR"],
    )
    if ok:
        flash(
            f"Escritório '{nome}' excluído em definitivo "
            f"({contagens.get('clientes', 0)} clientes, "
            f"{contagens.get('veiculos', 0)} veículos, "
            f"{contagens.get('usuarios', 0)} usuários)."
        )
    else:
        flash(msg)
    return redirect(url_for("super_admin.escritorios"))
