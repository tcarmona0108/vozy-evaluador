"""Evalúa un archivo de conversaciones en local (sin servidor), para desarrollo y medición.

Uso: python scripts/evaluar_local.py [--archivo data/conversaciones_prueba_fde.json] [--ids C01,C02]
                                     [--salida out/results_local.json]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import cargar_config  # noqa: E402
from app.evaluator import Evaluador  # noqa: E402
from app.llm.gemini import ClienteGemini  # noqa: E402
from app.llm.base import RespuestaLLMCruda  # noqa: E402
from app.schemas import ArchivoConversaciones, EspecificacionAgente  # noqa: E402


class CacheDisco:
    """Solo desarrollo: guarda la respuesta cruda del LLM por hash del prompt para re-medir sin gastar cuota
    (el tier gratuito permite 20 solicitudes/día por modelo). Un cambio de prompt invalida la entrada."""

    def __init__(self, llm, carpeta: Path):
        self.llm, self.carpeta = llm, carpeta
        self.modelo = llm.modelo
        carpeta.mkdir(parents=True, exist_ok=True)

    async def generar_json(self, sistema: str, usuario: str, esquema_json: dict) -> RespuestaLLMCruda:
        clave = hashlib.sha256(json.dumps([sistema, usuario, esquema_json], sort_keys=True).encode()).hexdigest()
        ruta = self.carpeta / f"{clave}.json"
        if ruta.exists():
            return RespuestaLLMCruda(**json.loads(ruta.read_text(encoding="utf-8")))
        r = await self.llm.generar_json(sistema, usuario, esquema_json)
        ruta.write_text(json.dumps(r.__dict__, ensure_ascii=False), encoding="utf-8")
        return r


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--archivo", default="data/conversaciones_prueba_fde.json")
    p.add_argument("--ids", default="")
    p.add_argument("--salida", default="out/results_local.json")
    p.add_argument("--sin-cache-disco", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    config = cargar_config()
    dataset = json.loads(config.ruta_dataset.read_text(encoding="utf-8"))
    spec = EspecificacionAgente.model_validate(dataset["especificacion_agente"])
    archivo = ArchivoConversaciones.model_validate(json.loads(Path(args.archivo).read_text(encoding="utf-8")))
    if args.ids:
        ids = set(args.ids.split(","))
        archivo.conversaciones = [c for c in archivo.conversaciones if c.id in ids]

    llm = ClienteGemini(config)
    if not args.sin_cache_disco:
        llm = CacheDisco(llm, Path("out/llm_cache"))
    evaluador = Evaluador(llm, spec)
    resultados = asyncio.run(evaluador.evaluar_lote(archivo, config.max_concurrencia, servicio="local"))
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(resultados.model_dump_json(indent=2), encoding="utf-8")

    for e in resultados.evaluaciones:
        m = e.metadatos
        print(f"{e.conversacion_id} {e.estado_evaluacion:8} {e.severidad_global:10} pts={e.puntaje_global} "
              f"fallas={','.join(e.fallas) or '-'} {m.modelo} {m.latencia_ms}ms in={m.tokens_entrada} "
              f"out={m.tokens_salida} think={m.tokens_razonamiento} err={len(m.errores)} disc={len(m.discrepancias)}")
    print(f"-> {salida}")


if __name__ == "__main__":
    main()
