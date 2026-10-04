"""
Base para services que lidam com dado pertencente a um escritório.

Por que existir: com múltiplos escritórios compartilhando o mesmo banco,
"esquecer de filtrar uma query por escritorio_id" é o jeito mais fácil de um
escritório ver (ou editar) dado do outro. Em vez de confiar em lembrar disso
em cada um dos vários pontos de query espalhados pelos services, o
`escritorio_id` vira obrigatório no construtor — sem ele, o service nem
consegue montar uma query escopada, e o erro aparece na hora (em
desenvolvimento/teste), não em produção como um vazamento silencioso.
"""
from __future__ import annotations
from sqlalchemy.orm import Session


class TenantService:
    def __init__(self, session: Session, escritorio_id: int | None) -> None:
        self._s = session
        self.escritorio_id = escritorio_id

    def scoped(self, model):
        """
        Query do `model` já filtrada pelo escritório atual. Use isso em vez
        de `self._s.query(model)` para todo model que tem `escritorio_id`
        (Usuario, Cliente, Veiculo, RegraVencimento, TemplateRelatorio,
        LogAcao, Configuracao). Para models filhos sem escritorio_id
        próprio (Ipva, Licenciamento, Multa, Documento, IpvaParcela), faça
        join até Veiculo ou Cliente e filtre pelo escritorio_id de lá.
        """
        self._exigir_escritorio(model)
        return self._s.query(model).filter_by(escritorio_id=self.escritorio_id)

    def _exigir_escritorio(self, contexto="") -> None:
        if self.escritorio_id is None:
            nome = contexto.__name__ if isinstance(contexto, type) else contexto
            raise RuntimeError(
                f"{self.__class__.__name__}: escritorio_id não definido "
                f"(tentando usar {nome}). Toda operação que toca dado de "
                f"escritório precisa saber de qual escritório é — confira "
                f"se g.escritorio_id está setado antes de instanciar este "
                f"service."
            )


def escritorio_padrao_id(session: Session) -> int:
    """
    Id do primeiro escritório cadastrado (o mais antigo). Usado só em
    bootstrap de startup (seed de admin/configurações default), onde ainda
    não existe usuário logado para saber "de qual escritório é isso" — a
    própria migração (`aplicar_migracoes_leves`) garante que sempre existe
    pelo menos um escritório antes desse ponto rodar.
    """
    from app.models.escritorio import Escritorio
    row = session.query(Escritorio.id).order_by(Escritorio.id).first()
    if row is None:
        raise RuntimeError(
            "Nenhum escritório cadastrado — aplicar_migracoes_leves() deveria "
            "ter criado um antes deste ponto rodar."
        )
    return row[0]
