"""
Serviço de validação de campos obrigatórios.
Todas as regras de formato ficam aqui — rotas nunca duplicam essa lógica.
"""
import re


# ── CPF ───────────────────────────────────────────────────────────────────────

def validar_cpf(cpf: str) -> bool:
    """
    Valida CPF verificando formato e dígitos verificadores.
    Aceita entrada com ou sem máscara (000.000.000-00 ou 00000000000).
    """
    apenas_digitos = re.sub(r"\D", "", cpf or "")

    if len(apenas_digitos) != 11:
        return False

    # Rejeita sequências trivialmente inválidas (111.111.111-11 etc.)
    if len(set(apenas_digitos)) == 1:
        return False

    def calcular_digito(digitos: str, pesos: range) -> int:
        soma = sum(int(d) * p for d, p in zip(digitos, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = calcular_digito(apenas_digitos[:9], range(10, 1, -1))
    d2 = calcular_digito(apenas_digitos[:10], range(11, 1, -1))

    return apenas_digitos[9] == str(d1) and apenas_digitos[10] == str(d2)


def normalizar_cpf(cpf: str) -> str:
    """Remove máscara — armazena só dígitos."""
    return re.sub(r"\D", "", cpf or "")


def formatar_cpf(cpf: str) -> str:
    """Formata 11 dígitos para exibição: 000.000.000-00."""
    d = re.sub(r"\D", "", cpf or "")
    if len(d) != 11:
        return cpf
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


# ── Telefone ──────────────────────────────────────────────────────────────────

def validar_telefone(telefone: str) -> bool:
    """
    Aceita celular (9 dígitos) e fixo (8 dígitos), ambos com DDD de 2 dígitos.
    Aceita entrada com ou sem máscara.
    """
    apenas_digitos = re.sub(r"\D", "", telefone or "")
    # DDD (2) + celular (9) = 11  |  DDD (2) + fixo (8) = 10
    return len(apenas_digitos) in (10, 11)


def normalizar_telefone(telefone: str) -> str:
    """Remove máscara — armazena só dígitos."""
    return re.sub(r"\D", "", telefone or "")


def formatar_telefone(telefone: str) -> str:
    """Formata dígitos para exibição: (00) 0000-0000 ou (00) 00000-0000."""
    d = re.sub(r"\D", "", telefone or "")
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return telefone


# ── Email ─────────────────────────────────────────────────────────────────────

# Regex baseado em RFC 5321/5322, simplificado mas robusto para uso prático.
# Exige pelo menos um ponto no domínio (rejeita nome@dominio sem TLD).
_RE_EMAIL = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


def validar_email(email: str) -> bool:
    return bool(_RE_EMAIL.match(email or ""))


# ── Placa ─────────────────────────────────────────────────────────────────────

# Mercosul: 3 letras + 1 dígito + 1 letra + 2 dígitos  (ABC1D23)
# Padrão antigo: 3 letras + hífen opcional + 4 dígitos  (ABC-1234 ou ABC1234)
_RE_PLACA_MERCOSUL = re.compile(r"^[A-Z]{3}\d[A-Z]\d{2}$")
_RE_PLACA_ANTIGA   = re.compile(r"^[A-Z]{3}-?\d{4}$")


def validar_placa(placa: str) -> bool:
    p = (placa or "").upper().strip()
    return bool(_RE_PLACA_MERCOSUL.match(p) or _RE_PLACA_ANTIGA.match(p))


def normalizar_placa(placa: str) -> str:
    """Remove hífen e converte para maiúsculas — padrão de armazenamento."""
    return re.sub(r"-", "", (placa or "").upper().strip())


# ── Validação combinada para clientes ─────────────────────────────────────────

def validar_campos_cliente(dados: dict) -> str:
    """
    Valida todos os campos obrigatórios de um cliente.
    Retorna mensagem de erro ou string vazia se tudo estiver correto.
    """
    cpf = dados.get("cpf", "")
    telefone = dados.get("telefone", "")
    email = dados.get("email", "")

    if not dados.get("nome", "").strip():
        return "Nome é obrigatório."
    if not cpf.strip():
        return "CPF é obrigatório."
    if not validar_cpf(cpf):
        return "CPF inválido. Verifique o formato e os dígitos verificadores."
    if not telefone.strip():
        return "Telefone é obrigatório."
    if not validar_telefone(telefone):
        return "Telefone inválido. Use (DDD) + número com 8 ou 9 dígitos."
    if not email.strip():
        return "E-mail é obrigatório."
    if not validar_email(email):
        return "E-mail inválido."
    return ""


def validar_campos_veiculo(dados: dict) -> str:
    """
    Valida campos obrigatórios de um veículo.
    Retorna mensagem de erro ou string vazia.
    """
    placa = dados.get("placa", "")
    if not placa.strip():
        return "Placa é obrigatória."
    if not validar_placa(placa):
        return "Placa inválida. Use o formato Mercosul (ABC1D23) ou padrão antigo (ABC-1234)."
    if not dados.get("renavam", "").strip():
        return "RENAVAM é obrigatório."
    if not dados.get("marca_modelo", "").strip():
        return "Marca/Modelo é obrigatório."
    if not dados.get("proprietario", "").strip():
        return "Proprietário é obrigatório."
    return ""
