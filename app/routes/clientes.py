from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from app import db
from app.services.cliente_service import ClienteService
from app.services.pdf_cliente_service import PdfClienteService
from app.services.validacao_service import (
    validar_campos_cliente, normalizar_cpf, normalizar_telefone,
)

bp = Blueprint("clientes", __name__)


def _svc() -> ClienteService:
    return ClienteService(db.session, current_app.config["UPLOAD_DIR"])


# ── Páginas ──────────────────────────────────────────────────────────────────

@bp.route("/clientes")
def clientes():
    return render_template("clientes.html")


# ── API — Clientes ───────────────────────────────────────────────────────────

@bp.route("/api/clientes", methods=["GET"])
def api_listar_clientes():
    busca = request.args.get("busca", "").strip()
    clientes = _svc().listar(busca)
    return jsonify([c.to_dict() for c in clientes])


@bp.route("/api/clientes/<int:cid>", methods=["GET"])
def api_obter_cliente(cid):
    c = _svc().obter(cid)
    if not c:
        return jsonify({"erro": "Não encontrado."}), 404
    return jsonify(c.to_dict())


@bp.route("/api/clientes", methods=["POST"])
def api_criar_cliente():
    dados = request.get_json(silent=True) or {}
    erro = validar_campos_cliente(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    _normalizar_cliente(dados)
    _svc().criar(dados)
    return jsonify({"ok": True})


@bp.route("/api/clientes/<int:cid>", methods=["PUT"])
def api_editar_cliente(cid):
    dados = request.get_json(silent=True) or {}
    erro = validar_campos_cliente(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    _normalizar_cliente(dados)
    ok, msg = _svc().atualizar(cid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


@bp.route("/api/clientes/<int:cid>", methods=["DELETE"])
def api_deletar_cliente(cid):
    ok, msg = _svc().excluir(cid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── API — Documentos ─────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/documentos", methods=["GET"])
def api_listar_documentos(cid):
    docs = _svc().listar_documentos(cid)
    return jsonify([d.to_dict() for d in docs])


@bp.route("/api/documentos", methods=["POST"])
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
    return jsonify({"ok": True})


@bp.route("/api/documentos/<int:did>", methods=["DELETE"])
def api_deletar_documento(did):
    ok, msg = _svc().excluir_documento(did)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── PDF do cliente ───────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/relatorio")
def relatorio_cliente_pdf(cid):
    incluir = request.args.getlist("incluir")
    svc = PdfClienteService(db.session, current_app.config["LOGO_DIR"])
    pdf_bytes, resultado = svc.gerar(cid, incluir)
    if pdf_bytes is None:
        return resultado, 404
    import io
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=resultado,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalizar_cliente(dados: dict) -> None:
    """
    Normaliza CPF e telefone para armazenamento sem máscara.
    Modifica o dict in-place antes de persistir.
    """
    if dados.get("cpf"):
        dados["cpf"] = normalizar_cpf(dados["cpf"])
    if dados.get("telefone"):
        dados["telefone"] = normalizar_telefone(dados["telefone"])
