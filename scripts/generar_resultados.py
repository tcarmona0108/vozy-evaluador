"""Genera results.json llamando a la URL PÚBLICA del servicio (prueba de que lo produjo el despliegue).

Uso: python scripts/generar_resultados.py --url https://usuario-space.hf.space [--archivo data/...json]
                                          [--salida results.json] [--intentos 3]

Si alguna conversación vuelve en estado "parcial" (cuota o caída del LLM), reintenta el lote: las
evaluaciones completas salen de la caché del servicio y solo se vuelven a consultar las parciales.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.schemas import ResultadosLote  # noqa: E402


def verificar(res: ResultadosLote, esperadas: int) -> list[str]:
    problemas = []
    if len(res.evaluaciones) != esperadas:
        problemas.append(f"{len(res.evaluaciones)} evaluaciones de {esperadas}")
    for e in res.evaluaciones:
        if e.estado_evaluacion != "completa":
            problemas.append(f"{e.conversacion_id} parcial: {e.metadatos.errores[-1:] }")
        for c in e.criterios:
            if c.resultado == "no_evaluado":
                problemas.append(f"{e.conversacion_id}/{c.criterio_id} no_evaluado")
            if c.resultado == "no_cumple" and not c.evidencia:
                problemas.append(f"{e.conversacion_id}/{c.criterio_id} no_cumple sin cita")
    return problemas


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--archivo", default="data/conversaciones_prueba_fde.json")
    p.add_argument("--salida", default="results.json")
    p.add_argument("--intentos", type=int, default=3)
    args = p.parse_args()
    url = args.url.rstrip("/")
    cuerpo = json.loads(Path(args.archivo).read_text(encoding="utf-8"))
    esperadas = len(cuerpo["conversaciones"])

    with httpx.Client(timeout=httpx.Timeout(1200.0, connect=60.0)) as cliente:
        salud = cliente.get(f"{url}/health")
        salud.raise_for_status()
        print("health:", salud.json())
        res = None
        for intento in range(1, args.intentos + 1):
            t0 = time.time()
            r = cliente.post(f"{url}/evaluate/batch", json=cuerpo)
            r.raise_for_status()
            res = ResultadosLote.model_validate(r.json())
            problemas = verificar(res, esperadas)
            print(f"intento {intento}: {time.time() - t0:.0f}s, problemas: {len(problemas)}")
            if not problemas:
                break
            for x in problemas[:10]:
                print("  -", x)
            time.sleep(30)

    Path(args.salida).write_text(res.model_dump_json(indent=2), encoding="utf-8")
    problemas = verificar(res, esperadas)
    print(f"-> {args.salida} ({'OK' if not problemas else f'{len(problemas)} problemas'})")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
