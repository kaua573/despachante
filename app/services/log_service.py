"""
Serviço de log de ações.
Centraliza o registro de toda ação relevante no sistema.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from flask import request
from flask_login import current_user
from sqlalchemy.orm import Session

from app.models.log_acao import LogAcao


class LogService:
    def __init__(self, session: Session) -> None:
        self._s = session

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
        """
        usuario_id = None
        if current_user and current_user.is_authenticated:
            usuario_id = current_user.id

        ip = request.remote_addr if request else None

        detalhe_str = None
        if detalhe is not None:
            detalhe_str = json.dumps(detalhe, ensure_ascii=False) if isinstance(detalhe, (dict, list)) else str(detalhe)

        self._s.add(LogAcao(
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            detalhe=detalhe_str,
            ip=ip,
        ))
        self._s.commit()

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
