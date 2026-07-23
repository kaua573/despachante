from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required
from app import db
from app.services.auth_service import requer_permissao
from app.services.cliente_service import ClienteService
from app.services.log_service import LogService
from app.services.pdf_cliente_service import PdfClienteService
from app.services.validacao_service import (
    validar_campos_cliente, normalizar_cpf, normalizar_telefone,
)

bp = Blueprint("clientes", __name__)


def _svc() -> ClienteService:
    return ClienteService(db.session, current_app.config["UPLOAD_DIR"])


def _log() -> LogService:
    return LogService(db.session)


# ── Páginas ──────────────────────────────────────────────────────────────────

@bp.route("/clientes")
@login_required
@requer_permissao("visualizar_clientes")
def clientes():
    return render_template("clientes.html")


# ── API — Clientes ───────────────────────────────────────────────────────────

@bp.route("/api/clientes", methods=["GET"])
@login_required
@requer_permissao("visualizar_clientes")
def api_listar_clientes():
    busca = request.args.get("busca", "").strip()
    return jsonify([c.to_dict() for c in _svc().listar(busca)])


@bp.route("/api/clientes/<int:cid>", methods=["GET"])
@login_required
@requer_permissao("visualizar_clientes")
def api_obter_cliente(cid):
    c = _svc().obter(cid)
    if not c:
        return jsonify({"erro": "Não encontrado."}), 404
    return jsonify(c.to_dict())


@bp.route("/api/clientes", methods=["POST"])
@login_required
@requer_permissao("gerenciar_clientes")
def api_criar_cliente():
    dados = request.get_json(silent=True) or {}
    erro = validar_campos_cliente(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    _normalizar_cliente(dados)
    cliente, erro = _svc().criar(dados)
    if not cliente:
        return jsonify({"ok": False, "erro": erro}), 400
    _log().registrar("criar_cliente", "cliente", cliente.id, {"nome": cliente.nome})
    return jsonify({"ok": True})


@bp.route("/api/clientes/<int:cid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_clientes")
def api_editar_cliente(cid):
    dados = request.get_json(silent=True) or {}
    erro = validar_campos_cliente(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    _normalizar_cliente(dados)
    ok, msg = _svc().atualizar(cid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("editar_cliente", "cliente", cid, {"nome": dados.get("nome")})
    return jsonify({"ok": True})


@bp.route("/api/clientes/<int:cid>", methods=["DELETE"])
@login_required
@requer_permissao("excluir_clientes")
def api_deletar_cliente(cid):
    ok, msg = _svc().excluir(cid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_cliente", "cliente", cid)
    return jsonify({"ok": True})


# ── API — Documentos ─────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/documentos", methods=["GET"])
@login_required
@requer_permissao("visualizar_clientes")
def api_listar_documentos(cid):
    return jsonify([d.to_dict() for d in _svc().listar_documentos(cid)])


@bp.route("/api/documentos", methods=["POST"])
@login_required
@requer_permissao("gerenciar_clientes")
def api_criar_documento():
    dados = {
        "nome":           request.form.get("nome", "").strip(),
        "data_documento": request.form.get("data_documento", "").strip(),
        "categoria":      request.form.get("categoria", "").strip(),
        "observacao":     request.form.get("observacao", "").strip(),
    }
    cliente_id = request.form.get("cliente_id")
    if not cliente_id or not dados["nome"] or not dados["data_documento"] or not dados["categoria"]:
        return jsonify({"ok": False, "erro": "Campos obrigatórios ausentes."}), 400

    arquivo = request.files.get("arquivo")
    ok, msg = _svc().criar_documento(
        int(cliente_id), dados, arquivo, current_app.config["EXTENSOES_DOCUMENTO"]
    )
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("criar_documento", "documento", int(cliente_id), {"nome": dados["nome"]})
    return jsonify({"ok": True})


@bp.route("/api/documentos/<int:did>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_clientes")
def api_deletar_documento(did):
    ok, msg = _svc().excluir_documento(did)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_documento", "documento", did)
    return jsonify({"ok": True})


# ── PDF do cliente ───────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/relatorio")
@login_required
@requer_permissao("gerar_relatorios")
def relatorio_cliente_pdf(cid):
    incluir = request.args.getlist("incluir")
    svc = PdfClienteService(db.session, current_app.config["LOGO_DIR"])
    pdf_bytes, resultado = svc.gerar(cid, incluir)
    if pdf_bytes is None:
        return resultado, 404
    import io
    _log().registrar("gerar_pdf_cliente", "cliente", cid, {"incluir": incluir})
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=resultado,
    )


# ── Importação / exportação em massa ────────────────────────────────────────

@bp.route("/api/clientes/exportar")
@login_required
@requer_permissao("visualizar_clientes")
def exportar_clientes():
    from app.services.importacao_service import ImportacaoService
    import io
    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    conteudo = svc.exportar()
    _log().registrar("exportar_clientes")
    return send_file(
        io.BytesIO(conteudo),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="clientes_e_veiculos.xlsx",
    )


@bp.route("/api/clientes/modelo-importacao")
@login_required
@requer_permissao("gerenciar_clientes")
def modelo_importacao_clientes():
    from app.services.importacao_service import ImportacaoService
    import io
    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    conteudo = svc.gerar_modelo()
    return send_file(
        io.BytesIO(conteudo),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="modelo_importacao_clientes.xlsx",
    )


@bp.route("/api/clientes/importar", methods=["POST"])
@login_required
@requer_permissao("gerenciar_clientes")
def importar_clientes():
    from app.services.importacao_service import ImportacaoService

    if "arquivo" not in request.files or not request.files["arquivo"].filename:
        return jsonify({"ok": False, "erro": "Nenhum arquivo enviado."}), 400

    arquivo = request.files["arquivo"]
    if not arquivo.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "erro": "Envie um arquivo .xlsx (use o modelo disponível para download)."}), 400

    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    resultado = svc.importar(arquivo.read())
    _log().registrar("importar_clientes", detalhe={
        "clientes_criados": resultado["clientes_criados"],
        "clientes_atualizados": resultado["clientes_atualizados"],
        "veiculos_criados": resultado["veiculos_criados"],
        "veiculos_atualizados": resultado["veiculos_atualizados"],
        "erros": len(resultado["erros"]),
    })
    return jsonify({"ok": True, **resultado})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalizar_cliente(dados: dict) -> None:
    if dados.get("cpf"):
        dados["cpf"] = normalizar_cpf(dados["cpf"])
    if dados.get("telefone"):
        dados["telefone"] = normalizar_telefone(dados["telefone"])
