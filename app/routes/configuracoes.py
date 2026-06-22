import os
from flask import Blueprint, render_template, request, jsonify, current_app
from app import db
from app.services.configuracao_service import (
    ConfiguracaoService, PALETA_CORES, FONTES_PDF, TAMANHOS_PDF
)
from app.services.backup_service import BackupService

bp = Blueprint("configuracoes", __name__)


def _cfg() -> ConfiguracaoService:
    return ConfiguracaoService(db.session)


# ── Página ────────────────────────────────────────────────────────────────────

@bp.route("/configuracoes")
def pagina_configuracoes():
    return render_template("configuracoes.html")


# ── API — Geral ──────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes", methods=["GET"])
def api_get_configuracoes():
    cfg = _cfg()
    return jsonify({
        "backup_intervalo_min": cfg.get("backup_intervalo_min", "30"),
        "senha_configurada": cfg.get("senha_exclusao", "0000") != "0000",
    })


# ── API — Senha ──────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/senha", methods=["POST"])
def api_set_senha():
    dados = request.get_json(silent=True) or {}
    ok, msg = _cfg().trocar_senha(
        dados.get("senha_atual", ""),
        dados.get("nova_senha", ""),
    )
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    return jsonify({"ok": True})


@bp.route("/api/configuracoes/verificar-senha", methods=["POST"])
def api_verificar_senha():
    dados = request.get_json(silent=True) or {}
    if _cfg().senha_ok(dados.get("senha", "")):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "erro": "Senha incorreta."}), 403


# ── API — Backup ─────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/backup-intervalo", methods=["POST"])
def api_set_backup_intervalo():
    dados = request.get_json(silent=True) or {}
    try:
        minutos = int(dados.get("minutos", 0))
        if minutos < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"ok": False, "erro": "Número de minutos inválido (mínimo 1)."}), 400
    _cfg().set("backup_intervalo_min", str(minutos))
    BackupService.reagendar()
    return jsonify({"ok": True})


@bp.route("/api/configuracoes/backup-agora", methods=["POST"])
def api_backup_agora():
    svc = BackupService(current_app.config["BACKUP_DIR"])
    caminho = svc.fazer_backup()
    if caminho:
        return jsonify({"ok": True, "arquivo": os.path.basename(caminho)})
    return jsonify({"ok": False, "erro": "Banco de dados não encontrado."}), 500


@bp.route("/api/configuracoes/backups", methods=["GET"])
def api_listar_backups():
    svc = BackupService(current_app.config["BACKUP_DIR"])
    return jsonify(svc.listar())


# ── API — Tema ───────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/tema", methods=["GET"])
def api_get_tema():
    cfg = _cfg()
    return jsonify({
        "modo":   cfg.get("tema_modo", "claro"),
        "cor":    cfg.get("tema_cor", "azul"),
        "paleta": PALETA_CORES,
    })


@bp.route("/api/configuracoes/tema", methods=["POST"])
def api_set_tema():
    dados = request.get_json(silent=True) or {}
    modo = dados.get("modo")
    cor = dados.get("cor")
    if modo not in ("claro", "escuro"):
        return jsonify({"ok": False, "erro": "Modo inválido."}), 400
    if cor not in PALETA_CORES:
        return jsonify({"ok": False, "erro": "Cor inválida."}), 400
    cfg = _cfg()
    cfg.set("tema_modo", modo)
    cfg.set("tema_cor", cor)
    return jsonify({"ok": True})


# ── API — Identidade do escritório ──────────────────────────────────────────

@bp.route("/api/configuracoes/escritorio", methods=["GET"])
def api_get_escritorio():
    cfg = _cfg()
    nome = cfg.get("escritorio_nome", "")
    logo = cfg.get("escritorio_logo", "")
    return jsonify({
        "nome":     nome,
        "logo":     logo,
        "logo_url": f"/static/uploads/logo/{logo}" if logo else "",
    })


@bp.route("/api/configuracoes/escritorio", methods=["POST"])
def api_set_escritorio():
    cfg = _cfg()
    nome = request.form.get("nome", "").strip()
    cfg.set("escritorio_nome", nome)

    if "logo" in request.files:
        arquivo = request.files["logo"]
        if arquivo and arquivo.filename:
            ext = os.path.splitext(arquivo.filename)[1].lower()
            if ext not in current_app.config["EXTENSOES_LOGO"]:
                return jsonify({"ok": False, "erro": "Formato de logo não suportado."}), 400
            # Remove logo anterior do disco
            logo_ant = cfg.get("escritorio_logo", "")
            if logo_ant:
                _remover_logo_disco(logo_ant, current_app.config["LOGO_DIR"])
            arquivo_nome = f"logo{ext}"
            arquivo.save(os.path.join(current_app.config["LOGO_DIR"], arquivo_nome))
            cfg.set("escritorio_logo", arquivo_nome)

    logo_atual = cfg.get("escritorio_logo", "")
    return jsonify({
        "ok": True,
        "logo_url": f"/static/uploads/logo/{logo_atual}" if logo_atual else "",
    })


@bp.route("/api/configuracoes/escritorio/logo", methods=["DELETE"])
def api_remover_logo():
    cfg = _cfg()
    logo = cfg.get("escritorio_logo", "")
    if logo:
        _remover_logo_disco(logo, current_app.config["LOGO_DIR"])
        cfg.set("escritorio_logo", "")
    return jsonify({"ok": True})


# ── API — PDF ────────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/pdf", methods=["GET"])
def api_get_config_pdf():
    cfg = _cfg()
    return jsonify({
        "fonte":              cfg.get("pdf_fonte", "moderna"),
        "tamanho":            cfg.get("pdf_tamanho", "medio"),
        "cor":                cfg.get("pdf_cor", "azul"),
        "cor_texto":          cfg.get("pdf_cor_texto", "escuro"),
        "mostrar_data_geracao": cfg.get("pdf_mostrar_data_geracao", "1") == "1",
        "espacamento":        cfg.get("pdf_espacamento", "espacada"),
        "ordem_blocos":       cfg.get("pdf_ordem_blocos", "dados_primeiro"),
        "nome_escritorio":    cfg.get("pdf_nome_escritorio", ""),
        "opcoes_fonte":       FONTES_PDF,
        "opcoes_tamanho":     TAMANHOS_PDF,
        "opcoes_cor":         PALETA_CORES,
    })


@bp.route("/api/configuracoes/pdf", methods=["POST"])
def api_set_config_pdf():
    dados = request.get_json(silent=True) or {}
    validacoes = [
        (dados.get("fonte") not in FONTES_PDF,         "Fonte inválida."),
        (dados.get("tamanho") not in TAMANHOS_PDF,     "Tamanho inválido."),
        (dados.get("cor") not in PALETA_CORES,         "Cor inválida."),
        (dados.get("cor_texto") not in ("escuro", "cinza", "claro"), "Cor do texto inválida."),
        (dados.get("espacamento") not in ("compacta", "espacada"),   "Espaçamento inválido."),
        (dados.get("ordem_blocos") not in ("dados_primeiro", "veiculos_primeiro"), "Ordem de blocos inválida."),
    ]
    for invalido, msg in validacoes:
        if invalido:
            return jsonify({"ok": False, "erro": msg}), 400

    cfg = _cfg()
    cfg.set("pdf_fonte",              dados["fonte"])
    cfg.set("pdf_tamanho",            dados["tamanho"])
    cfg.set("pdf_cor",                dados["cor"])
    cfg.set("pdf_cor_texto",          dados["cor_texto"])
    cfg.set("pdf_mostrar_data_geracao", "1" if dados.get("mostrar_data_geracao") else "0")
    cfg.set("pdf_espacamento",        dados["espacamento"])
    cfg.set("pdf_ordem_blocos",       dados["ordem_blocos"])
    cfg.set("pdf_nome_escritorio",    dados.get("nome_escritorio", ""))
    return jsonify({"ok": True})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _remover_logo_disco(nome_arquivo: str, logo_dir: str) -> None:
    caminho = os.path.join(logo_dir, nome_arquivo)
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except OSError:
        pass
