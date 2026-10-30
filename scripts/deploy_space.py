"""Publica el servicio en un Hugging Face Space (Docker) en un solo commit.

GitHub es la fuente de verdad. Al Space se sube solo lo necesario para construir la imagen, y su
README.md (con los metadatos YAML que exige HF) sale de space/README.md, sin tocar el README del repo.

Uso: python scripts/deploy_space.py --space usuario/nombre [--crear] [--secretos]
  Requiere HF_TOKEN (token de escritura) en el entorno o en .env.
  --crear     crea el Space (Docker, CPU Basic) si no existe.
  --secretos  copia GEMINI_API_KEY y la configuración del modelo desde .env como Secret/Variables del Space.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import CommitOperationAdd, HfApi

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVOS = ["Dockerfile", ".dockerignore", "requirements.txt"]
CARPETAS = ["app", "data"]
VARIABLES = ["GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "MAX_CONCURRENCY", "LLM_MIN_INTERVAL_S",
             "LLM_TIMEOUT_S", "LLM_MAX_RETRIES", "GEMINI_THINKING_LEVEL"]


def operaciones() -> list[CommitOperationAdd]:
    ops = [CommitOperationAdd("README.md", str(RAIZ / "space" / "README.md"))]
    ops += [CommitOperationAdd(a, str(RAIZ / a)) for a in ARCHIVOS]
    for carpeta in CARPETAS:
        for ruta in sorted((RAIZ / carpeta).rglob("*")):
            if ruta.is_file() and "__pycache__" not in ruta.parts:
                ops.append(CommitOperationAdd(ruta.relative_to(RAIZ).as_posix(), str(ruta)))
    return ops


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--space", required=True)
    p.add_argument("--crear", action="store_true")
    p.add_argument("--secretos", action="store_true")
    args = p.parse_args()
    load_dotenv(RAIZ / ".env")
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        sys.exit("Falta HF_TOKEN (token de escritura de Hugging Face) en el entorno o en .env")
    api = HfApi(token=token)

    if args.crear:
        api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    if args.secretos:
        clave = os.getenv("GEMINI_API_KEY", "").strip()
        if not clave:
            sys.exit("Falta GEMINI_API_KEY en .env")
        api.add_space_secret(args.space, "GEMINI_API_KEY", clave)
        for nombre in VARIABLES:
            valor = os.getenv(nombre, "").strip()
            if valor:
                api.add_space_variable(args.space, nombre, valor)
        print("Secret GEMINI_API_KEY y variables configurados (valores no mostrados).")

    ops = operaciones()
    for op in ops:
        if op.path_in_repo.startswith(".env") or op.path_in_repo.startswith("eval/"):
            sys.exit(f"Archivo prohibido en el despliegue: {op.path_in_repo}")
    info = api.create_commit(args.space, repo_type="space", operations=ops,
                             commit_message="Despliegue del evaluador desde GitHub")
    print(f"{len(ops)} archivos subidos: {info.commit_url}")
    usuario, nombre = args.space.split("/")
    print(f"URL pública: https://{usuario}-{nombre}.hf.space".lower().replace("_", "-"))


if __name__ == "__main__":
    main()
