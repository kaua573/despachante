from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app import db
from app.services.auth_service import AuthService
from app.services.log_service import LogService
from app.models.usuario import Usuario
from app.models.permissao_usuario import PERMISSOES_DISPONIVEIS

bp = Blueprint("admin", __name__)


def _somente_admin():
    if not current_user.is_authenticated or current_user.perfil != "administrador":
        abort(403)


# ── Usuários ─────────────────────────────────────────────────────────────────

@bp.route("/admin/usuarios")
@login_required
def usuarios():
    _somente_admin()
    lista = db.session.query(Usuario).order_by(Usuario.nome_completo).all()
    return render_template("admin/usuarios.html", usuarios=lista)


@bp.route("/admin/usuarios/novo", methods=["GET", "POST"])
@login_required
def novo_usuario():
    _somente_admin()
    erro = None
    if request.method == "POST":
        dados = {
            "nome_usuario":  request.form.get("nome_usuario", "").strip(),
            "nome_completo": request.form.get("nome_completo", "").strip(),
            "senha":         request.form.get("senha", ""),
            "perfil":        request.form.get("perfil", ""),
            "permissoes":    request.form.getlist("permissoes"),
        }
        usuario, msg = AuthService(db.session).criar_usuario(dados)
        if not usuario:
            erro = msg
        else:
            LogService(db.session).registrar("criar_usuario", "usuario", usuario.id, {"nome": usuario.nome_usuario})
            flash(f"Usuário '{usuario.nome_completo}' criado com sucesso.")
            return redirect(url_for("admin.usuarios"))

    return render_template("admin/form_usuario.html", usuario=None, permissoes=PERMISSOES_DISPONIVEIS, erro=erro)


@bp.route("/admin/usuarios/<int:uid>/editar", methods=["GET", "POST"])
@login_required
def editar_usuario(uid):
    _somente_admin()
    usuario = db.session.get(Usuario, uid)
    if not usuario:
        abort(404)

    erro = None
    if request.method == "POST":
        dados = {
            "nome_usuario":  request.form.get("nome_usuario", "").strip(),
            "nome_completo": request.form.get("nome_completo", "").strip(),
            "perfil":        request.form.get("perfil", ""),
            "permissoes":    request.form.getlist("permissoes"),
        }
        ok, msg = AuthService(db.session).atualizar_usuario(uid, dados)
        if not ok:
            erro = msg
        else:
            LogService(db.session).registrar("editar_usuario", "usuario", uid, {"nome": dados["nome_usuario"]})
            flash("Usuário atualizado.")
            return redirect(url_for("admin.usuarios"))

    permissoes_atuais = {p.permissao for p in usuario.permissoes}
    return render_template(
        "admin/form_usuario.html",
        usuario=usuario,
        permissoes=PERMISSOES_DISPONIVEIS,
        permissoes_atuais=permissoes_atuais,
        erro=erro,
    )


@bp.route("/admin/usuarios/<int:uid>/redefinir-senha", methods=["POST"])
@login_required
def redefinir_senha(uid):
    _somente_admin()
    senha_temp = request.form.get("senha_temp", "").strip()
    ok, msg = AuthService(db.session).definir_senha_temporaria(uid, senha_temp)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    LogService(db.session).registrar("redefinir_senha", "usuario", uid)
    return jsonify({"ok": True})


@bp.route("/admin/usuarios/<int:uid>/toggle-ativo", methods=["POST"])
@login_required
def toggle_ativo(uid):
    _somente_admin()
    ok, msg = AuthService(db.session).toggle_ativo(uid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    LogService(db.session).registrar("toggle_ativo_usuario", "usuario", uid)
    return jsonify({"ok": True})


# ── Log de ações ──────────────────────────────────────────────────────────────

@bp.route("/admin/log")
@login_required
def log_acoes():
    _somente_admin()
    pagina      = int(request.args.get("pagina", 1))
    usuario_id  = request.args.get("usuario_id") or None
    acao        = request.args.get("acao", "").strip() or None
    data_inicio = request.args.get("data_inicio", "").strip() or None
    data_fim    = request.args.get("data_fim", "").strip() or None

    resultado = LogService(db.session).listar(
        usuario_id=int(usuario_id) if usuario_id else None,
        acao=acao,
        data_inicio=data_inicio,
        data_fim=data_fim,
        pagina=pagina,
    )
    usuarios = db.session.query(Usuario).order_by(Usuario.nome_completo).all()
    return render_template("admin/log.html", **resultado, usuarios=usuarios,
                           filtros={"usuario_id": usuario_id, "acao": acao,
                                    "data_inicio": data_inicio, "data_fim": data_fim})
