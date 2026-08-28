"""Pipeline: audio -> VAD -> huella de voz -> Whisper (solo inglés) -> subtítulo."""

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx

from .audio import AudioCapture, SAMPLE_RATE
from .speakers import SpeakerRegistry

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
VAD_MODEL = MODELS_DIR / "silero_vad.onnx"
SPK_MODEL = MODELS_DIR / "nemo_en_titanet_small.onnx"

# Frases basura que Whisper alucina en silencio/ruido
HALLUCINATIONS = {
    "thank you.", "thanks for watching.", "thank you for watching.",
    "you", "you.", "bye.", "bye bye.", ".", "the end.", "so,", "oh.",
    "thanks for watching!", "thank you for watching!", "subtitles by",
}


@dataclass
class Subtitle:
    speaker_id: int
    speaker_name: str
    color: str
    text: str
    timestamp: float
    translation: str = ""


class SubtitlePipeline:
    """Hilo que consume audio y emite subtítulos via callback (thread-safe)."""

    def __init__(self, on_subtitle, on_status, model_size=None,
                 min_volume=0.012):
        self.on_subtitle = on_subtitle      # callback(Subtitle)
        self.on_status = on_status          # callback(str)
        self.model_size = model_size
        # solo voces cercanas/fuertes: el murmullo lejano se ignora
        # (y no gasta CPU)
        self.min_volume = float(min_volume)
        self.registry = SpeakerRegistry()
        self.capture = AudioCapture()
        self._stop = threading.Event()
        self._thread = None
        self.whisper = None
        self.min_english_prob = 0.55
        # cola corta de frases pendientes: bajo congestión (mucha gente
        # hablando) se descartan las más viejas y se transcriben las nuevas
        self._seg_queue = queue.Queue(maxsize=3)
        self._last_drop_note = 0.0

    # ---------- carga de modelos ----------
    def _load_models(self):
        self.on_status("Cargando modelos…")

        vad_cfg = sherpa_onnx.VadModelConfig()
        vad_cfg.silero_vad.model = str(VAD_MODEL)
        vad_cfg.silero_vad.threshold = 0.5
        # frases cortas => subtítulos salen mucho antes (menos latencia)
        vad_cfg.silero_vad.min_silence_duration = 0.35
        vad_cfg.silero_vad.min_speech_duration = 0.25
        vad_cfg.silero_vad.max_speech_duration = 5.5
        vad_cfg.sample_rate = SAMPLE_RATE
        self.vad = sherpa_onnx.VoiceActivityDetector(
            vad_cfg, buffer_size_in_seconds=90
        )
        self.vad_window = vad_cfg.silero_vad.window_size

        spk_cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(SPK_MODEL), num_threads=2
        )
        self.spk_extractor = sherpa_onnx.SpeakerEmbeddingExtractor(spk_cfg)

        self._load_whisper()

    @staticmethod
    def _free_vram_mb():
        import subprocess
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip().splitlines()[0]
            return int(out)
        except Exception:
            return 0

    def _load_whisper(self, force_cpu=False):
        from faster_whisper import WhisperModel

        self._whisper_fails = 0
        # con VRChat abierto la GPU suele estar llena: si hay poca VRAM
        # libre, Whisper falla en cada frase => mejor CPU directamente
        if not force_cpu and self._free_vram_mb() < 2000:
            force_cpu = True
            self.on_status("GPU ocupada por el juego: Whisper irá en CPU")
        if not force_cpu:
            try:
                size = self.model_size or "small"
                # int8_float16: mitad de VRAM que float16 => convive mejor
                # con VRChat y Ollama en la misma GPU
                self.whisper = WhisperModel(
                    size, device="cuda", compute_type="int8_float16",
                )
                # forzar inicialización real de CUDA con una pasada corta
                list(self.whisper.transcribe(
                    np.zeros(SAMPLE_RATE, dtype=np.float32), language="en"
                )[0])
                self._device = "cuda"
                self.on_status(f"Whisper {size} en GPU ✓")
                return
            except Exception:
                pass
        # en CPU el modelo "base" es 3x más rápido que "small" y detecta
        # idioma igual de bien: subtítulos en ~1 s
        size = self.model_size or "base"
        # 6 hilos bastan para "base" y dejan CPU libre para el juego y
        # para Ollama (que también corre en CPU cuando la GPU está llena)
        cores = __import__("os").cpu_count() or 8
        self.whisper = WhisperModel(
            size, device="cpu", compute_type="int8",
            cpu_threads=min(6, max(4, cores // 2)),
        )
        self._device = "cpu"
        self.on_status(f"Whisper {size} en CPU ✓")

    # ---------- ciclo principal ----------
    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.capture.stop()
        self.registry.save()

    def _run(self):
        try:
            self._load_models()
        except Exception as e:
            self.on_status(f"Error cargando modelos: {e}")
            return

        # transcribir en un hilo aparte: la captura y el VAD nunca se
        # bloquean aunque Whisper vaya atrasado
        threading.Thread(target=self._transcribe_worker, daemon=True).start()

        self.capture.start()
        self.on_status(f"Escuchando: {self.capture.source_desc}")
        pending = np.zeros(0, dtype=np.float32)
        last_src = self.capture.source_desc

        while not self._stop.is_set():
            try:
                chunk = self.capture.chunks.get(timeout=0.5)
            except Exception:
                continue

            if self.capture.source_desc != last_src:
                last_src = self.capture.source_desc
                self.on_status(f"Escuchando: {last_src}")

            pending = np.concatenate([pending, chunk])
            # alimentar el VAD en ventanas exactas; SIEMPRE con copia propia:
            # sherpa-onnx referencia el buffer y numpy lo liberaría al reasignar
            while len(pending) >= self.vad_window:
                self.vad.accept_waveform(
                    np.array(pending[: self.vad_window], copy=True))
                pending = pending[self.vad_window:]

            while not self.vad.empty():
                # copiar las muestras ANTES de pop(): pop invalida el buffer
                samples = np.array(self.vad.front.samples,
                                   dtype=np.float32, copy=True)
                self.vad.pop()
                self._enqueue_segment(samples)

    def _enqueue_segment(self, samples):
        # filtro de volumen: gente lejana / hablando bajito se ignora
        rms = float(np.sqrt(np.mean(samples ** 2)))
        if rms < self.min_volume:
            return
        try:
            self._seg_queue.put_nowait(samples)
            return
        except queue.Full:
            pass
        # congestión: tirar la frase más vieja y quedarnos con la nueva
        try:
            self._seg_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self._seg_queue.put_nowait(samples)
        except queue.Full:
            pass
        now = time.time()
        if now - self._last_drop_note > 10:
            self._last_drop_note = now
            self.on_status("Mucha gente hablando: salto frases viejas "
                           "para no atrasarme")

    def _transcribe_worker(self):
        while not self._stop.is_set():
            try:
                samples = self._seg_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._process_segment(samples)
            except Exception:
                pass  # nunca dejar morir el hilo de transcripción

    # ---------- por segmento de voz ----------
    def _process_segment(self, samples):
        dur = len(samples) / SAMPLE_RATE
        if dur < 0.3:
            return

        # 1) ¿quién habla?
        speaker = None
        try:
            st = self.spk_extractor.create_stream()
            st.accept_waveform(SAMPLE_RATE, samples)
            st.input_finished()
            if self.spk_extractor.is_ready(st):
                emb = self.spk_extractor.compute(st)
                speaker = self.registry.identify(emb)
        except Exception:
            pass

        # 2) ¿qué dice? (solo inglés)
        try:
            segments, info = self.whisper.transcribe(
                samples,
                language=None,          # detectar idioma
                beam_size=1,            # greedy: máxima velocidad
                temperature=0.0,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                without_timestamps=True,
            )
            lang_ok = (info.language == "en"
                       and info.language_probability >= self.min_english_prob)
            strict = False
            if not lang_ok:
                if (info.language != "en"
                        and info.language_probability >= 0.75):
                    return  # claramente otro idioma: se ignora
                # detección dudosa (p.ej. base confunde inglés con galés):
                # reintentar forzando inglés y exigir calidad alta
                segments, info = self.whisper.transcribe(
                    samples,
                    language="en",
                    beam_size=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.6,
                    without_timestamps=True,
                )
                strict = True
            texts = []
            min_logprob = -0.8 if strict else -1.2
            for seg in segments:
                if seg.no_speech_prob > 0.85 or seg.avg_logprob < min_logprob:
                    continue
                texts.append(seg.text.strip())
            text = " ".join(t for t in texts if t).strip()
            self._whisper_fails = 0
        except Exception:
            # GPU saturada por el juego: tras 3 fallos seguidos el contexto
            # CUDA puede quedar roto => recargar Whisper en CPU y seguir
            self._whisper_fails += 1
            if self._whisper_fails >= 2 and self._device == "cuda":
                self.on_status("GPU saturada: cambiando Whisper a CPU…")
                try:
                    self._load_whisper(force_cpu=True)
                    # reintentar esta misma frase en CPU (una sola vez,
                    # porque _device ya es "cpu")
                    return self._process_segment(samples)
                except Exception:
                    pass
            return

        if not text or text.lower() in HALLUCINATIONS:
            return

        if speaker is None:
            name, color, sid = "???", "#BBBBBB", 0
        else:
            name, color, sid = speaker.name, speaker.color, speaker.sid

        self.on_subtitle(Subtitle(sid, name, color, text, time.time()))
