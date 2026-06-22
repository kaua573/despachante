"""
Serviço de configurações do sistema.
Centraliza leitura/escrita de configurações, paleta de cores e fontes PDF.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session

from app.models.configuracao import Configuracao

# ── Paleta compartilhada entre tema web e PDF ──────────────────────────────
PALETA_CORES: dict[str, dict] = {
    "azul":     {"nome": "Azul",     "principal": "#1a4f8a", "secundaria": "#2563ae"},
    "vermelho": {"nome": "Vermelho", "principal": "#9a2424", "secundaria": "#c0392b"},
    "verde":    {"nome": "Verde",    "principal": "#1a6b40", "secundaria": "#218c52"},
    "amarelo":  {"nome": "Amarelo",  "principal": "#92650a", "secundaria": "#b8860b"},
    "roxo":     {"nome": "Roxo",     "principal": "#5b3a8a", "secundaria": "#7448ad"},
    "laranja":  {"nome": "Laranja",  "principal": "#a04a14", "secundaria": "#c8631e"},
}

FONTES_PDF: dict[str, dict] = {
    "moderna":  {"nome": "Moderna (sem serifa)",    "base": "Helvetica",   "bold": "Helvetica-Bold"},
    "classica": {"nome": "Clássica (serifada)",     "base": "Times-Roman", "bold": "Times-Bold"},
    "tecnica":  {"nome": "Técnica (monoespaçada)",  "base": "Courier",     "bold": "Courier-Bold"},
}

TAMANHOS_PDF: dict[str, dict] = {
    "pequeno": {"nome": "Pequeno", "titulo": 15, "secao": 10, "texto": 8,  "mini": 7},
    "medio":   {"nome": "Médio",   "titulo": 18, "secao": 12, "texto": 10, "mini": 8},
    "grande":  {"nome": "Grande",  "titulo": 21, "secao": 14, "texto": 12, "mini": 9},
}

# Valores padrão de fábrica para todas as chaves de configuração
DEFAULTS: dict[str, str] = {
    "senha_exclusao":            "0000",
    "backup_intervalo_min":      "30",
    "tema_modo":                 "claro",
    "tema_cor":                  "azul",
    "pdf_fonte":                 "moderna",
    "pdf_tamanho":               "medio",
    "pdf_cor":                   "azul",
    "pdf_cor_texto":             "escuro",
    "pdf_mostrar_data_geracao":  "1",
    "pdf_espacamento":           "espacada",
    "pdf_ordem_blocos":          "dados_primeiro",
    "pdf_nome_escritorio":       "",
    "escritorio_nome":           "",
    "escritorio_logo":           "",
}


class ConfiguracaoService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, chave: str, padrao: Optional[str] = None) -> Optional[str]:
        row = self._session.get(Configuracao, chave)
        if row is not None:
            return row.valor
        return DEFAULTS.get(chave, padrao)

    def set(self, chave: str, valor: str) -> None:
        row = self._session.get(Configuracao, chave)
        if row is None:
            row = Configuracao(chave=chave, valor=str(valor))
            self._session.add(row)
        else:
            row.valor = str(valor)
        self._session.commit()

    def seed_defaults(self) -> None:
        """Insere valores padrão para chaves ainda não existentes no banco."""
        for chave, valor in DEFAULTS.items():
            if self._session.get(Configuracao, chave) is None:
                self._session.add(Configuracao(chave=chave, valor=valor))
        self._session.commit()

    def senha_ok(self, senha: str) -> bool:
        return senha == self.get("senha_exclusao", "0000")

    def trocar_senha(self, senha_atual: str, nova_senha: str) -> tuple[bool, str]:
        if not self.senha_ok(senha_atual):
            return False, "Senha atual incorreta."
        if not nova_senha or len(nova_senha) < 4:
            return False, "A nova senha deve ter ao menos 4 caracteres."
        self.set("senha_exclusao", nova_senha)
        return True, ""
