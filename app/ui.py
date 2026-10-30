"""Interfaz Gradio (montada en /ui): subir el JSON o usar el archivo de la prueba, ver tablas y descargar."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import gradio as gr
from pydantic import ValidationError

from app.evaluator import Evaluador
from app.rubric import IDS_CRITERIOS
from app.schemas import ArchivoConversaciones, ResultadosLote

SIMBOLO = {"cumple": "✅", "no_cumple": "❌", "no_aplica": "—", "no_evaluado": "?"}


def _tablas(res: ResultadosLote) -> tuple[list[list], list[list], list[list], str]:
    por_conv = []
    detalle = []
    for e in res.evaluaciones:
        por_conv.append([e.conversacion_id, e.puntaje_global, e.severidad_global, e.estado_evaluacion,
                         ", ".join(e.fallas) or "-"] + [SIMBOLO[c.resultado] for c in e.criterios])
        for c in e.criterios:
            if c.resultado == "no_cumple":
                detalle.append([e.conversacion_id, c.criterio_id, c.severidad, c.explicacion,
                                " | ".join(f"[{x.turno}] {x.texto}" for x in c.evidencia)])
    rep = res.reporte_agregado
    agregado = [[c.criterio_id, c.nombre, c.aplicables, c.cumple, c.no_cumple, c.no_aplica,
                 "-" if c.tasa_cumplimiento is None else f"{100 * c.tasa_cumplimiento:.1f}%"] for c in rep.por_criterio]
    top = "\n".join(f"{i}. **{f.criterio_id}** {f.nombre}: {f.ocurrencias} llamadas ({f.porcentaje_conversaciones}%), "
                    f"impacto {f.impacto}, severidad {f.severidad} — {', '.join(f.conversaciones)}"
                    for i, f in enumerate(rep.fallas_por_impacto[:5], 1))
    resumen = (f"**{rep.total_conversaciones} conversaciones** · puntaje promedio **{rep.puntaje_promedio}** · "
               f"severidad: {rep.distribucion_severidad} · críticas: {', '.join(rep.conversaciones_criticas) or '-'}"
               f"\n\n**Fallas por impacto (severidad × frecuencia)**\n\n{top or 'Sin fallas.'}")
    return por_conv, detalle, agregado, resumen


def crear_ui(evaluador: Evaluador, ruta_dataset: Path, max_concurrencia: int) -> gr.Blocks:
    async def evaluar(ruta_archivo: str | None, usar_prueba: bool):
        ruta = ruta_dataset if usar_prueba or not ruta_archivo else Path(ruta_archivo)
        try:
            archivo = ArchivoConversaciones.model_validate(json.loads(Path(ruta).read_text(encoding="utf-8-sig")))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise gr.Error(f"El archivo no es JSON válido: {e}")
        except ValidationError as e:
            raise gr.Error(f"Formato inválido: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
        res = await evaluador.evaluar_lote(archivo, max_concurrencia, servicio="ui")
        por_conv, detalle, agregado, resumen = _tablas(res)
        salida = Path(tempfile.mkdtemp()) / "results.json"
        salida.write_text(res.model_dump_json(indent=2), encoding="utf-8")
        return resumen, por_conv, detalle, agregado, str(salida)

    with gr.Blocks(title="Evaluador Lina · Banco Andino") as demo:
        gr.Markdown("# Evaluador de llamadas de cobranza — Lina (Banco Andino)\n"
                    "Rúbrica de 13 criterios (R1–R10). Código determinista para lo objetivo, Gemini para lo "
                    "semántico; cada falla trae su cita literal. API y Swagger en [/docs](/docs).")
        with gr.Row():
            archivo = gr.File(label="Archivo JSON (formato de la prueba)", file_types=[".json"], type="filepath")
            with gr.Column():
                usar_prueba = gr.Checkbox(label="Usar el archivo de la prueba (20 conversaciones)", value=True)
                boton = gr.Button("Evaluar", variant="primary")
        resumen = gr.Markdown()
        with gr.Tab("Por conversación"):
            tabla = gr.Dataframe(headers=["id", "puntaje", "severidad", "estado", "fallas"] + IDS_CRITERIOS, wrap=True)
        with gr.Tab("Fallas con evidencia"):
            fallas = gr.Dataframe(headers=["id", "criterio", "severidad", "explicación", "cita"], wrap=True)
        with gr.Tab("Reporte agregado"):
            agregado = gr.Dataframe(headers=["criterio", "nombre", "aplicables", "cumple", "no_cumple",
                                             "no_aplica", "tasa"], wrap=True)
        descarga = gr.File(label="Descargar results.json")
        boton.click(evaluar, [archivo, usar_prueba], [resumen, tabla, fallas, agregado, descarga])
    return demo
