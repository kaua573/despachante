from flask import Blueprint, jsonify, request
from flask_login import login_required
from app import db
from app.services.auth_service import requer_permissao
from app.services.ipva_service import IpvaService
from app.services.log_service import LogService

bp = Blueprint("ipva", __name__)


def _svc() -> IpvaService:
    return IpvaService(db.session)


def _log() -> LogService:
    return LogService(db.session)


@bp.route("/api/ipva/<int:ipva_id>/parcelas", methods=["GET"])
@login_required
@requer_permissao("visualizar_ipva")
def api_listar_parcelas(ipva_id):
    parcelas = _svc().listar_parcelas(ipva_id)
    status   = _svc().status_geral(ipva_id)
    return jsonify({"parcelas": [p.to_dict() for p in parcelas], "status_geral": status})


@bp.route("/api/ipva/<int:ipva_id>/parcelas/gerar", methods=["POST"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_gerar_parcelas(ipva_id):
    dados = request.get_json(silent=True) or {}
    try:
        num_parcelas = int(dados.get("num_parcelas", 1))
    except (ValueError, TypeError):
        return jsonify({"ok": False, "erro": "num_parcelas inválido."}), 400

    valor_total   = dados.get("valor_total")
    data_primeira = dados.get("data_primeira", "")

    if not valor_total:
        return jsonify({"ok": False, "erro": "valor_total é obrigatório."}), 400
    if not data_primeira:
        return jsonify({"ok": False, "erro": "data_primeira é obrigatória."}), 400

    ok, msg = _svc().gerar_parcelas(ipva_id, num_parcelas, float(valor_total), data_primeira)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("gerar_parcelas_ipva", "ipva", ipva_id, {"num_parcelas": num_parcelas})
    return jsonify({"ok": True})


@bp.route("/api/ipva/parcelas/<int:parcela_id>/quitar", methods=["POST"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_quitar_parcela(parcela_id):
    ok, msg = _svc().quitar_parcela(parcela_id)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("quitar_parcela_ipva", "ipva_parcela", parcela_id)
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:ipva_id>/quitar", methods=["POST"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_quitar_avista(ipva_id):
    ok, msg = _svc().quitar_avista(ipva_id)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("quitar_ipva_avista", "ipva", ipva_id)
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:ipva_id>/parcelas/desfazer", methods=["POST"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_desfazer_parcelamento(ipva_id):
    ok, msg = _svc().desfazer_parcelamento(ipva_id)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    _log().registrar("desfazer_parcelamento_ipva", "ipva", ipva_id)
    return jsonify({"ok": True})
