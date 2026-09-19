from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort, Response
from flask_login import login_required, current_user
from datetime import datetime

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
            depois = usuario.to_dict()
            depois["permissoes"] = sorted(p.permissao for p in usuario.permissoes)
            LogService(db.session).registrar_alteracao("criar_usuario", "usuario", usuario.id, None, depois)
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
        antes = usuario.to_dict()
        antes["permissoes"] = sorted(p.permissao for p in usuario.permissoes)

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
            db.session.refresh(usuario)
            depois = usuario.to_dict()
            depois["permissoes"] = sorted(p.permissao for p in usuario.permissoes)
            LogService(db.session).registrar_alteracao("editar_usuario", "usuario", uid, antes, depois)
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
    from app.models.log_acao import LogAcao

    pagina      = int(request.args.get("pagina", 1))
    usuario_id  = request.args.get("usuario_id") or None
    acao        = request.args.get("acao", "").strip() or None
    entidade    = request.args.get("entidade", "").strip() or None
    data_inicio = request.args.get("data_inicio", "").strip() or None
    data_fim    = request.args.get("data_fim", "").strip() or None

    resultado = LogService(db.session).listar(
        usuario_id=int(usuario_id) if usuario_id else None,
        acao=acao,
        entidade=entidade,
        data_inicio=data_inicio,
        data_fim=data_fim,
        pagina=pagina,
    )
    usuarios = db.session.query(Usuario).order_by(Usuario.nome_completo).all()
    entidades = [
        r[0] for r in
        db.session.query(LogAcao.entidade).filter(LogAcao.entidade.isnot(None)).distinct().order_by(LogAcao.entidade)
    ]
    return render_template("admin/log.html", **resultado, usuarios=usuarios, entidades=entidades,
                           filtros={"usuario_id": usuario_id, "acao": acao, "entidade": entidade,
                                    "data_inicio": data_inicio, "data_fim": data_fim})


@bp.route("/admin/log/verificar-integridade")
@login_required
def log_verificar_integridade():
    """Confere a corrente de hashes do log de ações — ver
    LogService.verificar_integridade() para a explicação completa."""
    _somente_admin()
    resultado = LogService(db.session).verificar_integridade()
    LogService(db.session).registrar("verificar_integridade_log", detalhe={"integro": resultado["integro"]})
    return jsonify(resultado)


@bp.route("/admin/log/exportar")
@login_required
def log_exportar():
    """Exporta pra CSV os mesmos registros filtrados na tela — pra auditoria
    externa ou pra guardar fora do sistema."""
    _somente_admin()
    import csv
    import io

    usuario_id  = request.args.get("usuario_id") or None
    acao        = request.args.get("acao", "").strip() or None
    entidade    = request.args.get("entidade", "").strip() or None
    data_inicio = request.args.get("data_inicio", "").strip() or None
    data_fim    = request.args.get("data_fim", "").strip() or None

    resultado = LogService(db.session).listar(
        usuario_id=int(usuario_id) if usuario_id else None,
        acao=acao, entidade=entidade, data_inicio=data_inicio, data_fim=data_fim,
        pagina=1, por_pagina=100000,
    )

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";")
    escritor.writerow(["Data/Hora", "Usuário", "Ação", "Entidade", "ID entidade", "Detalhe", "IP"])
    for r in resultado["registros"]:
        escritor.writerow([
            r.criado_em.strftime("%d/%m/%Y %H:%M:%S"),
            r.usuario.nome_completo if r.usuario else (r.usuario_nome or "—"),
            r.acao,
            r.entidade or "",
            r.entidade_id or "",
            r.detalhe or "",
            r.ip or "",
        ])

    LogService(db.session).registrar("exportar_log", detalhe={"quantidade": len(resultado["registros"])})

    nome_arquivo = f"log_acoes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        "\ufeff" + buffer.getvalue(),  # BOM — Excel abre acentuação certa
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"},
    )
