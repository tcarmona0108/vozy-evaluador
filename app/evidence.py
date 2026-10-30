"""Verificación de citas: toda cita publicada es literal o se reemplaza por el turno completo."""
from __future__ import annotations

from rapidfuzz import fuzz

from app.schemas import Cita, Turno, es_subcadena, normalizar_espacios

UMBRAL_SIMILITUD = 90.0


def cita_turno(transcripcion: list[Turno], turno: int, texto: str | None = None) -> Cita:
    """Cita construida por código (turno base 1); sin texto, usa el turno completo."""
    t = transcripcion[turno - 1]
    return Cita(turno=turno, hablante=t.hablante, texto=normalizar_espacios(texto or t.texto))


def ubicar_cita(transcripcion: list[Turno], turno: int | None, texto: str) -> tuple[Cita | None, str | None]:
    """Devuelve una cita literal verificada y, si hubo que corregirla, una nota de constancia.

    Orden: (1) subcadena exacta del turno indicado; (2) subcadena exacta de otro turno;
    (3) mejor alineación difusa >= umbral (turno indicado primero); (4) turno indicado completo.
    """
    texto = normalizar_espacios(texto or "")
    valido = turno is not None and 1 <= turno <= len(transcripcion)

    if texto and valido and es_subcadena(texto, transcripcion[turno - 1].texto):
        return cita_turno(transcripcion, turno, texto), None

    if texto:
        for i, t in enumerate(transcripcion, start=1):
            if es_subcadena(texto, t.texto):
                return cita_turno(transcripcion, i, texto), f"cita reubicada del turno {turno} al {i}"

        orden = ([turno] if valido else []) + [i for i in range(1, len(transcripcion) + 1) if i != turno]
        mejor: tuple[float, int, str] | None = None
        for i in orden:
            destino = normalizar_espacios(transcripcion[i - 1].texto)
            al = fuzz.partial_ratio_alignment(texto, destino)
            if al is None:
                continue
            fragmento = destino[al.dest_start:al.dest_end].strip()
            if fragmento and (mejor is None or al.score > mejor[0]):
                mejor = (al.score, i, fragmento)
        if mejor and mejor[0] >= UMBRAL_SIMILITUD:
            return cita_turno(transcripcion, mejor[1], mejor[2]), (
                f"cita ajustada por similitud ({mejor[0]:.0f}) al texto literal del turno {mejor[1]}")

    if valido:
        return cita_turno(transcripcion, turno), f"cita no literal; se usa el turno {turno} completo"
    return None, f"cita descartada: turno {turno} inexistente y texto no encontrado"
