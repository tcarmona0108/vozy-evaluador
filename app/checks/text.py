"""Utilidades de texto: plegado de tildes que conserva posiciones y tokenización."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def plegar(texto: str) -> str:
    """Minúsculas y sin tildes, con la MISMA longitud que el original (para mapear posiciones)."""
    salida = []
    for ch in texto:
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c))
        salida.append((base if len(base) == 1 else ch).lower()[:1] or ch)
    return "".join(salida)


@dataclass(frozen=True)
class Token:
    texto: str      # plegado
    inicio: int
    fin: int


_TOKEN = re.compile(r"\$|\d+(?:[.,]\d+)*|[a-zñ]+")


def tokenizar(texto: str) -> list[Token]:
    plegado = plegar(texto)
    return [Token(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(plegado)]
