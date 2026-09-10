"""
Rotas da visão geral de veículos (itens 1, 2 e 3 do pedido de set/2026):
  - Listagem geral (todos os clientes) com filtros, incluindo "sem
    licenciamento do ano corrente".
  - Agrupamento por espécie (carga/passeio/reboque).
  - Regras de vencimento por final de placa + espécie, previsão e
    lançamento em lote com supervisão manual.
"""
from datetime import date

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required

from app import db
from app.models.cliente import Cliente
from app.services.auth_service import requer_permissao
from app.services.log_service import LogService
from app.services.veiculo_geral_service import VeiculoGeralService
from app.services.vencimento_regra_service import VencimentoRegraService

bp = Blueprint("veiculos_geral", __name__)


def _svc() -> VeiculoGeralService:
    return VeiculoGeralService(db.session)


def _svc_regras() -> VencimentoRegraService:
    return VencimentoRegraService(db.session)


def _log() -> LogService:
    return LogService(db.session)


# ── Páginas ──────────────────────────────────────────────────────────────────

@bp.route("/veiculos")
@login_required
@requer_permissao("visualizar_veiculos")
def veiculos_geral():
    return render_template("veiculos_geral.html", ano_atual=date.today().year)


@bp.route("/veiculos/vencimentos-placa")
@login_required
@requer_permissao("visualizar_veiculos")
def vencimentos_placa():
    return render_template("vencimentos_placa.html", ano_atual=date.today().year)


# ── API — Listagem / filtros gerais (itens 1 e 2) ────────────────────────────

@bp.route("/api/veiculos/geral", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_veiculos_geral():
    cliente_id = request.args.get("cliente_id", type=int)
    especie = request.args.get("especie") or None
    situacao = request.args.get("situacao") or None
    sem_lic_ano = request.args.get("sem_licenciamento_ano", type=int)
    return jsonify(_svc().listar(
        cliente_id=cliente_id, especie=especie, situacao=situacao,
        sem_licenciamento_ano=sem_lic_ano,
    ))


@bp.route("/api/veiculos/especies-resumo", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_especies_resumo():
    cliente_id = request.args.get("cliente_id", type=int)
    return jsonify(_svc().resumo_por_especie(cliente_id=cliente_id))


@bp.route("/api/veiculos/clientes-opcoes", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_clientes_opcoes():
    """Lista enxuta (id, nome) para popular filtros — não exige visualizar_clientes."""
    rows = db.session.query(Cliente.id, Cliente.nome).order_by(Cliente.nome).all()
    return jsonify([{"id": r[0], "nome": r[1]} for r in rows])


# ── API — Regras de vencimento por final de placa (item 3) ──────────────────

@bp.route("/api/regras-vencimento", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_listar_regras():
    return jsonify([r.to_dict() for r in _svc_regras().listar_regras()])


@bp.route("/api/regras-vencimento", methods=["POST"])
@login_required
@requer_permissao("gerenciar_regras_vencimento")
def api_salvar_regra():
    dados = request.get_json(silent=True) or {}
    regra, erro = _svc_regras().salvar_regra(dados)
    if not regra:
        return jsonify({"ok": False, "erro": erro}), 400
    _log().registrar("salvar_regra_vencimento", "regra_vencimento", regra.id, regra.to_dict())
    return jsonify({"ok": True, "regra": regra.to_dict()})


@bp.route("/api/regras-vencimento/<int:rid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_regras_vencimento")
def api_excluir_regra(rid):
    ok, msg = _svc_regras().excluir_regra(rid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar("excluir_regra_vencimento", "regra_vencimento", rid)
    return jsonify({"ok": True})


@bp.route("/api/regras-vencimento/previsao", methods=["GET"])
@login_required
@requer_permissao("visualizar_veiculos")
def api_previsao():
    ano = request.args.get("ano", type=int)
    cliente_id = request.args.get("cliente_id", type=int)
    especie = request.args.get("especie") or None
    final_placa = request.args.get("final_placa") or None
    apenas_sem_lic = request.args.get("apenas_sem_licenciamento") == "1"
    return jsonify(_svc_regras().previsao(
        ano=ano, cliente_id=cliente_id, especie=especie,
        final_placa=final_placa, apenas_sem_licenciamento=apenas_sem_lic,
    ))


@bp.route("/api/regras-vencimento/lancar-lote", methods=["POST"])
@login_required
@requer_permissao("gerenciar_regras_vencimento")
def api_lancar_lote():
    dados = request.get_json(silent=True) or {}
    itens = dados.get("itens") or []
    ano = dados.get("ano")
    if not isinstance(itens, list) or not itens:
        return jsonify({"ok": False, "erro": "Nenhum veículo selecionado."}), 400
    try:
        ano = int(ano)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "erro": "Ano de referência inválido."}), 400

    resultado = _svc_regras().lancar_lote(itens, ano)
    if resultado["criados"]:
        _log().registrar(
            "lancar_lote_licenciamento", "licenciamento", None,
            {"ano": ano, "quantidade": len(resultado["criados"]),
             "placas": [c["placa"] for c in resultado["criados"]]},
        )
    return jsonify({"ok": True, **resultado})
