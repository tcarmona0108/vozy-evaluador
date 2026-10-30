"""API FastAPI + interfaz Gradio en /ui."""
from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError

from app.config import cargar_config
from app.evaluator import Evaluador
from app.llm.base import ErrorLLM
from app.llm.gemini import ClienteGemini
from app.rubric import RUBRICA, VERSION_RUBRICA, CriterioRubrica
from app.schemas import (ArchivoConversaciones, EspecificacionAgente, EvaluacionConversacion, ResultadosLote,
                         SolicitudEvaluacion)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("evaluador.api")

CONFIG = cargar_config()
SPEC_DEFECTO = EspecificacionAgente.model_validate(
    json.loads(CONFIG.ruta_dataset.read_text(encoding="utf-8"))["especificacion_agente"])

try:
    LLM = ClienteGemini(CONFIG)
except ErrorLLM as e:  # sin key el servicio arranca igual, en modo degradado
    log.warning("LLM deshabilitado: %s", e)
    LLM = None

EVALUADOR = Evaluador(LLM, SPEC_DEFECTO)

app = FastAPI(
    title="Evaluador de llamadas de cobranza — Lina (Banco Andino)",
    version=VERSION_RUBRICA,
    description="Evalúa conversaciones del agente de voz Lina contra una rúbrica de 13 criterios derivada de las "
                "reglas R1–R10. Combina validaciones deterministas (código) con juicio semántico (Gemini). "
                "Cada 'no_cumple' trae una cita literal de la transcripción.",
)


def _detalle_errores(errores: list[dict]) -> list[dict]:
    return [{"ubicacion": ".".join(str(x) for x in e.get("loc", ())), "mensaje": e.get("msg", "")} for e in errores]


@app.exception_handler(RequestValidationError)
async def _entrada_invalida(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "entrada inválida",
                                                  "detalle": _detalle_errores(exc.errors())})


@app.exception_handler(Exception)
async def _error_inesperado(_: Request, exc: Exception) -> JSONResponse:
    log.exception("error inesperado")
    return JSONResponse(status_code=500, content={"error": "error interno", "tipo": type(exc).__name__})


@app.get("/", include_in_schema=False)
def raiz() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/health", tags=["servicio"])
def health() -> dict:
    return {"estado": "ok", "version_rubrica": VERSION_RUBRICA, "llm_configurado": LLM is not None,
            "modelo": CONFIG.modelo, "modelos_respaldo": list(CONFIG.modelos_respaldo)}


@app.get("/rubrica", response_model=list[CriterioRubrica], tags=["servicio"])
def rubrica() -> list[CriterioRubrica]:
    return RUBRICA


@app.post("/evaluate", response_model=EvaluacionConversacion, tags=["evaluación"])
async def evaluate(solicitud: SolicitudEvaluacion) -> EvaluacionConversacion:
    """Evalúa una conversación (mismo formato de cada elemento de `conversaciones` del archivo)."""
    return await EVALUADOR.evaluar(solicitud, solicitud.especificacion_agente)


@app.post("/evaluate/batch", response_model=ResultadosLote, tags=["evaluación"])
async def evaluate_batch(archivo: ArchivoConversaciones, request: Request) -> ResultadosLote:
    """Evalúa el archivo completo (JSON con `especificacion_agente` y `conversaciones`)."""
    return await EVALUADOR.evaluar_lote(archivo, CONFIG.max_concurrencia, servicio=str(request.base_url))


@app.post("/evaluate/batch/upload", response_model=ResultadosLote, tags=["evaluación"])
async def evaluate_batch_upload(request: Request, archivo: UploadFile = File(...)) -> ResultadosLote:
    """Igual que /evaluate/batch, pero subiendo el archivo .json (útil desde Swagger)."""
    try:
        contenido = json.loads((await archivo.read()).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=422, detail=f"el archivo no es JSON válido: {e}") from e
    try:
        datos = ArchivoConversaciones.model_validate(contenido)
    except ValidationError as e:
        return JSONResponse(status_code=422, content={"error": "entrada inválida",
                                                      "detalle": _detalle_errores(e.errors())})
    return await EVALUADOR.evaluar_lote(datos, CONFIG.max_concurrencia, servicio=str(request.base_url))


if os.getenv("DISABLE_UI", "").lower() not in ("1", "true"):
    import gradio as gr

    from app.ui import CSS, LOGO, crear_ui, tema

    app = gr.mount_gradio_app(app, crear_ui(EVALUADOR, CONFIG.ruta_dataset, CONFIG.max_concurrencia), path="/ui",
                              theme=tema(), css=CSS, footer_links=[], favicon_path=str(LOGO))
