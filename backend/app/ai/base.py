"""Interfaz común para los proveedores de IA (DeepSeek, Gemini)."""

from abc import ABC, abstractmethod


class AIProvider(ABC):
    name: str = "base"
    supports_audio: bool = False

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """messages en formato OpenAI: [{"role": "system|user|assistant", "content": "..."}].

        Devuelve el texto de la respuesta. Con json_mode=True el proveedor
        garantiza (o se le pide con fuerza) que la salida sea JSON válido.
        """

    async def chat_with_audio(
        self,
        system: str,
        user_text: str,
        audio_bytes: bytes,
        audio_mime: str,
        json_mode: bool = True,
    ) -> str:
        """Envía texto + audio al modelo (solo proveedores multimodales)."""
        raise NotImplementedError(
            f"El proveedor {self.name} no soporta audio."
        )
