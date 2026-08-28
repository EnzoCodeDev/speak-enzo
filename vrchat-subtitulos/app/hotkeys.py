"""Teclas rápidas GLOBALES (funcionan aunque VRChat tenga el foco).

Por defecto:
  9 -> traducir las últimas 5 frases
  0 -> respuesta sugerida a lo último que se dijo

Se cambian en ~/.config/vrchat-subtitulos/config.json
(hotkey_translate / hotkey_suggest). Solo se observa el teclado: la tecla
sigue llegando normalmente al juego.
"""

import time
import threading

DEBOUNCE = 0.6  # s: ignora la auto-repetición al mantener la tecla


class GlobalHotkeys:
    def __init__(self, translate_key, suggest_key,
                 on_translate, on_suggest):
        self.translate_key = str(translate_key)
        self.suggest_key = str(suggest_key)
        self.on_translate = on_translate
        self.on_suggest = on_suggest
        self._last = {}
        self._listener = None

    def _fire(self, name, callback):
        now = time.time()
        if now - self._last.get(name, 0) < DEBOUNCE:
            return
        self._last[name] = now
        try:
            callback()
        except Exception:
            pass

    def _on_press(self, key):
        try:
            ch = key.char
        except AttributeError:
            return
        if ch == self.translate_key:
            self._fire("translate", self.on_translate)
        elif ch == self.suggest_key:
            self._fire("suggest", self.on_suggest)

    def start(self):
        def run():
            try:
                from pynput import keyboard
                self._listener = keyboard.Listener(on_press=self._on_press)
                self._listener.start()
                self._listener.join()
            except Exception:
                pass  # sin X11/permiso: la app sigue sin teclas rápidas
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
