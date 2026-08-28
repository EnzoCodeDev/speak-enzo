"""Guarda TODAS las conversaciones (subtítulos) en JSON, una por semana.

Los archivos van a la app Enzo Speak (web/vrchat/) para analizar allá las
palabras más usadas en VRChat y practicar con ellas:

    <transcript_dir>/index.json      -> lista de semanas disponibles
    <transcript_dir>/2026-W35.json   -> {"week": ..., "phrases": [
                                          {"ts", "speaker", "text"}, ...]}
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path

FLUSH_DELAY = 2.0  # s: agrupa escrituras


def week_key(t=None):
    """Clave ISO de la semana, p.ej. '2026-W35'."""
    return time.strftime("%G-W%V", time.localtime(t))


class TranscriptLogger:
    def __init__(self, out_dir):
        self.dir = Path(out_dir).expanduser()
        self._lock = threading.Lock()
        self._timer = None
        self._week = None
        self._phrases = []      # frases de la semana actual
        self.enabled = True
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.enabled = False

    # ------------------------------------------------------------ público
    def add(self, sub):
        """Registra un subtítulo (llamar con cada frase transcrita)."""
        if not self.enabled:
            return
        with self._lock:
            wk = week_key(sub.timestamp)
            if wk != self._week:
                self._load_week(wk)
            self._phrases.append({
                "ts": datetime.fromtimestamp(sub.timestamp)
                              .isoformat(timespec="seconds"),
                "speaker": sub.speaker_name,
                "text": sub.text,
            })
            if self._timer is None:
                self._timer = threading.Timer(FLUSH_DELAY, self._flush)
                self._timer.daemon = True
                self._timer.start()

    def stop(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        self._flush()

    # ------------------------------------------------------------ interno
    def _week_file(self, wk):
        return self.dir / f"{wk}.json"

    def _load_week(self, wk):
        """Cambia a la semana wk, cargando lo ya guardado (si existe)."""
        self._week = wk
        self._phrases = []
        try:
            data = json.loads(self._week_file(wk).read_text(encoding="utf-8"))
            self._phrases = list(data.get("phrases", []))
        except (OSError, json.JSONDecodeError):
            pass

    def _flush(self):
        with self._lock:
            self._timer = None
            if not self._week:
                return
            wk, phrases = self._week, list(self._phrases)
        try:
            tmp = self._week_file(wk).with_suffix(".tmp")
            tmp.write_text(json.dumps(
                {"week": wk, "app": "vrchat-subtitulos", "phrases": phrases},
                ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._week_file(wk))
            self._write_index()
        except OSError:
            pass

    def _write_index(self):
        weeks = []
        for f in sorted(self.dir.glob("*-W*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                weeks.append({
                    "week": data.get("week", f.stem),
                    "file": f.name,
                    "phrases": len(data.get("phrases", [])),
                })
            except (OSError, json.JSONDecodeError):
                continue
        (self.dir / "index.json").write_text(
            json.dumps({"weeks": weeks}, ensure_ascii=False),
            encoding="utf-8")
