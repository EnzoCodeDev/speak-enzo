"""Modo aprendizaje puntual: gramática por temas (presente, pasado, preguntas...)."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import prompts
from ..ai.router import get_provider, parse_json_response

router = APIRouter(prefix="/api/grammar", tags=["grammar"])

TOPICS_FILE = Path(__file__).resolve().parent.parent / "data" / "grammar_topics.json"


@lru_cache(maxsize=1)
def _topics() -> list[dict]:
    return json.loads(TOPICS_FILE.read_text(encoding="utf-8"))["topics"]


def _find_topic(topic_id: str) -> dict:
    for t in _topics():
        if t["id"] == topic_id:
            return t
    raise HTTPException(404, f"Tema '{topic_id}' no existe.")


class ExerciseRequest(BaseModel):
    topic_id: str
    level: str = "beginner"
    provider: str | None = None


class CheckRequest(BaseModel):
    question: str
    expected_answer: str
    user_answer: str
    exercise_type: str = "translate"
    provider: str | None = None


@router.get("/topics")
async def list_topics():
    return {"topics": _topics()}


@router.post("/exercise")
async def generate_exercise(req: ExerciseRequest):
    topic = _find_topic(req.topic_id)
    provider = get_provider(req.provider)
    raw = await provider.chat(
        [
            {
                "role": "system",
                "content": prompts.grammar_exercise_system(
                    topic["name_en"], topic["description_en"], req.level
                ),
            },
            {"role": "user", "content": "Genera la lección y los 5 ejercicios."},
        ],
        json_mode=True,
        temperature=0.9,
        max_tokens=2048,
    )
    data = parse_json_response(raw)
    exercises = data.get("exercises") or []
    return {
        "topic": topic,
        "mini_lesson_es": data.get("mini_lesson_es", ""),
        "exercises": exercises[:5],
        "provider": provider.name,
    }


@router.post("/check")
async def check_answer(req: CheckRequest):
    # Respuestas exactas (opción múltiple / hueco) se validan sin IA.
    normalized_user = req.user_answer.strip().lower().rstrip(".!?")
    normalized_expected = req.expected_answer.strip().lower().rstrip(".!?")
    if normalized_user == normalized_expected:
        return {"correct": True, "feedback_es": "¡Exacto! 🎉"}

    if req.exercise_type == "multiple_choice":
        return {
            "correct": False,
            "feedback_es": f'La respuesta correcta era "{req.expected_answer}".',
        }

    # Respuestas abiertas: la IA juzga si es una variación válida.
    provider = get_provider(req.provider)
    raw = await provider.chat(
        [
            {"role": "system", "content": prompts.GRAMMAR_CHECK_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"EJERCICIO: {req.question}\n"
                    f"RESPUESTA ESPERADA: {req.expected_answer}\n"
                    f"RESPUESTA DEL ESTUDIANTE: {req.user_answer}"
                ),
            },
        ],
        json_mode=True,
        temperature=0.2,
    )
    data = parse_json_response(raw)
    return {
        "correct": bool(data.get("correct", False)),
        "feedback_es": data.get("feedback_es", ""),
    }
