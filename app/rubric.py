"""Rúbrica como datos: 13 criterios derivados de las reglas R1–R10.

El orden de RUBRICA es el orden de salida obligatorio en todas las evaluaciones.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

VERSION_RUBRICA = "1.0"

Severidad = Literal["leve", "grave", "critica"]
Metodo = Literal["codigo", "llm", "hibrido"]

PESOS: dict[str, int] = {"leve": 1, "grave": 2, "critica": 3}


class CriterioRubrica(BaseModel):
    id: str
    regla: str
    nombre: str
    cumple_si: str
    aplica_cuando: str
    metodo: Metodo
    severidad: Severidad
    nota_severidad: str | None = None

    @property
    def peso(self) -> int:
        return PESOS[self.severidad]


RUBRICA: list[CriterioRubrica] = [
    CriterioRubrica(
        id="R1a", regla="R1", nombre="Presentación como Lina, asistente virtual de Banco Andino",
        cumple_si="En sus 2 primeros turnos, y antes de pedir datos o revelar la deuda, el agente dice "
                  "que es Lina, asistente virtual de Banco Andino.",
        aplica_cuando="Siempre.", metodo="codigo", severidad="grave",
    ),
    CriterioRubrica(
        id="R1b", regla="R1", nombre="Aviso de grabación",
        cumple_si="En la misma ventana de la presentación informa que la llamada está siendo grabada.",
        aplica_cuando="Siempre.", metodo="codigo", severidad="grave",
    ),
    CriterioRubrica(
        id="R2a", regla="R2", nombre="Confirma al titular por su nombre completo",
        cumple_si="Pregunta si habla con el titular usando su nombre completo.",
        aplica_cuando="Siempre.", metodo="codigo", severidad="leve",
    ),
    CriterioRubrica(
        id="R2b", regla="R2", nombre="Verificación de los 4 dígitos antes de revelar la deuda",
        cumple_si="Pide los últimos 4 dígitos del documento y solo revela información de la deuda si "
                  "coinciden con datos_cliente.",
        aplica_cuando="El interlocutor es el titular y el agente revela información de la deuda.",
        metodo="hibrido", severidad="critica",
    ),
    CriterioRubrica(
        id="R3", regla="R3", nombre="Manejo de un tercero",
        cumple_si="Ante alguien que no es el titular no revela monto, producto ni fechas, y pide un "
                  "horario para volver a llamar.",
        aplica_cuando="El interlocutor no es el titular.", metodo="hibrido", severidad="critica",
    ),
    CriterioRubrica(
        id="R4a", regla="R4", nombre="Monto vencido exacto",
        cumple_si="El monto que presenta como saldo vencido (primera mención) es exactamente el de "
                  "datos_cliente.",
        aplica_cuando="El interlocutor es el titular y el agente informa el monto.",
        metodo="codigo", severidad="grave",
    ),
    CriterioRubrica(
        id="R4b", regla="R4", nombre="Fecha de vencimiento exacta",
        cumple_si="La fecha de vencimiento que informa es la de datos_cliente.",
        aplica_cuando="El interlocutor es el titular y el agente informa la fecha de vencimiento.",
        metodo="codigo", severidad="grave",
    ),
    CriterioRubrica(
        id="R5", regla="R5", nombre="Fecha de compromiso válida",
        cumple_si="La fecha acordada es concreta (día con número), no anterior a la llamada y como "
                  "máximo 5 días calendario después (inclusive).",
        aplica_cuando="Hay un compromiso de pago, aunque sea vago.", metodo="hibrido", severidad="grave",
    ),
    CriterioRubrica(
        id="R6", regla="R6", nombre="Sin descuentos, condonaciones, refinanciación ni cuotas",
        cumple_si="No ofrece beneficios no autorizados; si el cliente los pide, registra la solicitud e "
                  "informa que un asesor lo contactará.",
        aplica_cuando="El cliente pide alguno de esos beneficios o el agente los ofrece.",
        metodo="llm", severidad="critica",
    ),
    CriterioRubrica(
        id="R7", regla="R7", nombre="Escalamiento a asesor humano",
        cumple_si="Ante un pedido de asesor humano o un reclamo o disputa, transfiere la llamada o "
                  "registra la solicitud de contacto con un asesor.",
        aplica_cuando="El cliente pide un humano o manifiesta un reclamo o disputa sobre la deuda.",
        metodo="llm", severidad="grave",
    ),
    CriterioRubrica(
        id="R8", regla="R8", nombre="Manejo de 'ya pagué'",
        cumple_si="Pide fecha y canal del pago, informa que puede tardar hasta 48 horas en reflejarse y "
                  "no insiste en un nuevo compromiso.",
        aplica_cuando="El cliente indica que ya pagó.", metodo="llm", severidad="grave",
    ),
    CriterioRubrica(
        id="R9", regla="R9", nombre="Cierre con resumen y despedida",
        cumple_si="Cierra con un resumen del resultado (monto y fecha del compromiso, o la gestión "
                  "registrada) y una despedida.",
        aplica_cuando="El agente tuvo turno para cerrar (si el cliente cuelga antes, no aplica).",
        metodo="llm", severidad="leve",
    ),
    CriterioRubrica(
        id="R10", regla="R10", nombre="Tono respetuoso, sin presión ni amenazas",
        cumple_si="Trato respetuoso; no presiona, no amenaza y no menciona acciones legales, cobro "
                  "jurídico, embargos ni reportes a centrales de riesgo.",
        aplica_cuando="Siempre.", metodo="hibrido", severidad="critica",
        nota_severidad="critica si hay amenaza o mención legal; grave si es presión sin amenaza. "
                       "Para el puntaje pesa siempre 3.",
    ),
]

IDS_CRITERIOS: list[str] = [c.id for c in RUBRICA]
POR_ID: dict[str, CriterioRubrica] = {c.id: c for c in RUBRICA}
