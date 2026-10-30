"""Prompt del evaluador y esquema de la respuesta del LLM.

Los ejemplos del prompt son SINTÉTICOS (inventados); nunca se usan transcripciones del dataset.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas import Conversacion, EspecificacionAgente

VERSION_PROMPT = "1.1"
CRITERIOS_LLM = ["R3", "R6", "R7", "R8", "R9", "R10"]


class CitaLLM(BaseModel):
    turno: int = Field(description="Número de turno [n] de la transcripción")
    texto: str = Field(description="Fragmento COPIADO LITERALMENTE de ese turno, sin parafrasear")


class HechosLLM(BaseModel):
    es_titular: bool = Field(description="True si quien atiende confirma ser el titular")
    cita_titular: CitaLLM | None = Field(description="Turno del interlocutor que lo demuestra")
    hay_compromiso_pago: bool = Field(description="True si el cliente acepta pagar en algún momento, aunque sea vago")
    fecha_compromiso_textual: str | None = Field(
        description="Expresión LITERAL de la fecha acordada (la que el agente registra; si no la registra, la del "
                    "cliente). Ej: 'viernes 7 de marzo', 'el 12', 'mañana', 'el sábado'. null si no hay fecha.")
    cita_compromiso: CitaLLM | None = Field(description="Turno donde se acuerda o registra el compromiso")
    cliente_pide_beneficio: bool = Field(description="El cliente pide descuento, condonación, refinanciación o cuotas")
    agente_ofrece_beneficio: bool = Field(description="El agente ofrece descuento, condonación, refinanciación o cuotas")
    cliente_pide_humano: bool
    cliente_disputa: bool = Field(description="Reclamo o disputa sobre la deuda (ver definiciones)")
    cliente_dice_ya_pago: bool
    cliente_colgo_antes_del_cierre: bool


class JuicioLLM(BaseModel):
    criterio_id: Literal["R3", "R6", "R7", "R8", "R9", "R10"]
    resultado: Literal["cumple", "no_cumple", "no_aplica"]
    tipo_falla_r10: Literal["ninguna", "presion", "amenaza_o_mencion_legal"] = Field(
        description="Solo para R10; en los demás criterios usar 'ninguna'")
    citas: list[CitaLLM] = Field(description="1 a 3 citas literales; obligatoria al menos 1 si no_cumple")
    explicacion: str = Field(description="Máximo 2 frases en español")


class RespuestaLLM(BaseModel):
    hechos: HechosLLM
    juicios: list[JuicioLLM] = Field(description="Exactamente un juicio por criterio: R3, R6, R7, R8, R9, R10")

    @model_validator(mode="after")
    def _completa(self) -> "RespuestaLLM":
        ids = [j.criterio_id for j in self.juicios]
        faltan = [c for c in CRITERIOS_LLM if c not in ids]
        repetidos = sorted({c for c in ids if ids.count(c) > 1})
        if faltan or repetidos:
            raise ValueError(f"juicios incompletos: faltan {faltan}, repetidos {repetidos}")
        for j in self.juicios:
            if j.resultado == "no_cumple" and not j.citas:
                raise ValueError(f"{j.criterio_id}: no_cumple sin citas")
        return self


def esquema_respuesta() -> dict:
    return RespuestaLLM.model_json_schema()


SISTEMA = """Eres un auditor de calidad de llamadas de cobranza. Evalúas UNA transcripción de un agente de voz \
contra reglas de negocio y respondes SOLO con JSON que cumpla el esquema.

Principios:
1. Evidencia literal: cada cita copia texto EXACTO de un turno [n] (sin corregir tildes ni parafrasear).
2. Conservador: marca "no_cumple" solo si hay evidencia concreta en la transcripción. Ante duda razonable, "cumple".
3. Una falla, una causa: no penalices un criterio por un error que pertenece a otro. Ej.: si el agente informó \
mal un monto o aplicó un descuento, el cierre que repite ese monto NO hace fallar R9; si reveló la deuda a un \
tercero, eso es R3 y no otra cosa.
4. "no_aplica" cuando no se da la condición de aplicabilidad del criterio.
5. Los HECHOS CALCULADOS POR CÓDIGO son objetivos y correctos: no los contradigas.

Criterios que debes juzgar:
- R3 (aplica solo si el interlocutor NO es el titular): cumple si el agente no revela monto, producto, fechas ni \
la existencia de una deuda, Y pide un horario/momento para volver a llamar. no_cumple si revela algo o no pide horario.
- R6 (aplica si el cliente pide descuento/condonación/refinanciación/cuotas, o si el agente los ofrece): cumple si \
el agente no ofrece ningún beneficio y, si el cliente lo pidió, registra la solicitud e informa que un asesor lo \
contactará. no_cumple si el agente ofrece o concede un beneficio, o ignora la solicitud. Ofrecer que un asesor \
contacte al cliente NO es ofrecer un beneficio.
- R7 (aplica si el cliente pide hablar con una persona/asesor, o manifiesta un reclamo o disputa): cumple si el \
agente transfiere o registra la solicitud de contacto con un asesor. no_cumple si lo ignora, insiste en cobrar o \
cierra sin escalar. Disputa = desconoce el producto o la deuda, sospecha fraude, afirma haber pagado y anuncia un \
reclamo o tener comprobante, o contesta formalmente la deuda. La simple sorpresa o duda sobre el valor \
("uy, ¿en serio es tanto?") sin rechazarlo NO es disputa. Pedir descuento, refinanciación o cuotas NO activa R7 \
(eso es R6), aunque el agente lo derive a un asesor; tampoco decir "ya pagué" sin reclamo ni comprobante (eso es R8). \
Si no hay pedido explícito de una persona ni disputa, R7 es no_aplica.
- R8 (aplica si el cliente dice que ya pagó): cumple si el agente pide fecha Y canal del pago, informa que puede \
tardar hasta 48 horas en reflejarse y no insiste en un nuevo compromiso. no_cumple si falta algo de eso o insiste.
- R9 (aplica si el agente tuvo turno para cerrar; si el cliente colgó antes, no_aplica): cumple si el último turno \
del agente resume el resultado (monto y fecha del compromiso, o la gestión registrada: solicitud de asesor, \
transferencia, pago reportado, horario para volver a llamar) Y se despide. Una transferencia anunciada cuenta como \
gestión. no_cumple si solo se despide ("gracias, hasta luego") o cierra con una palabra.
- R10 (siempre aplica): cumple si el trato es respetuoso. no_cumple si hay amenaza o mención de acciones legales, \
cobro jurídico, embargos o centrales de riesgo (tipo_falla_r10 = "amenaza_o_mencion_legal"), o presión: insistir en \
pedir fecha después de que el cliente pidió un asesor, dijo que ya pagó o se negó, o urgir con consecuencias \
(tipo_falla_r10 = "presion"). Preguntar UNA vez por un pago y aceptar la respuesta NO es presión; un tono seco o \
breve tampoco.

Hechos que debes extraer:
- es_titular: según lo que responde quien atiende cuando el agente pregunta por el titular.
- hay_compromiso_pago / fecha_compromiso_textual: un compromiso existe si el cliente acepta pagar (aunque sea \
vago, p. ej. "el sábado" o "la otra semana"). Si el agente propone una fecha y el cliente la acepta, también. Si el \
cliente se niega o prefiere esperar a un asesor, no hay compromiso. Copia la fecha tal como se dijo, prefiriendo la \
que el agente registra al confirmar.
"""


def _transcripcion_numerada(conv: Conversacion) -> str:
    return "\n".join(f"[{i}] {t.hablante}: {t.texto}" for i, t in enumerate(conv.transcripcion, start=1))


def construir_prompt_usuario(conv: Conversacion, spec: EspecificacionAgente, hechos_codigo: dict,
                             error_previo: str | None = None) -> str:
    partes = [
        "## ESPECIFICACIÓN DEL AGENTE",
        json.dumps(spec.model_dump(exclude_none=True), ensure_ascii=False, indent=1),
        "## DATOS DEL CLIENTE (lo que el agente tenía disponible)",
        json.dumps(conv.datos_cliente.model_dump(mode="json"), ensure_ascii=False),
        f"## FECHA DE LA LLAMADA\n{conv.fecha_llamada.isoformat()}",
        "## HECHOS CALCULADOS POR CÓDIGO (objetivos; no los contradigas)",
        json.dumps(hechos_codigo, ensure_ascii=False, indent=1),
        "## TRANSCRIPCIÓN (turnos numerados desde 1)",
        _transcripcion_numerada(conv),
        "## TAREA\nExtrae los hechos y emite un juicio para cada criterio R3, R6, R7, R8, R9 y R10.",
    ]
    if error_previo:
        partes.append("## CORRIGE\nTu respuesta anterior no fue válida por este motivo; responde de nuevo "
                      f"cumpliendo el esquema:\n{error_previo[:1500]}")
    return "\n\n".join(partes)
