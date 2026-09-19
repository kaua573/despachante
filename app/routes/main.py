from flask import Blueprint, render_template, jsonify, send_from_directory, current_app, request
from flask_login import login_required, current_user
from app import db
from app.services.dashboard_service import DashboardService

bp = Blueprint("main", __name__)


@bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@bp.route("/dashboard/geral")
@login_required
def dashboard_geral():
    return render_template("dashboard_geral.html")


@bp.route("/api/dashboard")
@login_required
def api_dashboard():
    svc = DashboardService(db.session)
    return jsonify(svc.resumo())


@bp.route("/api/dashboard/geral")
@login_required
def api_dashboard_geral():
    svc = DashboardService(db.session)
    return jsonify(svc.resumo_geral())


@bp.route("/api/busca-global")
@login_required
def api_busca_global():
    """Busca rápida usada pela caixa de pesquisa do topo — cliente por
    nome/CPF/CNPJ e veículo por placa, cada um só entra no resultado se o
    usuário logado tiver a permissão de visualização correspondente."""
    termo = (request.args.get("q") or "").strip()
    resultado = {"clientes": [], "veiculos": []}
    if len(termo) < 2:
        return jsonify(resultado)

    like = f"%{termo}%"

    if current_user.tem_permissao("visualizar_clientes"):
        from app.models.cliente import Cliente
        clientes = (
            db.session.query(Cliente)
            .filter(db.or_(Cliente.nome.ilike(like), Cliente.cpf.ilike(like), Cliente.cnpj.ilike(like)))
            .order_by(Cliente.nome)
            .limit(8)
            .all()
        )
        resultado["clientes"] = [
            {"id": c.id, "nome": c.nome, "documento": c.cpf or c.cnpj or ""}
            for c in clientes
        ]

    if current_user.tem_permissao("visualizar_veiculos"):
        from app.models.veiculo import Veiculo
        from app.models.cliente import Cliente
        veiculos = (
            db.session.query(Veiculo)
            .join(Cliente, Veiculo.cliente_id == Cliente.id)
            .filter(Veiculo.placa.ilike(like))
            .order_by(Veiculo.placa)
            .limit(8)
            .all()
        )
        resultado["veiculos"] = [
            {"id": v.id, "placa": v.placa, "cliente_id": v.cliente_id, "cliente_nome": v.cliente.nome}
            for v in veiculos
        ]

    return jsonify(resultado)


@bp.route("/static/uploads/documentos/<nome>")
@login_required
def baixar_documento(nome):
    return send_from_directory(current_app.config["UPLOAD_DIR"], nome, as_attachment=True)


@bp.route("/static/uploads/logo/<nome>")
def logo_arquivo(nome):
    # Rota dedicada (não é o /static automático do Flask): a logo é enviada
    # pelo usuário em tempo de execução e fica em LOGO_DIR, que no .exe
    # empacotado mora na pasta "dados", fora da pasta estática somente-leitura
    # do bundle. Mantém a mesma URL de sempre para não quebrar templates.
    return send_from_directory(current_app.config["LOGO_DIR"], nome)
