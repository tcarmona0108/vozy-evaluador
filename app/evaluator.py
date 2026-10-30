"""Orquestación: hechos por código + una llamada al LLM + combinación, puntaje y modo degradado."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import re
import time
from collections import OrderedDict

from pydantic import ValidationError

from app.checks.dates import resolver_fecha, validar_plazo
from app.checks.facts import HechosCodigo, calcular_hechos, criterios_codigo, r10_por_terminos, resultado
from app.evidence import cita_turno, ubicar_cita
from app.llm.base import ClienteLLM, ErrorLLM
from app.llm.prompt import SISTEMA, VERSION_PROMPT, CitaLLM, JuicioLLM, RespuestaLLM, construir_prompt_usuario, esquema_respuesta
from app.report import generar_reporte
from app.rubric import IDS_CRITERIOS, PESOS, POR_ID, RUBRICA, VERSION_RUBRICA
from app.schemas import (ArchivoConversaciones, Cita, Conversacion, EspecificacionAgente, EvaluacionConversacion,
                         Metadatos, MetadatosLote, ResultadoCriterio, ResultadosLote)

log = logging.getLogger("evaluador")

_FRASE = re.compile(r"(?<=[.!?])\s+")


def dos_frases(texto: str) -> str:
    frases = [f for f in _FRASE.split(" ".join(texto.split())) if f]
    return " ".join(frases[:2]) or "Sin explicación."


class Contexto:
    """Acumula errores y discrepancias de una evaluación."""

    def __init__(self) -> None:
        self.errores: list[str] = []
        self.discrepancias: list[str] = []


# ------------------------------------------------------------------ citas del LLM

def _citas_verificadas(conv: Conversacion, citas: list[CitaLLM], criterio: str, ctx: Contexto) -> list[Cita]:
    salida: list[Cita] = []
    for c in citas[:3]:
        cita, nota = ubicar_cita(conv.transcripcion, c.turno, c.texto)
        if nota:
            ctx.discrepancias.append(f"{criterio}: {nota}")
        if cita and all((cita.turno, cita.texto) != (s.turno, s.texto) for s in salida):
            salida.append(cita)
    return salida


def _desde_juicio(conv: Conversacion, h: HechosCodigo, j: JuicioLLM, ctx: Contexto,
                  severidad: str | None = None) -> ResultadoCriterio:
    citas = _citas_verificadas(conv, j.citas, j.criterio_id, ctx)
    if j.resultado == "no_cumple" and not citas and h.ultimo_turno_agente:
        # Falla por omisión sin cita utilizable: se cita el último turno del agente (principio 3).
        citas = [cita_turno(conv.transcripcion, h.ultimo_turno_agente)]
        ctx.discrepancias.append(f"{j.criterio_id}: sin cita literal; se cita el último turno del agente")
    return resultado(j.criterio_id, j.resultado, citas, dos_frases(j.explicacion), severidad=severidad)


# ------------------------------------------------------------------ combinación

def _r3(conv: Conversacion, h: HechosCodigo, es_titular: bool | None, juicio: JuicioLLM | None,
        ctx: Contexto) -> ResultadoCriterio:
    if es_titular is None:
        return resultado("R3", "no_evaluado", [], "No se pudo determinar si el interlocutor es el titular.")
    if es_titular:
        return resultado("R3", "no_aplica", [], "El interlocutor es el titular.")
    if h.revelaciones:
        # Hecho objetivo: el agente reveló información de la deuda a un tercero. Decide el código.
        if juicio and juicio.resultado != "no_cumple":
            ctx.discrepancias.append(f"R3: el LLM dijo '{juicio.resultado}' pero el código detecta revelación "
                                     f"en el turno {h.revelaciones[0].turno}; gana el código")
        vistas = list({m.turno: m for m in h.revelaciones}.values())[:2]
        citas = [cita_turno(conv.transcripcion, m.turno, m.texto) for m in vistas]
        return resultado("R3", "no_cumple", citas, "Revela información de la deuda a alguien que no es el "
                                                    "titular.", metodo="hibrido")
    if juicio is None:
        return resultado("R3", "no_evaluado", [], "No se pudo verificar si pidió un horario para volver a llamar.")
    if juicio.resultado == "no_aplica":
        ctx.discrepancias.append("R3: el LLM dijo no_aplica con un interlocutor tercero; se toma su juicio como cumple")
        juicio = juicio.model_copy(update={"resultado": "cumple"})
    return _desde_juicio(conv, h, juicio, ctx)


def _r5(conv: Conversacion, r: RespuestaLLM | None, ctx: Contexto) -> ResultadoCriterio:
    if r is None:
        return resultado("R5", "no_evaluado", [], "No se pudo extraer el compromiso de pago.")
    hechos = r.hechos
    if not hechos.hay_compromiso_pago:
        return resultado("R5", "no_aplica", [], "No hay compromiso de pago.")
    tr = conv.transcripcion
    cita = None
    if hechos.fecha_compromiso_textual:
        turno = hechos.cita_compromiso.turno if hechos.cita_compromiso else None
        cita, nota = ubicar_cita(tr, turno, hechos.fecha_compromiso_textual)
        if nota:
            ctx.discrepancias.append(f"R5: {nota}")
    if cita is None and hechos.cita_compromiso:
        cita, _ = ubicar_cita(tr, hechos.cita_compromiso.turno, hechos.cita_compromiso.texto)
    evidencia = [cita] if cita else []
    texto_fecha = hechos.fecha_compromiso_textual or ""
    fecha = resolver_fecha(texto_fecha, conv.fecha_llamada)
    if not fecha.concreta or fecha.fecha is None:
        if not evidencia:
            return resultado("R5", "no_evaluado", [], "Hay compromiso pero no se pudo ubicar su evidencia.")
        return resultado("R5", "no_cumple", evidencia, f"El compromiso no tiene fecha concreta: {fecha.motivo}.",
                         metodo="hibrido")
    plazo = validar_plazo(fecha.fecha, conv.fecha_llamada)
    nota_semana = f" Además, {fecha.inconsistencia}." if fecha.inconsistencia else ""
    if fecha.inconsistencia:
        ctx.discrepancias.append(f"R5: {fecha.inconsistencia}")
    if plazo.valida:
        return resultado("R5", "cumple", evidencia, f"Fecha concreta: {plazo.motivo}.{nota_semana}")
    if not evidencia:
        return resultado("R5", "no_evaluado", [], "La fecha incumple el plazo pero no se pudo ubicar la cita.")
    return resultado("R5", "no_cumple", evidencia, f"Plazo inválido: {plazo.motivo}.{nota_semana}")


def _r10(conv: Conversacion, h: HechosCodigo, juicio: JuicioLLM | None, ctx: Contexto) -> ResultadoCriterio:
    por_codigo = r10_por_terminos(conv.transcripcion, h)
    if por_codigo:
        if juicio and juicio.resultado != "no_cumple":
            ctx.discrepancias.append("R10: el LLM no marcó falla pero el código detecta términos prohibidos; "
                                     "gana el código")
        return por_codigo
    if juicio is None:
        return resultado("R10", "no_evaluado", [], "Sin términos prohibidos; no se pudo evaluar presión ni tono.")
    if juicio.resultado == "no_aplica":
        juicio = juicio.model_copy(update={"resultado": "cumple"})
    severidad = None
    if juicio.resultado == "no_cumple":
        severidad = "critica" if juicio.tipo_falla_r10 == "amenaza_o_mencion_legal" else "grave"
    r = _desde_juicio(conv, h, juicio, ctx, severidad=severidad)
    return r.model_copy(update={"metodo": "hibrido"})


def _r9(conv: Conversacion, h: HechosCodigo, juicio: JuicioLLM | None, ctx: Contexto) -> ResultadoCriterio:
    if h.cliente_colgo:
        if juicio and juicio.resultado != "no_aplica":
            ctx.discrepancias.append("R9: el cliente colgó antes del cierre (código); no aplica")
        return resultado("R9", "no_aplica", [], "El cliente finalizó la llamada antes de que el agente pudiera cerrar.")
    if juicio is None:
        return resultado("R9", "no_evaluado", [], "No se pudo evaluar el cierre.")
    return _desde_juicio(conv, h, juicio, ctx)


_NO_APLICA = {
    "R6": "El cliente no pidió beneficios y el agente no los ofreció.",
    "R7": "El cliente no pidió un asesor humano ni manifestó una disputa.",
    "R8": "El cliente no indicó que ya hubiera pagado.",
}


def _aplica_segun_hechos(criterio: str, r: RespuestaLLM) -> bool:
    h = r.hechos
    if criterio == "R6":
        return h.cliente_pide_beneficio or h.agente_ofrece_beneficio
    if criterio == "R7":
        return h.cliente_pide_humano or h.cliente_disputa
    return h.cliente_dice_ya_pago


def combinar(conv: Conversacion, h: HechosCodigo, r: RespuestaLLM | None, ctx: Contexto) -> list[ResultadoCriterio]:
    juicios = {j.criterio_id: j for j in r.juicios} if r else {}

    # es_titular: hecho semántico, decide el LLM; la heurística de código es respaldo en modo degradado.
    es_titular = r.hechos.es_titular if r else h.es_titular_heuristico
    if r and h.es_titular_heuristico is not None and h.es_titular_heuristico != r.hechos.es_titular:
        ctx.discrepancias.append(f"es_titular: LLM={r.hechos.es_titular}, heurística={h.es_titular_heuristico}; "
                                 "gana el LLM (hecho semántico)")

    por_id = criterios_codigo(conv, h, es_titular)
    por_id["R3"] = _r3(conv, h, es_titular, juicios.get("R3"), ctx)
    por_id["R5"] = _r5(conv, r, ctx)
    for cid in ("R6", "R7", "R8"):
        j = juicios.get(cid)
        if j and r and j.resultado == "cumple" and not _aplica_segun_hechos(cid, r):
            # Coherencia: los hechos extraídos dicen que el criterio no aplica. Solo se corrige un "cumple";
            # un "no_cumple" nunca se descarta por esta vía.
            ctx.discrepancias.append(f"{cid}: el LLM dijo 'cumple' pero sus hechos indican que no aplica; "
                                     "se registra no_aplica")
            j = j.model_copy(update={"resultado": "no_aplica", "explicacion": _NO_APLICA[cid]})
        por_id[cid] = _desde_juicio(conv, h, j, ctx) if j else resultado(cid, "no_evaluado", [], "LLM no disponible.")
    por_id["R9"] = _r9(conv, h, juicios.get("R9"), ctx)
    por_id["R10"] = _r10(conv, h, juicios.get("R10"), ctx)
    return [por_id[cid] for cid in IDS_CRITERIOS]


# ------------------------------------------------------------------ puntaje

def puntaje(criterios: list[ResultadoCriterio]) -> float | None:
    """100 × Σ peso(cumple) / Σ peso(cumple + no_cumple), con el peso nominal de cada criterio."""
    aplicables = [c for c in criterios if c.resultado in ("cumple", "no_cumple")]
    total = sum(POR_ID[c.criterio_id].peso for c in aplicables)
    if not total:
        return None
    ok = sum(POR_ID[c.criterio_id].peso for c in aplicables if c.resultado == "cumple")
    return round(100 * ok / total, 1)


def severidad_global(criterios: list[ResultadoCriterio]) -> str:
    sev = [c.severidad for c in criterios if c.resultado == "no_cumple" and c.severidad]
    return max(sev, key=PESOS.__getitem__) if sev else "sin_fallas"


def _resumen(criterios: list[ResultadoCriterio], pts: float | None, parcial: bool) -> str:
    fallas = [c for c in criterios if c.resultado == "no_cumple"]
    base = ("Sin fallas detectadas." if not fallas else
            "Fallas: " + ", ".join(f"{c.criterio_id} ({c.severidad})" for c in fallas) + ".")
    extra = f" Puntaje {pts}." if pts is not None else ""
    if parcial:
        extra += " Evaluación parcial: criterios semánticos sin evaluar."
    return base + extra


# ------------------------------------------------------------------ evaluador

class Evaluador:
    def __init__(self, llm: ClienteLLM | None, spec_defecto: EspecificacionAgente, max_cache: int = 512):
        self.llm = llm
        self.spec_defecto = spec_defecto
        self._cache: OrderedDict[str, EvaluacionConversacion] = OrderedDict()
        self._max_cache = max_cache

    @property
    def modelo(self) -> str | None:
        return getattr(self.llm, "modelo", None)

    def _clave(self, conv: Conversacion, spec: EspecificacionAgente) -> str:
        bruto = json.dumps([conv.model_dump(mode="json"), spec.model_dump(mode="json"), VERSION_RUBRICA,
                            VERSION_PROMPT, self.modelo], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(bruto.encode()).hexdigest()

    async def _consultar(self, conv: Conversacion, spec: EspecificacionAgente, h: HechosCodigo,
                         ctx: Contexto, uso: Metadatos) -> RespuestaLLM | None:
        if self.llm is None:
            ctx.errores.append("LLM no configurado: modo degradado")
            return None
        error_previo = None
        for intento in range(2):  # 1 llamada + 1 reintento enviando el error de validación
            try:
                cruda = await self.llm.generar_json(
                    SISTEMA, construir_prompt_usuario(conv, spec, h.resumen_para_llm(), error_previo),
                    esquema_respuesta())
            except ErrorLLM as e:
                ctx.errores.append(f"LLM: {e}")
                return None
            uso.modelo = cruda.modelo
            uso.tokens_entrada += cruda.tokens_entrada
            uso.tokens_salida += cruda.tokens_salida
            uso.tokens_razonamiento += cruda.tokens_razonamiento
            ctx.errores.extend(cruda.avisos)
            try:
                return RespuestaLLM.model_validate_json(cruda.texto)
            except ValidationError as e:
                error_previo = str(e)
                ctx.errores.append(f"respuesta del LLM inválida (intento {intento + 1}): {str(e)[:300]}")
        return None

    def _armar(self, conv: Conversacion, criterios: list[ResultadoCriterio], meta: Metadatos) -> EvaluacionConversacion:
        parcial = any(c.resultado == "no_evaluado" for c in criterios)
        pts = puntaje(criterios)
        datos = dict(
            conversacion_id=conv.id, fecha_llamada=conv.fecha_llamada,
            estado_evaluacion="parcial" if parcial else "completa",
            criterios=[c.model_dump() for c in criterios], puntaje_global=pts,
            severidad_global=severidad_global(criterios),
            fallas=[c.criterio_id for c in criterios if c.resultado == "no_cumple"],
            resumen=_resumen(criterios, pts, parcial), metadatos=meta.model_dump(),
        )
        # Validación final con contexto: toda cita debe ser literal del turno indicado.
        return EvaluacionConversacion.model_validate(datos, context={"transcripcion": conv.transcripcion})

    async def evaluar(self, conv: Conversacion, spec: EspecificacionAgente | None = None) -> EvaluacionConversacion:
        spec = spec or self.spec_defecto
        t0 = time.perf_counter()
        clave = self._clave(conv, spec)
        if clave in self._cache:
            self._cache.move_to_end(clave)
            previa = self._cache[clave]
            return previa.model_copy(update={"metadatos": previa.metadatos.model_copy(update={"desde_cache": True})})

        ctx = Contexto()
        meta = Metadatos(modelo=self.modelo, version_rubrica=VERSION_RUBRICA)
        h = calcular_hechos(conv)
        respuesta = await self._consultar(conv, spec, h, ctx, meta)
        try:
            criterios = combinar(conv, h, respuesta, ctx)
            meta.errores, meta.discrepancias = ctx.errores, ctx.discrepancias
            meta.latencia_ms = int((time.perf_counter() - t0) * 1000)
            ev = self._armar(conv, criterios, meta)
        except Exception as e:  # salvaguarda: si la combinación con el LLM falla, se degrada en vez de caer
            log.exception("fallo al combinar %s", conv.id)
            ctx.errores.append(f"combinación con LLM descartada: {type(e).__name__}: {str(e)[:300]}")
            criterios = combinar(conv, h, None, ctx)
            meta.errores, meta.discrepancias = ctx.errores, ctx.discrepancias
            meta.latencia_ms = int((time.perf_counter() - t0) * 1000)
            ev = self._armar(conv, criterios, meta)

        log.info("evaluada %s estado=%s modelo=%s latencia_ms=%d tokens_in=%d tokens_out=%d tokens_think=%d fallas=%s",
                 conv.id, ev.estado_evaluacion, meta.modelo, meta.latencia_ms, meta.tokens_entrada,
                 meta.tokens_salida, meta.tokens_razonamiento, ",".join(ev.fallas) or "-")
        if ev.estado_evaluacion == "completa":
            self._cache[clave] = ev
            if len(self._cache) > self._max_cache:
                self._cache.popitem(last=False)
        return ev

    async def evaluar_lote(self, archivo: ArchivoConversaciones, max_concurrencia: int = 2,
                           servicio: str | None = None) -> ResultadosLote:
        spec = archivo.especificacion_agente or self.spec_defecto
        semaforo = asyncio.Semaphore(max(1, max_concurrencia))
        t0 = time.perf_counter()

        async def una(conv: Conversacion) -> EvaluacionConversacion:
            async with semaforo:
                try:
                    return await self.evaluar(conv, spec)
                except Exception as e:  # una conversación que falla no detiene las demás
                    log.exception("fallo inesperado en %s", conv.id)
                    ctx = Contexto()
                    ctx.errores.append(f"fallo inesperado: {type(e).__name__}: {str(e)[:300]}")
                    criterios = combinar(conv, calcular_hechos(conv), None, ctx)
                    meta = Metadatos(modelo=self.modelo, version_rubrica=VERSION_RUBRICA, errores=ctx.errores,
                                     discrepancias=ctx.discrepancias)
                    return self._armar(conv, criterios, meta)

        evaluaciones = await asyncio.gather(*(una(c) for c in archivo.conversaciones))
        modelos = sorted({e.metadatos.modelo for e in evaluaciones if e.metadatos.modelo})
        return ResultadosLote(
            metadatos=MetadatosLote(
                generado_en=dt.datetime.now(dt.timezone.utc), version_rubrica=VERSION_RUBRICA,
                modelo=", ".join(modelos) or None, servicio=servicio,
                total_conversaciones=len(evaluaciones),
                latencia_total_ms=int((time.perf_counter() - t0) * 1000),
                tokens_entrada=sum(e.metadatos.tokens_entrada for e in evaluaciones),
                tokens_salida=sum(e.metadatos.tokens_salida for e in evaluaciones),
                tokens_razonamiento=sum(e.metadatos.tokens_razonamiento for e in evaluaciones),
            ),
            rubrica=RUBRICA,
            evaluaciones=list(evaluaciones),
            reporte_agregado=generar_reporte(list(evaluaciones)),
        )
