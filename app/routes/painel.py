from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required
from app import db
from app.models.veiculo import Veiculo
from app.models.cliente import Cliente
from app.services.auth_service import requer_permissao

bp = Blueprint("painel", __name__)


@bp.route("/veiculos/<int:vid>/painel")
@login_required
@requer_permissao("visualizar_veiculos")
def painel(vid):
    v = db.session.get(Veiculo, vid)
    if not v:
        return redirect(url_for("clientes.clientes"))
    cliente = db.session.get(Cliente, v.cliente_id)
    dados = v.to_dict()
    dados["cliente_nome"] = cliente.nome if cliente else ""
    return render_template("painel.html", veiculo=dados)
