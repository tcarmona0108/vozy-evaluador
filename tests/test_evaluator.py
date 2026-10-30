"""Orquestación con LLM simulado: combinación, modo degradado, caché y reporte (datos sintéticos)."""
import asyncio
import json
from pathlib import Path

from app.evaluator import Evaluador
from app.llm.base import ErrorLLM, RespuestaLLMCruda
from app.rubric import IDS_CRITERIOS
from app.schemas import ArchivoConversaciones, Conversacion, EspecificacionAgente

FIX = json.loads((Path(__file__).parent / "fixtures" / "sinteticas.json").read_text(encoding="utf-8"))
CONVS = {c["id"]: Conversacion.model_validate(c) for c in FIX["conversaciones"]}
SPEC = EspecificacionAgente(nombre_agente="Lina", empresa="Banco Andino", reglas=["R1. ...", "R2. ..."])


def juicio(cid, res="cumple", turno=1, texto="Lina", tipo="ninguna"):
    return {"criterio_id": cid, "resultado": res, "tipo_falla_r10": tipo,
            "citas": [{"turno": turno, "texto": texto}], "explicacion": "Ok. Dos. Tres."}


def respuesta(es_titular=True, juicios=None, compromiso=None):
    j = {c: juicio(c, "no_aplica") for c in ("R3", "R6", "R7", "R8")}
    j["R9"] = juicio("R9", "cumple")
    j["R10"] = juicio("R10", "cumple")
    j.update(juicios or {})
    fecha, turno = compromiso or (None, None)
    return json.dumps({
        "hechos": {"es_titular": es_titular, "cita_titular": None, "hay_compromiso_pago": fecha is not None,
                   "fecha_compromiso_textual": fecha,
                   "cita_compromiso": {"turno": turno, "texto": fecha} if fecha else None,
                   "cliente_pide_beneficio": False, "agente_ofrece_beneficio": False, "cliente_pide_humano": False,
                   "cliente_disputa": False, "cliente_dice_ya_pago": False, "cliente_colgo_antes_del_cierre": False},
        "juicios": list(j.values()),
    })


class LLMFalso:
    modelo = "falso-1"

    def __init__(self, salidas):
        self.salidas = list(salidas)
        self.llamadas = 0

    async def generar_json(self, sistema, usuario, esquema_json):
        self.llamadas += 1
        s = self.salidas.pop(0) if self.salidas else ErrorLLM("sin más salidas")
        if isinstance(s, Exception):
            raise s
        return RespuestaLLMCruda(texto=s, modelo=self.modelo, tokens_entrada=100, tokens_salida=20)


def correr(coro):
    return asyncio.run(coro)


def por_id(ev):
    return {c.criterio_id: c for c in ev.criterios}


def test_evaluacion_completa_y_codigo_gana_en_r10():
    llm = LLMFalso([respuesta(compromiso=("jueves 5 de noviembre", 9))])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S02"]))
    c = por_id(ev)
    assert ev.estado_evaluacion == "completa"
    assert [x.criterio_id for x in ev.criterios] == IDS_CRITERIOS
    assert c["R10"].resultado == "no_cumple" and c["R10"].severidad == "critica"
    assert any("R10" in d and "gana el código" in d for d in ev.metadatos.discrepancias)
    assert c["R5"].resultado == "cumple"            # 2026-11-05 = llamada + 2 días
    assert ev.severidad_global == "critica" and ev.fallas == ["R10"]
    assert c["R9"].explicacion == "Ok. Dos."        # máximo 2 frases


def test_r5_dia_sin_numero_y_fecha_pasada():
    ev = correr(Evaluador(LLMFalso([respuesta(compromiso=("el jueves", 8))]), SPEC).evaluar(CONVS["S02"]))
    assert por_id(ev)["R5"].resultado == "no_cumple"
    ev = correr(Evaluador(LLMFalso([respuesta(compromiso=("lunes 2", 8))]), SPEC).evaluar(CONVS["S05"]))
    assert por_id(ev)["R5"].resultado == "no_cumple"  # 2 de noviembre < 3 de noviembre


def test_r3_revelacion_a_tercero_la_decide_el_codigo():
    llm = LLMFalso([respuesta(es_titular=False, juicios={"R3": juicio("R3", "cumple", 5, "¿A qué hora lo encuentro?")})])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S03"]))
    c = por_id(ev)
    assert c["R3"].resultado == "no_cumple" and c["R3"].severidad == "critica"
    assert c["R2b"].resultado == "no_aplica" and c["R4a"].resultado == "no_aplica"


def test_cita_inventada_no_se_publica():
    falsa = juicio("R7", "no_cumple", 7, "El agente dijo algo que nunca dijo")
    ev = correr(Evaluador(LLMFalso([respuesta(juicios={"R7": falsa})]), SPEC).evaluar(CONVS["S04"]))
    r7 = por_id(ev)["R7"]
    tr = CONVS["S04"].transcripcion
    assert r7.resultado == "no_cumple"
    assert all(c.texto in tr[c.turno - 1].texto for c in r7.evidencia)


def test_coherencia_hechos_convierte_cumple_en_no_aplica():
    # El LLM juzga R6 "cumple" aunque sus propios hechos dicen que nadie pidió ni ofreció beneficios.
    llm = LLMFalso([respuesta(juicios={"R6": juicio("R6", "cumple")}, compromiso=("viernes 6 de noviembre", 7))])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S01"]))
    assert por_id(ev)["R6"].resultado == "no_aplica"
    assert any(d.startswith("R6:") for d in ev.metadatos.discrepancias)


def test_coherencia_nunca_descarta_un_no_cumple():
    falla = juicio("R6", "no_cumple", 5, "Su tarjeta de crédito registra un saldo vencido")
    llm = LLMFalso([respuesta(juicios={"R6": falla}, compromiso=("viernes 6 de noviembre", 7))])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S01"]))
    assert por_id(ev)["R6"].resultado == "no_cumple"


def test_modo_degradado_por_excepcion():
    llm = LLMFalso([ErrorLLM("429 cuota agotada")])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S02"]))
    c = por_id(ev)
    assert ev.estado_evaluacion == "parcial"
    assert c["R1a"].resultado == "cumple" and c["R4a"].resultado == "cumple"   # código sigue funcionando
    assert c["R10"].resultado == "no_cumple"                                   # términos prohibidos por código
    assert c["R6"].resultado == "no_evaluado" and c["R5"].resultado == "no_evaluado"
    assert any("429" in e for e in ev.metadatos.errores)


def test_modo_degradado_por_json_invalido_con_un_reintento():
    llm = LLMFalso(["{no es json", '{"hechos": {}}'])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S01"]))
    assert llm.llamadas == 2
    assert ev.estado_evaluacion == "parcial"
    assert sum("inválida" in e for e in ev.metadatos.errores) == 2


def test_reintento_de_validacion_recupera():
    llm = LLMFalso(["{no es json", respuesta(compromiso=("viernes 6 de noviembre", 7))])
    ev = correr(Evaluador(llm, SPEC).evaluar(CONVS["S01"]))
    assert ev.estado_evaluacion == "completa" and ev.severidad_global == "sin_fallas"
    assert ev.puntaje_global == 100.0


def test_sin_llm_configurado():
    ev = correr(Evaluador(None, SPEC).evaluar(CONVS["S04"]))
    c = por_id(ev)
    assert ev.estado_evaluacion == "parcial"
    assert c["R1b"].resultado == "no_cumple" and c["R2b"].resultado == "no_cumple"


def test_cache_evita_segunda_llamada():
    llm = LLMFalso([respuesta(compromiso=("viernes 6 de noviembre", 7))])
    ev_ = Evaluador(llm, SPEC)
    correr(ev_.evaluar(CONVS["S01"]))
    segunda = correr(ev_.evaluar(CONVS["S01"]))
    assert llm.llamadas == 1 and segunda.metadatos.desde_cache


def test_lote_no_se_detiene_y_reporte():
    convs = [CONVS["S01"], CONVS["S02"], CONVS["S04"]]
    archivo = ArchivoConversaciones(especificacion_agente=SPEC, conversaciones=convs)
    llm = LLMFalso([respuesta(compromiso=("viernes 6 de noviembre", 7)), ErrorLLM("500"), ErrorLLM("500")])
    res = correr(Evaluador(llm, SPEC).evaluar_lote(archivo, max_concurrencia=1))
    assert len(res.evaluaciones) == 3
    rep = res.reporte_agregado
    assert rep.total_conversaciones == 3 and rep.evaluaciones_parciales == 2
    r1b = next(x for x in rep.por_criterio if x.criterio_id == "R1b")
    assert r1b.no_cumple == 1 and r1b.tasa_cumplimiento == round(2 / 3, 3)
    assert rep.fallas_por_impacto[0].impacto >= rep.fallas_por_impacto[-1].impacto
