from fastapi import APIRouter
from pydantic import BaseModel

from ..config import load_settings, mask_key, save_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    active_provider: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_model: str | None = None


def _public_view(settings: dict) -> dict:
    return {
        "active_provider": settings["active_provider"],
        "gemini_model": settings["gemini_model"],
        "deepseek_model": settings["deepseek_model"],
        "gemini_api_key_masked": mask_key(settings["gemini_api_key"]),
        "deepseek_api_key_masked": mask_key(settings["deepseek_api_key"]),
        "gemini_configured": bool(settings["gemini_api_key"]),
        "deepseek_configured": bool(settings["deepseek_api_key"]),
        "audio_evaluation_available": bool(settings["gemini_api_key"]),
    }


@router.get("")
async def get_settings():
    return _public_view(load_settings())


@router.post("")
async def update_settings(update: SettingsUpdate):
    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    # Cadena vacía = borrar el token; se permite explícitamente.
    saved = save_settings(updates)
    return _public_view(saved)
