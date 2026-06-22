from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from app import db
from app.models.cliente import Cliente
from app.services.veiculo_service import VeiculoService

bp = Blueprint("veiculos", __name__)


def _svc() -> VeiculoService:
    return VeiculoService(db.session)


# ── Páginas ──────────────────────────────────────────────────────────────────

@bp.route("/clientes/<int:cid>/veiculos")
def veiculos(cid):
    cliente = db.session.get(Cliente, cid)
    if not cliente:
        return redirect(url_for("clientes.clientes"))
    return render_template("veiculos.html", cliente=cliente.to_dict())


# ── API — Veículos ───────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/veiculos", methods=["GET"])
def api_listar_veiculos(cid):
    veics = _svc().listar_por_cliente(cid)
    return jsonify([v.to_dict() for v in veics])


@bp.route("/api/veiculos", methods=["POST"])
def api_criar_veiculo():
    dados = request.get_json(silent=True) or {}
    erro = _validar_veiculo(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    _svc().criar(dados)
    return jsonify({"ok": True})


@bp.route("/api/veiculos/<int:vid>", methods=["PUT"])
def api_editar_veiculo(vid):
    dados = request.get_json(silent=True) or {}
    erro = _validar_veiculo(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    ok, msg = _svc().atualizar(vid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


@bp.route("/api/veiculos/<int:vid>", methods=["DELETE"])
def api_deletar_veiculo(vid):
    ok, msg = _svc().excluir(vid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── API — IPVA ───────────────────────────────────────────────────────────────

@bp.route("/api/veiculos/<int:vid>/ipva", methods=["GET"])
def api_listar_ipva(vid):
    return jsonify([r.to_dict() for r in _svc().listar_ipva(vid)])


@bp.route("/api/ipva", methods=["POST"])
def api_criar_ipva():
    dados = request.get_json(silent=True) or {}
    if not dados.get("veiculo_id") or not dados.get("ano_referencia"):
        return jsonify({"ok": False, "erro": "veiculo_id e ano_referencia são obrigatórios."}), 400
    _svc().criar_ipva(dados)
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:iid>", methods=["PUT"])
def api_editar_ipva(iid):
    dados = request.get_json(silent=True) or {}
    ok, msg = _svc().atualizar_ipva(iid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:iid>", methods=["DELETE"])
def api_deletar_ipva(iid):
    ok, msg = _svc().excluir_ipva(iid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── API — Licenciamento ──────────────────────────────────────────────────────

@bp.route("/api/veiculos/<int:vid>/licenciamento", methods=["GET"])
def api_listar_licenciamento(vid):
    return jsonify([r.to_dict() for r in _svc().listar_licenciamento(vid)])


@bp.route("/api/licenciamento", methods=["POST"])
def api_criar_licenciamento():
    dados = request.get_json(silent=True) or {}
    if not dados.get("veiculo_id") or not dados.get("ano_referencia"):
        return jsonify({"ok": False, "erro": "veiculo_id e ano_referencia são obrigatórios."}), 400
    _svc().criar_licenciamento(dados)
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>", methods=["PUT"])
def api_editar_licenciamento(lid):
    dados = request.get_json(silent=True) or {}
    ok, msg = _svc().atualizar_licenciamento(lid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>", methods=["DELETE"])
def api_deletar_licenciamento(lid):
    ok, msg = _svc().excluir_licenciamento(lid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── API — Multas ─────────────────────────────────────────────────────────────

@bp.route("/api/veiculos/<int:vid>/multas", methods=["GET"])
def api_listar_multas(vid):
    return jsonify([r.to_dict() for r in _svc().listar_multas(vid)])


@bp.route("/api/multas", methods=["POST"])
def api_criar_multa():
    dados = request.get_json(silent=True) or {}
    if not dados.get("veiculo_id"):
        return jsonify({"ok": False, "erro": "veiculo_id é obrigatório."}), 400
    _svc().criar_multa(dados)
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>", methods=["PUT"])
def api_editar_multa(mid):
    dados = request.get_json(silent=True) or {}
    ok, msg = _svc().atualizar_multa(mid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>", methods=["DELETE"])
def api_deletar_multa(mid):
    ok, msg = _svc().excluir_multa(mid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── Validação ────────────────────────────────────────────────────────────────

def _validar_veiculo(dados: dict) -> str:
    for campo in ("placa", "renavam", "marca_modelo", "proprietario"):
        if not dados.get(campo, "").strip():
            return f"Campo obrigatório ausente: {campo}."
    return ""
