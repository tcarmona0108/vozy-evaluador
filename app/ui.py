"""Interfaz Gradio (montada en /ui) con la identidad visual de Vozy: subir un JSON o usar el de la prueba,
ver indicadores, tablas por conversación y criterio, fallas con evidencia y descargar results.json."""
from __future__ import annotations

import base64
import html
import inspect
import json
import tempfile
from pathlib import Path

import gradio as gr
from pydantic import ValidationError

from app.evaluator import Evaluador
from app.rubric import IDS_CRITERIOS
from app.schemas import ArchivoConversaciones, ResultadosLote

SIMBOLO = {"cumple": "✅", "no_cumple": "❌", "no_aplica": "—", "no_evaluado": "?"}
REPO = "https://github.com/tcarmona0108/vozy-evaluador"

# Paleta tomada de vozy.ai
NEGRO, GRIS_OSCURO, LIMA, VIOLETA, TEXTO, GRIS = "#1C1C1C", "#262626", "#CBFC00", "#821CFF", "#F2F2F2", "#9A9A9A"
LOGO = Path(__file__).parent / "static" / "vozy-logo.png"


def _logo_data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""


def tema() -> gr.themes.Base:
    t = gr.themes.Base(font=[gr.themes.GoogleFont("Work Sans"), "sans-serif"],
                       radius_size=gr.themes.sizes.radius_none)
    colores = dict(
        body_background_fill=NEGRO, body_text_color=TEXTO, body_text_color_subdued=GRIS,
        background_fill_primary=NEGRO, background_fill_secondary=GRIS_OSCURO,
        block_background_fill=GRIS_OSCURO, block_border_color="#3A3A3A", block_label_text_color=GRIS,
        block_label_background_fill=GRIS_OSCURO, block_title_text_color=TEXTO, border_color_primary="#3A3A3A",
        input_background_fill="#2E2E2E", input_border_color="#3A3A3A", color_accent=LIMA,
        color_accent_soft="#2E2E2E", link_text_color=LIMA, link_text_color_hover=LIMA,
        button_primary_background_fill=LIMA, button_primary_background_fill_hover="#B6E300",
        button_primary_text_color=NEGRO, button_primary_border_color=LIMA,
        button_secondary_background_fill="#2E2E2E", button_secondary_text_color=TEXTO,
        table_even_background_fill=GRIS_OSCURO, table_odd_background_fill="#2B2B2B",
        table_border_color="#3A3A3A", checkbox_background_color_selected=LIMA,
    )
    # El mismo valor en modo claro y oscuro: la página se ve igual en cualquier navegador.
    aceptados = inspect.signature(t.set).parameters
    return t.set(**colores, **{f"{k}_dark": v for k, v in colores.items() if f"{k}_dark" in aceptados})


CSS = f"""
footer {{ display: none !important; }}
.gradio-container {{ max-width: 1180px !important; min-width: 0 !important; width: 100% !important;
                     margin: 0 auto !important; }}
html, body {{ overflow-x: hidden; }}
.vz-hero {{ background: linear-gradient(120deg, #3B1173 0%, #24113F 38%, {NEGRO} 75%); padding: 34px 36px 30px;
           border-bottom: 3px solid {VIOLETA}; }}
.vz-hero img {{ height: 46px; display: block; margin-bottom: 26px; }}
.vz-hero h1 {{ color: {LIMA}; font-weight: 300; font-size: 40px; line-height: 1.15; margin: 0 0 14px; }}
.vz-hero p {{ color: {TEXTO}; font-weight: 300; font-size: 19px; max-width: 760px; margin: 0 0 14px; }}
.vz-tags {{ color: {LIMA}; font-style: italic; font-weight: 300; font-size: 17px; margin-bottom: 18px; }}
.vz-links a {{ display: inline-block; background: {LIMA}; color: {NEGRO} !important; font-weight: 700;
              padding: 9px 18px; margin: 0 10px 8px 0; text-decoration: none; }}
.vz-links a.sec {{ background: transparent; color: {LIMA} !important; border: 1px solid {LIMA}; }}
.vz-nota {{ color: {GRIS}; font-size: 13px; margin-top: 10px; }}
.vz-pasos {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; background: {VIOLETA};
            padding: 22px 24px; }}
.vz-pasos div {{ color: #FFFFFF; font-size: 15px; font-weight: 300; }}
.vz-pasos b {{ display: block; color: {LIMA}; font-size: 17px; font-weight: 600; margin-bottom: 4px; }}
.vz-kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 6px 0 4px; }}
.vz-kpi {{ background: {GRIS_OSCURO}; border-left: 4px solid {LIMA}; padding: 16px 18px; }}
.vz-kpi .v {{ color: {LIMA}; font-size: 34px; font-weight: 300; line-height: 1.1; }}
.vz-kpi .l {{ color: {GRIS}; font-size: 13px; text-transform: uppercase; letter-spacing: .04em; }}
.vz-sev {{ margin: 12px 0 4px; }}
.vz-sev span {{ display: inline-block; padding: 4px 12px; margin: 0 8px 6px 0; font-size: 13px; font-weight: 600; }}
.vz-top {{ margin-top: 12px; }}
.vz-top h3 {{ color: {TEXTO}; font-weight: 400; font-size: 18px; margin: 4px 0 8px; }}
.vz-top li {{ color: {TEXTO}; font-weight: 300; margin-bottom: 4px; }}
.vz-top li b {{ color: {LIMA}; font-weight: 600; }}
#vz-evaluar {{ font-size: 18px !important; font-weight: 700 !important; min-height: 52px; }}
@media (max-width: 760px) {{
  .vz-pasos, .vz-kpis {{ grid-template-columns: 1fr 1fr; }}
  .vz-hero {{ padding: 24px 18px 22px; }}
  .vz-hero h1 {{ font-size: 28px; }}
  .vz-hero h1 br {{ display: none; }}
  .vz-hero p {{ font-size: 16px; }}
}}
"""


def _encabezado() -> str:
    return f"""
<div class="vz-hero">
  <img src="{_logo_data_uri()}" alt="Vozy">
  <h1>Evaluador de calidad<br>de agentes de IA</h1>
  <p>Auditoría automática de las llamadas de cobranza de <b>Lina</b>, agente de voz de Banco Andino:
     13 criterios derivados de sus 10 reglas de negocio, con la cita literal de cada falla.</p>
  <div class="vz-tags">#LLMasJudge #QualityAssurance #ConversationalAI</div>
  <div class="vz-links">
    <a href="/docs" target="_blank">API · Swagger</a>
    <a class="sec" href="{REPO}" target="_blank">Código en GitHub</a>
  </div>
  <div class="vz-nota">Prueba técnica para el cargo de Forward Deployed Engineer en Vozy · Autor: Tomás Carmona ·
     Banco Andino es una entidad ficticia. No es un producto oficial de Vozy.</div>
</div>
<div class="vz-pasos">
  <div><b>1 · Código determinista</b>Presentación, dígitos de verificación, montos, fechas y términos prohibidos.</div>
  <div><b>2 · Gemini como juez</b>Titularidad, presión, escalamiento y cierre, con salida JSON validada.</div>
  <div><b>3 · Evidencia verificada</b>Cada cita es literal del turno; si el LLM falla, el servicio sigue en modo degradado.</div>
</div>"""


def _resumen_html(res: ResultadosLote) -> str:
    rep = res.reporte_agregado
    cumple = sum(c.cumple for c in rep.por_criterio)
    aplicables = sum(c.aplicables for c in rep.por_criterio)
    tasa = f"{100 * cumple / aplicables:.1f}%" if aplicables else "-"
    fallas = sum(len(e.fallas) for e in res.evaluaciones)
    kpis = [(rep.total_conversaciones, "conversaciones"), (rep.puntaje_promedio if rep.puntaje_promedio is not None else "-",
            "puntaje promedio"), (tasa, "cumplimiento de criterios"), (len(rep.conversaciones_criticas),
            "llamadas con falla crítica")]
    tarjetas = "".join(f'<div class="vz-kpi"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in kpis)
    estilos = {"sin_fallas": (LIMA, NEGRO), "leve": ("#E8E8E8", NEGRO), "grave": ("#FFB020", NEGRO),
               "critica": ("#FF4D6D", "#FFFFFF")}
    sev = "".join(f'<span style="background:{estilos[k][0]};color:{estilos[k][1]}">{k.replace("_", " ")}: {n}</span>'
                  for k, n in rep.distribucion_severidad.items())
    nombres_sev = {"leve": "leve", "grave": "grave", "critica": "crítica"}
    top = "".join(f"<li><b>{f.criterio_id}</b> {html.escape(f.nombre)} — {f.ocurrencias} "
                  f"{'llamada' if f.ocurrencias == 1 else 'llamadas'} ({f.porcentaje_conversaciones}%), severidad "
                  f"{nombres_sev[f.severidad]}: {', '.join(f.conversaciones)}</li>"
                  for f in rep.fallas_por_impacto[:5])
    parciales = (f'<div class="vz-nota">{rep.evaluaciones_parciales} evaluaciones parciales (LLM no disponible): sus '
                 f'criterios semánticos quedan "no evaluado" y no cuentan como cumple.</div>'
                 if rep.evaluaciones_parciales else "")
    return (f'<div class="vz-kpis">{tarjetas}</div><div class="vz-sev">{sev}</div>'
            f'<div class="vz-top"><h3>Fallas más importantes (severidad × frecuencia) · {fallas} fallas en total</h3>'
            f'<ol>{top or "<li>Sin fallas.</li>"}</ol></div>{parciales}')


def _tablas(res: ResultadosLote) -> tuple[list[list], list[list], list[list]]:
    por_conv, detalle = [], []
    for e in res.evaluaciones:
        por_conv.append([e.conversacion_id, e.puntaje_global, e.severidad_global, e.estado_evaluacion,
                         ", ".join(e.fallas) or "-"] + [SIMBOLO[c.resultado] for c in e.criterios])
        for c in e.criterios:
            if c.resultado == "no_cumple":
                detalle.append([e.conversacion_id, c.criterio_id, c.severidad, c.explicacion,
                                " | ".join(f"[{x.turno}] {x.texto}" for x in c.evidencia)])
    agregado = [[c.criterio_id, c.nombre, c.aplicables, c.cumple, c.no_cumple, c.no_aplica, c.no_evaluado,
                 "-" if c.tasa_cumplimiento is None else f"{100 * c.tasa_cumplimiento:.1f}%"]
                for c in res.reporte_agregado.por_criterio]
    return por_conv, detalle, agregado


def crear_ui(evaluador: Evaluador, ruta_dataset: Path, max_concurrencia: int) -> gr.Blocks:
    async def evaluar(ruta_archivo: str | None):
        ruta = Path(ruta_archivo) if ruta_archivo else ruta_dataset
        try:
            archivo = ArchivoConversaciones.model_validate(json.loads(ruta.read_text(encoding="utf-8-sig")))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise gr.Error(f"El archivo no es JSON válido: {e}")
        except ValidationError as e:
            err = e.errors()[0]
            raise gr.Error(f"Formato inválido en {'.'.join(str(x) for x in err['loc'])}: {err['msg']}")
        res = await evaluador.evaluar_lote(archivo, max_concurrencia, servicio="ui")
        por_conv, detalle, agregado = _tablas(res)
        salida = Path(tempfile.mkdtemp()) / "results.json"
        salida.write_text(res.model_dump_json(indent=2), encoding="utf-8")
        return _resumen_html(res), por_conv, detalle, agregado, str(salida)

    with gr.Blocks(title="Evaluador de agentes de IA · Vozy") as demo:
        gr.HTML(_encabezado())
        with gr.Row(equal_height=True):
            archivo = gr.File(label="Sube un JSON con la estructura de la prueba (opcional)", file_types=[".json"],
                              type="filepath", scale=3)
            with gr.Column(scale=2):
                gr.Markdown("Si no subes un archivo, se evalúan las **20 conversaciones de la prueba**. "
                            "Un lote de 20 tarda unos 2 minutos; si el servicio estaba inactivo, suma ≈1 minuto.")
                boton = gr.Button("¡Evaluar!", variant="primary", elem_id="vz-evaluar")
        resumen = gr.HTML()
        with gr.Tab("Por conversación"):
            tabla = gr.Dataframe(headers=["id", "puntaje", "severidad", "estado", "fallas"] + IDS_CRITERIOS,
                                 wrap=True)
        with gr.Tab("Fallas con evidencia"):
            fallas = gr.Dataframe(headers=["id", "criterio", "severidad", "explicación", "cita literal [turno]"],
                                  wrap=True)
        with gr.Tab("Reporte agregado"):
            agregado = gr.Dataframe(headers=["criterio", "nombre", "aplicables", "cumple", "no_cumple", "no_aplica",
                                             "no_evaluado", "tasa"], wrap=True)
        descarga = gr.File(label="Descargar results.json")
        boton.click(evaluar, [archivo], [resumen, tabla, fallas, agregado, descarga])
    return demo
