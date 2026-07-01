# settings_dialog.py — config.json editor

import json
import os

from PyQt6.QtCore    import Qt, QThread, pyqtSignal
from PyQt6.QtGui     import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QPushButton,
    QCheckBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QFrame,
)

from constants import (
    COLOR_BG, COLOR_PANEL, COLOR_PANEL_ALT, COLOR_BORDER, COLOR_BORDER_BRIGHT,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_ACCENT_DIM,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER,
    COLOR_STATUS_ERROR, COLOR_STATUS_RUNNING, COLOR_STATUS_STARTING,
    FONT_UI_FAMILY, FONT_UI_SIZE, FONT_LOG_FAMILY,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "config.json")
_ARROW_UP    = os.path.join(_HERE, "assets", "arrow_up.svg").replace("\\", "/")
_ARROW_DOWN  = os.path.join(_HERE, "assets", "arrow_down.svg").replace("\\", "/")

_STYLE = f"""
QDialog {{
    background: {COLOR_BG};
    font-family: {FONT_UI_FAMILY};
    font-size: {FONT_UI_SIZE}pt;
    color: {COLOR_TEXT};
}}
QWidget {{
    background: {COLOR_BG};
    font-family: {FONT_UI_FAMILY};
    font-size: {FONT_UI_SIZE}pt;
    color: {COLOR_TEXT};
}}
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    background: {COLOR_BG};
}}
QTabBar::tab {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_BORDER};
    padding: 5px 16px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    color: {COLOR_TEXT};
    background: {COLOR_BG};
    border-bottom-color: {COLOR_BG};
}}
QLineEdit {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 7px;
}}
QLineEdit:focus {{
    border-color: {COLOR_ACCENT_DIM};
}}
QLineEdit:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}
QSpinBox {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 20px 3px 6px;
}}
QSpinBox:focus {{
    border-color: {COLOR_ACCENT_DIM};
}}
QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid {COLOR_BORDER_BRIGHT};
    border-bottom: 1px solid {COLOR_BORDER};
    border-top-right-radius: 3px;
    background: {COLOR_BUTTON_BG};
}}
QSpinBox::up-button:hover {{ background: {COLOR_BUTTON_HOVER}; }}
QSpinBox::up-button:pressed {{ background: {COLOR_ACCENT_DIM}; }}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid {COLOR_BORDER_BRIGHT};
    border-bottom-right-radius: 3px;
    background: {COLOR_BUTTON_BG};
}}
QSpinBox::down-button:hover {{ background: {COLOR_BUTTON_HOVER}; }}
QSpinBox::down-button:pressed {{ background: {COLOR_ACCENT_DIM}; }}
QSpinBox::up-arrow {{
    image: url({_ARROW_UP});
    width: 8px;
    height: 6px;
}}
QSpinBox::down-arrow {{
    image: url({_ARROW_DOWN});
    width: 8px;
    height: 6px;
}}
QPushButton {{
    background: {COLOR_BUTTON_BG};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 12px;
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
}}
QPushButton#accent:hover:enabled {{
    background: {COLOR_ACCENT};
}}
QCheckBox {{
    color: {COLOR_TEXT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 3px;
    background: {COLOR_PANEL};
}}
QCheckBox::indicator:checked {{
    background: {COLOR_ACCENT_DIM};
    border-color: {COLOR_ACCENT};
}}
QLabel {{
    color: {COLOR_TEXT};
    background: transparent;
}}
QTableWidget {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER};
    gridline-color: {COLOR_BORDER};
    selection-background-color: {COLOR_ACCENT_DIM};
    outline: none;
}}
QTableWidget QHeaderView::section {{
    background: {COLOR_PANEL_ALT};
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {COLOR_BORDER};
    padding: 4px 8px;
    font-size: 8pt;
}}
QTableWidget::item:selected {{
    background: {COLOR_ACCENT_DIM};
    color: {COLOR_TEXT};
}}
"""


def _lbl(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
    return l


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {COLOR_BORDER}; border: none;")
    return f


def _section(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color: {COLOR_ACCENT}; font-size: 8pt; font-weight: bold; padding-top: 6px;"
    )
    return l


# ---------------------------------------------------------------------------
# Live API test worker (uses field values, not saved config)
# ---------------------------------------------------------------------------

class _SettingsApiTestWorker(QThread):
    result = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, base_url: str, api_key: str, model: str, parent=None):
        super().__init__(parent)
        self._base_url = base_url.rstrip("/")
        self._api_key  = api_key
        self._model    = model

    def run(self):
        import urllib.request
        import urllib.error

        headers = {"User-Agent": "python-requests/2.31.0"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models", headers=headers
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                n = len(data.get("data", []))
                self.result.emit(True, f"Connected — {n} models available")
                return
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.result.emit(False, "Invalid API key (401)")
                return
        except urllib.error.URLError as e:
            self.result.emit(False, f"Cannot reach endpoint ({e.reason})")
            return
        except Exception:
            pass

        payload = json.dumps({
            **({"model": self._model} if self._model else {}),
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1, "stream": False,
        }).encode()
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/chat/completions",
                data=payload,
                headers={**headers, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as _:
                self.result.emit(True, "Connected")
        except urllib.error.HTTPError as e:
            self.result.emit(False, f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            self.result.emit(False, f"Cannot reach endpoint ({e.reason})")
        except Exception as e:
            self.result.emit(False, str(e))


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(620, 520)
        self.resize(660, 560)
        self.setStyleSheet(_STYLE)

        self._cfg    = {}
        self._worker = None

        self._load_config()
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------
    # Config I/O
    # ------------------------------------------------------------------

    def _load_config(self):
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                self._cfg = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Settings", f"Could not read config.json:\n{e}")
            self._cfg = {}

    def _save_config(self) -> bool:
        self._collect()
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Settings", f"Could not save config.json:\n{e}")
            return False

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        root.addWidget(self._tabs, 1)

        self._tabs.addTab(self._tab_kobold(),    "  KoboldCpp  ")
        self._tabs.addTab(self._tab_st(),        "  SillyTavern  ")
        self._tabs.addTab(self._tab_api(),       "  API  ")
        self._tabs.addTab(self._tab_models(),    "  Models  ")
        self._tabs.addTab(self._tab_app(),       "  App  ")

        # Footer
        footer = QWidget()
        footer.setStyleSheet(f"background: {COLOR_PANEL}; border-top: 1px solid {COLOR_BORDER};")
        foot_layout = QHBoxLayout(footer)
        foot_layout.setContentsMargins(14, 8, 14, 8)
        foot_layout.setSpacing(8)

        self._lbl_restart = QLabel("Changes take effect on next launch.")
        self._lbl_restart.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        foot_layout.addWidget(self._lbl_restart, 1)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(28)
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Save & Close")
        btn_ok.setObjectName("accent")
        btn_ok.setFixedHeight(28)
        btn_ok.clicked.connect(self._on_save)

        foot_layout.addWidget(btn_cancel)
        foot_layout.addWidget(btn_ok)
        root.addWidget(footer)

    # ── KoboldCpp tab ─────────────────────────────────────────────────

    def _tab_kobold(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(16, 14, 16, 14)
        g.setVerticalSpacing(8)
        g.setHorizontalSpacing(10)
        g.setColumnStretch(1, 1)

        row = 0
        g.addWidget(_lbl("Executable path"), row, 0)
        self._kob_exe = QLineEdit()
        g.addWidget(self._kob_exe, row, 1)
        btn = QPushButton("Browse…")
        btn.setFixedWidth(72)
        btn.clicked.connect(lambda: self._browse_file(self._kob_exe, "KoboldCpp (*.exe)"))
        g.addWidget(btn, row, 2)

        row += 1
        g.addWidget(_divider(), row, 0, 1, 3)

        row += 1
        g.addWidget(_section("Network"), row, 0, 1, 3)

        row += 1
        g.addWidget(_lbl("Host"), row, 0)
        self._kob_host = QLineEdit()
        self._kob_host.setFixedWidth(140)
        g.addWidget(self._kob_host, row, 1, Qt.AlignmentFlag.AlignLeft)

        row += 1
        g.addWidget(_lbl("Port"), row, 0)
        self._kob_port = QSpinBox()
        self._kob_port.setRange(1024, 65535)
        self._kob_port.setFixedWidth(100)
        g.addWidget(self._kob_port, row, 1, Qt.AlignmentFlag.AlignLeft)

        row += 1
        g.addWidget(_divider(), row, 0, 1, 3)

        row += 1
        g.addWidget(_section("Performance"), row, 0, 1, 3)

        row += 1
        g.addWidget(_lbl("GPU layers"), row, 0)
        self._kob_gpu = QSpinBox()
        self._kob_gpu.setRange(0, 200)
        self._kob_gpu.setFixedWidth(80)
        g.addWidget(self._kob_gpu, row, 1, Qt.AlignmentFlag.AlignLeft)

        row += 1
        g.addWidget(_lbl("Context size"), row, 0)
        self._kob_ctx = QSpinBox()
        self._kob_ctx.setRange(512, 131072)
        self._kob_ctx.setSingleStep(512)
        self._kob_ctx.setFixedWidth(104)
        g.addWidget(self._kob_ctx, row, 1, Qt.AlignmentFlag.AlignLeft)

        row += 1
        g.addWidget(_divider(), row, 0, 1, 3)

        row += 1
        g.addWidget(_section("Options"), row, 0, 1, 3)

        row += 1
        self._kob_cuda   = QCheckBox("Use CUDA (NVIDIA GPU)")
        self._kob_vulkan = QCheckBox("Use Vulkan (AMD / Intel GPU)")
        self._kob_flash  = QCheckBox("Flash Attention")
        self._kob_quiet  = QCheckBox("Quiet mode (suppress console output)")
        for chk in (self._kob_cuda, self._kob_vulkan, self._kob_flash, self._kob_quiet):
            g.addWidget(chk, row, 0, 1, 3)
            row += 1

        # Mutually exclusive — build_kobold_args() only ever passes one of --usecublas /
        # --usevulkan (CUDA wins if both are set), so keep the UI honest about that.
        self._kob_cuda.toggled.connect(
            lambda checked: checked and self._kob_vulkan.setChecked(False)
        )
        self._kob_vulkan.toggled.connect(
            lambda checked: checked and self._kob_cuda.setChecked(False)
        )

        g.setRowStretch(row, 1)
        return w

    # ── SillyTavern tab ───────────────────────────────────────────────

    def _tab_st(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(16, 14, 16, 14)
        g.setVerticalSpacing(8)
        g.setHorizontalSpacing(10)
        g.setColumnStretch(1, 1)

        g.addWidget(_lbl("SillyTavern directory"), 0, 0)
        self._st_dir = QLineEdit()
        g.addWidget(self._st_dir, 0, 1)
        btn = QPushButton("Browse…")
        btn.setFixedWidth(72)
        btn.clicked.connect(lambda: self._browse_dir(self._st_dir))
        g.addWidget(btn, 0, 2)

        g.addWidget(_lbl("Port"), 1, 0)
        self._st_port = QSpinBox()
        self._st_port.setRange(1024, 65535)
        self._st_port.setFixedWidth(100)
        g.addWidget(self._st_port, 1, 1, Qt.AlignmentFlag.AlignLeft)

        g.setRowStretch(2, 1)
        return w

    # ── API tab ───────────────────────────────────────────────────────

    def _tab_api(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(16, 14, 16, 14)
        g.setVerticalSpacing(8)
        g.setHorizontalSpacing(10)
        g.setColumnStretch(1, 1)

        note = QLabel(
            "Any OpenAI-compatible endpoint — OpenRouter, Groq, LM Studio, Ollama, etc."
        )
        note.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        note.setWordWrap(True)
        g.addWidget(note, 0, 0, 1, 3)

        g.addWidget(_lbl("Base URL"), 1, 0)
        self._api_url = QLineEdit()
        self._api_url.setPlaceholderText("https://api.groq.com/openai")
        g.addWidget(self._api_url, 1, 1, 1, 2)

        g.addWidget(_lbl("API key"), 2, 0)
        key_row = QHBoxLayout()
        key_row.setSpacing(6)
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("sk-… or gsk_…")
        key_row.addWidget(self._api_key)
        self._btn_show_key = QPushButton("Show")
        self._btn_show_key.setFixedWidth(52)
        self._btn_show_key.setCheckable(True)
        self._btn_show_key.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._btn_show_key)
        g.addLayout(key_row, 2, 1, 1, 2)

        g.addWidget(_lbl("Default model"), 3, 0)
        self._api_model = QLineEdit()
        self._api_model.setPlaceholderText("llama-3.3-70b-versatile")
        g.addWidget(self._api_model, 3, 1, 1, 2)

        g.addWidget(_divider(), 4, 0, 1, 3)

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self._btn_api_test = QPushButton("Test Connection")
        self._btn_api_test.setFixedWidth(130)
        self._btn_api_test.clicked.connect(self._test_api)
        test_row.addWidget(self._btn_api_test)
        self._lbl_api_status = QLabel("—")
        self._lbl_api_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        test_row.addWidget(self._lbl_api_status)
        test_row.addStretch()
        g.addLayout(test_row, 5, 0, 1, 3)

        g.setRowStretch(6, 1)
        return w

    # ── Models tab ────────────────────────────────────────────────────

    def _tab_models(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        hint = QLabel(
            "These are the models KoboldCpp can load. "
            "Key is a short internal identifier (no spaces). "
            "The first entry is the default."
        )
        hint.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self._model_table = QTableWidget(0, 3)
        self._model_table.setHorizontalHeaderLabels(["Name", "Key", "Path"])
        self._model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._model_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._model_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._model_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._model_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked |
                                          QTableWidget.EditTrigger.SelectedClicked)
        self._model_table.verticalHeader().setDefaultSectionSize(24)
        self._model_table.setFont(QFont(FONT_LOG_FAMILY, 8))
        v.addWidget(self._model_table, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_add = QPushButton("Add row")
        btn_add.setFixedHeight(26)
        btn_add.clicked.connect(self._model_add)

        btn_remove = QPushButton("Remove selected")
        btn_remove.setFixedHeight(26)
        btn_remove.clicked.connect(self._model_remove)

        btn_browse = QPushButton("Browse path…")
        btn_browse.setFixedHeight(26)
        btn_browse.clicked.connect(self._model_browse_path)

        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_browse)
        btn_row.addStretch()
        v.addLayout(btn_row)

        return w

    # ── App tab ───────────────────────────────────────────────────────

    def _tab_app(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(16, 14, 16, 14)
        g.setVerticalSpacing(8)
        g.setHorizontalSpacing(10)
        g.setColumnStretch(1, 1)

        g.addWidget(_section("Character Card Generator"), 0, 0, 1, 3)

        g.addWidget(_lbl("Output directory"), 1, 0)
        self._cg_dir = QLineEdit()
        g.addWidget(self._cg_dir, 1, 1)
        btn = QPushButton("Browse…")
        btn.setFixedWidth(72)
        btn.clicked.connect(lambda: self._browse_dir(self._cg_dir))
        g.addWidget(btn, 1, 2)

        g.setRowStretch(2, 1)
        return w

    # ------------------------------------------------------------------
    # Populate / collect
    # ------------------------------------------------------------------

    def _populate(self):
        kob = self._cfg.get("koboldcpp", {})
        self._kob_exe.setText(kob.get("exe", ""))
        self._kob_host.setText(kob.get("host", "127.0.0.1"))
        self._kob_port.setValue(int(kob.get("port", 5001)))
        self._kob_gpu.setValue(int(kob.get("gpu_layers", 40)))
        self._kob_ctx.setValue(int(kob.get("context_size", 6144)))
        self._kob_cuda.setChecked(bool(kob.get("use_cuda", True)))
        self._kob_vulkan.setChecked(bool(kob.get("use_vulkan", False)))
        self._kob_flash.setChecked(bool(kob.get("flash_attention", True)))
        self._kob_quiet.setChecked(bool(kob.get("quiet", True)))

        st = self._cfg.get("sillytavern", {})
        self._st_dir.setText(st.get("dir", ""))
        self._st_port.setValue(int(st.get("port", 8000)))

        api = self._cfg.get("api", {})
        self._api_url.setText(api.get("base_url", ""))
        self._api_key.setText(api.get("api_key", ""))
        self._api_model.setText(api.get("model", ""))

        self._model_table.setRowCount(0)
        for m in self._cfg.get("models", []):
            self._model_table_add_row(m.get("name", ""), m.get("key", ""), m.get("path", ""))

        cg = self._cfg.get("chargen", {})
        self._cg_dir.setText(cg.get("output_dir", ""))

    def _collect(self):
        kob = self._cfg.setdefault("koboldcpp", {})
        kob["exe"]            = self._kob_exe.text().strip()
        kob["host"]           = self._kob_host.text().strip() or "127.0.0.1"
        kob["port"]           = self._kob_port.value()
        kob["gpu_layers"]     = self._kob_gpu.value()
        kob["context_size"]   = self._kob_ctx.value()
        kob["use_cuda"]       = self._kob_cuda.isChecked()
        kob["use_vulkan"]     = self._kob_vulkan.isChecked()
        kob["flash_attention"]= self._kob_flash.isChecked()
        kob["quiet"]          = self._kob_quiet.isChecked()

        st = self._cfg.setdefault("sillytavern", {})
        st["dir"]  = self._st_dir.text().strip()
        st["port"] = self._st_port.value()

        api = self._cfg.setdefault("api", {})
        api["base_url"] = self._api_url.text().strip().rstrip("/")
        api["api_key"]  = self._api_key.text().strip()
        api["model"]    = self._api_model.text().strip()

        models = []
        for r in range(self._model_table.rowCount()):
            name = (self._model_table.item(r, 0) or QTableWidgetItem("")).text().strip()
            key  = (self._model_table.item(r, 1) or QTableWidgetItem("")).text().strip()
            path = (self._model_table.item(r, 2) or QTableWidgetItem("")).text().strip()
            if name or key or path:
                models.append({"name": name, "key": key, "path": path})
        self._cfg["models"] = models

        cg = self._cfg.setdefault("chargen", {})
        cg["output_dir"] = self._cg_dir.text().strip()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_save(self):
        if self._save_config():
            self.accept()

    def _toggle_key_visibility(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self._api_key.setEchoMode(mode)
        self._btn_show_key.setText("Hide" if checked else "Show")

    def _test_api(self):
        url = self._api_url.text().strip()
        if not url:
            self._lbl_api_status.setText("Enter a base URL first.")
            self._lbl_api_status.setStyleSheet(f"color: {COLOR_STATUS_ERROR}; font-size: 8pt;")
            return
        if self._worker and self._worker.isRunning():
            return
        self._btn_api_test.setEnabled(False)
        self._lbl_api_status.setText("Connecting…")
        self._lbl_api_status.setStyleSheet(f"color: {COLOR_STATUS_STARTING}; font-size: 8pt;")
        self._worker = _SettingsApiTestWorker(
            url,
            self._api_key.text().strip(),
            self._api_model.text().strip(),
            self,
        )
        self._worker.result.connect(self._on_test_result)
        self._worker.finished.connect(self._on_test_finished)
        self._worker.start()

    def _on_test_finished(self):
        self._btn_api_test.setEnabled(True)
        self._worker = None

    def _on_test_result(self, ok: bool, msg: str):
        color = COLOR_STATUS_RUNNING if ok else COLOR_STATUS_ERROR
        self._lbl_api_status.setText(msg)
        self._lbl_api_status.setStyleSheet(f"color: {color}; font-size: 8pt;")

    # -- Model table helpers -------------------------------------------

    def _model_table_add_row(self, name: str = "", key: str = "", path: str = ""):
        r = self._model_table.rowCount()
        self._model_table.insertRow(r)
        self._model_table.setItem(r, 0, QTableWidgetItem(name))
        self._model_table.setItem(r, 1, QTableWidgetItem(key))
        self._model_table.setItem(r, 2, QTableWidgetItem(path))

    def _model_add(self):
        self._model_table_add_row()
        r = self._model_table.rowCount() - 1
        self._model_table.selectRow(r)
        self._model_table.editItem(self._model_table.item(r, 0))

    def _model_remove(self):
        rows = sorted({i.row() for i in self._model_table.selectedItems()}, reverse=True)
        for r in rows:
            self._model_table.removeRow(r)

    def _model_browse_path(self):
        rows = list({i.row() for i in self._model_table.selectedItems()})
        if not rows:
            QMessageBox.information(self, "Models", "Select a row first.")
            return
        r = rows[0]
        current = (self._model_table.item(r, 2) or QTableWidgetItem("")).text()
        start = os.path.dirname(current) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select model file", start,
            "GGUF models (*.gguf);;All files (*)"
        )
        if path:
            self._model_table.setItem(r, 2, QTableWidgetItem(path))

    # -- Browse helpers ------------------------------------------------

    def _browse_file(self, field: QLineEdit, filter_str: str):
        start = os.path.dirname(field.text()) if field.text() else ""
        path, _ = QFileDialog.getOpenFileName(self, "Select file", start, filter_str)
        if path:
            field.setText(path)

    def _browse_dir(self, field: QLineEdit):
        start = field.text() if os.path.isdir(field.text()) else ""
        path = QFileDialog.getExistingDirectory(self, "Select folder", start)
        if path:
            field.setText(path)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        event.accept()
