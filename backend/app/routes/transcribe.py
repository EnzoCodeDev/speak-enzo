"""Transcripción de voz a texto con Gemini.

Lo usa la app de escritorio (Linux), donde no existe reconocimiento de voz
nativo: graba un WAV con el micrófono y lo sube aquí para convertirlo en texto.
Con assess_accent=true, además evalúa el acento del estudiante en esa misma
pasada (una sola llamada a Gemini).
"""

from fastapi import APIRouter, File, Form, UploadFile

from .. import prompts
from ..ai.errors import AIError
from ..ai.router import get_audio_provider, parse_json_response

router = APIRouter(prefix="/api/transcribe", tags=["transcribe"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("")
async def transcribe(
    audio: UploadFile = File(...),
    language: str = Form(default="en"),
    assess_accent: bool = Form(default=False),
    level: str = Form(default="beginner"),
):
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise AIError("El audio es demasiado grande (máx 10 MB).", status_code=413)
    if not audio_bytes:
        raise AIError("El audio llegó vacío. Graba de nuevo.", status_code=400)

    provider = get_audio_provider()
    if provider is None:
        raise AIError(
            "La transcripción necesita un token de Gemini. Configúralo en Ajustes.",
            status_code=428,
        )

    mime = audio.content_type or ""
    if not mime.startswith("audio/"):
        mime = "audio/wav"

    if assess_accent:
        raw = await provider.chat_with_audio(
            system=prompts.transcribe_accent_system(level),
            user_text=(
                "Transcribe el audio adjunto y evalúa el acento del estudiante."
            ),
            audio_bytes=audio_bytes,
            audio_mime=mime,
        )
        data = parse_json_response(raw)
        score = data.get("accent_score")
        try:
            score = None if score is None else max(0, min(100, int(score)))
        except (TypeError, ValueError):
            score = None
        return {
            "text": str(data.get("text") or "").strip(),
            "accent_score": score,
            "accent_tip_es": data.get("accent_tip_es"),
        }

    lang_hint = "English" if language == "en" else "Spanish or English"
    raw = await provider.chat_with_audio(
        system=(
            "You are a precise speech-to-text engine. Transcribe exactly what "
            "the speaker says, with normal punctuation. Reply with ONLY the "
            "transcription text: no quotes, no labels, no commentary. If there "
            "is no intelligible speech, reply with an empty string."
        ),
        user_text=(
            "Transcribe the attached audio. The speaker is a Spanish-speaking "
            f"English learner; the expected language is {lang_hint}."
        ),
        audio_bytes=audio_bytes,
        audio_mime=mime,
        json_mode=False,
    )
    return {"text": raw.strip().strip('"').strip(), "accent_score": None,
            "accent_tip_es": None}
