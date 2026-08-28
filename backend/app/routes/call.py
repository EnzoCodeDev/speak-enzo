"""Modo llamada: conversación de voz con Enzo, el tutor de IA."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import prompts
from ..ai.router import get_provider, parse_json_response

router = APIRouter(prefix="/api/call", tags=["call"])


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class CallRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    level: str = "beginner"
    provider: str | None = None


@router.post("/chat")
async def call_chat(req: CallRequest):
    provider = get_provider(req.provider)
    messages = [{"role": "system", "content": prompts.call_system(req.level)}]
    # Solo los últimos 20 turnos para no crecer sin límite.
    for m in req.messages[-20:]:
        messages.append({"role": m.role, "content": m.content})

    raw = await provider.chat(messages, json_mode=True, temperature=0.8)
    data = parse_json_response(raw)
    return {
        "reply": data.get("reply", ""),
        "correction": data.get("correction"),
        "better_phrase": data.get("better_phrase"),
        "translation_hint": data.get("translation_hint"),
        "provider": provider.name,
    }
