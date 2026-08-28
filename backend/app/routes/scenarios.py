"""Modo escenarios: juegos de rol (pedir comida, aeropuerto, entrevista...)."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import prompts
from ..ai.router import get_provider, parse_json_response

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

SCENARIOS_FILE = Path(__file__).resolve().parent.parent / "data" / "scenarios.json"


@lru_cache(maxsize=1)
def _scenarios() -> list[dict]:
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))["scenarios"]


def _find(scenario_id: str) -> dict:
    for s in _scenarios():
        if s["id"] == scenario_id:
            return s
    raise HTTPException(404, f"Escenario '{scenario_id}' no existe.")


class Message(BaseModel):
    role: str
    content: str


class ScenarioChatRequest(BaseModel):
    scenario_id: str
    messages: list[Message] = Field(min_length=1)
    level: str = "beginner"
    provider: str | None = None


class ScenarioReportRequest(BaseModel):
    scenario_id: str
    messages: list[Message] = Field(min_length=1)
    provider: str | None = None


@router.get("")
async def list_scenarios():
    return {"scenarios": _scenarios()}


@router.post("/chat")
async def scenario_chat(req: ScenarioChatRequest):
    scenario = _find(req.scenario_id)
    provider = get_provider(req.provider)
    messages = [
        {"role": "system", "content": prompts.scenario_system(scenario, req.level)}
    ]
    for m in req.messages[-24:]:
        messages.append({"role": m.role, "content": m.content})

    raw = await provider.chat(messages, json_mode=True, temperature=0.8)
    data = parse_json_response(raw)
    return {
        "reply": data.get("reply", ""),
        "correction": data.get("correction"),
        "better_phrase": data.get("better_phrase"),
        "translation_hint": data.get("translation_hint"),
        "goal_completed": bool(data.get("goal_completed", False)),
        "provider": provider.name,
    }


@router.post("/report")
async def scenario_report(req: ScenarioReportRequest):
    scenario = _find(req.scenario_id)
    provider = get_provider(req.provider)
    conversation = "\n".join(
        f"{'ESTUDIANTE' if m.role == 'user' else 'IA'}: {m.content}"
        for m in req.messages
    )
    raw = await provider.chat(
        [
            {"role": "system", "content": prompts.scenario_report_system(scenario)},
            {"role": "user", "content": f"CONVERSACIÓN COMPLETA:\n{conversation}"},
        ],
        json_mode=True,
        temperature=0.4,
        max_tokens=2048,
    )
    data = parse_json_response(raw)
    score = data.get("score", 0)
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = 0
    return {
        "score": score,
        "goal_achieved": bool(data.get("goal_achieved", False)),
        "strengths_es": data.get("strengths_es") or [],
        "improvements_es": data.get("improvements_es") or [],
        "vocabulary_tips": data.get("vocabulary_tips") or [],
        "provider": provider.name,
    }
