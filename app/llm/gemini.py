"""Cliente Gemini (SDK google-genai): salida JSON con esquema, reintentos y modelo de respaldo."""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time

from google import genai
from google.genai import errors, types

from app.config import Config
from app.llm.base import ErrorLLM, RespuestaLLMCruda

log = logging.getLogger("evaluador.llm")

REINTENTABLES = {408, 429, 500, 502, 503, 504}
_RETRY_DELAY = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"](\d+(?:\.\d+)?)s")
MAX_ESPERA_S = 60.0  # si la API pide esperar más (p. ej. cuota diaria agotada), se pasa al respaldo


class ClienteGemini:
    def __init__(self, config: Config):
        if not config.gemini_api_key:
            raise ErrorLLM("GEMINI_API_KEY no está configurada")
        self.config = config
        self.modelo = config.modelo
        self._cliente = genai.Client(
            api_key=config.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(config.timeout_llm_s * 1000)),
        )
        self._candado = asyncio.Lock()
        self._ultima_llamada = 0.0
        self._agotado_hasta: dict[str, float] = {}

    def _config_generacion(self, sistema: str, esquema_json: dict) -> types.GenerateContentConfig:
        thinking = None
        if self.config.thinking_level or self.config.thinking_budget is not None:
            thinking = types.ThinkingConfig(thinking_level=self.config.thinking_level,
                                            thinking_budget=self.config.thinking_budget)
        return types.GenerateContentConfig(
            system_instruction=sistema,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=esquema_json,
            thinking_config=thinking,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    async def _espaciar(self) -> None:
        """Intervalo mínimo entre llamadas (para no superar las RPM del tier gratuito)."""
        if self.config.intervalo_min_llm_s <= 0:
            return
        async with self._candado:
            espera = self._ultima_llamada + self.config.intervalo_min_llm_s - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            self._ultima_llamada = time.monotonic()

    async def _llamar(self, modelo: str, sistema: str, usuario: str, esquema_json: dict) -> RespuestaLLMCruda:
        await self._espaciar()
        resp = await asyncio.wait_for(
            self._cliente.aio.models.generate_content(
                model=modelo, contents=usuario, config=self._config_generacion(sistema, esquema_json)),
            timeout=self.config.timeout_llm_s,
        )
        texto = resp.text or ""
        if not texto.strip():
            razon = resp.candidates[0].finish_reason if resp.candidates else "sin candidatos"
            raise ErrorLLM(f"respuesta vacía de {modelo} ({razon})")
        uso = resp.usage_metadata
        return RespuestaLLMCruda(
            texto=texto, modelo=modelo,
            tokens_entrada=(uso.prompt_token_count or 0) if uso else 0,
            tokens_salida=(uso.candidates_token_count or 0) if uso else 0,
            tokens_razonamiento=(uso.thoughts_token_count or 0) if uso else 0,
        )

    async def generar_json(self, sistema: str, usuario: str, esquema_json: dict) -> RespuestaLLMCruda:
        avisos: list[str] = []
        modelos = list(dict.fromkeys([self.config.modelo, *self.config.modelos_respaldo]))

        for modelo in modelos:
            if time.monotonic() < self._agotado_hasta.get(modelo, 0.0):
                continue  # cuota diaria agotada o modelo no disponible: no se gasta una llamada en él
            for intento in range(self.config.max_reintentos + 1):
                try:
                    r = await self._llamar(modelo, sistema, usuario, esquema_json)
                    r.avisos = avisos
                    return r
                except errors.APIError as e:
                    msg = f"{modelo}: error {e.code} {getattr(e, 'status', '') or ''}".strip()
                    if e.code not in REINTENTABLES:
                        avisos.append(f"{msg} (no reintentable; se usa el respaldo)")
                        self._agotado_hasta[modelo] = time.monotonic() + 3600
                        break
                    m = _RETRY_DELAY.search(str(e.details))
                    espera = float(m.group(1)) if m else min(2 ** intento * 2.0, 30.0) + random.uniform(0, 1.5)
                    if espera > MAX_ESPERA_S:
                        avisos.append(f"{msg}: cuota agotada (la API pide esperar {espera:.0f}s); se usa el respaldo")
                        self._agotado_hasta[modelo] = time.monotonic() + espera
                        break
                    avisos.append(f"{msg}: reintento {intento + 1} en {espera:.1f}s")
                except (asyncio.TimeoutError, TimeoutError):
                    espera = min(2 ** intento * 2.0, 30.0) + random.uniform(0, 1.5)
                    avisos.append(f"{modelo}: timeout; reintento {intento + 1} en {espera:.1f}s")
                except ErrorLLM as e:
                    espera = 1.0 + random.uniform(0, 1.0)
                    avisos.append(f"{e}; reintento {intento + 1}")
                except Exception as e:  # red, SDK u otros: se registran sin detener el servicio
                    espera = min(2 ** intento * 2.0, 30.0) + random.uniform(0, 1.5)
                    avisos.append(f"{modelo}: {type(e).__name__}: {str(e)[:160]}")
                if intento < self.config.max_reintentos:
                    log.warning(avisos[-1])
                    await asyncio.sleep(espera)
        raise ErrorLLM("; ".join(avisos[-4:]) or "fallo del LLM")
