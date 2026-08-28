"""Almacenamiento de configuración: tokens de IA y proveedor activo.

Los tokens se guardan en backend/data/settings.json (fuera del paquete app,
ignorado por git). El usuario los configura desde la app o vía POST /api/settings.
"""

import json
import threading
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"

_lock = threading.Lock()

DEFAULTS = {
    "active_provider": "gemini",          # "gemini" | "deepseek"
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-chat",
}


def load_settings() -> dict:
    with _lock:
        if SETTINGS_FILE.exists():
            try:
                stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                stored = {}
        else:
            stored = {}
        merged = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
        return merged


def save_settings(updates: dict) -> dict:
    current = load_settings()
    for key, value in updates.items():
        if key in DEFAULTS and value is not None:
            current[key] = value
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return current


def mask_key(key: str) -> str:
    """Devuelve una versión enmascarada del token para mostrar en la UI."""
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * 8 + key[-4:]
