"""Parser de números en español (palabras y cifras) y detección de montos en pesos.

Alcance: enteros hasta los miles de millones dichos en palabras ("un millón doscientos cincuenta
mil"), cifras con separadores de miles ("$1.250.000", "1,250,000"), decimales con multiplicador
("2,4 millones") y mezclas ("1 millón 250 mil"). No cubre fracciones ni "millón y medio" con
otras variantes coloquiales.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.checks.text import Token, tokenizar

UNIDADES: dict[str, int] = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
DECENAS: dict[str, int] = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
    "ochenta": 80, "noventa": 90,
}
CENTENAS: dict[str, int] = {
    "cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300,
    "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500,
    "quinientas": 500, "seiscientos": 600, "seiscientas": 600, "setecientos": 700,
    "setecientas": 700, "ochocientos": 800, "ochocientas": 800, "novecientos": 900,
    "novecientas": 900,
}
MULTIPLICADORES: dict[str, int] = {"mil": 1_000, "millon": 1_000_000, "millones": 1_000_000}
PALABRAS_NUMERO: dict[str, int] = {**UNIDADES, **DECENAS, **CENTENAS}

_MILES = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_DECIMAL = re.compile(r"^\d+[.,]\d{1,2}$")


def valor_cifra(tok: str) -> float | None:
    """'1.250.000' -> 1250000; '2,4' -> 2.4; '4821' -> 4821."""
    if _MILES.match(tok):
        return int(re.sub(r"[.,]", "", tok))
    if _DECIMAL.match(tok):
        return float(tok.replace(",", "."))
    if tok.isdigit():
        return int(tok)
    return None


def es_token_numerico(tok: str) -> bool:
    return tok in PALABRAS_NUMERO or tok in MULTIPLICADORES or valor_cifra(tok) is not None


def palabras_a_numero(tokens: list[str]) -> int | None:
    """Convierte una secuencia de tokens numéricos (ya plegados) en un entero."""
    total = 0.0
    actual = 0.0
    vistos = False
    for tok in tokens:
        if tok in ("y", "de"):
            continue
        if tok in PALABRAS_NUMERO:
            actual += PALABRAS_NUMERO[tok]
        elif tok == "mil":
            actual = (actual or 1) * 1_000
        elif tok in ("millon", "millones"):
            total += (actual or 1) * 1_000_000
            actual = 0
        else:
            v = valor_cifra(tok)
            if v is None:
                return None
            actual += v
        vistos = True
    if not vistos:
        return None
    return int(round(total + actual))


def parse_numero(texto: str) -> int | None:
    """Parsea un texto que contiene SOLO un número ('un millón cincuenta mil', '$1.250.000')."""
    toks = [t.texto for t in tokenizar(texto) if t.texto not in ("$", "pesos", "cop")]
    return palabras_a_numero(toks)


@dataclass(frozen=True)
class Monto:
    valor: int
    texto: str
    inicio: int
    fin: int


def _corridas(tokens: list[Token]) -> list[tuple[int, int]]:
    """Índices [i, j) de corridas maximales de tokens numéricos (con 'y'/'de' internos)."""
    corridas = []
    i = 0
    while i < len(tokens):
        if not es_token_numerico(tokens[i].texto):
            i += 1
            continue
        j = i + 1
        while j < len(tokens):
            t = tokens[j].texto
            if es_token_numerico(t):
                j += 1
            elif t == "y" and j + 1 < len(tokens) and tokens[j + 1].texto in PALABRAS_NUMERO:
                j += 1
            elif (t == "de" and j + 1 < len(tokens) and tokens[j + 1].texto in ("pesos", "cop")
                  and tokens[j - 1].texto in ("millon", "millones")):
                break
            else:
                break
        corridas.append((i, j))
        i = j
    return corridas


def encontrar_montos(texto: str, minimo_sin_moneda: int = 10_000) -> list[Monto]:
    """Montos de dinero en un texto, en orden de aparición.

    Una corrida numérica es monto si va precedida de '$', seguida de 'pesos'/'COP' (con 'de'
    opcional) o si su valor es >= minimo_sin_moneda (evita confundir días, horas o dígitos).
    """
    tokens = tokenizar(texto)
    montos: list[Monto] = []
    for i, j in _corridas(tokens):
        valor = palabras_a_numero([t.texto for t in tokens[i:j]])
        if valor is None:
            continue
        previo = tokens[i - 1].texto if i > 0 else ""
        sig = [t.texto for t in tokens[j:j + 2]]
        con_moneda = previo == "$" or (sig[:1] and sig[0] in ("pesos", "cop")) or sig == ["de", "pesos"]
        if con_moneda or valor >= minimo_sin_moneda:
            inicio = tokens[i - 1].inicio if previo == "$" else tokens[i].inicio
            fin = tokens[j - 1].fin
            montos.append(Monto(valor, texto[inicio:fin], inicio, fin))
    return montos
