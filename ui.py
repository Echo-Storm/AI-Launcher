# ui.py — AI Writing Tools Launcher

import os
import webbrowser
import logging

from PyQt6.QtCore    import Qt, QProcess
from PyQt6.QtGui     import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFrame,
    QSplitter,
)

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


# ---------------------------------------------------------------------------
# Service card — one card per process
# ---------------------------------------------------------------------------

class ServiceCard(QFrame):
    def __init__(self, title: str, has_open_btn: bool = False,
                 has_chargen_btn: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("ServiceCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(8)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont(FONT_UI_FAMILY, 10, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {COLOR_ACCENT};")
        outer.addWidget(title_lbl)

        # Subtitle — shows loaded model name (hidden when no model loaded)
        self.lbl_subtitle = QLabel("")
        self.lbl_subtitle.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE - 1))
        self.lbl_subtitle.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        self.lbl_subtitle.setVisible(False)
        outer.addWidget(self.lbl_subtitle)

        # Status badge
        self.status = StatusBadge()
        outer.addWidget(self.status)

        # Buttons
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

        if has_open_btn:
            self.btn_open = QPushButton("Open in Browser")
            self.btn_open.setFixedHeight(26)
            self.btn_open.setEnabled(False)
            self.btn_open.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
            btn_row.addWidget(self.btn_open)
        else:
            self.btn_open = None

        if has_chargen_btn:
            self.btn_chargen = QPushButton("Card Generator")
            self.btn_chargen.setFixedHeight(26)
            self.btn_chargen.setEnabled(True)
            self.btn_chargen.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
            btn_row.addWidget(self.btn_chargen)
        else:
            self.btn_chargen = None

        btn_row.addStretch()
        outer.addLayout(btn_row)


# ---------------------------------------------------------------------------
# Main window
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
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(580, 500)
        self.resize(660, 580)
        self.setStyleSheet(STYLESHEET)

        self._kobold_proc           = None
        self._st_proc               = None
        self._kobold_ready          = False
        self._st_ready              = False
        self._kobold_stopping       = False
        self._st_stopping           = False
        self._st_pending_autostart  = False
        self._current_model_key     = None
        self._pending_chargen_open  = False
        self._chargen_dlg           = None

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
        hdr_title.setStyleSheet(f"color: {COLOR_TEXT}; font-size: 11pt; font-weight: bold; background: transparent;")

        hdr_ver = QLabel(f"v{APP_VERSION}")
        hdr_ver.setObjectName("version")
        hdr_ver.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt; background: transparent;")

        hdr_layout.addWidget(hdr_title)
        hdr_layout.addStretch()
        hdr_layout.addWidget(hdr_ver)
        header_row.setFixedHeight(40)
        vbox.addWidget(header_row)

        # Accent divider under header
        _div = QFrame()
        _div.setFixedHeight(2)
        _div.setStyleSheet(f"background: {COLOR_ACCENT_DIM}; border: none;")
        vbox.addWidget(_div)

        # Main content area
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        # Splitter: service cards (top) | log (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # Service cards pane
        cards_widget = QWidget()
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(8)

        self.kobold_card = ServiceCard(
            "KoboldCpp  ·  Model Backend",
            has_chargen_btn=True,
        )
        self.st_card = ServiceCard("SillyTavern  ·  Writing Interface", has_open_btn=True)

        cards_layout.addWidget(self.kobold_card)
        cards_layout.addWidget(self.st_card)

        # Global controls row
        global_row = QHBoxLayout()
        global_row.setSpacing(8)
        self.btn_start_all = QPushButton("Start All")
        self.btn_start_all.setObjectName("accent")
        self.btn_start_all.setFixedHeight(28)
        self.btn_stop_all  = QPushButton("Stop All")
        self.btn_stop_all.setFixedHeight(28)
        for b in (self.btn_start_all, self.btn_stop_all):
            b.setFont(QFont(FONT_UI_FAMILY, FONT_UI_SIZE))
        global_row.addWidget(self.btn_start_all)
        global_row.addWidget(self.btn_stop_all)
        global_row.addStretch()
        cards_layout.addLayout(global_row)

        hint = QLabel(
            "KoboldCpp loads a large model on first start — this takes 1-2 minutes. "
            "Use Start All to launch both services; SillyTavern will wait for KoboldCpp to be ready."
        )
        hint.setWordWrap(True)
        hint.setFont(QFont(FONT_UI_FAMILY, 8))
        hint.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; padding-top: 4px;")
        cards_layout.addWidget(hint)
        cards_layout.addStretch()

        splitter.addWidget(cards_widget)

        # Log pane
        log_pane = QWidget()
        log_layout = QVBoxLayout(log_pane)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)

        log_lbl = QLabel("Output")
        log_lbl.setFont(QFont(FONT_UI_FAMILY, 8))
        log_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        log_layout.addWidget(log_lbl)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont(FONT_LOG_FAMILY, FONT_LOG_SIZE))
        log_layout.addWidget(self.log)

        splitter.addWidget(log_pane)
        splitter.setSizes([280, 200])

        content_layout.addWidget(splitter)
        vbox.addWidget(content)

        # Wire up signals
        self.kobold_card.btn_start.clicked.connect(self._start_kobold_writing)
        self.kobold_card.btn_stop.clicked.connect(self._stop_kobold)
        self.kobold_card.btn_chargen.clicked.connect(self._click_chargen)
        self.st_card.btn_start.clicked.connect(self._start_st)
        self.st_card.btn_stop.clicked.connect(self._stop_st)
        self.st_card.btn_open.clicked.connect(self._open_st)
        self.btn_start_all.clicked.connect(self._start_all)
        self.btn_stop_all.clicked.connect(self._stop_all)

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

    # ------------------------------------------------------------------
    # KoboldCpp process
    # ------------------------------------------------------------------

    def _start_kobold_writing(self):
        self._start_kobold("cydonia")

    def _start_kobold(self, model_key: str):
        if self._kobold_proc and self._kobold_proc.state() != QProcess.ProcessState.NotRunning:
            return

        model = next((m for m in MODELS if m.get("key") == model_key), MODELS[0] if MODELS else None)
        if not model:
            self._log("[KoboldCpp] ERROR: No models configured in config.json.", COLOR_STATUS_ERROR)
            self.kobold_card.status.set_error()
            self._st_pending_autostart = False
            self._pending_chargen_open = False
            return

        model_path = model["path"]
        model_name = model["name"]

        if not os.path.isfile(model_path):
            self._log_kobold(f"ERROR: Model file not found:\n  {model_path}")
            self.kobold_card.status.set_error()
            self._st_pending_autostart = False
            self._pending_chargen_open = False
            return

        self._current_model_key = model_key
        self._kobold_ready = False
        self.kobold_card.status.set_starting()
        self.kobold_card.lbl_subtitle.setText(f"Loading  {model_name}…")
        self.kobold_card.lbl_subtitle.setVisible(True)
        self.kobold_card.btn_start.setEnabled(False)
        self.kobold_card.btn_stop.setEnabled(True)
        self.kobold_card.btn_chargen.setEnabled(False)
        self.kobold_card.btn_chargen.setToolTip("")
        self._log_kobold(f"Starting with model: {model_name}")

        proc = QProcess(self)
        proc.setProgram(KOBOLD_EXE)
        proc.setArguments(build_kobold_args(model_path))
        proc.readyReadStandardOutput.connect(self._on_kobold_stdout)
        proc.readyReadStandardError.connect(self._on_kobold_stderr)
        proc.finished.connect(self._on_kobold_finished)
        proc.start()
        self._kobold_proc = proc

    def _stop_kobold(self):
        if self._kobold_proc and self._kobold_proc.state() != QProcess.ProcessState.NotRunning:
            self._kobold_stopping = True
            pid = self._kobold_proc.processId()
            if pid:
                import subprocess
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
            self._kobold_proc.kill()
            self._kobold_proc.waitForFinished(3000)
        self._kobold_ready = False

    def _on_kobold_stdout(self):
        data = self._kobold_proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._log_kobold(data)
        self._check_kobold_ready(data)

    def _on_kobold_stderr(self):
        data = self._kobold_proc.readAllStandardError().data().decode("utf-8", errors="replace")
        self._log_kobold(data)
        self._check_kobold_ready(data)

    def _check_kobold_ready(self, text: str):
        if self._kobold_ready:
            return
        lower = text.lower()
        if any(s in lower for s in KOBOLD_READY_STRINGS):
            self._kobold_ready = True
            self.kobold_card.status.set_running()

            model = next((m for m in MODELS if m.get("key") == self._current_model_key), None)
            model_name = model["name"] if model else (self._current_model_key or "Unknown")
            self.kobold_card.lbl_subtitle.setText(model_name)
            self._log_kobold(f"Ready  —  {model_name}")

            self.kobold_card.btn_chargen.setEnabled(True)
            self.kobold_card.btn_chargen.setToolTip("")

            if self._pending_chargen_open:
                self._pending_chargen_open = False
                self._open_chargen()

            if self._st_pending_autostart:
                self._st_pending_autostart = False
                self._start_st()

    def _on_kobold_finished(self, exit_code: int, exit_status):
        self._kobold_ready = False
        self._st_pending_autostart = False
        self._pending_chargen_open = False
        self._current_model_key = None
        if self._kobold_stopping or exit_code == 0:
            self.kobold_card.status.set_stopped()
        else:
            self.kobold_card.status.set_error()
        self._kobold_stopping = False
        self.kobold_card.lbl_subtitle.setVisible(False)
        self.kobold_card.btn_start.setEnabled(True)
        self.kobold_card.btn_stop.setEnabled(False)
        self.kobold_card.btn_chargen.setEnabled(True)
        self.kobold_card.btn_chargen.setToolTip("")
        self._log_kobold(f"Exited (code {exit_code})")
        self._kobold_proc = None

    # ------------------------------------------------------------------
    # SillyTavern process
    # ------------------------------------------------------------------

    def _start_st(self):
        if self._st_proc and self._st_proc.state() != QProcess.ProcessState.NotRunning:
            return

        self._st_ready = False
        self.st_card.status.set_starting()
        self.st_card.btn_start.setEnabled(False)
        self.st_card.btn_stop.setEnabled(True)
        if self.st_card.btn_open:
            self.st_card.btn_open.setEnabled(False)
        self._log_st("Starting…")

        node_exe = self._find_node()
        if not node_exe:
            self._log("ERROR: node.exe not found on PATH.", COLOR_STATUS_ERROR)
            self.st_card.status.set_error()
            self.st_card.btn_start.setEnabled(True)
            self.st_card.btn_stop.setEnabled(False)
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

    def _stop_st(self):
        if self._st_proc and self._st_proc.state() != QProcess.ProcessState.NotRunning:
            self._st_stopping = True
            pid = self._st_proc.processId()
            if pid:
                import subprocess
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
            self._st_proc.kill()
            self._st_proc.waitForFinished(3000)
        self._st_ready = False

    def _on_st_stdout(self):
        data = self._st_proc.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._log_st(data)
        self._check_st_ready(data)

    def _on_st_stderr(self):
        data = self._st_proc.readAllStandardError().data().decode("utf-8", errors="replace")
        self._log_st(data)
        self._check_st_ready(data)

    def _check_st_ready(self, text: str):
        if self._st_ready:
            return
        lower = text.lower()
        if any(s in lower for s in SILLYTAVERN_READY_STRINGS):
            self._st_ready = True
            self.st_card.status.set_running()
            if self.st_card.btn_open:
                self.st_card.btn_open.setEnabled(True)
            self._log_st("Ready.")

    def _on_st_finished(self, exit_code: int, exit_status):
        self._st_ready = False
        if self._st_stopping or exit_code == 0:
            self.st_card.status.set_stopped()
        else:
            self.st_card.status.set_error()
        self._st_stopping = False
        self.st_card.btn_start.setEnabled(True)
        self.st_card.btn_stop.setEnabled(False)
        if self.st_card.btn_open:
            self.st_card.btn_open.setEnabled(False)
        self._log_st(f"Exited (code {exit_code})")
        self._st_proc = None

    # ------------------------------------------------------------------
    # Global controls
    # ------------------------------------------------------------------

    def _start_all(self):
        if self._kobold_ready:
            self._start_st()
        else:
            self._st_pending_autostart = True
            self._start_kobold("cydonia")

    def _stop_all(self):
        self._stop_kobold()
        self._stop_st()

    def _open_st(self):
        webbrowser.open(SILLYTAVERN_URL)

    def _click_chargen(self):
        if self._kobold_ready:
            self._open_chargen()
        elif not (self._kobold_proc and self._kobold_proc.state() != QProcess.ProcessState.NotRunning):
            self._pending_chargen_open = True
            self._start_kobold("chargen")

    def _open_chargen(self):
        from chargen_dialog import CharGenDialog
        if self._chargen_dlg is None:
            self._chargen_dlg = CharGenDialog(KOBOLD_API_BASE, CHARGEN_OUTPUT_DIR, self)
        self._chargen_dlg.set_model_hint(self._current_model_key)
        self._chargen_dlg.show()
        self._chargen_dlg.raise_()
        self._chargen_dlg.activateWindow()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_node(self) -> str | None:
        import shutil
        path = shutil.which("node")
        if path:
            return path
        candidates = [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def closeEvent(self, event):
        if self._chargen_dlg is not None:
            self._chargen_dlg.close()
        self._stop_kobold()
        self._stop_st()
        event.accept()
