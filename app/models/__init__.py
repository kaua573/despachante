from app.models.cliente import Cliente
from app.models.veiculo import Veiculo
from app.models.ipva import Ipva
from app.models.ipva_parcela import IpvaParcela
from app.models.licenciamento import Licenciamento
from app.models.multa import Multa
from app.models.documento import Documento
from app.models.configuracao import Configuracao
from app.models.template_relatorio import TemplateRelatorio
from app.models.usuario import Usuario
from app.models.permissao_usuario import PermissaoUsuario
from app.models.log_acao import LogAcao

__all__ = [
    "Cliente", "Veiculo", "Ipva", "IpvaParcela",
    "Licenciamento", "Multa", "Documento",
    "Configuracao", "TemplateRelatorio",
    "Usuario", "PermissaoUsuario", "LogAcao",
]
