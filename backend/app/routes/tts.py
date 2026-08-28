"""Texto a voz con Piper: voz neuronal que vive guardada en el servidor.

El modelo (data/tts/*.onnx) y el motor (data/tts/piper/) se guardan una sola
vez en el backend; cualquier app cliente pide aquí el audio ya sintetizado,
así no tiene que descargar nada. Las frases se cachean en data/tts/cache.
"""

import asyncio
import hashlib
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..ai.errors import AIError

router = APIRouter(prefix="/api/tts", tags=["tts"])

TTS_DIR = Path(__file__).resolve().parents[2] / "data" / "tts"
PIPER_BIN = TTS_DIR / "piper" / "piper"
CACHE_DIR = TTS_DIR / "cache"

MAX_TEXT_CHARS = 2000


def _find_model() -> Path | None:
    if not TTS_DIR.exists():
        return None
    models = sorted(TTS_DIR.glob("*.onnx"))
    return models[0] if models else None


class TtsRequest(BaseModel):
    text: str
    # 1.0 = velocidad normal; más alto = más lento (útil para estudiantes).
    length_scale: float = 1.0


@router.get("/status")
async def status():
    model = _find_model()
    return {
        "available": PIPER_BIN.exists() and model is not None,
        "voice": model.stem if model else None,
    }


@router.post("")
async def synthesize(req: TtsRequest):
    text = req.text.strip()
    if not text:
        raise AIError("No hay texto para leer.", status_code=400)
    text = text[:MAX_TEXT_CHARS]

    model = _find_model()
    if not PIPER_BIN.exists() or model is None:
        raise AIError(
            "El servidor no tiene la voz instalada (falta data/tts con Piper).",
            status_code=501,
        )

    scale = max(0.7, min(2.0, req.length_scale))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5(f"{model.name}|{scale:.2f}|{text}".encode()).hexdigest()
    out = CACHE_DIR / f"{key}.wav"

    if not out.exists():
        proc = await asyncio.create_subprocess_exec(
            str(PIPER_BIN),
            "--model", str(model),
            "--length_scale", f"{scale:.2f}",
            "--output_file", str(out),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate(text.encode())
        if proc.returncode != 0 or not out.exists():
            detail = (err or b"").decode(errors="replace")[:200]
            raise AIError(f"La síntesis de voz falló: {detail}", status_code=500)

    return FileResponse(out, media_type="audio/wav")
