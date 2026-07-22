from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required
from app import db
from app.models.cliente import Cliente
from app.models.veiculo import Veiculo
from app.services.auth_service import requer_permissao
from app.services.log_service import LogService
from app.services.veiculo_service import VeiculoService
from app.services.validacao_service import validar_campos_veiculo, normalizar_placa

bp = Blueprint("veiculos", __name__)


def _svc() -> VeiculoService:
    return VeiculoService(db.session)


def _log() -> LogService:
    return LogService(db.session)


# ── Páginas ──────────────────────────────────────────────────────────────────

@bp.route("/clientes/<int:cid>/veiculos")
@login_required
@requer_permissao("visualizar_veiculos")
def veiculos(cid):
    cliente = db.session.get(Cliente, cid)
    if not cliente:
        return redirect(url_for("clientes.clientes"))
    return render_template("veiculos.html", cliente=cliente.to_dict())


# ── API — Proprietários ──────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/proprietarios", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_proprietarios_por_cliente(cid):
    cliente = db.session.get(Cliente, cid)
    if not cliente:
        return jsonify({"ok": False, "erro": "Cliente não encontrado."}), 404
    rows = (
        db.session.query(Veiculo.proprietario)
        .filter(Veiculo.cliente_id == cid, Veiculo.proprietario != None, Veiculo.proprietario != "")
        .distinct().order_by(Veiculo.proprietario).all()
    )
    return jsonify([r[0] for r in rows if r[0]])


# ── API — Veículos ───────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/veiculos", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_listar_veiculos(cid):
    return jsonify([v.to_dict() for v in _svc().listar_por_cliente(cid)])


@bp.route("/api/veiculos", methods=["POST"])
@login_required
@requer_permissao("cadastrar_veiculos")
def api_criar_veiculo():
    dados = request.get_json(silent=True) or {}
    erro = _validar_e_normalizar(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    v = _svc().criar(dados)
    _log().registrar("criar_veiculo", "veiculo", v.id, {"placa": v.placa})
    return jsonify({"ok": True}) 


@bp.route("/api/veiculos/<int:vid>", methods=["PUT"])
@login_required
@requer_permissao("cadastrar_veiculos")
def api_editar_veiculo(vid):
    dados = request.get_json(silent=True) or {}
    erro = _validar_e_normalizar(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    ok, msg = _svc().atualizar(vid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("editar_veiculo", "veiculo", vid, {"placa": dados.get("placa")})
    return jsonify({"ok": True})


@bp.route("/api/veiculos/<int:vid>", methods=["DELETE"])
@login_required
@requer_permissao("excluir_veiculos")
def api_deletar_veiculo(vid):
    ok, msg = _svc().excluir(vid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_veiculo", "veiculo", vid)
    return jsonify({"ok": True})


# ── API — IPVA ───────────────────────────────────────────────────────────────

@bp.route("/api/veiculos/<int:vid>/ipva", methods=["GET"])
@login_required
@requer_permissao("visualizar_ipva")
def api_listar_ipva(vid):
    return jsonify([r.to_dict() for r in _svc().listar_ipva(vid)])


@bp.route("/api/ipva", methods=["POST"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_criar_ipva():
    dados = request.get_json(silent=True) or {}
    if not dados.get("veiculo_id") or not dados.get("ano_referencia"):
        return jsonify({"ok": False, "erro": "veiculo_id e ano_referencia são obrigatórios."}), 400
    r = _svc().criar_ipva(dados)
    _log().registrar("criar_ipva", "ipva", r.id, {"ano": dados.get("ano_referencia")})
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:iid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_editar_ipva(iid):
    dados = request.get_json(silent=True) or {}
    ok, msg = _svc().atualizar_ipva(iid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("editar_ipva", "ipva", iid)
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:iid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_deletar_ipva(iid):
    ok, msg = _svc().excluir_ipva(iid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_ipva", "ipva", iid)
    return jsonify({"ok": True})


# ── API — Licenciamento ──────────────────────────────────────────────────────

@bp.route("/api/veiculos/<int:vid>/licenciamento", methods=["GET"])
@login_required
@requer_permissao("visualizar_licenciamento")
def api_listar_licenciamento(vid):
    return jsonify([r.to_dict() for r in _svc().listar_licenciamento(vid)])


@bp.route("/api/licenciamento", methods=["POST"])
@login_required
@requer_permissao("gerenciar_licenciamento")
def api_criar_licenciamento():
    dados = request.get_json(silent=True) or {}
    if not dados.get("veiculo_id") or not dados.get("ano_referencia"):
        return jsonify({"ok": False, "erro": "veiculo_id e ano_referencia são obrigatórios."}), 400
    r = _svc().criar_licenciamento(dados)
    _log().registrar("criar_licenciamento", "licenciamento", r.id)
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_licenciamento")
def api_editar_licenciamento(lid):
    dados = request.get_json(silent=True) or {}
    ok, msg = _svc().atualizar_licenciamento(lid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("editar_licenciamento", "licenciamento", lid)
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_licenciamento")
def api_deletar_licenciamento(lid):
    ok, msg = _svc().excluir_licenciamento(lid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_licenciamento", "licenciamento", lid)
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>/quitar", methods=["POST"])
@login_required
@requer_permissao("gerenciar_licenciamento")
def api_quitar_licenciamento(lid):
    from app.services.pendencia_service import PendenciaService
    ok, msg = PendenciaService(db.session).quitar_licenciamento(lid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("quitar_licenciamento", "licenciamento", lid)
    return jsonify({"ok": True})


# ── API — Multas ─────────────────────────────────────────────────────────────

@bp.route("/api/veiculos/<int:vid>/multas", methods=["GET"])
@login_required
@requer_permissao("visualizar_multas")
def api_listar_multas(vid):
    return jsonify([r.to_dict() for r in _svc().listar_multas(vid)])


@bp.route("/api/multas", methods=["POST"])
@login_required
@requer_permissao("gerenciar_multas")
def api_criar_multa():
    dados = request.get_json(silent=True) or {}
    if not dados.get("veiculo_id"):
        return jsonify({"ok": False, "erro": "veiculo_id é obrigatório."}), 400
    r = _svc().criar_multa(dados)
    _log().registrar("criar_multa", "multa", r.id)
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_multas")
def api_editar_multa(mid):
    dados = request.get_json(silent=True) or {}
    ok, msg = _svc().atualizar_multa(mid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("editar_multa", "multa", mid)
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_multas")
def api_deletar_multa(mid):
    ok, msg = _svc().excluir_multa(mid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_multa", "multa", mid)
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>/quitar", methods=["POST"])
@login_required
@requer_permissao("gerenciar_multas")
def api_quitar_multa(mid):
    from app.services.pendencia_service import PendenciaService
    ok, msg = PendenciaService(db.session).quitar_multa(mid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("quitar_multa", "multa", mid)
    return jsonify({"ok": True})


# ── Validação ─────────────────────────────────────────────────────────────────

def _validar_e_normalizar(dados: dict) -> str:
    erro = validar_campos_veiculo(dados)
    if erro:
        return erro
    dados["placa"] = normalizar_placa(dados.get("placa", ""))
    return ""
