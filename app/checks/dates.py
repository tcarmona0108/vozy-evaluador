"""Detección y resolución de fechas en español y validación del plazo de R5."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from app.checks.numbers import UNIDADES
from app.checks.text import plegar

MESES: dict[str, int] = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
DIAS_SEMANA: dict[str, int] = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
}
NOMBRES_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIA_PALABRA = {**{k: v for k, v in UNIDADES.items() if 1 <= v <= 29}, "primero": 1,
                "treinta": 30, "treintaiuno": 31}

_P_MES = "|".join(MESES)
_P_SEM = "|".join(DIAS_SEMANA)
_P_DIA = r"\d{1,2}|" + "|".join(sorted(_DIA_PALABRA, key=len, reverse=True)) + r"|treinta y uno"

# "15 de septiembre", "el 4 de octubre de 2026", "sábado 26 de septiembre"
RE_DIA_MES = re.compile(rf"\b(?:(?P<sem>{_P_SEM})\s+)?(?P<dia>{_P_DIA})\s+de\s+(?P<mes>{_P_MES})"
                        rf"(?:\s+(?:de|del)\s+(?P<anio>\d{{4}}))?\b")
# "25/09", "25-09-2026"
RE_NUMERICA = re.compile(r"\b(?P<dia>\d{1,2})[/-](?P<mes>\d{1,2})(?:[/-](?P<anio>\d{2,4}))?\b")
# "sábado 26", "el 27"
RE_DIA_SOLO = re.compile(rf"\b(?:(?P<sem>{_P_SEM})\s+(?P<dia1>{_P_DIA})|el\s+(?P<dia2>\d{{1,2}}))\b")
RE_SEMANA = re.compile(rf"\b(?P<sem>{_P_SEM})\b")
RE_RELATIVA = re.compile(r"\b(?P<rel>pasado manana|manana|hoy)\b")


def _dia(token: str) -> int | None:
    token = token.strip()
    if token == "treinta y uno":
        return 31
    if token.isdigit():
        return int(token)
    return _DIA_PALABRA.get(token)


@dataclass(frozen=True)
class FechaEncontrada:
    fecha: dt.date | None
    texto: str
    inicio: int
    fin: int
    con_mes: bool
    dia_semana: int | None = None


def _construir(anio: int, mes: int, dia: int) -> dt.date | None:
    try:
        return dt.date(anio, mes, dia)
    except ValueError:
        return None


def _anio_para(mes: int, dia: int, ref: dt.date, anio: str | None) -> int:
    if anio:
        a = int(anio)
        return a + 2000 if a < 100 else a
    candidata = _construir(ref.year, mes, dia)
    # Una fecha más de 6 meses en el pasado se interpreta como del año siguiente (p. ej. enero en diciembre).
    if candidata and (ref - candidata).days > 180:
        return ref.year + 1
    return ref.year


def encontrar_fechas_con_mes(texto: str, ref: dt.date) -> list[FechaEncontrada]:
    """Fechas con día y mes explícitos (en palabras o numéricas)."""
    plegado = plegar(texto)
    halladas: list[FechaEncontrada] = []
    for m in RE_DIA_MES.finditer(plegado):
        dia, mes = _dia(m["dia"]), MESES[m["mes"]]
        if dia is None:
            continue
        fecha = _construir(_anio_para(mes, dia, ref, m["anio"]), mes, dia)
        sem = DIAS_SEMANA.get(m["sem"]) if m["sem"] else None
        halladas.append(FechaEncontrada(fecha, texto[m.start():m.end()], m.start(), m.end(), True, sem))
    for m in RE_NUMERICA.finditer(plegado):
        dia, mes = int(m["dia"]), int(m["mes"])
        if not (1 <= mes <= 12):
            continue
        fecha = _construir(_anio_para(mes, dia, ref, m["anio"]), mes, dia)
        halladas.append(FechaEncontrada(fecha, texto[m.start():m.end()], m.start(), m.end(), True))
    return sorted(halladas, key=lambda f: f.inicio)


@dataclass(frozen=True)
class FechaResuelta:
    fecha: dt.date | None
    concreta: bool
    motivo: str
    inconsistencia: str | None = None


def resolver_fecha(texto: str, fecha_llamada: dt.date) -> FechaResuelta:
    """Resuelve la expresión de fecha de un compromiso a una fecha concreta, si la hay.

    Concreta = trae número de día (con o sin mes) o es relativa inequívoca (hoy, mañana, pasado
    mañana). Un día de la semana solo ("el sábado") NO es concreto.
    """
    plegado = plegar(texto)
    con_mes = encontrar_fechas_con_mes(texto, fecha_llamada)
    if con_mes:
        f = con_mes[-1]
        if f.fecha is None:
            return FechaResuelta(None, False, f"'{f.texto}' no es una fecha válida")
        return FechaResuelta(f.fecha, True, f"fecha explícita '{f.texto}'", _chequear_semana(f.fecha, f.dia_semana))

    m = RE_DIA_SOLO.search(plegado)
    if m:
        dia = _dia(m["dia1"] or m["dia2"])
        sem = DIAS_SEMANA.get(m["sem"]) if m["sem"] else None
        fecha = _resolver_dia_sin_mes(dia, sem, fecha_llamada) if dia else None
        if fecha is None:
            return FechaResuelta(None, False, f"'{texto}' no corresponde a un día válido")
        return FechaResuelta(fecha, True, f"día {dia} sin mes, resuelto al {fecha.isoformat()}",
                             _chequear_semana(fecha, sem))

    m = RE_RELATIVA.search(plegado)
    if m:
        delta = {"hoy": 0, "manana": 1, "pasado manana": 2}[m["rel"]]
        return FechaResuelta(fecha_llamada + dt.timedelta(days=delta), True, f"fecha relativa '{m['rel']}'")

    m = RE_SEMANA.search(plegado)
    if m:
        return FechaResuelta(None, False, f"solo indica el día de la semana ('{NOMBRES_SEMANA[DIAS_SEMANA[m['sem']]]}') sin número de día")
    return FechaResuelta(None, False, "no hay una fecha concreta")


def _resolver_dia_sin_mes(dia: int, sem: int | None, ref: dt.date) -> dt.date | None:
    actual = _construir(ref.year, ref.month, dia)
    sig_mes = (ref.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    siguiente = _construir(sig_mes.year, sig_mes.month, dia)
    if actual is None:
        return siguiente
    if actual >= ref:
        return actual
    # Día ya pasado en el mes de la llamada: si el día de la semana dicho cuadra con el mes siguiente,
    # o si quedó hace más de una semana, se interpreta como del mes siguiente.
    if sem is not None:
        if actual.weekday() == sem:
            return actual
        if siguiente and siguiente.weekday() == sem:
            return siguiente
        return actual
    return siguiente if (ref - actual).days > 7 and siguiente else actual


def _chequear_semana(fecha: dt.date, sem: int | None) -> str | None:
    if sem is None or fecha.weekday() == sem:
        return None
    return f"el día de la semana no coincide: el {fecha.isoformat()} es {NOMBRES_SEMANA[fecha.weekday()]}"


@dataclass(frozen=True)
class ValidacionPlazo:
    valida: bool
    dias: int
    motivo: str


def validar_plazo(fecha: dt.date, fecha_llamada: dt.date, max_dias: int = 5) -> ValidacionPlazo:
    dias = (fecha - fecha_llamada).days
    if dias < 0:
        return ValidacionPlazo(False, dias, f"la fecha {fecha.isoformat()} es anterior a la llamada")
    if dias > max_dias:
        return ValidacionPlazo(False, dias, f"la fecha {fecha.isoformat()} está {dias} días después de la "
                                            f"llamada (máximo {max_dias})")
    return ValidacionPlazo(True, dias, f"la fecha {fecha.isoformat()} está {dias} días después de la llamada")

