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
