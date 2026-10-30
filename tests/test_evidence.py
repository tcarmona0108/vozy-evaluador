import pytest
from pydantic import ValidationError

from app.evidence import ubicar_cita
from app.schemas import Cita, ResultadoCriterio, Turno

TR = [
    Turno(hablante="agente", texto="Buenos días, le habla Lina, asistente virtual de Banco Andino."),
    Turno(hablante="cliente", texto="Sí,   con él."),
    Turno(hablante="agente", texto="Le recomiendo pagar hoy mismo para evitar el cobro jurídico."),
]


def test_cita_exacta_normaliza_espacios():
    cita, nota = ubicar_cita(TR, 2, "Sí, con él.")
    assert cita.turno == 2 and cita.hablante == "cliente" and nota is None


def test_cita_en_turno_equivocado_se_reubica():
    cita, nota = ubicar_cita(TR, 1, "evitar el cobro jurídico")
    assert cita.turno == 3 and "reubicada" in nota


def test_cita_parafraseada_se_ajusta_por_similitud():
    cita, nota = ubicar_cita(TR, 3, "Le recomiendo pagar hoy mismo para evitar el cobro juridico")
    assert cita.turno == 3
    assert cita.texto in TR[2].texto
    assert "similitud" in nota


def test_cita_inventada_usa_turno_completo():
    cita, nota = ubicar_cita(TR, 3, "Lo vamos a demandar mañana")
    assert cita.texto == TR[2].texto and "turno 3 completo" in nota


def test_cita_turno_inexistente_se_descarta():
    cita, nota = ubicar_cita(TR, 99, "texto que no existe en ninguna parte")
    assert cita is None and "descartada" in nota


def test_validador_de_cita_con_contexto():
    ctx = {"transcripcion": TR}
    Cita.model_validate({"turno": 1, "hablante": "agente", "texto": "le habla Lina"}, context=ctx)
    with pytest.raises(ValidationError):
        Cita.model_validate({"turno": 1, "hablante": "agente", "texto": "le habla Pedro"}, context=ctx)
    with pytest.raises(ValidationError):
        Cita.model_validate({"turno": 2, "hablante": "agente", "texto": "Sí"}, context=ctx)


def test_no_cumple_exige_evidencia_y_severidad():
    base = dict(criterio_id="R1a", regla="R1", nombre="x", explicacion="x", metodo="codigo")
    with pytest.raises(ValidationError):
        ResultadoCriterio(**base, resultado="no_cumple", severidad="grave")
    with pytest.raises(ValidationError):
        ResultadoCriterio(**base, resultado="cumple", severidad="grave")
