from flask import Blueprint, jsonify, request

from app import db
from app.services.ipva_service import IpvaService

bp = Blueprint("ipva", __name__)


def _svc() -> IpvaService:
    return IpvaService(db.session)


@bp.route("/api/ipva/<int:ipva_id>/parcelas", methods=["GET"])
def api_listar_parcelas(ipva_id):
    """Lista parcelas com status atualizado automaticamente."""
    parcelas = _svc().listar_parcelas(ipva_id)
    status   = _svc().status_geral(ipva_id)
    return jsonify({
        "parcelas":     [p.to_dict() for p in parcelas],
        "status_geral": status,
    })


@bp.route("/api/ipva/<int:ipva_id>/parcelas/gerar", methods=["POST"])
def api_gerar_parcelas(ipva_id):
    """
    Gera ou regenera parcelas de um IPVA, marcando-o como 'parcelado'.
    Body JSON: { num_parcelas, valor_total, data_primeira }
    """
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
    return jsonify({"ok": True})


@bp.route("/api/ipva/parcelas/<int:parcela_id>/quitar", methods=["POST"])
def api_quitar_parcela(parcela_id):
    """Quita uma parcela individual."""
    ok, msg = _svc().quitar_parcela(parcela_id)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:ipva_id>/quitar", methods=["POST"])
def api_quitar_avista(ipva_id):
    """
    Quita o IPVA integralmente (modo à vista).
    Retorna 400 se o IPVA for do tipo parcelado.
    """
    ok, msg = _svc().quitar_avista(ipva_id)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:ipva_id>/parcelas/desfazer", methods=["POST"])
def api_desfazer_parcelamento(ipva_id):
    """Remove todas as parcelas e volta o IPVA para modo à vista."""
    ok, msg = _svc().desfazer_parcelamento(ipva_id)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    return jsonify({"ok": True})
