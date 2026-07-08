# ui.py — AI Writing Tools Launcher

import json
import logging
import os
import subprocess
import threading
import webbrowser

from PyQt6.QtCore    import Qt, QProcess, QProcessEnvironment, QThread, pyqtSignal
from PyQt6.QtGui     import QFont, QColor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QApplication,
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFrame,
    QSplitter, QComboBox, QMessageBox,
)

import imagegen_engine
import imagegen_server
from constants import *

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status indicator — coloured dot + text label
# ---------------------------------------------------------------------------

class StatusBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setFont(QFont(FONT_UI_FAMILY, 10))

        self._label = QLabel("Stopped")
        self._label.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))

        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        layout.addStretch()

        self.set_stopped()

    def _apply(self, color: str, text: str):
        self._dot.setStyleSheet(f"color: {color};")
        self._label.setStyleSheet(f"color: {color};")
        self._label.setText(text)

    def set_stopped(self):  self._apply(COLOR_STATUS_STOPPED,  "Stopped")
    def set_starting(self): self._apply(COLOR_STATUS_STARTING, "Starting…")
    def set_running(self):  self._apply(COLOR_STATUS_RUNNING,  "Running")
    def set_error(self):    self._apply(COLOR_STATUS_ERROR,    "Error")
    def set_text(self, color: str, text: str): self._apply(color, text)


# ---------------------------------------------------------------------------
# Service card — backend process card (KoboldCpp only)
# ---------------------------------------------------------------------------

class ServiceCard(QFrame):
    def __init__(self, title: str,
                 model_items: list[tuple[str, str]] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("ServiceCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)

        title_lbl = QLabel(title)
        title_lbl.setFont(QFont(FONT_UI_FAMILY, 10, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {COLOR_ACCENT};")
        outer.addWidget(title_lbl)

        self.lbl_subtitle = QLabel("")
        self.lbl_subtitle.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE - 1))
        self.lbl_subtitle.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        self.lbl_subtitle.setVisible(False)
        outer.addWidget(self.lbl_subtitle)

        self.status = StatusBadge()
        outer.addWidget(self.status)

        if model_items:
            self.model_combo = QComboBox()
            self.model_combo.setFixedHeight(26)
            for name, key in model_items:
                self.model_combo.addItem(name, userData=key)
            outer.addWidget(self.model_combo)
        else:
            self.model_combo = None

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_start = QPushButton("Start")
        self.btn_stop  = QPushButton("Stop")
        self.btn_stop.setEnabled(False)

        for btn in (self.btn_start, self.btn_stop):
            btn.setFixedHeight(26)
            btn.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        outer.addLayout(btn_row)


# ---------------------------------------------------------------------------
# Image Gen (local SDXL) pipeline warm-up worker
# ---------------------------------------------------------------------------

class _ImageGenLoadWorker(QThread):
    """Loads (or confirms already-loaded) the SDXL checkpoint/LoRA/TI into GPU
    memory so Start finishes before anyone actually needs to generate — the
    Launcher's own dialog, or later a SillyTavern-facing API server, can then
    generate immediately instead of eating the ~10s checkpoint-load cost on
    their first request.
    """

    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def run(self):
        try:
            imagegen_engine.load_pipeline()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# API test worker
# ---------------------------------------------------------------------------

class _ApiTestWorker(QThread):
    success = pyqtSignal(str, list)
    error   = pyqtSignal(str)

    def run(self):
        import urllib.request
        import urllib.error

        headers = {"User-Agent": "python-requests/2.31.0"}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"

        try:
            req = urllib.request.Request(f"{API_BASE_URL}/v1/models", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                model_ids = [m["id"] for m in data.get("data", [])]
                msg = f"{len(model_ids)} models available" if model_ids else "Connected"
                self.success.emit(msg, model_ids)
                return
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.error.emit("Invalid API key (401)")
                return
        except urllib.error.URLError as e:
            self.error.emit(f"Cannot reach endpoint ({e.reason})")
            return
        except Exception:
            pass

        payload = json.dumps({
            **({"model": API_MODEL} if API_MODEL else {}),
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
            "stream": False,
        }).encode()
        try:
            req = urllib.request.Request(
                f"{API_BASE_URL}/v1/chat/completions",
                data=payload,
                headers={**headers, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as _:
                self.success.emit("Connected", [])
        except urllib.error.HTTPError as e:
            self.error.emit(f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            self.error.emit(f"Cannot reach endpoint ({e.reason})")
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# API card — compact backend card for remote API
# ---------------------------------------------------------------------------

class ApiCard(QFrame):
    model_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ServiceCard")
        self._worker = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(6)

        title_lbl = QLabel("API Backend  ·  Remote Models")
        title_lbl.setFont(QFont(FONT_UI_FAMILY, 10, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {COLOR_ACCENT};")
        outer.addWidget(title_lbl)

        url_text = API_BASE_URL if API_BASE_URL else "Not configured — add \"api\" block to config.json"
        url_lbl = QLabel(url_text)
        url_lbl.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE - 1))
        url_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        outer.addWidget(url_lbl)

        self.model_combo = QComboBox()
        self.model_combo.setFixedHeight(24)
        self.model_combo.setVisible(False)
        if API_MODEL:
            self.model_combo.addItem(API_MODEL, userData=API_MODEL)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        outer.addWidget(self.model_combo)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.status = StatusBadge()
        if not API_BASE_URL:
            self.status.set_text(COLOR_STATUS_STOPPED, "Not configured")
        else:
            self.status.set_text(COLOR_STATUS_STOPPED, "Not activated")
        row.addWidget(self.status)
        row.addStretch()
        self.btn_activate = QPushButton("Activate")
        self.btn_activate.setFixedHeight(26)
        self.btn_activate.setEnabled(bool(API_BASE_URL))
        self.btn_activate.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
        row.addWidget(self.btn_activate)
        outer.addLayout(row)

    def populate_models(self, model_ids: list):
        self.model_combo.blockSignals(True)
        current = self.current_model
        self.model_combo.clear()
        for mid in sorted(model_ids):
            self.model_combo.addItem(mid, userData=mid)
        prefer = current or API_MODEL
        idx = self.model_combo.findData(prefer)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)
        self.model_combo.setVisible(bool(model_ids))
        if model_ids:
            self.model_changed.emit(self.current_model)

    @property
    def current_model(self) -> str:
        if self.model_combo.isVisible() and self.model_combo.count():
            return self.model_combo.currentData() or self.model_combo.currentText()
        return API_MODEL

    def _on_model_changed(self):
        self.model_changed.emit(self.current_model)


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
QMainWindow, QWidget#root {{
    background: {COLOR_BG};
}}
QFrame#ServiceCard {{
    background: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}
QFrame#ToolsSection {{
    background: {COLOR_PANEL};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
}}
QPushButton {{
    background: {COLOR_BUTTON_BG};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 2px 10px;
}}
QPushButton:hover:enabled {{
    background: {COLOR_BUTTON_HOVER};
    border-color: {COLOR_ACCENT_DIM};
}}
QPushButton:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}
QPushButton#accent {{
    background: {COLOR_ACCENT_DIM};
    border-color: {COLOR_ACCENT};
    color: {COLOR_TEXT};
}}
QPushButton#accent:hover:enabled {{
    background: {COLOR_ACCENT};
}}
QPushButton#danger {{
    background: #3d1a1a;
    border-color: {COLOR_STATUS_ERROR};
    color: {COLOR_STATUS_ERROR};
}}
QPushButton#danger:hover:enabled {{
    background: #5a2020;
}}
QTextEdit {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    font-family: {FONT_LOG_FAMILY};
    font-size: {FONT_LOG_SIZE}pt;
}}
QLabel#header {{
    background: {COLOR_HEADER_BAR};
    color: {COLOR_TEXT};
    padding: 8px 14px;
    font-size: 11pt;
    font-weight: bold;
}}
QLabel#version {{
    background: {COLOR_HEADER_BAR};
    color: {COLOR_TEXT_MUTED};
    padding: 8px 14px;
    font-size: 8pt;
}}
QSplitter::handle {{
    background: {COLOR_BORDER};
}}
QComboBox {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 2px 8px;
    selection-background-color: {COLOR_ACCENT_DIM};
}}
QComboBox:hover {{
    border-color: {COLOR_ACCENT_DIM};
}}
QComboBox:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    selection-background-color: {COLOR_ACCENT_DIM};
    outline: none;
}}
"""

_BTN_ST_START_READY = (
    f"background: {COLOR_ACCENT_DIM}; border-color: {COLOR_ACCENT}; color: {COLOR_ACCENT};"
)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(580, 560)
        self.resize(680, 720)
        self.setStyleSheet(STYLESHEET)

        self._kobold_proc       = None
        self._st_proc           = None
        self._kobold_ready      = False
        self._st_ready          = False
        self._kobold_stopping   = False
        self._st_stopping       = False
        self._current_model_key = None
        self._chargen_dlg       = None
        self._imagegen_local_dlg = None
        self._imagegen_local_ready   = False
        self._imagegen_local_loading = False
        self._imagegen_load_worker   = None
        self._imagegen_stop_requested = False
        self._api_ready         = False

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Header bar
        header_row = QWidget()
        header_row.setStyleSheet(f"background: {COLOR_HEADER_BAR};")
        hdr_layout = QHBoxLayout(header_row)
        hdr_layout.setContentsMargins(14, 0, 14, 0)

        hdr_title = QLabel(APP_NAME)
        hdr_title.setObjectName("header")
        hdr_title.setStyleSheet(
            f"color: {COLOR_TEXT}; font-size: 11pt; font-weight: bold; background: transparent;"
        )
        hdr_ver = QLabel(f"v{APP_VERSION}")
        hdr_ver.setObjectName("version")
        hdr_ver.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: 8pt; background: transparent;"
        )
        btn_settings = QPushButton("Settings")
        btn_settings.setFixedHeight(24)
        btn_settings.setFont(QFont(FONT_UI_FAMILY, 8))
        btn_settings.setStyleSheet(
            f"background: transparent; border: 1px solid {COLOR_ACCENT};"
            f" color: {COLOR_TEXT}; border-radius: 3px; padding: 1px 8px;"
        )
        btn_settings.clicked.connect(self._open_settings)

        btn_donate = QPushButton("♥ Donate")
        btn_donate.setFixedHeight(24)
        btn_donate.setFont(QFont(FONT_UI_FAMILY, 8))
        btn_donate.setStyleSheet(
            "background: transparent; border: none;"
            " color: #c0665a; padding: 1px 4px;"
        )
        btn_donate.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_donate.clicked.connect(
            lambda: webbrowser.open("https://ko-fi.com/xechostormx")
        )

        hdr_layout.addWidget(hdr_title)
        hdr_layout.addStretch()
        hdr_layout.addWidget(btn_donate)
        hdr_layout.addSpacing(6)
        hdr_layout.addWidget(btn_settings)
        hdr_layout.addSpacing(10)
        hdr_layout.addWidget(hdr_ver)
        header_row.setFixedHeight(40)
        vbox.addWidget(header_row)

        _div = QFrame()
        _div.setFixedHeight(2)
        _div.setStyleSheet(f"background: {COLOR_ACCENT_DIM}; border: none;")
        vbox.addWidget(_div)

        # Main content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        cards_widget = QWidget()
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(8)

        # ── Backends ──────────────────────────────────────────────────

        cards_layout.addWidget(self._section_header("Backends"))

        backends_row = QHBoxLayout()
        backends_row.setSpacing(8)

        self.kobold_card = ServiceCard(
            "KoboldCpp  ·  Local Backend",
            model_items=[(m["name"], m.get("key", "")) for m in MODELS],
        )
        self.api_card = ApiCard()

        backends_row.addWidget(self.kobold_card, 1)
        backends_row.addWidget(self.api_card, 1)
        cards_layout.addLayout(backends_row)

        # ── Tools ─────────────────────────────────────────────────────

        cards_layout.addWidget(self._section_header("Tools"))

        tools_frame = QFrame()
        tools_frame.setObjectName("ToolsSection")
        tools_vbox = QVBoxLayout(tools_frame)
        tools_vbox.setContentsMargins(0, 0, 0, 0)
        tools_vbox.setSpacing(0)

        # SillyTavern tool row
        st_row = QWidget()
        st_row.setStyleSheet(f"background: transparent;")
        st_layout = QHBoxLayout(st_row)
        st_layout.setContentsMargins(14, 9, 14, 9)
        st_layout.setSpacing(8)

        st_title = QLabel("SillyTavern")
        st_title.setFont(QFont(FONT_UI_FAMILY, 9, QFont.Weight.Bold))
        st_title.setStyleSheet(f"color: {COLOR_TEXT};")
        st_title.setFixedWidth(108)
        st_layout.addWidget(st_title)

        self.st_status = StatusBadge()
        st_layout.addWidget(self.st_status)

        self.st_via_lbl = QLabel("")
        self.st_via_lbl.setFont(QFont(FONT_UI_FAMILY, 8))
        self.st_via_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        st_layout.addWidget(self.st_via_lbl, 1)

        self.btn_st_start = QPushButton("Start")
        self.btn_st_stop  = QPushButton("Stop")
        self.btn_st_open  = QPushButton("Open ST")
        self.btn_st_stop.setEnabled(False)
        self.btn_st_open.setEnabled(False)
        for b in (self.btn_st_start, self.btn_st_stop, self.btn_st_open):
            b.setFixedHeight(26)
            b.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
        st_layout.addWidget(self.btn_st_start)
        st_layout.addWidget(self.btn_st_stop)
        st_layout.addWidget(self.btn_st_open)

        tools_vbox.addWidget(st_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {COLOR_BORDER}; border: none;")
        tools_vbox.addWidget(sep)

        # CharGen tool row
        cg_row = QWidget()
        cg_row.setStyleSheet("background: transparent;")
        cg_layout = QHBoxLayout(cg_row)
        cg_layout.setContentsMargins(14, 9, 14, 9)
        cg_layout.setSpacing(8)

        cg_title = QLabel("Character Card Generator")
        cg_title.setFont(QFont(FONT_UI_FAMILY, 9, QFont.Weight.Bold))
        cg_title.setStyleSheet(f"color: {COLOR_TEXT};")
        cg_title.setFixedWidth(180)
        cg_layout.addWidget(cg_title)

        self.chargen_via_lbl = QLabel("")
        self.chargen_via_lbl.setFont(QFont(FONT_UI_FAMILY, 8))
        self.chargen_via_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        cg_layout.addWidget(self.chargen_via_lbl, 1)

        self.btn_chargen = QPushButton("Open CharGen")
        self.btn_chargen.setFixedHeight(26)
        self.btn_chargen.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
        cg_layout.addWidget(self.btn_chargen)

        tools_vbox.addWidget(cg_row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {COLOR_BORDER}; border: none;")
        tools_vbox.addWidget(sep2)

        # Image Gen (local in-process SDXL) tool row
        lig_row = QWidget()
        lig_row.setStyleSheet("background: transparent;")
        lig_layout = QHBoxLayout(lig_row)
        lig_layout.setContentsMargins(14, 9, 14, 9)
        lig_layout.setSpacing(8)

        lig_title = QLabel("Image Gen")
        lig_title.setFont(QFont(FONT_UI_FAMILY, 9, QFont.Weight.Bold))
        lig_title.setStyleSheet(f"color: {COLOR_TEXT};")
        lig_title.setFixedWidth(140)
        lig_layout.addWidget(lig_title)

        self.imagegen_local_status = StatusBadge()
        lig_layout.addWidget(self.imagegen_local_status)

        self.imagegen_local_via_lbl = QLabel("txt2img + LoRA + TI + hires-fix")
        self.imagegen_local_via_lbl.setFont(QFont(FONT_UI_FAMILY, 8))
        self.imagegen_local_via_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        lig_layout.addWidget(self.imagegen_local_via_lbl, 1)

        self.btn_imagegen_local_start = QPushButton("Start")
        self.btn_imagegen_local_stop  = QPushButton("Stop")
        self.btn_imagegen_local_open  = QPushButton("Open")
        self.btn_imagegen_local_stop.setEnabled(False)
        self.btn_imagegen_local_open.setEnabled(False)
        self.btn_imagegen_local_start.setEnabled(bool(SDXL_MODEL_PATH))
        for b in (self.btn_imagegen_local_start, self.btn_imagegen_local_stop, self.btn_imagegen_local_open):
            b.setFixedHeight(26)
            b.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
        lig_layout.addWidget(self.btn_imagegen_local_start)
        lig_layout.addWidget(self.btn_imagegen_local_stop)
        lig_layout.addWidget(self.btn_imagegen_local_open)

        tools_vbox.addWidget(lig_row)

        # Kill All footer
        kill_row = QHBoxLayout()
        kill_row.setContentsMargins(14, 6, 14, 8)
        self.btn_kill_all = QPushButton("Kill All")
        self.btn_kill_all.setObjectName("danger")
        self.btn_kill_all.setFixedHeight(24)
        self.btn_kill_all.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
        kill_row.addStretch()
        kill_row.addWidget(self.btn_kill_all)
        tools_vbox.addLayout(kill_row)

        cards_layout.addWidget(tools_frame)
        cards_layout.addStretch()

        splitter.addWidget(cards_widget)

        # Log pane
        log_pane = QWidget()
        log_layout = QVBoxLayout(log_pane)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_header.setContentsMargins(0, 0, 0, 0)
        log_header.setSpacing(6)

        log_lbl = QLabel("Output")
        log_lbl.setFont(QFont(FONT_UI_FAMILY, 8))
        log_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        log_header.addWidget(log_lbl)
        log_header.addStretch()

        btn_copy_log = QPushButton("Copy")
        btn_copy_log.setFixedHeight(20)
        btn_copy_log.setFont(QFont(FONT_UI_FAMILY, 7))
        btn_copy_log.clicked.connect(self._copy_log)
        log_header.addWidget(btn_copy_log)

        btn_clear_log = QPushButton("Clear")
        btn_clear_log.setFixedHeight(20)
        btn_clear_log.setFont(QFont(FONT_UI_FAMILY, 7))
        btn_clear_log.clicked.connect(self._clear_log)
        log_header.addWidget(btn_clear_log)

        log_layout.addLayout(log_header)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont(FONT_LOG_FAMILY, FONT_LOG_SIZE))
        log_layout.addWidget(self.log)

        splitter.addWidget(log_pane)
        splitter.setSizes([420, 200])

        content_layout.addWidget(splitter)
        vbox.addWidget(content)

        # Wire up signals
        self.kobold_card.btn_start.clicked.connect(self._start_kobold_writing)
        self.kobold_card.btn_stop.clicked.connect(self._stop_kobold)
        self.btn_st_start.clicked.connect(self._start_st)
        self.btn_st_stop.clicked.connect(self._stop_st)
        self.btn_st_open.clicked.connect(self._open_st)
        self.btn_chargen.clicked.connect(self._open_chargen)
        self.btn_imagegen_local_start.clicked.connect(self._start_imagegen_local)
        self.btn_imagegen_local_stop.clicked.connect(self._stop_imagegen_local)
        self.btn_imagegen_local_open.clicked.connect(self._open_imagegen_local)
        self.btn_kill_all.clicked.connect(self._kill_all)
        self.api_card.btn_activate.clicked.connect(self._activate_api)
        self.api_card.model_changed.connect(self._on_api_model_changed)

        self._update_tools()

    @staticmethod
    def _section_header(text: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)
        lbl = QLabel(text.upper())
        lbl.setFont(QFont(FONT_UI_FAMILY, 7, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {COLOR_ACCENT_DIM}; letter-spacing: 1px;")
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {COLOR_BORDER}; border: none;")
        h.addWidget(lbl)
        h.addWidget(line, 1)
        return w

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log(self, text: str, color: str = COLOR_TEXT_MUTED):
        self.log.setTextColor(QColor(color))
        for line in text.splitlines():
            if line.strip():
                self.log.append(line)
        log.info(text.strip())

    def _log_kobold(self, text: str):
        self._log(f"[KoboldCpp] {text}", "#7c6fcd")

    def _log_st(self, text: str):
        self._log(f"[SillyTavern] {text}", "#5ba0c8")

    def _log_imagegen(self, text: str, color: str = "#c77dd4"):
        self._log(f"[ImageGen] {text}", color)

    def _copy_log(self):
        QApplication.clipboard().setText(self.log.toPlainText())

    def _clear_log(self):
        self.log.clear()

    # ------------------------------------------------------------------
    # Tool row state
    # ------------------------------------------------------------------

    def _update_tools(self):
        if self._api_ready:
            model = self.api_card.current_model
            via   = f"via API — {model}" if model else "via API"
            color = "#4a9edd"
        elif self._kobold_ready:
            m    = next((m for m in MODELS if m.get("key") == self._current_model_key), None)
            name = m["name"] if m else "KoboldCpp"
            via  = f"via KoboldCpp — {name}"
            color = COLOR_STATUS_RUNNING
        else:
            via   = "start a backend above"
            color = COLOR_TEXT_MUTED

        style = f"color: {color}; font-size: 8pt;"
        self.st_via_lbl.setText(via)
        self.st_via_lbl.setStyleSheet(style)
        self.chargen_via_lbl.setText(via)
        self.chargen_via_lbl.setStyleSheet(style)

        backend_ready = self._api_ready or self._kobold_ready
        self.btn_chargen.setEnabled(backend_ready)
        # Only touch Start when ST is not mid-launch (otherwise we'd re-enable it while starting)
        st_idle = not self._st_proc or self._st_proc.state() == QProcess.ProcessState.NotRunning
        if st_idle:
            self.btn_st_start.setEnabled(backend_ready)
        if backend_ready and not self._st_ready and st_idle:
            self.btn_st_start.setStyleSheet(_BTN_ST_START_READY)
        else:
            self.btn_st_start.setStyleSheet("")

    # ------------------------------------------------------------------
    # KoboldCpp process
    # ------------------------------------------------------------------

    def _start_kobold_writing(self):
        combo = self.kobold_card.model_combo
        key = combo.currentData() if combo else ""
        self._start_kobold(key or (MODELS[0].get("key", "") if MODELS else ""))

    def _start_kobold(self, model_key: str):
        if self._kobold_proc and self._kobold_proc.state() != QProcess.ProcessState.NotRunning:
            return

        if not KOBOLD_EXE or not os.path.isfile(KOBOLD_EXE):
            self._log("[KoboldCpp] ERROR: Executable not found — check Settings.", COLOR_STATUS_ERROR)
            self.kobold_card.status.set_error()
            return

        model = next((m for m in MODELS if m.get("key") == model_key), MODELS[0] if MODELS else None)
        if not model:
            self._log("[KoboldCpp] ERROR: No models configured in config.json.", COLOR_STATUS_ERROR)
            self.kobold_card.status.set_error()
            return

        model_path = model["path"]
        model_name = model["name"]

        if not os.path.isfile(model_path):
            self._log_kobold(f"ERROR: Model file not found:\n  {model_path}")
            self.kobold_card.status.set_error()
            return

        if EMBEDDINGS_MODEL and not os.path.isfile(EMBEDDINGS_MODEL):
            self._log_kobold(
                f"WARNING: Embeddings model not found — Vector Storage / CharMemory "
                f"embeddings will be unavailable this session:\n  {EMBEDDINGS_MODEL}"
            )

        self._current_model_key = model_key
        self._kobold_ready = False
        self.kobold_card.status.set_starting()
        self.kobold_card.lbl_subtitle.setText(f"Loading  {model_name}…")
        self.kobold_card.lbl_subtitle.setVisible(True)
        self.kobold_card.btn_start.setEnabled(False)
        self.kobold_card.btn_stop.setEnabled(True)
        if self.kobold_card.model_combo:
            self.kobold_card.model_combo.setEnabled(False)
        self._log_kobold(f"Starting with model: {model_name}")
        self._update_tools()

        proc = QProcess(self)
        proc.setProgram(KOBOLD_EXE)
        proc.setArguments(build_kobold_args(model_path))
        proc.readyReadStandardOutput.connect(self._on_kobold_stdout)
        proc.readyReadStandardError.connect(self._on_kobold_stderr)
        proc.finished.connect(self._on_kobold_finished)
        proc.start()
        self._kobold_proc = proc

    def _tree_kill(self, pid: int, wait: bool = False):
        """taskkill /T (tree-kill) — needed because koboldcpp.exe (a PyInstaller
        onefile bootloader) and SillyTavern's node.exe can both spawn a real
        worker child that QProcess's own PID doesn't reach; .kill() alone can
        leave that child orphaned holding the GPU/VRAM or the port. Async by
        default (fire on a background thread and return immediately) to match
        this app's "stops are async" architecture — pass wait=True only from
        closeEvent, which is the one place allowed to block briefly on exit
        to guarantee the tree-kill actually completes before the app quits."""
        def _run():
            try:
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                log.warning(f"taskkill /T /PID {pid} failed or timed out: {e}")

        if wait:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

    def _stop_kobold(self, wait: bool = False):
        if self._kobold_proc and self._kobold_proc.state() != QProcess.ProcessState.NotRunning:
            self._kobold_stopping = True
            pid = self._kobold_proc.processId()
            if pid:
                self._tree_kill(pid, wait=wait)
            self._kobold_proc.kill()
        self._kobold_ready = False
        self.kobold_card.btn_stop.setEnabled(False)

    def _on_kobold_stdout(self):
        if not self._kobold_proc:
            return
        data = self._kobold_proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._log_kobold(data)
        self._check_kobold_ready(data)

    def _on_kobold_stderr(self):
        if not self._kobold_proc:
            return
        data = self._kobold_proc.readAllStandardError().data().decode("utf-8", errors="replace")
        self._log_kobold(data)
        self._check_kobold_ready(data)

    def _check_kobold_ready(self, text: str):
        if self._kobold_ready:
            return
        if any(s in text.lower() for s in KOBOLD_READY_STRINGS):
            self._kobold_ready = True
            self.kobold_card.status.set_running()
            m = next((m for m in MODELS if m.get("key") == self._current_model_key), None)
            model_name = m["name"] if m else (self._current_model_key or "Unknown")
            self.kobold_card.lbl_subtitle.setText(model_name)
            self._log_kobold(f"Ready — {model_name}")
            self._update_tools()

    def _on_kobold_finished(self, exit_code: int, exit_status):
        self._kobold_ready = False
        self._current_model_key = None
        if self._kobold_stopping or exit_code == 0:
            self.kobold_card.status.set_stopped()
        else:
            self.kobold_card.status.set_error()
        self._kobold_stopping = False
        self.kobold_card.lbl_subtitle.setVisible(False)
        self.kobold_card.btn_start.setEnabled(True)
        self.kobold_card.btn_stop.setEnabled(False)
        if self.kobold_card.model_combo:
            self.kobold_card.model_combo.setEnabled(True)
        self._log_kobold(f"Exited (code {exit_code})")
        self._kobold_proc = None
        self._update_tools()

    # ------------------------------------------------------------------
    # SillyTavern process
    # ------------------------------------------------------------------

    def _start_st(self):
        if self._st_proc and self._st_proc.state() != QProcess.ProcessState.NotRunning:
            return

        if not SILLYTAVERN_DIR or not os.path.isdir(SILLYTAVERN_DIR):
            self._log("[SillyTavern] ERROR: Directory not found — check Settings.", COLOR_STATUS_ERROR)
            self.st_status.set_error()
            return

        self._st_ready = False
        self.st_status.set_starting()
        self.btn_st_start.setEnabled(False)
        self.btn_st_stop.setEnabled(True)
        self.btn_st_open.setEnabled(False)
        self.btn_st_start.setStyleSheet("")
        self._log_st("Starting…")

        node_exe = self._find_node()
        if not node_exe:
            self._log("ERROR: node.exe not found on PATH.", COLOR_STATUS_ERROR)
            self.st_status.set_error()
            self.btn_st_start.setEnabled(True)
            self.btn_st_stop.setEnabled(False)
            self._update_tools()
            return

        proc = QProcess(self)
        proc.setProgram(node_exe)
        proc.setArguments(SILLYTAVERN_ARGS)
        proc.setWorkingDirectory(SILLYTAVERN_DIR)
        proc.readyReadStandardOutput.connect(self._on_st_stdout)
        proc.readyReadStandardError.connect(self._on_st_stderr)
        proc.finished.connect(self._on_st_finished)
        proc.start()
        self._st_proc = proc

    def _stop_st(self, wait: bool = False):
        if self._st_proc and self._st_proc.state() != QProcess.ProcessState.NotRunning:
            self._st_stopping = True
            pid = self._st_proc.processId()
            if pid:
                self._tree_kill(pid, wait=wait)
            self._st_proc.kill()
        self._st_ready = False
        self.btn_st_stop.setEnabled(False)
        self.btn_st_open.setEnabled(False)

    def _on_st_stdout(self):
        if not self._st_proc:
            return
        data = self._st_proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._log_st(data)
        self._check_st_ready(data)

    def _on_st_stderr(self):
        if not self._st_proc:
            return
        data = self._st_proc.readAllStandardError().data().decode("utf-8", errors="replace")
        self._log_st(data)
        self._check_st_ready(data)

    def _check_st_ready(self, text: str):
        if self._st_ready:
            return
        if any(s in text.lower() for s in SILLYTAVERN_READY_STRINGS):
            self._st_ready = True
            self.st_status.set_running()
            self.btn_st_open.setEnabled(True)
            self._log_st("Ready.")
            self._update_tools()

    def _on_st_finished(self, exit_code: int, exit_status):
        self._st_ready = False
        if self._st_stopping or exit_code == 0:
            self.st_status.set_stopped()
        else:
            self.st_status.set_error()
        self._st_stopping = False
        self.btn_st_stop.setEnabled(False)
        self.btn_st_open.setEnabled(False)
        self._log_st(f"Exited (code {exit_code})")
        self._st_proc = None
        self._update_tools()

    # ------------------------------------------------------------------
    # Image Gen (local SDXL) pipeline warm-up
    # ------------------------------------------------------------------

    def _start_imagegen_local(self):
        if self._imagegen_local_loading or self._imagegen_local_ready:
            return
        if not SDXL_MODEL_PATH or not os.path.isfile(SDXL_MODEL_PATH):
            self._log_imagegen("ERROR: SDXL checkpoint not found — check Settings/config.", COLOR_STATUS_ERROR)
            self.imagegen_local_status.set_error()
            return

        self._imagegen_local_loading = True
        self.imagegen_local_status.set_starting()
        self.btn_imagegen_local_start.setEnabled(False)
        self._log_imagegen("Loading model into memory…")

        worker = _ImageGenLoadWorker(self)
        worker.finished.connect(self._on_imagegen_local_loaded)
        worker.error.connect(self._on_imagegen_local_load_error)
        worker.start()
        self._imagegen_load_worker = worker

    def _on_imagegen_local_loaded(self):
        self._imagegen_local_loading = False
        self._imagegen_load_worker = None
        if self._imagegen_stop_requested:
            # User clicked Stop/Kill All/closed the window while this load was
            # still in flight — the pipeline only just now finished loading
            # and grabbed the lock, so try_unload_pipeline() (which failed or
            # was skipped earlier) can actually succeed now. Land in a
            # stopped state instead of silently flipping back to "ready".
            self._imagegen_stop_requested = False
            imagegen_engine.try_unload_pipeline()
            self._imagegen_local_ready = False
            self.imagegen_local_status.set_stopped()
            self.imagegen_local_via_lbl.setText("txt2img + LoRA + TI + hires-fix")
            self.btn_imagegen_local_start.setEnabled(True)
            self._log_imagegen("Stopped (was still loading when Stop was requested).")
            return
        # The pipeline itself is loaded and usable via Open (ImageGenDialog
        # talks to imagegen_engine directly) regardless of whether the
        # SillyTavern-facing HTTP server below manages to bind its port, so
        # Stop/Open get enabled either way — only the status text/log
        # distinguish a bind failure from a real "Ready".
        self._imagegen_local_ready = True
        self.btn_imagegen_local_stop.setEnabled(True)
        self.btn_imagegen_local_open.setEnabled(True)
        try:
            imagegen_server.start()
        except OSError as e:
            self.imagegen_local_status.set_error()
            self.imagegen_local_via_lbl.setText("Pipeline ready — API server failed to start")
            self._log_imagegen(
                f"ERROR: pipeline loaded, but the Image Gen API server failed to bind "
                f"port {SDXL_API_PORT}: {e}", COLOR_STATUS_ERROR)
            return
        self.imagegen_local_status.set_running()
        self.imagegen_local_via_lbl.setText(f"Ready — http://127.0.0.1:{SDXL_API_PORT}")
        self._log_imagegen(f"Ready. API listening on http://127.0.0.1:{SDXL_API_PORT}")

    def _on_imagegen_local_load_error(self, message: str):
        self._imagegen_local_loading = False
        self._imagegen_stop_requested = False
        self.imagegen_local_status.set_error()
        self.btn_imagegen_local_start.setEnabled(True)
        self._log_imagegen(f"ERROR: {message}", COLOR_STATUS_ERROR)
        self._imagegen_load_worker = None

    def _stop_imagegen_local(self):
        if not self._imagegen_local_ready and not self._imagegen_local_loading:
            return
        if self._imagegen_local_loading:
            # The load worker may not have acquired the pipeline lock yet, so
            # try_unload_pipeline() could spuriously succeed on an empty cache
            # right now and let this function flip state to "stopped" — only
            # for the load to finish moments later and flip it back to
            # "ready". Defer the actual stop to the load-completion callback
            # instead, which is guaranteed to run after the lock is held.
            self._imagegen_stop_requested = True
            self._log_imagegen("Stop requested — finishing the in-progress load, then stopping.")
            return
        # Non-blocking: if a generation is in progress it holds the pipeline
        # lock, so this reports busy instead of freezing the GUI thread
        # waiting on it. Retry Stop once the generation finishes.
        if not imagegen_engine.try_unload_pipeline():
            self._log_imagegen("Can't stop while a generation is in progress — try again once it finishes.", COLOR_STATUS_ERROR)
            return
        imagegen_server.stop()
        self._imagegen_local_ready = False
        self._imagegen_local_loading = False
        self.imagegen_local_status.set_stopped()
        self.imagegen_local_via_lbl.setText("txt2img + LoRA + TI + hires-fix")
        self.btn_imagegen_local_start.setEnabled(True)
        self.btn_imagegen_local_stop.setEnabled(False)
        self.btn_imagegen_local_open.setEnabled(False)
        self._log_imagegen("Unloaded.")

    # ------------------------------------------------------------------
    # Global controls
    # ------------------------------------------------------------------

    def _kill_all(self):
        self._stop_kobold()
        self._stop_st()
        self._stop_imagegen_local()

    def _open_st(self):
        webbrowser.open(SILLYTAVERN_URL)

    # ------------------------------------------------------------------
    # CharGen
    # ------------------------------------------------------------------

    def _open_chargen(self):
        from chargen_dialog import CharGenDialog
        if self._chargen_dlg is None:
            self._chargen_dlg = CharGenDialog(KOBOLD_API_BASE, CHARGEN_OUTPUT_DIR, self)
        self._chargen_dlg.set_model_hint(self._current_model_key)
        self._chargen_dlg.set_api_model(self.api_card.current_model)
        self._chargen_dlg.auto_select_backend(self._api_ready, self._kobold_ready)
        self._chargen_dlg.show()
        self._chargen_dlg.raise_()
        self._chargen_dlg.activateWindow()

    def _open_imagegen_local(self):
        from imagegen_dialog import ImageGenDialog
        if self._imagegen_local_dlg is None:
            self._imagegen_local_dlg = ImageGenDialog(self)
        self._imagegen_local_dlg.show()
        self._imagegen_local_dlg.raise_()
        self._imagegen_local_dlg.activateWindow()

    # ------------------------------------------------------------------
    # API backend
    # ------------------------------------------------------------------

    def _activate_api(self):
        if self._api_ready:
            self._deactivate_api()
            return
        if self.api_card._worker and self.api_card._worker.isRunning():
            return
        self.api_card.btn_activate.setEnabled(False)
        self.api_card.status.set_text(COLOR_STATUS_STARTING, "Connecting…")
        w = _ApiTestWorker(self)
        w.success.connect(self._on_api_test_ok)
        w.error.connect(self._on_api_test_error)
        def _on_finished():
            self.api_card._worker = None
            self.api_card.btn_activate.setEnabled(True)
        w.finished.connect(_on_finished)
        self.api_card._worker = w
        w.start()

    def _deactivate_api(self):
        self._api_ready = False
        self.api_card.status.set_text(COLOR_STATUS_STOPPED, "Not activated")
        self.api_card.model_combo.setVisible(False)
        self.api_card.btn_activate.setText("Activate")
        self._log("[API] Deactivated.", COLOR_TEXT_MUTED)
        if self._chargen_dlg is not None:
            self._chargen_dlg.auto_select_backend(False, self._kobold_ready)
        self._update_tools()

    def _on_api_test_ok(self, msg: str, models: list):
        self._api_ready = True
        self.api_card.btn_activate.setText("Deactivate")
        self.api_card.status.set_text(COLOR_STATUS_RUNNING, msg)
        self._log(f"[API] {msg}", COLOR_STATUS_RUNNING)
        if models:
            self.api_card.populate_models(models)  # fires model_changed → _update_tools
        else:
            self._update_tools()

    def _on_api_test_error(self, msg: str):
        self.api_card.status.set_text(COLOR_STATUS_ERROR, msg)
        self._log(f"[API] Error: {msg}", COLOR_STATUS_ERROR)

    def _on_api_model_changed(self, model: str):
        self._log(f"[API] Active model: {model}", COLOR_TEXT_MUTED)
        if self._chargen_dlg is not None:
            self._chargen_dlg.set_api_model(model)
        self._update_tools()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _open_settings(self):
        from settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        dlg.exec()

    def _find_node(self) -> str | None:
        import shutil
        path = shutil.which("node")
        if path:
            return path
        for c in (r"C:\Program Files\nodejs\node.exe",
                  r"C:\Program Files (x86)\nodejs\node.exe"):
            if os.path.isfile(c):
                return c
        return None

    def closeEvent(self, event):
        if imagegen_engine.is_busy():
            reply = QMessageBox.question(
                self, "Image Gen is busy",
                "An image is still loading or generating. Closing now won't wait "
                "for it to finish and may leave it in an inconsistent state.\n\n"
                "Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self._chargen_dlg is not None:
            self._chargen_dlg.close()
        if self._imagegen_local_dlg is not None:
            self._imagegen_local_dlg.close()
        if self.api_card._worker and self.api_card._worker.isRunning():
            self.api_card._worker.terminate()
            self.api_card._worker.wait(2000)
        self._stop_kobold(wait=True)
        self._stop_st(wait=True)
        self._stop_imagegen_local()
        # Brief wait to let processes actually exit before the app quits
        if self._kobold_proc:
            self._kobold_proc.waitForFinished(2000)
        if self._st_proc:
            self._st_proc.waitForFinished(2000)
        event.accept()
