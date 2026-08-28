"""Selecciona el proveedor de IA según la configuración guardada."""

import json
import re

from ..config import load_settings
from .base import AIProvider
from .deepseek import DeepSeekProvider
from .errors import AIError
from .gemini import GeminiProvider


def get_provider(override: str | None = None) -> AIProvider:
    settings = load_settings()
    name = (override or settings["active_provider"]).lower()
    if name == "deepseek":
        return DeepSeekProvider(settings["deepseek_api_key"], settings["deepseek_model"])
    if name == "gemini":
        return GeminiProvider(settings["gemini_api_key"], settings["gemini_model"])
    raise AIError(f"Proveedor desconocido: {name}", status_code=400)


def get_audio_provider() -> AIProvider | None:
    """Devuelve un proveedor capaz de recibir audio (Gemini), si hay token."""
    settings = load_settings()
    if settings["gemini_api_key"]:
        return GeminiProvider(settings["gemini_api_key"], settings["gemini_model"])
    return None


def parse_json_response(raw: str) -> dict:
    """Extrae el JSON de la respuesta del modelo, tolerando ```json ...``` y texto extra."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Último intento: recorta al primer '{' y al último '}'
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise AIError("La IA devolvió un formato inesperado. Intenta de nuevo.")
