import os
from flask import Blueprint, render_template, request, jsonify, current_app, abort
from flask_login import login_required, current_user
from app import db
from app.services.configuracao_service import (
    ConfiguracaoService, PALETA_CORES,
    hex_valido, resolver_cor,
)
from app.services.backup_service import BackupService

bp = Blueprint("configuracoes", __name__)


def _cfg() -> ConfiguracaoService:
    return ConfiguracaoService(db.session)


def _somente_admin() -> None:
    """
    Configurações do sistema (senha de exclusão, backup, identidade
    visual, personalização de PDF) afetam todo mundo que usa o sistema —
    só administradores podem ver ou alterar essa tela.
    """
    if not current_user.is_authenticated or current_user.perfil != "administrador":
        abort(403)


# ── Página ────────────────────────────────────────────────────────────────────

@bp.route("/configuracoes")
@login_required
def pagina_configuracoes():
    _somente_admin()
    return render_template("configuracoes.html")


# ── API — Geral ──────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes", methods=["GET"])
@login_required
def api_get_configuracoes():
    _somente_admin()
    cfg = _cfg()
    return jsonify({
        "backup_intervalo_min": cfg.get("backup_intervalo_min", "30"),
        "senha_configurada": cfg.get("senha_exclusao", "0000") != "0000",
    })


# ── API — Senha ──────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/senha", methods=["POST"])
@login_required
def api_set_senha():
    _somente_admin()
    dados = request.get_json(silent=True) or {}
    ok, msg = _cfg().trocar_senha(
        dados.get("senha_atual", ""),
        dados.get("nova_senha", ""),
    )
    if not ok:
        return jsonify({"ok": False, "erro": msg}), 400
    return jsonify({"ok": True})


@bp.route("/api/configuracoes/verificar-senha", methods=["POST"])
@login_required
def api_verificar_senha():
    _somente_admin()
    dados = request.get_json(silent=True) or {}
    if _cfg().senha_ok(dados.get("senha", "")):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "erro": "Senha incorreta."}), 403


# ── API — Backup ─────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/backup-intervalo", methods=["POST"])
@login_required
def api_set_backup_intervalo():
    _somente_admin()
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
@login_required
def api_backup_agora():
    _somente_admin()
    svc = BackupService(current_app.config["BACKUP_DIR"])
    caminho = svc.fazer_backup()
    if caminho:
        return jsonify({"ok": True, "arquivo": os.path.basename(caminho)})
    return jsonify({"ok": False, "erro": "Banco de dados não encontrado."}), 500


@bp.route("/api/configuracoes/backups", methods=["GET"])
@login_required
def api_listar_backups():
    _somente_admin()
    svc = BackupService(current_app.config["BACKUP_DIR"])
    return jsonify(svc.listar())


# ── API — Tema ───────────────────────────────────────────────────────────────

@bp.route("/api/configuracoes/tema", methods=["GET"])
@login_required
def api_get_tema():
    _somente_admin()
    cfg = _cfg()
    cor = cfg.get("tema_cor", "azul")
    return jsonify({
        "modo":      cfg.get("tema_modo", "claro"),
        "cor":       cor,
        "resolvida": resolver_cor(cor),
        "sugestoes": PALETA_CORES,
    })


@bp.route("/api/configuracoes/tema", methods=["POST"])
@login_required
def api_set_tema():
    _somente_admin()
    dados = request.get_json(silent=True) or {}
    modo = dados.get("modo")
    cor = dados.get("cor", "")
    if modo not in ("claro", "escuro"):
        return jsonify({"ok": False, "erro": "Modo inválido."}), 400
    if cor not in PALETA_CORES and not hex_valido(cor):
        return jsonify({"ok": False, "erro": "Cor inválida. Use um código hexadecimal, ex: #1a4f8a."}), 400
    cfg = _cfg()
    cfg.set("tema_modo", modo)
    cfg.set("tema_cor", cor)
    return jsonify({"ok": True})


# ── API — Identidade do escritório ──────────────────────────────────────────

@bp.route("/api/configuracoes/escritorio", methods=["GET"])
@login_required
def api_get_escritorio():
    _somente_admin()
    cfg = _cfg()
    nome = cfg.get("escritorio_nome", "")
    logo = cfg.get("escritorio_logo", "")
    return jsonify({
        "nome":     nome,
        "logo":     logo,
        "logo_url": f"/static/uploads/logo/{logo}" if logo else "",
    })


@bp.route("/api/configuracoes/escritorio", methods=["POST"])
@login_required
def api_set_escritorio():
    _somente_admin()
    cfg = _cfg()
    nome = request.form.get("nome", "").strip()
    cfg.set("escritorio_nome", nome)

    if "logo" in request.files:
        arquivo = request.files["logo"]
        if arquivo and arquivo.filename:
            ext = os.path.splitext(arquivo.filename)[1].lower()
            if ext not in current_app.config["EXTENSOES_LOGO"]:
                return jsonify({"ok": False, "erro": "Formato de logo não suportado."}), 400
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
@login_required
def api_remover_logo():
    _somente_admin()
    cfg = _cfg()
    logo = cfg.get("escritorio_logo", "")
    if logo:
        _remover_logo_disco(logo, current_app.config["LOGO_DIR"])
        cfg.set("escritorio_logo", "")
    return jsonify({"ok": True})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _remover_logo_disco(nome_arquivo: str, logo_dir: str) -> None:
    caminho = os.path.join(logo_dir, nome_arquivo)
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
    except OSError:
        pass
