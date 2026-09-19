from datetime import datetime
from app import db


class LogAcao(db.Model):
    __tablename__ = "log_acao"

    id          = db.Column(db.Integer, primary_key=True)
    usuario_id  = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    # Nome do usuário "congelado" no momento do registro — garante que o
    # log continue mostrando quem fez o quê mesmo que o usuário seja
    # excluído depois (usuario_id vira NULL, mas o nome permanece).
    usuario_nome = db.Column(db.String(100), nullable=True)
    acao        = db.Column(db.String(100), nullable=False)
    entidade    = db.Column(db.String(50), nullable=True)
    entidade_id = db.Column(db.Integer, nullable=True)
    detalhe     = db.Column(db.Text, nullable=True)
    ip          = db.Column(db.String(45), nullable=True)
    criado_em   = db.Column(db.DateTime, default=datetime.now)

    # Corrente de hashes (estilo "blockchain" simples): cada registro guarda
    # o hash do registro anterior + um hash próprio calculado a partir do
    # seu conteúdo. Alterar ou apagar um registro no meio da corrente quebra
    # a sequência de forma detectável — ver LogService.verificar_integridade().
    # Registros gravados ANTES dessa coluna existir ficam com hash NULL
    # (não são verificáveis, mas não invalidam o restante da corrente).
    #
    # `hash_anterior` é UNIQUE de propósito: é o que impede duas gravações
    # concorrentes (rede local com várias máquinas) de "bifurcarem" a
    # corrente reivindicando o mesmo pai ao mesmo tempo — a segunda gravação
    # esbarra na constraint e tenta de novo com o pai atualizado
    # (LogService.registrar já trata esse retry).
    hash_anterior = db.Column(db.String(64), nullable=True, unique=True)
    hash_atual    = db.Column(db.String(64), nullable=True, unique=True)
