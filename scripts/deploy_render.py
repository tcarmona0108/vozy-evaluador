"""Crea o actualiza el servicio en Render (Docker, plan Free) usando la API de Render.

GitHub es la fuente de verdad: Render construye la imagen desde el Dockerfile del repo y redespliega
en cada push a main. La API key de Gemini se copia desde .env como variable de entorno del servicio
(nunca se escribe en el repositorio ni se imprime).

Uso: python scripts/deploy_render.py [--nombre vozy-evaluador-lina] [--repo https://github.com/...]
  Requiere RENDER_API_KEY en el entorno o en .env.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
API = "https://api.render.com/v1"
VARIABLES = ["GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "MAX_CONCURRENCY", "LLM_MIN_INTERVAL_S",
             "LLM_TIMEOUT_S", "LLM_MAX_RETRIES", "GEMINI_THINKING_LEVEL"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--nombre", default="vozy-evaluador-lina")
    p.add_argument("--repo", default="https://github.com/tcarmona0108/vozy-evaluador")
    p.add_argument("--region", default="oregon")
    args = p.parse_args()
    load_dotenv(RAIZ / ".env")
    clave = os.getenv("RENDER_API_KEY", "").strip()
    if not clave:
        sys.exit("Falta RENDER_API_KEY en el entorno o en .env")
    env_vars = [{"key": k, "value": os.environ[k].strip()} for k in VARIABLES if os.getenv(k, "").strip()]
    if not any(v["key"] == "GEMINI_API_KEY" for v in env_vars):
        sys.exit("Falta GEMINI_API_KEY en .env")

    with httpx.Client(base_url=API, headers={"Authorization": f"Bearer {clave}", "Accept": "application/json"},
                      timeout=60) as api:
        owners = api.get("/owners", params={"limit": 20})
        owners.raise_for_status()
        owner = owners.json()[0]["owner"]
        print(f"workspace: {owner['name']} ({owner['id']})")

        existentes = api.get("/services", params={"name": args.nombre, "ownerId": owner["id"]})
        existentes.raise_for_status()
        if existentes.json():
            servicio = existentes.json()[0]["service"]
            print(f"servicio existente: {servicio['id']}")
            r = api.put(f"/services/{servicio['id']}/env-vars", json=env_vars)
            r.raise_for_status()
            r = api.post(f"/services/{servicio['id']}/deploys", json={"clearCache": "do_not_clear"})
            r.raise_for_status()
        else:
            r = api.post("/services", json={
                "type": "web_service", "name": args.nombre, "ownerId": owner["id"],
                "repo": args.repo, "branch": "main", "autoDeployTrigger": "commit", "envVars": env_vars,
                "serviceDetails": {"runtime": "docker", "plan": "free", "region": args.region,
                                   "healthCheckPath": "/health",
                                   "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."}},
            })
            if r.status_code >= 400:
                sys.exit(f"Render respondió {r.status_code}: {r.text[:800]}")
            servicio = r.json()["service"]
            print(f"servicio creado: {servicio['id']}")
        print(f"variables configuradas: {', '.join(v['key'] for v in env_vars)} (valores no mostrados)")

        url = servicio.get("serviceDetails", {}).get("url")
        print(f"URL pública: {url}")
        for _ in range(90):  # hasta ~15 min de construcción
            deploys = api.get(f"/services/{servicio['id']}/deploys", params={"limit": 1})
            deploys.raise_for_status()
            estado = deploys.json()[0]["deploy"]["status"] if deploys.json() else "pendiente"
            print(f"  despliegue: {estado}", flush=True)
            if estado in ("live", "build_failed", "update_failed", "canceled", "deactivated"):
                break
            time.sleep(10)
        sys.exit(0 if estado == "live" else 1)


if __name__ == "__main__":
    main()
