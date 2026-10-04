"""
Serviço de configurações do sistema.
Centraliza leitura/escrita de configurações, paleta de cores e fontes PDF.
"""
from __future__ import annotations
import logging
import os
import re
from typing import Optional
from sqlalchemy.orm import Session

from app.models.configuracao import Configuracao
from app.services.base import TenantService

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

# Valores padrão de fábrica para todas as chaves de configuração
DEFAULTS: dict[str, str] = {
    "senha_exclusao":            "0000",
    "backup_intervalo_min":      "30",
    "tema_modo":                 "claro",
    "tema_cor":                  "azul",
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


def nome_arquivo_logo(escritorio_id: int, extensao: str) -> str:
    """
    Nome do arquivo de logo de um escritório: `logo-<id>.<ext>`.

    Antes era sempre `logo.<ext>`, igual para todos os escritórios — o upload
    de um sobrescrevia a logo do outro. O id no nome garante um arquivo por
    escritório. `extensao` deve vir já validada contra EXTENSOES_LOGO.
    """
    return f"logo-{int(escritorio_id)}{extensao.lower()}"


def logo_em_uso(session: Session, nome_arquivo: str) -> bool:
    """True se algum escritório ainda aponta para este arquivo de logo."""
    return (
        session.query(Configuracao)
        .filter(Configuracao.chave == "escritorio_logo", Configuracao.valor == nome_arquivo)
        .first()
        is not None
    )


def remover_logo_se_orfa(session: Session, logo_dir: str, nome_arquivo: str) -> bool:
    """
    Apaga o arquivo de logo do disco SÓ se nenhum escritório o referencia.

    Instalações antigas têm um `logo.png` compartilhado por vários escritórios;
    apagá-lo "por ser a logo anterior de X" tiraria a logo dos outros. Chamar
    depois de já ter atualizado/removido a referência do escritório atual.
    Devolve True se removeu.
    """
    # Nunca sai da pasta de logos, mesmo se o valor guardado vier adulterado.
    if not nome_arquivo or os.path.basename(nome_arquivo) != nome_arquivo:
        return False
    if logo_em_uso(session, nome_arquivo):
        return False
    caminho = os.path.join(logo_dir, nome_arquivo)
    try:
        if os.path.exists(caminho):
            os.remove(caminho)
            return True
    except OSError:
        logging.getLogger(__name__).warning("Não foi possível remover a logo %s", nome_arquivo)
    return False


class ConfiguracaoService(TenantService):
    def __init__(self, session: Session, escritorio_id: int) -> None:
        super().__init__(session, escritorio_id)

    def get(self, chave: str, padrao: Optional[str] = None) -> Optional[str]:
        row = self._s.get(Configuracao, (self.escritorio_id, chave))
        if row is not None:
            return row.valor
        return DEFAULTS.get(chave, padrao)

    def set(self, chave: str, valor: str) -> None:
        row = self._s.get(Configuracao, (self.escritorio_id, chave))
        if row is None:
            row = Configuracao(escritorio_id=self.escritorio_id, chave=chave, valor=str(valor))
            self._s.add(row)
        else:
            row.valor = str(valor)
        self._s.commit()

    def seed_defaults(self) -> None:
        """Insere valores padrão para chaves ainda não existentes no banco."""
        for chave, valor in DEFAULTS.items():
            if self._s.get(Configuracao, (self.escritorio_id, chave)) is None:
                self._s.add(Configuracao(escritorio_id=self.escritorio_id, chave=chave, valor=valor))
        self._s.commit()

    def senha_ok(self, senha: str) -> bool:
        return senha == self.get("senha_exclusao", "0000")

    def trocar_senha(self, senha_atual: str, nova_senha: str) -> tuple[bool, str]:
        if not self.senha_ok(senha_atual):
            return False, "Senha atual incorreta."
        if not nova_senha or len(nova_senha) < 4:
            return False, "A nova senha deve ter ao menos 4 caracteres."
        self.set("senha_exclusao", nova_senha)
        return True, ""
