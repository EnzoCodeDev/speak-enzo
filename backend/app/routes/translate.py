"""Modo traductor: traducción con matices, alternativas y ejemplos."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..prompts import translate_system
from ..ai.router import get_provider, parse_json_response

router = APIRouter(prefix="/api/translate", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    direction: str = "auto"  # "auto" | "es-en" | "en-es"
    level: str = "beginner"
    provider: str | None = None


@router.post("")
async def translate(req: TranslateRequest):
    provider = get_provider(req.provider)
    if req.direction == "es-en":
        instruction = "Traduce este texto del español al inglés"
    elif req.direction == "en-es":
        instruction = "Traduce este texto del inglés al español"
    else:
        instruction = "Detecta el idioma y traduce al otro (español↔inglés)"

    raw = await provider.chat(
        [
            {"role": "system", "content": translate_system(req.level)},
            {"role": "user", "content": f"{instruction}:\n\n{req.text}"},
        ],
        json_mode=True,
        temperature=0.3,
    )
    data = parse_json_response(raw)
    return {
        "detected_language": data.get("detected_language", "?"),
        "translation": data.get("translation", ""),
        "alternatives": data.get("alternatives") or [],
        "notes": data.get("notes"),
        "examples": data.get("examples") or [],
        "provider": provider.name,
    }
