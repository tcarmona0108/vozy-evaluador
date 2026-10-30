"""Criterios deterministas sobre conversaciones sintéticas (nunca sobre el dataset de la prueba)."""
import json
from pathlib import Path

import pytest

from app.checks.facts import calcular_hechos, criterios_codigo, r10_por_terminos
from app.schemas import Conversacion

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinteticas.json").read_text(encoding="utf-8"))
CASOS = [(c["id"], Conversacion.model_validate(c), c["esperado"]) for c in FIXTURES["conversaciones"]]
CODIGO = ("R1a", "R1b", "R2a", "R2b", "R4a", "R4b")


@pytest.mark.parametrize("cid, conv, esperado", CASOS, ids=[c[0] for c in CASOS])
def test_criterios_codigo_sinteticos(cid, conv, esperado):
    h = calcular_hechos(conv)
    obtenido = criterios_codigo(conv, h, h.es_titular_heuristico)
    for criterio in CODIGO:
        assert obtenido[criterio].resultado == esperado[criterio], (criterio, obtenido[criterio].explicacion)


def test_heuristica_titular_detecta_tercero():
    conv = next(c for i, c, _ in CASOS if i == "S03")
    assert calcular_hechos(conv).es_titular_heuristico is False


def test_terminos_prohibidos_abogado():
    conv = next(c for i, c, _ in CASOS if i == "S02")
    r10 = r10_por_terminos(conv.transcripcion, calcular_hechos(conv))
    assert r10 and r10.resultado == "no_cumple" and r10.severidad == "critica"
    assert "abogado" in r10.evidencia[0].texto


def test_sin_terminos_prohibidos():
    conv = next(c for i, c, _ in CASOS if i == "S01")
    assert r10_por_terminos(conv.transcripcion, calcular_hechos(conv)) is None
