"""Interfaz mínima de un proveedor LLM: cambiar de proveedor = implementar ClienteLLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RespuestaLLMCruda:
    texto: str
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_razonamiento: int = 0
    avisos: list[str] = field(default_factory=list)


class ErrorLLM(Exception):
    """Fallo definitivo del proveedor (tras reintentos y modelo de respaldo)."""


class ClienteLLM(Protocol):
    modelo: str

    async def generar_json(self, sistema: str, usuario: str, esquema_json: dict) -> RespuestaLLMCruda:
        """Devuelve texto JSON que debería cumplir esquema_json. Lanza ErrorLLM si no lo logra."""
        ...
