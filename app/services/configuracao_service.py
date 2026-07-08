"""
Serviço de configurações do sistema.
Centraliza leitura/escrita de configurações, paleta de cores e fontes PDF.
"""
from __future__ import annotations
import re
from typing import Optional
from sqlalchemy.orm import Session

from app.models.configuracao import Configuracao

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# ── Paleta compartilhada entre tema web e PDF ──────────────────────────────
# Continuam existindo como sugestões de clique rápido na interface, mas deixaram
# de ser as únicas cores aceitas — qualquer hexadecimal válido pode ser usado.
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


# ── Utilitários de cor (espectro livre + contraste automático) ──────────────

def hex_valido(cor: Optional[str]) -> bool:
    """Valida o formato #RRGGBB."""
    return bool(cor) and bool(_HEX_RE.match(cor))


def _clamp(v: int) -> int:
    return max(0, min(255, v))


def variar_cor(cor_hex: str, fator: float) -> str:
    """Clareia (fator > 0) ou escurece (fator < 0) uma cor hex. fator vai de -1 a 1.
    Usada para derivar automaticamente a cor 'secundária' a partir da cor escolhida
    pelo usuário, sem exigir um segundo seletor."""
    h = cor_hex.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if fator >= 0:
        r, g, b = (_clamp(int(c + (255 - c) * fator)) for c in (r, g, b))
    else:
        r, g, b = (_clamp(int(c * (1 + fator))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _luminancia_relativa(cor_hex: str) -> float:
    """Luminância relativa (fórmula WCAG 2.0), usada para decidir contraste."""
    h = cor_hex.lstrip("#")
    canais = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        canais.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canais
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def cor_contraste_solida(cor_hex: str) -> str:
    """Retorna a cor de texto/ícone (branco ou escuro) com melhor leitura sobre `cor_hex`."""
    return "#1c2333" if _luminancia_relativa(cor_hex) > 0.5 else "#ffffff"


def resolver_cor(cor: Optional[str]) -> dict:
    """
    Resolve uma cor configurada — hexadecimal livre ou uma das chaves antigas
    da paleta fixa, mantidas por compatibilidade com bancos já existentes —
    em um conjunto pronto para uso: principal, secundária (derivada
    automaticamente) e variantes de contraste para texto/ícones.
    """
    principal = PALETA_CORES[cor]["principal"] if cor in PALETA_CORES else cor
    if not hex_valido(principal):
        principal = PALETA_CORES["azul"]["principal"]
    secundaria = variar_cor(principal, 0.18)

    def _variantes(fundo: str) -> dict:
        contraste = cor_contraste_solida(fundo)
        rgb = "28,35,51" if contraste == "#1c2333" else "255,255,255"
        return {
            "solida": contraste,
            "forte":  f"rgba({rgb},.9)",
            "medio":  f"rgba({rgb},.75)",
            "fraco":  f"rgba({rgb},.15)",
        }

    c_principal  = _variantes(principal)
    c_secundaria = _variantes(secundaria)
    return {
        "principal":  principal,
        "secundaria": secundaria,
        # Contraste calculado sobre a cor principal (usada como fundo do menu
        # no modo claro) e sobre a secundária (fundo do menu no modo escuro),
        # garantindo que texto/ícones fiquem legíveis em qualquer cor escolhida.
        "contraste":             c_principal["solida"],
        "contraste_forte":       c_principal["forte"],
        "contraste_medio":       c_principal["medio"],
        "contraste_fraco":       c_principal["fraco"],
        "contraste_sec":         c_secundaria["solida"],
        "contraste_sec_forte":   c_secundaria["forte"],
        "contraste_sec_medio":   c_secundaria["medio"],
        "contraste_sec_fraco":   c_secundaria["fraco"],
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
