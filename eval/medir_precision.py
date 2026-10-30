"""Mide la precisión del evaluador contra la referencia manual (solo uso offline; el servicio no la lee).

Uso: python eval/medir_precision.py --results results.json [--referencia eval/referencia_manual.json]
                                    [--md out/precision.md]

Reporta, por criterio y global, la matriz de confusión de la detección de "no_cumple" (VP, FP, FN, VN),
precisión, recall, concordancia exacta sobre las 260 etiquetas y la lista de desacuerdos con su cita.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "n/a"


def medir(results: dict, ref: dict) -> dict:
    criterios = ref["criterios"]
    ambiguos = {(a["conversacion"], a["criterio"]): a for a in ref.get("casos_ambiguos", [])}
    evals = {e["conversacion_id"]: e for e in results["evaluaciones"]}
    por_criterio = {c: {"vp": 0, "fp": 0, "fn": 0, "vn": 0, "iguales": 0, "total": 0} for c in criterios}
    desacuerdos = []
    severidad_ok = 0

    for cid, esperado in ref["conversaciones"].items():
        ev = evals.get(cid)
        if ev is None:
            desacuerdos.append({"conversacion": cid, "criterio": "*", "esperado": "evaluada", "obtenido": "ausente"})
            continue
        obtenidos = {c["criterio_id"]: c for c in ev["criterios"]}
        severidad_ok += ev["severidad_global"] == esperado["severidad_esperada"]
        for crit in criterios:
            exp = esperado["criterios"][crit]
            got = obtenidos[crit]
            res = got["resultado"]
            m = por_criterio[crit]
            m["total"] += 1
            m["iguales"] += res == exp
            pe, po = exp == "no_cumple", res == "no_cumple"
            m["vp"] += pe and po
            m["fp"] += po and not pe
            m["fn"] += pe and not po
            m["vn"] += not pe and not po
            if res != exp:
                amb = ambiguos.get((cid, crit))
                desacuerdos.append({
                    "conversacion": cid, "criterio": crit, "esperado": exp, "obtenido": res,
                    "tipo": "FP" if po and not pe else "FN" if pe and not po else "otro",
                    "ambiguo": bool(amb and amb.get("alternativa") == res),
                    "razon_referencia": amb["razon"] if amb else esperado.get("nota", ""),
                    "explicacion": got["explicacion"],
                    "cita": " | ".join(f"[{c['turno']}] {c['texto']}" for c in got["evidencia"]),
                })

    tot = {k: sum(m[k] for m in por_criterio.values()) for k in ("vp", "fp", "fn", "vn", "iguales", "total")}
    return {"por_criterio": por_criterio, "global": tot, "desacuerdos": desacuerdos,
            "severidad_global_ok": severidad_ok, "conversaciones": len(ref["conversaciones"])}


def a_markdown(r: dict) -> str:
    g = r["global"]
    lineas = [
        "| Criterio | VP | FP | FN | VN | Precisión | Recall | Concordancia |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for crit, m in r["por_criterio"].items():
        lineas.append(f"| {crit} | {m['vp']} | {m['fp']} | {m['fn']} | {m['vn']} | {_pct(m['vp'], m['vp'] + m['fp'])} "
                      f"| {_pct(m['vp'], m['vp'] + m['fn'])} | {_pct(m['iguales'], m['total'])} |")
    lineas.append(f"| **Global** | {g['vp']} | {g['fp']} | {g['fn']} | {g['vn']} | {_pct(g['vp'], g['vp'] + g['fp'])} "
                  f"| {_pct(g['vp'], g['vp'] + g['fn'])} | {_pct(g['iguales'], g['total'])} ({g['iguales']}/{g['total']}) |")
    lineas.append("")
    lineas.append(f"Severidad global coincidente: {r['severidad_global_ok']}/{r['conversaciones']}")
    lineas.append("")
    if r["desacuerdos"]:
        lineas += ["| Conv. | Criterio | Esperado | Obtenido | Tipo | ¿Ambiguo listado? | Cita del evaluador |",
                   "|---|---|---|---|---|---|---|"]
        for d in r["desacuerdos"]:
            lineas.append(f"| {d['conversacion']} | {d['criterio']} | {d['esperado']} | {d['obtenido']} | "
                          f"{d.get('tipo', '')} | {'sí' if d.get('ambiguo') else 'no'} | {d.get('cita', '')[:160]} |")
    else:
        lineas.append("Sin desacuerdos.")
    return "\n".join(lineas)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", default="results.json")
    p.add_argument("--referencia", default=str(Path(__file__).parent / "referencia_manual.json"))
    p.add_argument("--md", default="")
    args = p.parse_args()
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    ref = json.loads(Path(args.referencia).read_text(encoding="utf-8"))
    r = medir(results, ref)
    md = a_markdown(r)
    print(md)
    for d in r["desacuerdos"]:
        print(f"\n{d['conversacion']} {d['criterio']}: esperado={d['esperado']} obtenido={d['obtenido']}"
              f"\n  evaluador: {d.get('explicacion', '')}\n  referencia: {d.get('razon_referencia', '')}")
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
