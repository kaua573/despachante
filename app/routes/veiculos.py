from flask import Blueprint, render_template, request, jsonify, redirect, url_for, send_file, current_app
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
    v, erro = _svc().criar(dados)
    if not v:
        return jsonify({"ok": False, "erro": erro}), 400
    _log().registrar_alteracao("criar_veiculo", "veiculo", v.id, None, v.to_dict())
    return jsonify({"ok": True})


@bp.route("/api/veiculos/<int:vid>", methods=["PUT"])
@login_required
@requer_permissao("cadastrar_veiculos")
def api_editar_veiculo(vid):
    dados = request.get_json(silent=True) or {}
    erro = _validar_e_normalizar(dados)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    antes = _svc().obter(vid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().atualizar(vid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    depois = _svc().obter(vid).to_dict()
    _log().registrar_alteracao("editar_veiculo", "veiculo", vid, antes, depois)
    return jsonify({"ok": True})


@bp.route("/api/veiculos/<int:vid>", methods=["DELETE"])
@login_required
@requer_permissao("excluir_veiculos")
def api_deletar_veiculo(vid):
    antes = _svc().obter(vid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().excluir(vid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar_alteracao("excluir_veiculo", "veiculo", vid, antes, None)
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
    _log().registrar_alteracao("criar_ipva", "ipva", r.id, None, r.to_dict())
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:iid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_editar_ipva(iid):
    dados = request.get_json(silent=True) or {}
    antes = _svc().obter_ipva(iid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().atualizar_ipva(iid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    depois = _svc().obter_ipva(iid).to_dict()
    _log().registrar_alteracao("editar_ipva", "ipva", iid, antes, depois)
    return jsonify({"ok": True})


@bp.route("/api/ipva/<int:iid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_ipva")
def api_deletar_ipva(iid):
    antes = _svc().obter_ipva(iid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().excluir_ipva(iid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar_alteracao("excluir_ipva", "ipva", iid, antes, None)
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
    _log().registrar_alteracao("criar_licenciamento", "licenciamento", r.id, None, r.to_dict())
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_licenciamento")
def api_editar_licenciamento(lid):
    dados = request.get_json(silent=True) or {}
    antes = _svc().obter_licenciamento(lid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().atualizar_licenciamento(lid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    depois = _svc().obter_licenciamento(lid).to_dict()
    _log().registrar_alteracao("editar_licenciamento", "licenciamento", lid, antes, depois)
    return jsonify({"ok": True})


@bp.route("/api/licenciamento/<int:lid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_licenciamento")
def api_deletar_licenciamento(lid):
    antes = _svc().obter_licenciamento(lid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().excluir_licenciamento(lid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar_alteracao("excluir_licenciamento", "licenciamento", lid, antes, None)
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
    _log().registrar_alteracao("criar_multa", "multa", r.id, None, r.to_dict())
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>", methods=["PUT"])
@login_required
@requer_permissao("gerenciar_multas")
def api_editar_multa(mid):
    dados = request.get_json(silent=True) or {}
    antes = _svc().obter_multa(mid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().atualizar_multa(mid, dados)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    depois = _svc().obter_multa(mid).to_dict()
    _log().registrar_alteracao("editar_multa", "multa", mid, antes, depois)
    return jsonify({"ok": True})


@bp.route("/api/multas/<int:mid>", methods=["DELETE"])
@login_required
@requer_permissao("gerenciar_multas")
def api_deletar_multa(mid):
    antes = _svc().obter_multa(mid)
    antes = antes.to_dict() if antes else None
    ok, msg = _svc().excluir_multa(mid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    _log().registrar_alteracao("excluir_multa", "multa", mid, antes, None)
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


# ── Importação / exportação de veículos de UM cliente ───────────────────────────

@bp.route("/api/clientes/<int:cid>/veiculos/exportar")
@login_required
@requer_permissao("visualizar_veiculos")
def exportar_veiculos_cliente(cid):
    from app.services.importacao_service import ImportacaoService
    import io as io_
    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    conteudo = svc.exportar_veiculos_cliente(cid)
    _log().registrar("exportar_veiculos_cliente", "cliente", cid)
    return send_file(
        io_.BytesIO(conteudo),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="veiculos.xlsx",
    )


@bp.route("/api/clientes/<int:cid>/veiculos/modelo-importacao")
@login_required
@requer_permissao("cadastrar_veiculos")
def modelo_importacao_veiculos_cliente(cid):
    from app.services.importacao_service import ImportacaoService
    import io as io_
    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    conteudo = svc.gerar_modelo_veiculos_cliente()
    return send_file(
        io_.BytesIO(conteudo),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="modelo_importacao_veiculos.xlsx",
    )


@bp.route("/api/clientes/<int:cid>/veiculos/pre-importar", methods=["POST"])
@login_required
@requer_permissao("cadastrar_veiculos")
def pre_importar_veiculos_cliente(cid):
    from app.services.importacao_service import ImportacaoService

    if "arquivo" not in request.files or not request.files["arquivo"].filename:
        return jsonify({"ok": False, "erro": "Nenhum arquivo enviado."}), 400

    arquivo = request.files["arquivo"]
    if not arquivo.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "erro": "Envie um arquivo .xlsx (use o modelo disponível para download)."}), 400

    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    preview = svc.pre_visualizar_veiculos_cliente(cid, arquivo.read())
    return jsonify({"ok": True, **preview})


@bp.route("/api/clientes/<int:cid>/veiculos/importar", methods=["POST"])
@login_required
@requer_permissao("cadastrar_veiculos")
def importar_veiculos_cliente(cid):
    from app.services.importacao_service import ImportacaoService

    if "arquivo" not in request.files or not request.files["arquivo"].filename:
        return jsonify({"ok": False, "erro": "Nenhum arquivo enviado."}), 400

    arquivo = request.files["arquivo"]
    if not arquivo.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "erro": "Envie um arquivo .xlsx (use o modelo disponível para download)."}), 400

    svc = ImportacaoService(db.session, current_app.config["UPLOAD_DIR"])
    resultado = svc.importar_veiculos_cliente(cid, arquivo.read())
    _log().registrar("importar_veiculos_cliente", "cliente", cid, {
        "veiculos_criados": resultado["veiculos_criados"],
        "veiculos_atualizados": resultado["veiculos_atualizados"],
        "erros": len(resultado["erros"]),
    })
    return jsonify({"ok": True, **resultado})


# ── Validação ─────────────────────────────────────────────────────────────────

def _validar_e_normalizar(dados: dict) -> str:
    erro = validar_campos_veiculo(dados)
    if erro:
        return erro
    dados["placa"] = normalizar_placa(dados.get("placa", ""))
    return ""
