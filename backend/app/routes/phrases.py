"""Modo aprendizaje esencial: las 1000 frases más esenciales del inglés (beta)."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/phrases", tags=["phrases"])

PHRASES_FILE = Path(__file__).resolve().parent.parent / "data" / "essential_phrases.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not PHRASES_FILE.exists():
        raise HTTPException(500, "essential_phrases.json no encontrado en el servidor.")
    return json.loads(PHRASES_FILE.read_text(encoding="utf-8"))


@router.get("")
async def list_categories():
    data = _load()
    return {
        "version": data.get("version", 1),
        "total": data.get("total", 0),
        "categories": [
            {
                "id": c["id"],
                "name_es": c["name_es"],
                "name_en": c["name_en"],
                "emoji": c["emoji"],
                "count": len(c["phrases"]),
            }
            for c in data["categories"]
        ],
    }


@router.get("/{category_id}")
async def get_category(category_id: str):
    data = _load()
    for c in data["categories"]:
        if c["id"] == category_id:
            return c
    raise HTTPException(404, f"Categoría '{category_id}' no existe.")
