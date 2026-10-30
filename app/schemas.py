"""Contratos de entrada y salida (Pydantic v2). Claves en español, snake_case, sin tildes."""
from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.rubric import IDS_CRITERIOS, PESOS, CriterioRubrica, Metodo, Severidad

Hablante = Literal["agente", "cliente", "sistema"]
Resultado = Literal["cumple", "no_cumple", "no_aplica", "no_evaluado"]
SeveridadGlobal = Literal["sin_fallas", "leve", "grave", "critica"]

_ESPACIOS = re.compile(r"\s+")


def normalizar_espacios(texto: str) -> str:
    return _ESPACIOS.sub(" ", texto).strip()


def es_subcadena(cita: str, turno: str) -> bool:
    cita_n = normalizar_espacios(cita)
    return bool(cita_n) and cita_n in normalizar_espacios(turno)


# ---------------------------------------------------------------- entrada

class Turno(BaseModel):
    hablante: Hablante
    texto: str


class DatosCliente(BaseModel):
    model_config = ConfigDict(extra="allow")

    nombre: str = Field(min_length=1)
    ultimos4_documento: str
    producto: str
    monto_vencido_cop: int = Field(ge=0)
    fecha_vencimiento: dt.date

    @field_validator("ultimos4_documento", mode="before")
    @classmethod
    def _digitos(cls, v: object) -> str:
        s = str(v).strip()
        if not re.fullmatch(r"\d{4}", s):
            raise ValueError("ultimos4_documento debe tener exactamente 4 dígitos")
        return s


class Conversacion(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    fecha_llamada: dt.date
    datos_cliente: DatosCliente
    transcripcion: list[Turno] = Field(min_length=1)


class EspecificacionAgente(BaseModel):
    model_config = ConfigDict(extra="allow")

    nombre_agente: str
    empresa: str
    canal: str | None = None
    objetivo: str | None = None
    reglas: list[str] = Field(min_length=1)


class SolicitudEvaluacion(Conversacion):
    """Body de POST /evaluate: una conversación y, opcionalmente, la especificación del agente."""

    especificacion_agente: EspecificacionAgente | None = None


class ArchivoConversaciones(BaseModel):
    """Body de POST /evaluate/batch: el mismo formato del archivo de la prueba."""

    model_config = ConfigDict(extra="allow")

    descripcion: str | None = None
    especificacion_agente: EspecificacionAgente | None = None
    conversaciones: list[Conversacion] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_unicos(self) -> "ArchivoConversaciones":
        ids = [c.id for c in self.conversaciones]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"ids de conversación repetidos: {repetidos}")
        return self


# ---------------------------------------------------------------- salida

class Cita(BaseModel):
    turno: int = Field(ge=1, description="Índice base 1 sobre la transcripción")
    hablante: Hablante
    texto: str = Field(min_length=1)

    @model_validator(mode="after")
    def _literal(self, info: ValidationInfo) -> "Cita":
        # Con contexto (validación final del evaluador) se exige que la cita sea literal.
        transcripcion: list[Turno] | None = (info.context or {}).get("transcripcion")
        if transcripcion is not None:
            if self.turno > len(transcripcion):
                raise ValueError(f"la cita apunta al turno {self.turno}, que no existe")
            turno = transcripcion[self.turno - 1]
            if turno.hablante != self.hablante:
                raise ValueError(f"el turno {self.turno} es de '{turno.hablante}', no de '{self.hablante}'")
            if not es_subcadena(self.texto, turno.texto):
                raise ValueError(f"la cita no es subcadena literal del turno {self.turno}")
        return self


class ResultadoCriterio(BaseModel):
    criterio_id: str
    regla: str
    nombre: str
    resultado: Resultado
    evidencia: list[Cita] = Field(default_factory=list)
    explicacion: str
    severidad: Severidad | None = None
    metodo: Metodo

    @model_validator(mode="after")
    def _coherencia(self) -> "ResultadoCriterio":
        if self.resultado == "no_cumple":
            if not self.evidencia:
                raise ValueError(f"{self.criterio_id}: no_cumple requiere al menos una cita")
            if self.severidad is None:
                raise ValueError(f"{self.criterio_id}: no_cumple requiere severidad")
        elif self.severidad is not None:
            raise ValueError(f"{self.criterio_id}: solo un no_cumple lleva severidad")
        return self


class Metadatos(BaseModel):
    modelo: str | None = None
    version_rubrica: str
    latencia_ms: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_razonamiento: int = 0
    desde_cache: bool = False
    errores: list[str] = Field(default_factory=list)
    discrepancias: list[str] = Field(default_factory=list)


class EvaluacionConversacion(BaseModel):
    conversacion_id: str
    fecha_llamada: dt.date
    estado_evaluacion: Literal["completa", "parcial"]
    criterios: list[ResultadoCriterio]
    puntaje_global: float | None = Field(default=None, ge=0, le=100)
    severidad_global: SeveridadGlobal
    fallas: list[str]
    resumen: str
    metadatos: Metadatos

    @model_validator(mode="after")
    def _consistencia(self) -> "EvaluacionConversacion":
        ids = [c.criterio_id for c in self.criterios]
        if ids != IDS_CRITERIOS:
            raise ValueError(f"los criterios deben ser exactamente {IDS_CRITERIOS} en ese orden")
        fallas = [c.criterio_id for c in self.criterios if c.resultado == "no_cumple"]
        if self.fallas != fallas:
            raise ValueError("fallas debe listar los criterios no_cumple en orden de rúbrica")
        severidades = [c.severidad for c in self.criterios if c.severidad]
        esperada = max(severidades, key=PESOS.__getitem__) if severidades else "sin_fallas"
        if self.severidad_global != esperada:
            raise ValueError(f"severidad_global debe ser '{esperada}'")
        hay_no_evaluado = any(c.resultado == "no_evaluado" for c in self.criterios)
        if hay_no_evaluado != (self.estado_evaluacion == "parcial"):
            raise ValueError("estado_evaluacion 'parcial' si y solo si hay criterios no_evaluado")
        return self


class CriterioAgregado(BaseModel):
    criterio_id: str
    nombre: str
    aplicables: int
    cumple: int
    no_cumple: int
    no_aplica: int
    no_evaluado: int
    tasa_cumplimiento: float | None


class FallaFrecuente(BaseModel):
    criterio_id: str
    nombre: str
    ocurrencias: int
    porcentaje_conversaciones: float
    impacto: int = Field(description="Suma de pesos de severidad de cada ocurrencia")
    severidad: Severidad = Field(description="Máxima severidad observada")
    conversaciones: list[str]


class ReporteAgregado(BaseModel):
    total_conversaciones: int
    evaluaciones_completas: int
    evaluaciones_parciales: int
    puntaje_promedio: float | None
    distribucion_severidad: dict[SeveridadGlobal, int]
    por_criterio: list[CriterioAgregado]
    fallas_mas_frecuentes: list[FallaFrecuente]
    fallas_por_impacto: list[FallaFrecuente]
    conversaciones_criticas: list[str]


class MetadatosLote(BaseModel):
    generado_en: dt.datetime
    version_rubrica: str
    modelo: str | None
    servicio: str | None = None
    total_conversaciones: int
    latencia_total_ms: int
    tokens_entrada: int
    tokens_salida: int
    tokens_razonamiento: int


class ResultadosLote(BaseModel):
    metadatos: MetadatosLote
    rubrica: list[CriterioRubrica]
    evaluaciones: list[EvaluacionConversacion]
    reporte_agregado: ReporteAgregado
