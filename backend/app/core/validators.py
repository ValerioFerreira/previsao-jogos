"""Validação e normalização de CPF e telefone (Brasil)."""
from __future__ import annotations

import re


def normalize_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf or "")


def is_valid_cpf(cpf: str) -> bool:
    """Valida CPF pela regra oficial dos dígitos verificadores."""
    cpf = normalize_cpf(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    def _dv(base: str) -> int:
        weight = len(base) + 1
        total = sum(int(d) * (weight - i) for i, d in enumerate(base))
        rem = (total * 10) % 11
        return 0 if rem == 10 else rem

    return _dv(cpf[:9]) == int(cpf[9]) and _dv(cpf[:10]) == int(cpf[10])


def normalize_phone(phone: str) -> str:
    """Normaliza para dígitos, removendo o DDI 55 quando presente (guarda DDD+numero)."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    return digits


def is_valid_phone(phone: str) -> bool:
    """Telefone BR: DDD (2) + número (8 fixo ou 9 celular) = 10 ou 11 dígitos;
    se celular (11), o terceiro dígito deve ser 9."""
    d = normalize_phone(phone)
    if len(d) not in (10, 11):
        return False
    ddd = int(d[:2])
    if ddd < 11 or ddd > 99:
        return False
    if len(d) == 11 and d[2] != "9":
        return False
    return True
