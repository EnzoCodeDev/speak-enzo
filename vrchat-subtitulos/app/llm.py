"""Cliente de la IA local (Ollama) para traducir y sugerir respuestas.

Usa la API nativa de Ollama (/api/chat) con think:false para respuestas
rápidas sin razonamiento. Sin dependencias externas (urllib).
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TRANSLATE_SYSTEM = (
    "Translate the English text to Spanish. "
    "Reply ONLY with the translation, nothing else."
)

SUGGEST_SYSTEM = (
    "You are helping a Spanish speaker chat by voice in VRChat. "
    "Given the recent conversation (other players talking in English), "
    "suggest ONE short, natural, casual English reply they could say next. "
    "Keep it simple and friendly. Reply ONLY with the suggested sentence, "
    "no quotes, no explanations."
)

PRONOUNCE_SYSTEM = (
    "Ayudas a un hispanohablante a pronunciar inglés. Reescribe la frase "
    "en inglés como se leería FONÉTICAMENTE en español, sílaba a sílaba, "
    "para que al leerla en voz alta suene a inglés natural. Responde SOLO "
    "la fonética. Ejemplos: How are you today? -> jau ar yu tudéi | "
    "Nice to meet you -> náis tu mit yu | I love this world -> "
    "ái lav dis uérld | Where are you from? -> uér ar yu from"
)


class LocalLLM:
    def __init__(self, base_url="http://localhost:11434", model="",
                 pron_model=""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        # modelo (más capaz) solo para fonética; el chico la hace mal
        self.pron_model = pron_model
        # 1 worker: las peticiones a la IA van en serie; dos inferencias de
        # qwen en paralelo sobre CPU saturaban todos los núcleos
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()

    # ---------- HTTP ----------
    def _post(self, path, payload, timeout=30):
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def _get(self, path, timeout=5):
        with urllib.request.urlopen(self.base_url + path, timeout=timeout) as r:
            return json.loads(r.read())

    # ---------- estado / modelos ----------
    def list_models(self):
        try:
            return [m["name"] for m in self._get("/api/tags")["models"]]
        except Exception:
            return []

    def ensure_server(self):
        """Si Ollama está caído, lo arranca (self-healing)."""
        if self.list_models():
            return True
        with self._lock:
            if time.time() - getattr(self, "_last_spawn", 0) < 30:
                return False  # ya lo intentamos hace poco
            self._last_spawn = time.time()
        for cand in ("ollama",
                     os.path.expanduser("~/.local/bin/ollama"),
                     "/usr/local/bin/ollama", "/usr/bin/ollama"):
            try:
                subprocess.Popen(
                    [cand, "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,  # sobrevive al cierre de la app
                )
                break
            except FileNotFoundError:
                continue
        else:
            return False
        for _ in range(20):
            time.sleep(0.5)
            if self.list_models():
                return True
        return False

    def ensure_model(self):
        """Confirma que hay modelo utilizable; autodetecta si hace falta."""
        models = self.list_models()
        if not models:
            self.ensure_server()
            models = self.list_models()
        if not models:
            return None
        with self._lock:
            if self.model not in models:
                # preferir el más pequeño (menor latencia, deja VRAM a Whisper)
                small_first = sorted(
                    models, key=lambda n: ("2b" not in n, "4b" not in n, n)
                )
                self.model = small_first[0]
        return self.model

    # ---------- chat ----------
    def _chat(self, system, user, temperature, num_predict, timeout=45,
              model=None):
        if not self.ensure_model():
            raise RuntimeError("Ollama sin modelos o no disponible")
        payload = {
            "model": model or self.model,
            "stream": False,
            "think": False,
            # mantener el modelo cargado toda la sesión: sin esto Ollama lo
            # descarga a los 5 min y la siguiente traducción tarda ~5 s
            "keep_alive": "3h",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": temperature,
                        "num_predict": num_predict},
        }
        try:
            out = self._post("/api/chat", payload, timeout=timeout)
        except urllib.error.HTTPError:
            payload.pop("think", None)  # modelo sin soporte de 'think'
            out = self._post("/api/chat", payload, timeout=timeout)
        text = out["message"]["content"].strip()
        # por si el modelo devolviera razonamiento entre <think>…</think>
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        return text

    def translate(self, text):
        return self._chat(TRANSLATE_SYSTEM, text,
                          temperature=0.2, num_predict=300)

    def pronounce(self, text):
        """Fonética «en español» de una frase en inglés (para leerla)."""
        model = None
        if self.pron_model and self.pron_model in self.list_models():
            model = self.pron_model
        return self._chat(PRONOUNCE_SYSTEM, text,
                          temperature=0.2, num_predict=120, model=model)

    def prewarm(self):
        """Carga el modelo en memoria al arrancar (en segundo plano)."""
        self.submit(self._chat, TRANSLATE_SYSTEM, "ok", 0.0, 2)

    def suggest_reply(self, conversation_lines):
        convo = "\n".join(conversation_lines)
        return self._chat(
            SUGGEST_SYSTEM,
            f"Conversation:\n{convo}\n\nSuggest my reply:",
            temperature=0.7, num_predict=80,
        )

    # ---------- asíncrono ----------
    def submit(self, fn, *args, on_done=None, on_error=None):
        """Ejecuta fn(*args) en un worker; llama on_done(result)/on_error(e)."""
        def run():
            try:
                result = fn(*args)
                if on_done:
                    on_done(result)
            except Exception as e:
                if on_error:
                    on_error(e)
        self._pool.submit(run)
