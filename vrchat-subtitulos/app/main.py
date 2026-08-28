"""Punto de entrada: subtítulos en tiempo real (inglés) para VRChat en Linux."""

import argparse
import signal
import sys

from PySide6.QtWidgets import QApplication

from . import config as config_mod
from .hotkeys import GlobalHotkeys
from .llm import LocalLLM
from .overlay import SubtitleOverlay, Bridge
from .pipeline import SubtitlePipeline
from .transcript import TranscriptLogger


def main():
    parser = argparse.ArgumentParser(
        description="Subtítulos en tiempo real (solo inglés) para VRChat"
    )
    parser.add_argument(
        "--model", default=None,
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Tamaño del modelo Whisper (por defecto automático: "
             "small en GPU, base en CPU)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Imprime estado y subtítulos también en la consola",
    )
    args = parser.parse_args()

    cfg = config_mod.load()
    llm = LocalLLM(cfg.get("ollama_url", "http://localhost:11434"),
                   cfg.get("ollama_model", ""),
                   pron_model=cfg.get("pron_model", "qwen3.5:4b"))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    bridge = Bridge()
    pipeline = SubtitlePipeline(
        on_subtitle=bridge.subtitle.emit,
        on_status=bridge.status.emit,
        model_size=args.model,
        min_volume=cfg.get("min_volume", 0.012),
    )
    overlay = SubtitleOverlay(pipeline, llm, cfg, bridge)
    bridge.subtitle.connect(overlay.add_subtitle)
    bridge.status.connect(overlay.set_status)

    # guardar TODA la conversación por semana (la analiza Enzo Speak)
    transcript = TranscriptLogger(
        cfg.get("transcript_dir") or config_mod.DEFAULTS["transcript_dir"])
    bridge.subtitle.connect(transcript.add)
    if args.debug:
        bridge.subtitle.connect(
            lambda s: print(f"[{s.speaker_name}] {s.text}", flush=True))
        bridge.status.connect(lambda t: print(f"[estado] {t}", flush=True))
        bridge.translated.connect(
            lambda s, es: print(f"    → {es}", flush=True))
        bridge.suggestion_ready.connect(
            lambda t: print(f"[sugerencia] {t}", flush=True))

    # teclas rápidas globales: funcionan aunque VRChat tenga el foco
    bridge.hk_translate.connect(
        lambda: overlay.translate_last(cfg.get("translate_last_n", 10)))
    bridge.hk_suggest.connect(overlay.suggest_latest)
    hotkeys = GlobalHotkeys(
        cfg.get("hotkey_translate", "9"), cfg.get("hotkey_suggest", "0"),
        on_translate=bridge.hk_translate.emit,
        on_suggest=bridge.hk_suggest.emit,
    )
    hotkeys.start()

    overlay.show()
    pipeline.start()
    llm.prewarm()  # cargar el modelo de Ollama ya, para traducir al instante

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    code = app.exec()
    hotkeys.stop()
    pipeline.stop()
    transcript.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()
