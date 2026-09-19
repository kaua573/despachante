from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.cliente import Cliente
from app.services.auth_service import requer_permissao
from app.services.log_service import LogService
from app.services.pendencia_service import PendenciaService, PERMISSAO_POR_TIPO, TIPOS_VALIDOS

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


@bp.route("/pendencias")
@login_required
@requer_permissao("visualizar_veiculos")
def pendencias_geral():
    return render_template("pendencias_geral.html")


# ── API ──────────────────────────────────────────────────────────────────────

@bp.route("/api/clientes/<int:cid>/pendencias", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_listar_pendencias(cid):
    return jsonify(_svc().listar(cid))


@bp.route("/api/pendencias", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_listar_pendencias_todas():
    return jsonify(_svc().listar_todas())


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


@bp.route("/api/pendencias/quitar-lote", methods=["POST"])
@login_required
def api_quitar_lote_geral():
    """Igual ao endpoint por cliente acima, mas para a Central de pendências
    — os itens do lote podem pertencer a clientes diferentes, então não há
    um único `cid` para checar."""
    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens") or []
    if not isinstance(itens, list) or not itens:
        return jsonify({"ok": False, "erro": "Nenhum item selecionado."}), 400

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
            "quitar_lote_pendencias", "sistema", None,
            {"quantidade": resultado["sucesso"]},
        )
    return jsonify({"ok": True, **resultado})


# ── Registro de contato com o cliente (Central de pendências) ───────────────
# Só sinaliza que alguém do escritório já ligou/entrou em contato — não
# quita nada e não dispara nenhum envio automático (e-mail/WhatsApp).

@bp.route("/api/pendencias/contato", methods=["POST"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_marcar_contato():
    dados = request.get_json(silent=True) or {}
    tipo = dados.get("tipo")
    pendencia_id = dados.get("id")
    observacao = dados.get("observacao")

    if tipo not in TIPOS_VALIDOS or not isinstance(pendencia_id, int):
        return jsonify({"ok": False, "erro": "Item inválido."}), 400

    ok, msg = _svc().marcar_contato(tipo, pendencia_id, current_user.id, observacao)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404

    _log().registrar("marcar_contato_pendencia", tipo, pendencia_id, {"observacao": observacao or ""})
    return jsonify({"ok": True})


@bp.route("/api/pendencias/contato/<string:tipo>/<int:pendencia_id>", methods=["DELETE"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_desmarcar_contato(tipo, pendencia_id):
    if tipo not in TIPOS_VALIDOS:
        return jsonify({"ok": False, "erro": "Tipo inválido."}), 400

    removido = _svc().desmarcar_contato(tipo, pendencia_id)
    if not removido:
        return jsonify({"ok": False, "erro": "Nenhum contato registrado para este item."}), 404

    _log().registrar("desmarcar_contato_pendencia", tipo, pendencia_id, {})
    return jsonify({"ok": True})
