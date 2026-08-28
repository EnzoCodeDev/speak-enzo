"""Configuración persistente en ~/.config/vrchat-subtitulos/config.json."""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "vrchat-subtitulos"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "translate": False,               # traducir subtítulos al español
    "ollama_url": "http://localhost:11434",
    "ollama_model": "",               # vacío = autodetectar
    "font_size": 15,
    "overlay_width": 780,             # tamaño FIJO de la ventana
    "overlay_height": 370,
    "hotkey_translate": "9",          # tecla global: traducir pantalla
    "hotkey_suggest": "0",            # tecla global: respuesta sugerida
    "min_volume": 0.012,              # ignora voces por debajo (lejanas);
                                      # sube a 0.02 para ser más estricto
    "pron_model": "qwen3.5:4b",       # modelo para la fonética en español
    "translate_last_n": 10,           # (ya no se usa: la tecla 9 traduce todo)
    # dónde se guardan las conversaciones por semana (las lee Enzo Speak):
    # <repo enzo-speak>/web/vrchat, relativo a esta app dentro del repo
    "transcript_dir": str(Path(__file__).resolve().parent.parent.parent
                          / "web" / "vrchat"),
}


def load():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text()))
    except Exception:
        pass
    return cfg


def save(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
