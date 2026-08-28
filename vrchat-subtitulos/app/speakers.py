"""Identificación de hablantes por huella de voz (embeddings).

Cada segmento de voz produce un embedding; se compara por similitud coseno
con los hablantes conocidos. Si no se parece a ninguno, se crea un hablante
nuevo ("Speaker N"). Los nombres que el usuario asigna se guardan en disco
junto con el centroide de la voz, así la misma persona conserva su nombre
en la próxima sesión.
"""

import json
import threading
from pathlib import Path

import numpy as np

CONFIG_DIR = Path.home() / ".config" / "vrchat-subtitulos"
SPEAKERS_FILE = CONFIG_DIR / "speakers.json"

# Colores distinguibles para los nombres (se reciclan si hay más hablantes)
PALETTE = [
    "#4FC3F7", "#AED581", "#FFB74D", "#F06292", "#BA68C8",
    "#4DB6AC", "#FFF176", "#FF8A65", "#90CAF9", "#CE93D8",
]

SIM_THRESHOLD = 0.40   # similitud coseno mínima para considerar "misma voz"
MAX_SPEAKERS = 24


class Speaker:
    def __init__(self, sid, name, color, centroid, count=1):
        self.sid = sid
        self.name = name
        self.color = color
        self.centroid = centroid  # np.ndarray normalizado
        self.count = count


class SpeakerRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self.speakers = {}
        self._next_id = 1
        self._load()

    # ---------- persistencia ----------
    def _load(self):
        try:
            data = json.loads(SPEAKERS_FILE.read_text())
            for item in data.get("speakers", []):
                c = np.array(item["centroid"], dtype=np.float32)
                n = np.linalg.norm(c)
                if n > 0:
                    c /= n
                sp = Speaker(item["sid"], item["name"], item["color"], c,
                             item.get("count", 5))
                self.speakers[sp.sid] = sp
            self._next_id = data.get("next_id", len(self.speakers) + 1)
        except Exception:
            pass

    def save(self):
        with self._lock:
            data = {
                "next_id": self._next_id,
                "speakers": [
                    {
                        "sid": sp.sid,
                        "name": sp.name,
                        "color": sp.color,
                        "count": sp.count,
                        "centroid": sp.centroid.tolist(),
                    }
                    for sp in self.speakers.values()
                ],
            }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SPEAKERS_FILE.write_text(json.dumps(data))

    # ---------- identificación ----------
    def identify(self, embedding):
        """Devuelve el Speaker de este embedding, creándolo si es nuevo."""
        emb = np.asarray(embedding, dtype=np.float32)
        norm = np.linalg.norm(emb)
        if norm == 0:
            return None
        emb /= norm

        with self._lock:
            best, best_sim = None, -1.0
            for sp in self.speakers.values():
                sim = float(np.dot(emb, sp.centroid))
                if sim > best_sim:
                    best, best_sim = sp, sim

            if best is not None and best_sim >= SIM_THRESHOLD:
                # actualizar centroide (media móvil, tope para no diluir)
                w = min(best.count, 50)
                c = best.centroid * w + emb
                best.centroid = c / np.linalg.norm(c)
                best.count += 1
                return best

            if len(self.speakers) >= MAX_SPEAKERS:
                return best  # no crear más: devolver el más parecido

            sid = self._next_id
            self._next_id += 1
            sp = Speaker(
                sid,
                f"Speaker {sid}",
                PALETTE[(sid - 1) % len(PALETTE)],
                emb,
            )
            self.speakers[sid] = sp
            return sp

    def rename(self, sid, new_name):
        with self._lock:
            if sid in self.speakers and new_name.strip():
                self.speakers[sid].name = new_name.strip()
        self.save()

    def forget_all(self):
        with self._lock:
            self.speakers.clear()
            self._next_id = 1
        self.save()
