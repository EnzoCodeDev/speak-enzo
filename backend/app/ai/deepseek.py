"""Proveedor DeepSeek — API compatible con OpenAI chat completions."""

import httpx

from .base import AIProvider
from .errors import AIError, NoTokenError

API_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekProvider(AIProvider):
    name = "deepseek"
    supports_audio = False

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        if not api_key:
            raise NoTokenError("DeepSeek")
        self.api_key = api_key
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=90) as client:
            try:
                resp = await client.post(
                    API_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError as exc:
                raise AIError(f"No pude conectar con DeepSeek: {exc}") from exc

        if resp.status_code == 401:
            raise AIError(
                "DeepSeek rechazó tu token (401). Revisa tu API key en Ajustes.",
                status_code=401,
            )
        if resp.status_code == 402:
            raise AIError(
                "Tu cuenta de DeepSeek no tiene saldo (402). Recarga en platform.deepseek.com.",
                status_code=402,
            )
        if resp.status_code == 429:
            raise AIError(
                "DeepSeek está limitando las peticiones (429). Espera unos segundos.",
                status_code=429,
            )
        if resp.status_code >= 400:
            raise AIError(f"Error de DeepSeek ({resp.status_code}): {resp.text[:300]}")

        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise AIError("DeepSeek devolvió una respuesta inesperada.") from exc
