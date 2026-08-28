"""Enzo Speak — backend FastAPI.

Aprende inglés con IA: modo llamada, traductor, 1000 frases esenciales,
gramática puntual y escenarios de rol. Los tokens de DeepSeek/Gemini los
configura el usuario desde la app (POST /api/settings).

Arrancar:  uvicorn app.main:app --host 0.0.0.0 --port 8100
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .ai.errors import AIError
from .config import load_settings
from .routes import (
    call,
    grammar,
    phrases,
    pronunciation,
    scenarios,
    settings,
    transcribe,
    translate,
    tts,
)

app = FastAPI(
    title="Enzo Speak API",
    description="Backend de la app de aprendizaje de inglés con IA 💙",
    version="0.1.0-beta",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AIError)
async def ai_error_handler(_request: Request, exc: AIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message_es, "error_type": "ai_error"},
    )


app.include_router(settings.router)
app.include_router(call.router)
app.include_router(translate.router)
app.include_router(pronunciation.router)
app.include_router(phrases.router)
app.include_router(grammar.router)
app.include_router(scenarios.router)
app.include_router(transcribe.router)
app.include_router(tts.router)


@app.get("/api/health")
async def health():
    s = load_settings()
    return {
        "status": "ok",
        "app": "Enzo Speak",
        "version": "0.1.0-beta",
        "active_provider": s["active_provider"],
        "gemini_configured": bool(s["gemini_api_key"]),
        "deepseek_configured": bool(s["deepseek_api_key"]),
    }
