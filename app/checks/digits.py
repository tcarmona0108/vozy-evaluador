"""Extracción de los dígitos de documento que dice el cliente (en cifras o en palabras).

Soporta "4821", "48 21", "4-8-2-1", "uno, tres, cinco, dos", "cuatro ocho dos uno" y pares
("cuarenta y ocho, veintiuno"). Cada número se convierte a su cadena de dígitos y se
concatenan en orden.
"""
from __future__ import annotations

import re

from app.checks.numbers import CENTENAS, DECENAS, UNIDADES
from app.checks.text import plegar

_TOKEN = re.compile(r"\d+|[a-zñ]+")


def extraer_digitos(texto: str) -> str:
    tokens = _TOKEN.findall(plegar(texto))
    salida: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.isdigit():
            salida.append(tok)
            i += 1
            continue
        valor = None
        if tok in CENTENAS:
            valor = CENTENAS[tok]
            i += 1
            if i < len(tokens) and tokens[i] in DECENAS:
                valor += DECENAS[tokens[i]]
                i += 1
                if i + 1 < len(tokens) and tokens[i] == "y" and 1 <= UNIDADES.get(tokens[i + 1], 0) <= 9:
                    valor += UNIDADES[tokens[i + 1]]
                    i += 2
            elif i < len(tokens) and tokens[i] in UNIDADES:
                valor += UNIDADES[tokens[i]]
                i += 1
        elif tok in DECENAS:
            valor = DECENAS[tok]
            i += 1
            if i + 1 < len(tokens) and tokens[i] == "y" and 1 <= UNIDADES.get(tokens[i + 1], 0) <= 9:
                valor += UNIDADES[tokens[i + 1]]
                i += 2
        elif tok in UNIDADES:
            valor = UNIDADES[tok]
            i += 1
        else:
            i += 1
        if valor is not None:
            salida.append(str(valor))
    return "".join(salida)


def coinciden(digitos_dichos: str, esperados: str) -> bool:
    """Compara los últimos 4 dígitos dichos con los esperados (si dijo el documento completo)."""
    return len(digitos_dichos) >= 4 and digitos_dichos[-4:] == esperados
