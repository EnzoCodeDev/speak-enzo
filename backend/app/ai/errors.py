class AIError(Exception):
    """Error al hablar con el proveedor de IA, con mensaje amigable en español."""

    def __init__(self, message_es: str, status_code: int = 502):
        super().__init__(message_es)
        self.message_es = message_es
        self.status_code = status_code


class NoTokenError(AIError):
    def __init__(self, provider: str):
        super().__init__(
            f"No hay token configurado para {provider}. "
            f"Ve a Ajustes en la app y pega tu API key.",
            status_code=428,
        )
