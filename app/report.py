"""Reporte agregado: tasa de cumplimiento por criterio y rankings de fallas."""
from __future__ import annotations

from collections import Counter

from app.rubric import PESOS, RUBRICA
from app.schemas import CriterioAgregado, EvaluacionConversacion, FallaFrecuente, ReporteAgregado


def generar_reporte(evaluaciones: list[EvaluacionConversacion]) -> ReporteAgregado:
    total = len(evaluaciones)
    por_criterio: list[CriterioAgregado] = []
    fallas: list[FallaFrecuente] = []

    for i, crit in enumerate(RUBRICA):
        resultados = [e.criterios[i] for e in evaluaciones]
        conteo = Counter(r.resultado for r in resultados)
        aplicables = conteo["cumple"] + conteo["no_cumple"]
        por_criterio.append(CriterioAgregado(
            criterio_id=crit.id, nombre=crit.nombre, aplicables=aplicables,
            cumple=conteo["cumple"], no_cumple=conteo["no_cumple"], no_aplica=conteo["no_aplica"],
            no_evaluado=conteo["no_evaluado"],
            tasa_cumplimiento=round(conteo["cumple"] / aplicables, 3) if aplicables else None,
        ))
        con_falla = [(e.conversacion_id, r.severidad) for e, r in zip(evaluaciones, resultados)
                     if r.resultado == "no_cumple"]
        if con_falla:
            severidades = [s for _, s in con_falla]
            fallas.append(FallaFrecuente(
                criterio_id=crit.id, nombre=crit.nombre, ocurrencias=len(con_falla),
                porcentaje_conversaciones=round(100 * len(con_falla) / total, 1),
                impacto=sum(PESOS[s] for s in severidades),
                severidad=max(severidades, key=PESOS.__getitem__),
                conversaciones=[cid for cid, _ in con_falla],
            ))

    puntajes = [e.puntaje_global for e in evaluaciones if e.puntaje_global is not None]
    distribucion = Counter(e.severidad_global for e in evaluaciones)
    orden_rubrica = {c.id: i for i, c in enumerate(RUBRICA)}
    return ReporteAgregado(
        total_conversaciones=total,
        evaluaciones_completas=sum(e.estado_evaluacion == "completa" for e in evaluaciones),
        evaluaciones_parciales=sum(e.estado_evaluacion == "parcial" for e in evaluaciones),
        puntaje_promedio=round(sum(puntajes) / len(puntajes), 1) if puntajes else None,
        distribucion_severidad={k: distribucion.get(k, 0) for k in ("sin_fallas", "leve", "grave", "critica")},
        por_criterio=por_criterio,
        fallas_mas_frecuentes=sorted(fallas, key=lambda f: (-f.ocurrencias, -f.impacto, orden_rubrica[f.criterio_id])),
        fallas_por_impacto=sorted(fallas, key=lambda f: (-f.impacto, -f.ocurrencias, orden_rubrica[f.criterio_id])),
        conversaciones_criticas=[e.conversacion_id for e in evaluaciones if e.severidad_global == "critica"],
    )
