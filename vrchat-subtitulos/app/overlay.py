"""Overlay de subtítulos: ventana flotante siempre-encima, estilo subtítulo.

- Cada línea: «Nombre: texto» con el color del hablante.
- Traducción al español opcional (IA local) debajo de cada línea.
- Clic sobre una línea: sugiere una respuesta en inglés (IA local).
- Doble clic sobre una línea: renombrar a ese hablante.
- Arrastrar para mover; clic derecho para el menú.
"""

import time
from collections import deque

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QMenu,
    QInputDialog, QFrame, QPushButton,
)

from . import config as config_mod
from . import osc

MAX_LINES = 20
LINE_TTL = 18.0        # segundos que vive un subtítulo
TRANSLATION_TTL = 10.0  # al llegar su traducción, vive al menos esto más
HISTORY = 12           # líneas de contexto para la IA


class Bridge(QObject):
    """Cruza callbacks desde hilos (pipeline / IA) al hilo de Qt."""
    subtitle = Signal(object)
    status = Signal(str)
    translated = Signal(object, object)   # (Subtitle, texto español)
    suggestion_ready = Signal(str)
    suggestion_gloss = Signal(str)
    suggestion_pron = Signal(str)         # fonética «en español»
    suggestion_failed = Signal(str)
    hk_translate = Signal()               # tecla rápida: traducir pantalla
    hk_suggest = Signal()                 # tecla rápida: respuesta sugerida


BTN_STYLE = """
QPushButton {
    color: #DDD; background: #333842; border: none;
    border-radius: 5px; padding: 3px 10px; font-size: 12px;
}
QPushButton:hover { background: #4A5160; }
"""


class SubtitleOverlay(QWidget):
    def __init__(self, pipeline, llm, cfg, bridge):
        super().__init__()
        self.pipeline = pipeline
        self.llm = llm
        self.cfg = cfg
        self.bridge = bridge
        self.lines = []                    # [(Subtitle, QLabel)]
        self.history = deque(maxlen=HISTORY)
        self.font_size = cfg.get("font_size", 15)
        self._drag_pos = None
        self._press_child = None
        self._press_global = None
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(280)
        self._click_timer.timeout.connect(self._click_timeout)
        self._pending_click_sid = None
        # selección tipo navegador: clic apretado + barrer + SOLTAR = traducir
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(320)
        self._hold_timer.timeout.connect(self._hold_timeout)
        self._selecting = False
        self._sel_anchor = None   # línea donde empezó la selección
        self._sel_range = None    # (primera, última) líneas seleccionadas

        self.setWindowTitle("Subtítulos VRChat")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(14, 10, 14, 10)
        self.layout_.setSpacing(4)
        self.layout_.addStretch(1)  # ancla los subtítulos abajo (estilo cine)

        # panel de sugerencia (oculto hasta que se pida)
        self.sugg_frame = QFrame()
        self.sugg_frame.setStyleSheet(
            "QFrame { background: rgba(40,60,50,190); border-radius: 8px; }"
        )
        sv = QVBoxLayout(self.sugg_frame)
        sv.setContentsMargins(10, 6, 10, 6)
        sv.setSpacing(2)
        self.sugg_label = QLabel()
        self.sugg_label.setWordWrap(True)
        self.sugg_label.setStyleSheet(
            f"color: #B9F6CA; font-size: {self.font_size}px; "
            "font-weight: bold; background: transparent;"
        )
        self.sugg_gloss = QLabel()
        self.sugg_gloss.setWordWrap(True)
        self.sugg_gloss.setStyleSheet(
            "color: #9E9E9E; font-size: 12px; font-style: italic; "
            "background: transparent;"
        )
        # cómo pronunciarla, escrita «en español» (ej: jau ar yu tudéi)
        self.sugg_pron = QLabel()
        self.sugg_pron.setWordWrap(True)
        self.sugg_pron.setStyleSheet(
            "color: #FFD54F; font-size: 13px; background: transparent;"
        )
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_copy = QPushButton("Copiar")
        self.btn_chatbox = QPushButton("Al chatbox")
        self.btn_retry = QPushButton("Otra")
        self.btn_close = QPushButton("✕")
        for b in (self.btn_copy, self.btn_chatbox, self.btn_retry,
                  self.btn_close):
            b.setStyleSheet(BTN_STYLE)
            b.setCursor(Qt.PointingHandCursor)
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        sv.addWidget(self.sugg_label)
        sv.addWidget(self.sugg_gloss)
        sv.addWidget(self.sugg_pron)
        sv.addLayout(btn_row)
        self.sugg_frame.hide()

        self.status_label = QLabel("Iniciando…")
        self.status_label.setStyleSheet(
            "color: #888; font-size: 11px; background: transparent;"
        )

        self.layout_.addWidget(self.sugg_frame)
        self.layout_.addWidget(self.status_label)

        self.btn_copy.clicked.connect(self._copy_suggestion)
        self.btn_chatbox.clicked.connect(self._send_chatbox)
        self.btn_retry.clicked.connect(lambda: self.request_suggestion())
        self.btn_close.clicked.connect(self.sugg_frame.hide)

        self.bridge.translated.connect(self._apply_translation)
        self.bridge.suggestion_ready.connect(self._show_suggestion)
        self.bridge.suggestion_gloss.connect(self._show_gloss)
        self.bridge.suggestion_pron.connect(self._show_pron)
        self.bridge.suggestion_failed.connect(self._suggestion_failed)

        # tamaño FIJO: la ventana nunca cambia de tamaño sola
        w = int(cfg.get("overlay_width", 780))
        h = int(cfg.get("overlay_height", 260))
        self.setFixedSize(w, h)
        screen = QApplication.primaryScreen().availableGeometry()
        x, y = cfg.get("pos_x"), cfg.get("pos_y")
        if (x is None or y is None or not screen.adjusted(-60, -60, 60, 60)
                .contains(QPoint(int(x), int(y)))):
            x = (screen.width() - w) // 2
            y = screen.height() - h - 80
        self.move(int(x), int(y))

        self._gc_timer = QTimer(self)
        self._gc_timer.timeout.connect(self._expire_lines)
        self._gc_timer.start(1000)

    # ---------- pintado del fondo ----------
    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(10, 10, 14, 175))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)

    # ---------- subtítulos ----------
    def add_subtitle(self, sub):
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("background: transparent;")
        label.setText(self._render(sub))
        label.setProperty("speaker_id", sub.speaker_id)
        label.setProperty("is_subtitle", True)
        label.mouseDoubleClickEvent = (
            lambda ev, sid=sub.speaker_id: self._double_click(sid)
        )
        self.layout_.insertWidget(self.layout_.indexOf(self.sugg_frame), label)
        self.lines.append((sub, label))
        self.history.append(sub)
        while len(self.lines) > MAX_LINES:
            _, old = self.lines.pop(0)
            old.deleteLater()
        self._prune_overflow()

        if self.cfg.get("translate"):
            self._translate_sub(sub)

    def _render(self, sub):
        safe = (sub.text.replace("&", "&amp;")
                        .replace("<", "&lt;").replace(">", "&gt;"))
        html = (
            f'<span style="color:{sub.color}; font-weight:bold; '
            f'font-size:{self.font_size}px;">{sub.speaker_name}:</span> '
            f'<span style="color:#F2F2F2; font-size:{self.font_size}px;">'
            f'{safe}</span>'
        )
        if getattr(sub, "translation", ""):
            tr = (sub.translation.replace("&", "&amp;")
                  .replace("<", "&lt;").replace(">", "&gt;"))
            html += (
                f'<br><span style="color:#9E9E9E; font-style:italic; '
                f'font-size:{max(self.font_size - 3, 9)}px;">→ {tr}</span>'
            )
        return html

    def _apply_translation(self, sub, spanish):
        sub.translating = False
        if spanish:
            sub.translation = spanish
            # que la traducción se alcance a leer: la línea vive al menos
            # TRANSLATION_TTL segundos más a partir de ahora
            sub.timestamp = max(sub.timestamp,
                                time.time() + TRANSLATION_TTL - LINE_TTL)
        for s, label in self.lines:
            if s is sub:
                try:
                    label.setText(self._render(s))  # quita el "traduciendo…"
                except RuntimeError:
                    pass
                break
        if not spanish:
            self.set_status("⚠ IA local no disponible — "
                            "selecciona de nuevo para reintentar")
        self._prune_overflow()

    def _expire_lines(self):
        if self._selecting:
            return  # no quitar líneas mientras el usuario selecciona
        now = time.time()
        for sub, label in self.lines[:]:
            if now - sub.timestamp > LINE_TTL:
                self.lines.remove((sub, label))
                label.deleteLater()

    def _prune_overflow(self):
        """Tamaño fijo: si el contenido no cabe, quitar las líneas más viejas."""
        avail_w = self.width() - 28
        spacing = self.layout_.spacing()

        def needed():
            h = 20  # márgenes verticales
            for _s, lb in self.lines:
                h += lb.heightForWidth(avail_w) + spacing
            if self.sugg_frame.isVisible():
                h += self.sugg_frame.sizeHint().height() + spacing
            h += self.status_label.sizeHint().height()
            return h

        while len(self.lines) > 1 and needed() > self.height():
            _, old = self.lines.pop(0)
            old.deleteLater()

    def set_status(self, text):
        if text.startswith("Escuchando"):
            tk = self.cfg.get("hotkey_translate", "9")
            sk = self.cfg.get("hotkey_suggest", "0")
            text += (f"   ·   [{tk}] traducir pantalla"
                     f"   [{sk}] respuesta")
        self.status_label.setText(text)

    # ---------- teclas rápidas globales ----------
    def translate_last(self, n=None):
        """Traducir lo que está en pantalla (todo, o las últimas n frases)."""
        if not self.lines:
            self.set_status("No hay frases que traducir todavía")
            return
        subs = [s for s, _lb in (self.lines if n is None
                                 else self.lines[-n:])]
        pending = [s for s in subs
                   if not s.translation
                   and not getattr(s, "translating", False)]
        for s in subs:
            self._translate_sub(s)
        if pending:
            self.set_status(
                f"Traduciendo {len(pending)} "
                f"frase{'s' if len(pending) != 1 else ''}…")

    def suggest_latest(self):
        """Respuesta sugerida a lo último que se dijo (tecla rápida)."""
        focus = self.lines[-1][0].speaker_id if self.lines else None
        self.request_suggestion(focus_sid=focus)

    # ---------- sugerencia de respuesta ----------
    def request_suggestion(self, focus_sid=None):
        if not self.history:
            self.set_status("Aún no hay conversación para responder")
            return
        # la respuesta se sugiere sobre las ÚLTIMAS 5 frases
        convo = [f"{s.speaker_name}: {s.text}"
                 for s in list(self.history)[-5:]]
        if focus_sid is not None:
            for s in reversed(self.history):
                if s.speaker_id == focus_sid:
                    convo.append(
                        f"(I want to reply to {s.speaker_name})")
                    break
        self.sugg_label.setText("Pensando respuesta…")
        self.sugg_gloss.setText("")
        self.sugg_pron.setText("")
        self.sugg_frame.show()
        self._prune_overflow()
        self.llm.submit(
            self.llm.suggest_reply, convo,
            on_done=self.bridge.suggestion_ready.emit,
            on_error=lambda e: self.bridge.suggestion_failed.emit(str(e)),
        )

    def _show_suggestion(self, english):
        self._current_suggestion = english
        self.sugg_label.setText(f"💬 {english}")
        self.sugg_pron.setText("🗣 …")
        self._prune_overflow()
        self.llm.submit(
            self.llm.translate, english,
            on_done=self.bridge.suggestion_gloss.emit,
            on_error=lambda e: None,
        )
        self.llm.submit(
            self.llm.pronounce, english,
            on_done=self.bridge.suggestion_pron.emit,
            on_error=lambda e: self.bridge.suggestion_pron.emit(""),
        )

    def _show_gloss(self, spanish):
        self.sugg_gloss.setText(f"({spanish})")
        self._prune_overflow()

    def _show_pron(self, phonetics):
        self.sugg_pron.setText(f"🗣 {phonetics}" if phonetics else "")
        self._prune_overflow()

    def _suggestion_failed(self, msg):
        self.sugg_label.setText("⚠ IA local no disponible (¿Ollama corriendo?)")
        self.sugg_gloss.setText("")
        self.sugg_pron.setText("")
        self._prune_overflow()

    def _copy_suggestion(self):
        text = getattr(self, "_current_suggestion", "")
        if text:
            QApplication.clipboard().setText(text)
            self.set_status("Sugerencia copiada ✓")

    def _send_chatbox(self):
        text = getattr(self, "_current_suggestion", "")
        if text:
            if osc.send_chatbox(text):
                self.set_status("Enviada al chatbox de VRChat ✓ "
                                "(requiere OSC activado en el juego)")
            else:
                self.set_status("No se pudo enviar por OSC")

    # ---------- traducción de UNA frase (mantener clic sobre ella) ----------
    def _label_for_child(self, child):
        """Sube por la jerarquía hasta encontrar una etiqueta de subtítulo."""
        while child is not None and child is not self:
            if child.property("is_subtitle"):
                return child
            child = child.parentWidget()
        return None

    def _line_index_of_label(self, label):
        for i, (_s, lb) in enumerate(self.lines):
            if lb is label:
                return i
        return None

    def _line_index_at(self, pos):
        return self._line_index_of_label(
            self._label_for_child(self.childAt(pos)))

    # ---------- selección tipo navegador ----------
    def _start_selection(self, idx):
        self._selecting = True
        self._drag_pos = None        # no es arrastre de ventana
        self._click_timer.stop()     # ni clic de sugerencia
        self._pending_click_sid = None
        self._sel_anchor = idx
        self._update_selection(idx)
        self.set_status("Suelta el clic para traducir lo seleccionado")

    def _update_selection(self, idx):
        if idx is None or self._sel_anchor is None:
            return  # fuera de las líneas: se mantiene la selección actual
        i0, i1 = sorted((self._sel_anchor, idx))
        self._sel_range = (i0, i1)
        for i, (_s, label) in enumerate(self.lines):
            if i0 <= i <= i1:
                label.setStyleSheet(
                    "background: rgba(80, 120, 200, 90); "
                    "border-radius: 4px;")
            else:
                label.setStyleSheet("background: transparent;")

    def _clear_selection(self):
        self._selecting = False
        self._sel_anchor = None
        self._sel_range = None
        for _s, label in self.lines:
            label.setStyleSheet("background: transparent;")

    def _translate_sub(self, sub):
        if sub.translation or getattr(sub, "translating", False):
            return  # ya traducida o en curso
        sub.translating = True
        # feedback inmediato mientras la IA responde
        for s, label in self.lines:
            if s is sub:
                try:
                    label.setText(
                        self._render(s)
                        + '<br><span style="color:#777; font-style:italic; '
                        'font-size:11px;">→ traduciendo…</span>')
                except RuntimeError:
                    pass
                break
        self.llm.submit(
            self.llm.translate, sub.text,
            on_done=lambda es, s=sub: self.bridge.translated.emit(s, es),
            # None = falló: se limpia y podrá reintentarse
            on_error=lambda e, s=sub: self.bridge.translated.emit(s, None),
        )

    def _hold_timeout(self):
        # clic mantenido quieto sobre una frase → empezar selección ahí
        idx = self._line_index_of_label(
            self._label_for_child(self._press_child))
        if idx is not None:
            self._start_selection(idx)

    # ---------- interacción ratón ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press_global = ev.globalPosition().toPoint()
            self._press_child = self.childAt(ev.position().toPoint())
            if self._label_for_child(self._press_child) is not None:
                # sobre una frase: candidata a selección, no a arrastre
                self._drag_pos = None
                self._hold_timer.start()
            else:
                self._drag_pos = (ev.globalPosition().toPoint()
                                  - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, ev):
        if self._selecting:
            # barrido con el clic apretado: extender la selección
            self._update_selection(
                self._line_index_at(ev.position().toPoint()))
            return
        if not (ev.buttons() & Qt.LeftButton):
            return
        moved = (self._press_global is not None
                 and (ev.globalPosition().toPoint() - self._press_global)
                 .manhattanLength() >= 4)
        if moved:
            idx = self._line_index_of_label(
                self._label_for_child(self._press_child))
            if idx is not None:
                # empezó sobre una frase y se movió: selección inmediata
                self._hold_timer.stop()
                self._start_selection(idx)
                self._update_selection(
                    self._line_index_at(ev.position().toPoint()))
                return
        if self._drag_pos is not None:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, ev):
        self._hold_timer.stop()
        if self._selecting:
            # al soltar: traducir SOLO lo seleccionado
            if self._sel_range is not None:
                i0, i1 = self._sel_range
                i1 = min(i1, len(self.lines) - 1)
                n = 0
                for i in range(i0, i1 + 1):
                    self._translate_sub(self.lines[i][0])
                    n += 1
                self.set_status(
                    f"Traduciendo {n} frase{'s' if n != 1 else ''}…")
            self._clear_selection()
        elif (self._press_global is not None
                and (ev.globalPosition().toPoint() - self._press_global)
                .manhattanLength() < 6):
            label = self._label_for_child(self._press_child)
            if label is not None:
                # clic corto (sin arrastre) sobre una línea → sugerir
                # respuesta, salvo doble clic en los próximos ms
                self._pending_click_sid = label.property("speaker_id")
                self._click_timer.start()
        if (self._drag_pos is not None and self._press_global is not None
                and (ev.globalPosition().toPoint() - self._press_global)
                .manhattanLength() >= 6):
            # recordar dónde dejó la ventana
            self.cfg["pos_x"], self.cfg["pos_y"] = self.x(), self.y()
            config_mod.save(self.cfg)
        self._drag_pos = None
        self._press_child = None
        self._press_global = None

    def _click_timeout(self):
        sid = self._pending_click_sid
        self._pending_click_sid = None
        if sid is not None:
            self.request_suggestion(focus_sid=sid)

    def _double_click(self, sid):
        self._click_timer.stop()
        self._hold_timer.stop()
        self._pending_click_sid = None
        self._clear_selection()
        self._rename_speaker(sid)

    # ---------- menú ----------
    def contextMenuEvent(self, ev):
        menu = QMenu(self)

        translate_a = menu.addAction("Traducir TODO automáticamente")
        translate_a.setCheckable(True)
        translate_a.setChecked(bool(self.cfg.get("translate")))

        suggest_a = menu.addAction("Sugerir respuesta ahora")

        model_menu = menu.addMenu("Modelo IA")
        models = self.llm.list_models()
        if not models:
            a = model_menu.addAction("(Ollama no disponible)")
            a.setEnabled(False)
        for name in models:
            act = model_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(name == self.llm.model)
            act.triggered.connect(
                lambda checked=False, n=name: self._set_model(n))

        menu.addSeparator()
        rename_menu = menu.addMenu("Renombrar hablante")
        speakers = list(self.pipeline.registry.speakers.values())
        if not speakers:
            a = rename_menu.addAction("(todavía no hay voces)")
            a.setEnabled(False)
        for sp in speakers:
            act = rename_menu.addAction(f"{sp.name}")
            act.triggered.connect(
                lambda checked=False, sid=sp.sid: self._rename_speaker(sid)
            )

        bigger = menu.addAction("Letra más grande")
        smaller = menu.addAction("Letra más pequeña")
        menu.addSeparator()
        forget = menu.addAction("Olvidar todas las voces")
        menu.addSeparator()
        quit_a = menu.addAction("Salir")

        chosen = menu.exec(ev.globalPos())
        if chosen == translate_a:
            self.cfg["translate"] = translate_a.isChecked()
            config_mod.save(self.cfg)
            if self.cfg["translate"] and not self.llm.ensure_model():
                self.set_status("⚠ Ollama no responde: la traducción "
                                "quedará en espera")
            else:
                self.set_status("Traducción al español: "
                                + ("ON" if self.cfg["translate"] else "OFF"))
        elif chosen == suggest_a:
            self.request_suggestion()
        elif chosen == bigger:
            self._set_font(min(self.font_size + 2, 40))
        elif chosen == smaller:
            self._set_font(max(self.font_size - 2, 9))
        elif chosen == forget:
            self.pipeline.registry.forget_all()
        elif chosen == quit_a:
            QApplication.quit()

    def _set_model(self, name):
        self.llm.model = name
        self.cfg["ollama_model"] = name
        config_mod.save(self.cfg)
        self.set_status(f"Modelo IA: {name}")

    def _set_font(self, size):
        self.font_size = size
        self.cfg["font_size"] = size
        config_mod.save(self.cfg)
        self.sugg_label.setStyleSheet(
            f"color: #B9F6CA; font-size: {size}px; "
            "font-weight: bold; background: transparent;"
        )
        for sub, label in self.lines:
            label.setText(self._render(sub))
        self._prune_overflow()

    def _rename_speaker(self, sid):
        reg = self.pipeline.registry
        sp = reg.speakers.get(sid)
        if sp is None:
            return
        name, ok = QInputDialog.getText(
            self, "Renombrar hablante",
            f"Nombre para «{sp.name}»:", text=sp.name,
        )
        if ok and name.strip():
            reg.rename(sid, name)
            for sub, label in self.lines:
                if sub.speaker_id == sid:
                    sub.speaker_name = name.strip()
                    label.setText(self._render(sub))
