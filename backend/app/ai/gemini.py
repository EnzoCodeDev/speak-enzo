"""Proveedor Google Gemini — API REST generateContent.

Gemini es multimodal: además de texto acepta audio, lo que permite evaluar
la pronunciación real del usuario (no solo la transcripción).
"""

import base64

import httpx

from .base import AIProvider
from .errors import AIError, NoTokenError

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(AIProvider):
    name = "gemini"
    supports_audio = True

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        if not api_key:
            raise NoTokenError("Gemini")
        self.api_key = api_key
        self.model = model

    def _convert_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Convierte mensajes estilo OpenAI al formato de Gemini."""
        system_parts = []
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                system_parts.append(text)
            else:
                contents.append(
                    {
                        "role": "model" if role == "assistant" else "user",
                        "parts": [{"text": text}],
                    }
                )
        return "\n\n".join(system_parts), contents

    async def _generate(self, payload: dict) -> str:
        url = f"{API_BASE}/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=90) as client:
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"x-goog-api-key": self.api_key},
                )
            except httpx.HTTPError as exc:
                raise AIError(f"No pude conectar con Gemini: {exc}") from exc

        if resp.status_code in (401, 403):
            raise AIError(
                "Gemini rechazó tu token. Revisa tu API key en Ajustes "
                "(la consigues gratis en aistudio.google.com).",
                status_code=401,
            )
        if resp.status_code == 429:
            raise AIError(
                "Gemini está limitando las peticiones (429). Espera unos segundos.",
                status_code=429,
            )
        if resp.status_code >= 400:
            raise AIError(f"Error de Gemini ({resp.status_code}): {resp.text[:300]}")

        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError):
            reason = (data.get("candidates") or [{}])[0].get("finishReason", "?")
            raise AIError(
                f"Gemini no devolvió texto (finishReason={reason}). Intenta de nuevo."
            )

    async def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        system, contents = self._convert_messages(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        return await self._generate(payload)

    async def chat_with_audio(
        self,
        system: str,
        user_text: str,
        audio_bytes: bytes,
        audio_mime: str,
        json_mode: bool = True,
    ) -> str:
        payload: dict = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": user_text},
                        {
                            "inlineData": {
                                "mimeType": audio_mime,
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        return await self._generate(payload)
