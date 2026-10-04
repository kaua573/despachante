from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, abort
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime

from app import db
from app.models.escritorio import Escritorio
from app.services.auth_service import AuthService
from app.services.log_service import LogService

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET"])
def login():
    """
    Ponto de entrada sem saber ainda de qual escritório é o usuário.

    - Com um único escritório ativo (o caso de hoje): redireciona direto
      pra `/e/<slug>/login` sem o usuário perceber nada diferente.
    - Com mais de um: mostra uma lista simples pra escolher qual acessar.
    - Mantido como endpoint "auth.login" (sem argumento) de propósito —
      é o nome usado em `login_manager.login_view` e em todo `url_for`
      existente no projeto; mudar isso quebraria esses pontos.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    ativos = Escritorio.query.filter_by(ativo=True).order_by(Escritorio.nome).all()
    if len(ativos) == 1:
        return redirect(url_for("auth.login_escritorio", slug=ativos[0].slug, next=request.args.get("next")))
    return render_template("auth/escolher_escritorio.html", escritorios=ativos)


@bp.route("/e/<slug>/login", methods=["GET", "POST"])
def login_escritorio(slug):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    escritorio = Escritorio.query.filter_by(slug=slug, ativo=True).first()
    if not escritorio:
        abort(404)
    # Fixa o escritório desta request ANTES do login acontecer — é o que
    # permite autenticar() buscar o usuário já escopado (sem isso, dois
    # escritórios não poderiam ter o mesmo nome_usuario) e também faz o
    # tema/logo da própria tela de login já virem do escritório certo (ver
    # inject_tema em app/__init__.py).
    g.escritorio_id = escritorio.id

    erro = None
    if request.method == "POST":
        nome_usuario = request.form.get("nome_usuario", "").strip()
        senha = request.form.get("senha", "")

        svc = AuthService(db.session, escritorio.id)
        usuario, msg = svc.autenticar(nome_usuario, senha)

        if not usuario:
            erro = msg
        else:
            # Senha temporária expirada — trata como inválida
            if svc.senha_temporaria_expirada(usuario):
                erro = "Sua senha temporária expirou. Contate o administrador."
            else:
                login_user(usuario, remember=False)
                LogService(db.session, escritorio.id).registrar("login", detalhe={"nome_usuario": nome_usuario})

                # Força troca de senha no primeiro acesso com senha temporária
                if usuario.senha_temporaria:
                    return redirect(url_for("auth.trocar_senha_obrigatorio"))

                destino = request.args.get("next") or url_for("main.dashboard")
                # Segurança: só redireciona para URLs relativas
                if destino and not destino.startswith("/"):
                    destino = url_for("main.dashboard")
                return redirect(destino)

    return render_template("auth/login.html", erro=erro, escritorio=escritorio)


@bp.route("/logout")
@login_required
def logout():
    LogService(db.session, g.escritorio_id).registrar("logout")
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha_obrigatorio():
    """Exigido quando o usuário loga com senha temporária."""
    erro = None
    if request.method == "POST":
        nova = request.form.get("nova_senha", "")
        confirma = request.form.get("confirmar_senha", "")
        if nova != confirma:
            erro = "As senhas não conferem."
        else:
            ok, msg = AuthService(db.session).trocar_senha(current_user.id, nova)
            if not ok:
                erro = msg
            else:
                LogService(db.session, g.escritorio_id).registrar("trocar_senha", entidade="usuario", entidade_id=current_user.id)
                flash("Senha atualizada com sucesso!")
                return redirect(url_for("main.dashboard"))

    return render_template("auth/trocar_senha.html", erro=erro)
