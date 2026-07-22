from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.cliente import Cliente
from app.services.auth_service import requer_permissao
from app.services.log_service import LogService
from app.services.pendencia_service import PendenciaService, PERMISSAO_POR_TIPO

bp = Blueprint("pendencias", __name__)


def _svc() -> PendenciaService:
    return PendenciaService(db.session)


def _log() -> LogService:
    return LogService(db.session)


# ── Página ───────────────────────────────────────────────────────────────────

@bp.route("/clientes/<int:cid>/pendencias")
@login_required
@requer_permissao("visualizar_veiculos")
def pendencias(cid):
    cliente = db.session.get(Cliente, cid)
    if not cliente:
        return redirect(url_for("clientes.clientes"))
    return render_template("pendencias.html", cliente=cliente.to_dict())


# ── API ──────────────────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/pendencias", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_listar_pendencias(cid):
    return jsonify(_svc().listar(cid))


@bp.route("/api/clientes/<int:cid>/pendencias/quitar-lote", methods=["POST"])
@login_required
def api_quitar_lote(cid):
    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens") or []
    if not isinstance(itens, list) or not itens:
        return jsonify({"ok": False, "erro": "Nenhum item selecionado."}), 400

    # Cada tipo de item exige sua própria permissão (gerenciar_ipva,
    # gerenciar_licenciamento, gerenciar_multas) — itens sem permissão são
    # rejeitados individualmente, sem travar o restante do lote.
    permitidos, negados = [], []
    for item in itens:
        codigo = PERMISSAO_POR_TIPO.get(item.get("tipo"))
        if codigo and current_user.tem_permissao(codigo):
            permitidos.append(item)
        else:
            negados.append({
                "tipo": item.get("tipo"),
                "id": item.get("id"),
                "erro": "Sem permissão para quitar este tipo de item.",
            })

    resultado = _svc().quitar_lote(permitidos)
    resultado["falhas"] = negados + resultado["falhas"]

    if resultado["sucesso"]:
        _log().registrar(
            "quitar_lote_pendencias", "cliente", cid,
            {"quantidade": resultado["sucesso"]},
        )
    return jsonify({"ok": True, **resultado})
