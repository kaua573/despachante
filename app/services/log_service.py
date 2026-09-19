"""
Serviço de log de ações.
Centraliza o registro de toda ação relevante no sistema.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from datetime import datetime
from typing import Any, Optional

from flask import request
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.log_acao import LogAcao

logger = logging.getLogger(__name__)

# Hash "raiz" — pai do primeiro registro que já existir com corrente ativa.
HASH_GENESIS = "0" * 64

# Quantas vezes tenta regravar se outra máquina da rede local gravou um
# registro no meio do caminho (mesmo "pai" disputado por duas gravações
# concorrentes) — normal em uma instalação com várias estações.
_TENTATIVAS_HASH = 8


class LogService:
    def __init__(self, session: Session) -> None:
        self._s = session

    @staticmethod
    def _calcular_hash(
        hash_anterior: str, usuario_id, acao: str, entidade, entidade_id,
        detalhe_str, criado_em: datetime,
    ) -> str:
        base = "|".join([
            hash_anterior,
            str(usuario_id or ""),
            acao,
            str(entidade or ""),
            str(entidade_id or ""),
            detalhe_str or "",
            criado_em.isoformat(),
        ])
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def registrar(
        self,
        acao: str,
        entidade: Optional[str] = None,
        entidade_id: Optional[int] = None,
        detalhe: Optional[Any] = None,
    ) -> None:
        """
        Registra uma ação no log.

        Args:
            acao: código da ação (ex: 'criar_veiculo', 'login')
            entidade: nome da entidade afetada (ex: 'veiculo', 'cliente')
            entidade_id: PK do registro afetado
            detalhe: dado extra — será serializado como JSON se for dict/list

        Cada registro encadeia um hash com o do registro anterior (ver
        `verificar_integridade`). Isso nunca deve impedir a ação de negócio
        que originou o log: qualquer falha aqui é registrada no logger do
        Python e engolida, sem propagar exceção pra fora.
        """
        usuario_id = None
        usuario_nome = None
        if current_user and current_user.is_authenticated:
            usuario_id = current_user.id
            usuario_nome = current_user.nome_completo

        ip = request.remote_addr if request else None

        detalhe_str = None
        if detalhe is not None:
            detalhe_str = json.dumps(detalhe, ensure_ascii=False) if isinstance(detalhe, (dict, list)) else str(detalhe)

        criado_em = datetime.now()

        for tentativa in range(_TENTATIVAS_HASH):
            ultimo = self._s.query(LogAcao).order_by(LogAcao.id.desc()).first()
            hash_anterior = ultimo.hash_atual if (ultimo and ultimo.hash_atual) else HASH_GENESIS
            hash_atual = self._calcular_hash(
                hash_anterior, usuario_id, acao, entidade, entidade_id, detalhe_str, criado_em,
            )
            self._s.add(LogAcao(
                usuario_id=usuario_id,
                usuario_nome=usuario_nome,
                acao=acao,
                entidade=entidade,
                entidade_id=entidade_id,
                detalhe=detalhe_str,
                ip=ip,
                criado_em=criado_em,
                hash_anterior=hash_anterior,
                hash_atual=hash_atual,
            ))
            try:
                self._s.commit()
                return
            except IntegrityError:
                # Duas gravações concorrentes disputaram o mesmo "pai" — tenta
                # de novo com o hash mais recente (outra máquina da rede local
                # gravou entre a leitura e o commit). Um pequeno atraso
                # aleatório reduz a chance de duas tentativas colidirem de novo.
                self._s.rollback()
                time.sleep(random.uniform(0.01, 0.05) * (tentativa + 1))
                continue

        # Esgotou as tentativas de encadear: grava mesmo assim, sem hash,
        # pra nunca perder o registro da ação em si por causa da corrente.
        logger.warning("Não foi possível encadear o hash do log de ações após %s tentativas (acao=%s)", _TENTATIVAS_HASH, acao)
        self._s.add(LogAcao(
            usuario_id=usuario_id, usuario_nome=usuario_nome, acao=acao, entidade=entidade,
            entidade_id=entidade_id, detalhe=detalhe_str, ip=ip, criado_em=criado_em,
        ))
        self._s.commit()

    def verificar_integridade(self) -> dict:
        """
        Percorre a corrente de hashes em ordem e confirma que cada registro
        aponta pro hash do anterior e que o conteúdo de cada um ainda bate
        com o hash gravado na hora da criação.

        Registros antigos, gravados antes dessa coluna existir, ficam de
        fora da verificação (hash_atual NULL) — não contam como violação,
        só como "não verificável".
        """
        registros = (
            self._s.query(LogAcao)
            .filter(LogAcao.hash_atual.isnot(None))
            .order_by(LogAcao.id.asc())
            .all()
        )
        total_sem_hash = self._s.query(LogAcao).filter(LogAcao.hash_atual.is_(None)).count()

        esperado = HASH_GENESIS
        for r in registros:
            if r.hash_anterior != esperado:
                return {
                    "integro": False,
                    "motivo": f"O registro #{r.id} não encaixa na sequência esperada — indício de registro apagado, "
                              f"inserido fora de ordem ou alterado.",
                    "registro_id": r.id,
                }
            recalculado = self._calcular_hash(
                r.hash_anterior, r.usuario_id, r.acao, r.entidade, r.entidade_id, r.detalhe, r.criado_em,
            )
            if recalculado != r.hash_atual:
                return {
                    "integro": False,
                    "motivo": f"O conteúdo do registro #{r.id} foi alterado depois de criado.",
                    "registro_id": r.id,
                }
            esperado = r.hash_atual

        return {
            "integro": True,
            "motivo": "Nenhuma alteração detectada na corrente de registros.",
            "total_verificado": len(registros),
            "total_legado_sem_hash": total_sem_hash,
        }

    # Campos que nunca fazem sentido aparecer no diff (ruído, não "alteração").
    _CAMPOS_IGNORADOS_DIFF = {"id", "criado_em", "num_parcelas"}

    def registrar_alteracao(
        self,
        acao: str,
        entidade: str,
        entidade_id: Optional[int],
        antes: Optional[dict] = None,
        depois: Optional[dict] = None,
        campos_ignorar: Optional[set] = None,
    ) -> None:
        """
        Registra uma ação guardando o estado ANTES e DEPOIS do registro
        afetado, para a tela de log mostrar exatamente o que mudou campo a
        campo — não só "editou o veículo X".

        - Só `depois` informado → tratado como criação.
        - Só `antes` informado → tratado como exclusão.
        - Os dois informados → tratado como edição; `alterado` traz somente
          os campos que de fato mudaram (ignora ruído como id/criado_em).
        """
        ignorar = self._CAMPOS_IGNORADOS_DIFF | (campos_ignorar or set())
        detalhe: dict = {}

        if antes is not None and depois is not None:
            alterado = {}
            for chave in set(antes) | set(depois):
                if chave in ignorar:
                    continue
                va, vd = antes.get(chave), depois.get(chave)
                if va != vd:
                    alterado[chave] = {"antes": va, "depois": vd}
            detalhe = {"tipo": "edicao", "alterado": alterado}
        elif depois is not None:
            detalhe = {"tipo": "criacao", "depois": {k: v for k, v in depois.items() if k not in ignorar}}
        elif antes is not None:
            detalhe = {"tipo": "exclusao", "antes": {k: v for k, v in antes.items() if k not in ignorar}}

        self.registrar(acao, entidade, entidade_id, detalhe or None)

    def listar(
        self,
        usuario_id: Optional[int] = None,
        acao: Optional[str] = None,
        entidade: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        pagina: int = 1,
        por_pagina: int = 50,
    ) -> dict:
        """Retorna registros paginados com filtros opcionais."""
        from app.models.usuario import Usuario
        from datetime import datetime

        q = self._s.query(LogAcao)
        if usuario_id:
            q = q.filter(LogAcao.usuario_id == usuario_id)
        if acao:
            q = q.filter(LogAcao.acao.ilike(f"%{acao}%"))
        if entidade:
            q = q.filter(LogAcao.entidade == entidade)
        if data_inicio:
            try:
                q = q.filter(LogAcao.criado_em >= datetime.fromisoformat(data_inicio))
            except ValueError:
                pass
        if data_fim:
            try:
                q = q.filter(LogAcao.criado_em <= datetime.fromisoformat(data_fim + "T23:59:59"))
            except ValueError:
                pass

        total = q.count()
        registros = q.order_by(LogAcao.criado_em.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "registros": registros,
            "total": total,
            "pagina": pagina,
            "paginas": (total + por_pagina - 1) // por_pagina,
        }
