from flask import Blueprint, render_template, jsonify, send_from_directory, current_app
from flask_login import login_required
from app import db
from app.services.dashboard_service import DashboardService

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@bp.route("/api/dashboard")
@login_required
def api_dashboard():
    svc = DashboardService(db.session)
    return jsonify(svc.resumo())


@bp.route("/static/uploads/documentos/<nome>")
@login_required
def baixar_documento(nome):
    return send_from_directory(current_app.config["UPLOAD_DIR"], nome, as_attachment=True)


@bp.route("/static/uploads/logo/<nome>")
def logo_arquivo(nome):
    # Rota dedicada (não é o /static automático do Flask): a logo é enviada
    # pelo usuário em tempo de execução e fica em LOGO_DIR, que no .exe
    # empacotado mora em %APPDATA%, fora da pasta estática somente-leitura
    # do bundle. Mantém a mesma URL de sempre para não quebrar templates.
    return send_from_directory(current_app.config["LOGO_DIR"], nome)
