"""Configuración por variables de entorno (nunca se registra la API key)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _int(nombre: str, defecto: int) -> int:
    valor = os.getenv(nombre, "").strip()
    return int(valor) if valor else defecto


def _float(nombre: str, defecto: float) -> float:
    valor = os.getenv(nombre, "").strip()
    return float(valor) if valor else defecto


RESPALDO_DEFECTO = "gemini-3-flash-preview,gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"


@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    modelo: str
    modelos_respaldo: tuple[str, ...]
    thinking_level: str | None
    thinking_budget: int | None
    max_concurrencia: int
    intervalo_min_llm_s: float
    timeout_llm_s: float
    max_reintentos: int
    ruta_dataset: Path


def cargar_config() -> Config:
    budget = os.getenv("GEMINI_THINKING_BUDGET", "").strip()
    # El tier gratuito limita a 20 solicitudes/día por modelo: el respaldo es una cadena (separada por comas).
    respaldo = os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or RESPALDO_DEFECTO
    return Config(
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        modelo=os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.6-flash",
        modelos_respaldo=tuple(m.strip() for m in respaldo.split(",") if m.strip()),
        thinking_level=os.getenv("GEMINI_THINKING_LEVEL", "").strip() or None,
        thinking_budget=int(budget) if budget else None,
        max_concurrencia=_int("MAX_CONCURRENCY", 2),
        intervalo_min_llm_s=_float("LLM_MIN_INTERVAL_S", 0.0),
        timeout_llm_s=_float("LLM_TIMEOUT_S", 60.0),
        max_reintentos=_int("LLM_MAX_RETRIES", 2),
        ruta_dataset=RAIZ / "data" / "conversaciones_prueba_fde.json",
    )
