"""Evaluación de pronunciación y acento.

Dos caminos:
1. AUDIO REAL (recomendado, requiere token de Gemini): la app graba al usuario
   y sube el audio; Gemini lo escucha y evalúa el acento de verdad.
2. TRANSCRIPCIÓN (fallback, funciona con DeepSeek): la app usa el reconocimiento
   de voz del teléfono y manda el texto transcrito; la IA compara contra la
   frase objetivo (lo que el reconocedor "malentiende" delata la pronunciación).
"""

from fastapi import APIRouter, File, Form, UploadFile

from .. import prompts
from ..ai.errors import AIError
from ..ai.router import get_audio_provider, get_provider, parse_json_response

router = APIRouter(prefix="/api/pronunciation", tags=["pronunciation"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


def _normalize_result(data: dict, mode: str) -> dict:
    words = []
    for w in data.get("words") or []:
        words.append(
            {
                "word": str(w.get("word", "")),
                "ok": bool(w.get("ok", False)),
                "tip_es": w.get("tip_es"),
            }
        )
    score = data.get("score", 0)
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = 0
    return {
        "mode": mode,  # "audio" | "transcript"
        "heard": data.get("heard", ""),
        "score": score,
        "feedback_es": data.get("feedback_es", ""),
        "words": words,
    }


@router.post("/evaluate")
async def evaluate(
    target_text: str = Form(...),
    audio: UploadFile | None = File(default=None),
    transcript: str | None = Form(default=None),
    level: str = Form(default="beginner"),
):
    if audio is not None:
        audio_bytes = await audio.read()
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise AIError("El audio es demasiado grande (máx 10 MB).", status_code=413)
        if not audio_bytes:
            raise AIError("El audio llegó vacío. Graba de nuevo.", status_code=400)

        provider = get_audio_provider()
        if provider is None:
            # Sin Gemini no hay evaluación de audio: cae al modo transcripción.
            if not transcript:
                raise AIError(
                    "La evaluación con audio real necesita un token de Gemini. "
                    "Configúralo en Ajustes, o usa el modo transcripción.",
                    status_code=428,
                )
        else:
            mime = audio.content_type or ""
            if not mime.startswith("audio/"):
                mime = "audio/wav"  # la app graba WAV; octet-stream confunde a Gemini
            raw = await provider.chat_with_audio(
                system=prompts.pronunciation_audio_system(level),
                user_text=(
                    f'Frase objetivo que el estudiante debía decir: "{target_text}"\n'
                    "Escucha el audio adjunto y evalúa su pronunciación."
                ),
                audio_bytes=audio_bytes,
                audio_mime=mime,
            )
            return _normalize_result(parse_json_response(raw), mode="audio")

    if not transcript:
        raise AIError(
            "Manda el audio grabado o la transcripción del reconocedor de voz.",
            status_code=400,
        )

    provider = get_provider()
    raw = await provider.chat(
        [
            {"role": "system", "content": prompts.pronunciation_text_system(level)},
            {
                "role": "user",
                "content": (
                    f'FRASE OBJETIVO: "{target_text}"\n'
                    f'TRANSCRIPCIÓN DEL TELÉFONO: "{transcript}"'
                ),
            },
        ],
        json_mode=True,
        temperature=0.3,
    )
    return _normalize_result(parse_json_response(raw), mode="transcript")
