"""Captura de audio del juego via PulseAudio/PipeWire (parec).

Captura SOLO la salida de audio (lo que suena en tus altavoces/auriculares),
nunca tu micrófono. Si VRChat está corriendo, captura únicamente el stream
de VRChat (--monitor-stream); si no, usa el monitor del sink por defecto.
"""

import os
import subprocess
import threading
import queue
import re
import time

import numpy as np

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1600  # 100 ms

# Nombres con los que VRChat aparece en pactl (nativo o via Proton/Wine)
VRCHAT_PATTERNS = re.compile(r"vrchat", re.IGNORECASE)

# pactl siempre en inglés: con locale español los encabezados cambian y
# la detección de VRChat fallaba
_ENV_C = dict(os.environ, LC_ALL="C")


def find_vrchat_sink_input():
    """Devuelve el índice del sink-input de VRChat, o None si no está sonando."""
    try:
        out = subprocess.run(
            ["pactl", "list", "sink-inputs"],
            capture_output=True, text=True, timeout=5, env=_ENV_C,
        ).stdout
    except Exception:
        return None

    index = None
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"Sink Input #(\d+)", line)
        if m:
            index = int(m.group(1))
            continue
        if index is not None and VRCHAT_PATTERNS.search(line):
            return index
    return None


def get_default_monitor():
    try:
        sink = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, text=True, timeout=5, env=_ENV_C,
        ).stdout.strip()
        if sink:
            return sink + ".monitor"
    except Exception:
        pass
    return None


class AudioCapture:
    """Lee PCM 16 kHz mono desde parec en un hilo y lo expone en una cola."""

    def __init__(self, prefer_vrchat=True):
        self.prefer_vrchat = prefer_vrchat
        # 10 s máximo de cola: si el pipeline se atrasa, se descarta audio
        # viejo en vez de acumular retraso en los subtítulos
        self.chunks = queue.Queue(maxsize=100)
        self.source_desc = "?"
        self._proc = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _spawn_parec(self):
        base = [
            "parec", "--format=s16le", f"--rate={SAMPLE_RATE}",
            "--channels=1", "--latency-msec=60",
        ]
        vr_idx = find_vrchat_sink_input() if self.prefer_vrchat else None
        if vr_idx is not None:
            cmd = base + [f"--monitor-stream={vr_idx}"]
            self.source_desc = f"VRChat (stream #{vr_idx})"
        else:
            monitor = get_default_monitor()
            if monitor is None:
                return None
            cmd = base + ["-d", monitor]
            self.source_desc = "salida general del sistema"
        try:
            return subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=CHUNK_SAMPLES * 2,
            )
        except FileNotFoundError:
            return None

    def _run(self):
        bytes_per_chunk = CHUNK_SAMPLES * 2  # s16le
        last_vrchat_check = 0.0
        while not self._stop.is_set():
            self._proc = self._spawn_parec()
            if self._proc is None:
                time.sleep(2)
                continue
            capturing_vrchat = "VRChat" in self.source_desc
            while not self._stop.is_set():
                data = self._proc.stdout.read(bytes_per_chunk)
                if not data:
                    break  # parec murió (p. ej. VRChat cerró su stream)
                samples = (
                    np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                )
                try:
                    self.chunks.put_nowait(samples)
                except queue.Full:
                    pass  # el pipeline va atrasado: descartamos audio viejo
                # Si estamos en el monitor general, reintentar engancharse a
                # VRChat cuando aparezca (cada 5 s)
                now = time.time()
                if (not capturing_vrchat and self.prefer_vrchat
                        and now - last_vrchat_check > 5):
                    last_vrchat_check = now
                    if find_vrchat_sink_input() is not None:
                        break  # reiniciar parec apuntando a VRChat
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                pass
            if not self._stop.is_set():
                time.sleep(1)
