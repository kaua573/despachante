import io
import json

from flask import Blueprint, render_template, request, jsonify, send_file, current_app

from app import db
from app.services.relatorio_service import RelatorioService, CAMPOS_POR_TIPO
from app.services.configuracao_service import ConfiguracaoService

bp = Blueprint("relatorios", __name__)


def _svc() -> RelatorioService:
    return RelatorioService(db.session)


# ── Páginas ──────────────────────────────────────────────────────────────────

@bp.route("/relatorios")
def pagina_relatorios():
    return render_template("relatorios/configurar.html")


@bp.route("/relatorios/visualizar")
def pagina_visualizar():
    config_raw = request.args.get("config", "{}")
    try:
        config = json.loads(config_raw)
    except (json.JSONDecodeError, TypeError):
        config = {}
    return render_template("relatorios/visualizar.html", config=config)


# ── API — Campos disponíveis ─────────────────────────────────────────────────

@bp.route("/api/relatorios/campos/<tipo>")
def api_campos(tipo):
    if tipo not in CAMPOS_POR_TIPO:
        return jsonify({"erro": "Tipo inválido."}), 400
    return jsonify(CAMPOS_POR_TIPO[tipo])


# ── API — Dados do relatório ─────────────────────────────────────────────────

@bp.route("/api/relatorios/dados", methods=["POST"])
def api_dados():
    config = request.get_json(silent=True) or {}
    erro = _validar_config(config)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400

    svc   = _svc()
    dados = svc.buscar_dados(config)

    campo_grupo = config.get("agrupar_por", "")
    if campo_grupo and campo_grupo != "nenhum":
        grupos = svc.agrupar(dados, campo_grupo)
        return jsonify({
            "ok":              True,
            "agrupado":        True,
            "grupos":          {k: v for k, v in grupos.items()},
            "totais_por_grupo":{k: svc.calcular_totais(v) for k, v in grupos.items()},
            "totais_geral":    svc.calcular_totais(dados),
        })

    return jsonify({
        "ok":      True,
        "agrupado":False,
        "dados":   dados,
        "totais":  svc.calcular_totais(dados),
    })


# ── API — Exportação PDF ──────────────────────────────────────────────────────

@bp.route("/api/relatorios/exportar/pdf", methods=["POST"])
def api_exportar_pdf():
    payload         = request.get_json(silent=True) or {}
    config          = payload.get("config", {})
    campos_visiveis = payload.get("campos_visiveis", [])

    erro = _validar_config(config)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    if not campos_visiveis:
        return jsonify({"ok": False, "erro": "Selecione ao menos um campo."}), 400

    svc     = _svc()
    dados   = svc.buscar_dados(config)
    cfg_svc = ConfiguracaoService(db.session)

    cfg_pdf = {
        "fonte":               cfg_svc.get("pdf_fonte", "moderna"),
        "tamanho":             cfg_svc.get("pdf_tamanho", "medio"),
        "cor":                 cfg_svc.get("pdf_cor", "azul"),
        "mostrar_data_geracao":cfg_svc.get("pdf_mostrar_data_geracao", "1") == "1",
        "nome_escritorio":     cfg_svc.get("pdf_nome_escritorio") or cfg_svc.get("escritorio_nome", ""),
        # Logo — necessário para montar o cabeçalho com imagem
        "logo_dir":            current_app.config["LOGO_DIR"],
        "logo_arquivo":        cfg_svc.get("escritorio_logo", ""),
    }

    pdf_bytes   = svc.gerar_pdf(dados, campos_visiveis, config, cfg_pdf)
    tipo_label  = {"ipva": "IPVA", "licenciamento": "Licenciamento", "multas": "Multas"}.get(
        config.get("tipo", "ipva"), "relatorio"
    )

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"relatorio_{tipo_label}.pdf",
    )


# ── API — Exportação Excel ────────────────────────────────────────────────────

@bp.route("/api/relatorios/exportar/excel", methods=["POST"])
def api_exportar_excel():
    payload         = request.get_json(silent=True) or {}
    config          = payload.get("config", {})
    campos_visiveis = payload.get("campos_visiveis", [])

    erro = _validar_config(config)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400
    if not campos_visiveis:
        return jsonify({"ok": False, "erro": "Selecione ao menos um campo."}), 400

    svc         = _svc()
    dados       = svc.buscar_dados(config)
    excel_bytes = svc.gerar_excel(dados, campos_visiveis, config)
    tipo_label  = {"ipva": "IPVA", "licenciamento": "Licenciamento", "multas": "Multas"}.get(
        config.get("tipo", "ipva"), "relatorio"
    )

    return send_file(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"relatorio_{tipo_label}.xlsx",
    )


# ── API — Templates salvos ────────────────────────────────────────────────────

@bp.route("/api/relatorios/templates", methods=["GET"])
def api_listar_templates():
    return jsonify([t.to_dict() for t in _svc().listar_templates()])


@bp.route("/api/relatorios/templates", methods=["POST"])
def api_salvar_template():
    dados      = request.get_json(silent=True) or {}
    nome       = dados.get("nome", "").strip()
    config     = dados.get("config", {})
    template_id= dados.get("id")

    if not nome:
        return jsonify({"ok": False, "erro": "Nome do template é obrigatório."}), 400
    erro = _validar_config(config)
    if erro:
        return jsonify({"ok": False, "erro": erro}), 400

    t = _svc().salvar_template(nome, config, template_id)
    return jsonify({"ok": True, "id": t.id, "nome": t.nome})


@bp.route("/api/relatorios/templates/<int:tid>", methods=["GET"])
def api_obter_template(tid):
    t = _svc().obter_template(tid)
    if not t:
        return jsonify({"erro": "Template não encontrado."}), 404
    return jsonify(t.to_dict())


@bp.route("/api/relatorios/templates/<int:tid>", methods=["DELETE"])
def api_excluir_template(tid):
    ok, msg = _svc().excluir_template(tid)
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 404
    return jsonify({"ok": True})


# ── Validação ─────────────────────────────────────────────────────────────────

def _validar_config(config: dict) -> str:
    if config.get("tipo") not in ("ipva", "licenciamento", "multas"):
        return "Tipo de relatório inválido."
    return ""
