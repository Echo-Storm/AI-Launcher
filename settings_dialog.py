# settings_dialog.py — config.json editor

import json
import os

from PyQt6.QtCore    import Qt, QThread, pyqtSignal
from PyQt6.QtGui     import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QWidget, QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QFrame, QScrollArea,
)

from constants import (
    COLOR_BG, COLOR_PANEL, COLOR_PANEL_ALT, COLOR_BORDER, COLOR_BORDER_BRIGHT,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_ACCENT_DIM,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER, COLOR_HEADER_BAR,
    COLOR_STATUS_ERROR, COLOR_STATUS_RUNNING, COLOR_STATUS_STARTING,
    FONT_UI_FAMILY, FONT_UI_SIZE, FONT_LOG_FAMILY,
    SDXL_GENERATION_DEFAULTS, SDXL_SCHEDULER_CHOICES,
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
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {COLOR_BG};
    border: none;
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
QAbstractSpinBox {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 20px 3px 6px;
}}
QAbstractSpinBox:focus {{
    border-color: {COLOR_ACCENT_DIM};
}}
QAbstractSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid {COLOR_BORDER_BRIGHT};
    border-bottom: 1px solid {COLOR_BORDER};
    border-top-right-radius: 3px;
    background: {COLOR_BUTTON_BG};
}}
QAbstractSpinBox::up-button:hover {{ background: {COLOR_BUTTON_HOVER}; }}
QAbstractSpinBox::up-button:pressed {{ background: {COLOR_ACCENT_DIM}; }}
QAbstractSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid {COLOR_BORDER_BRIGHT};
    border-bottom-right-radius: 3px;
    background: {COLOR_BUTTON_BG};
}}
QAbstractSpinBox::down-button:hover {{ background: {COLOR_BUTTON_HOVER}; }}
QAbstractSpinBox::down-button:pressed {{ background: {COLOR_ACCENT_DIM}; }}
QAbstractSpinBox::up-arrow {{
    image: url({_ARROW_UP});
    width: 8px;
    height: 6px;
}}
QAbstractSpinBox::down-arrow {{
    image: url({_ARROW_DOWN});
    width: 8px;
    height: 6px;
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
QTableWidget#kvTable QHeaderView::section {{
    background: {COLOR_HEADER_BAR};
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-bottom: 2px solid {COLOR_BORDER_BRIGHT};
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
# Generic add/remove/browse-path table helpers — used by the LoRA and
# Textual Inversion tables (both are "list of path + one other field").
# ---------------------------------------------------------------------------

def _table_add_row(table: QTableWidget, *values: str):
    r = table.rowCount()
    table.insertRow(r)
    for c, v in enumerate(values):
        table.setItem(r, c, QTableWidgetItem(v))


def _table_remove_selected(table: QTableWidget):
    rows = sorted({i.row() for i in table.selectedItems()}, reverse=True)
    for r in rows:
        table.removeRow(r)


def _table_browse_path(table: QTableWidget, column: int, parent, filter_str: str):
    rows = sorted({i.row() for i in table.selectedItems()})
    if not rows:
        QMessageBox.information(parent, "Browse", "Select a row first.")
        return
    if len(rows) > 1:
        QMessageBox.information(
            parent, "Browse",
            "Browse sets the path for one row at a time — select a single row first."
        )
        return
    r = rows[0]
    current = (table.item(r, column) or QTableWidgetItem("")).text()
    start = os.path.dirname(current) if current else ""
    path, _ = QFileDialog.getOpenFileName(parent, "Select file", start, filter_str)
    if path:
        table.setItem(r, column, QTableWidgetItem(path))


def _table_set_checkbox(table: QTableWidget, row: int, column: int, checked: bool = True):
    """Puts a centered QCheckBox in a cell — QTableWidgetItem has no native
    checkbox rendering worth using, so a real widget via setCellWidget is the
    standard Qt approach for a per-row enable/disable toggle."""
    chk = QCheckBox()
    chk.setChecked(checked)
    container = QWidget()
    lay = QHBoxLayout(container)
    lay.addWidget(chk)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.setContentsMargins(0, 0, 0, 0)
    table.setCellWidget(row, column, container)


def _table_checkbox_checked(table: QTableWidget, row: int, column: int) -> bool:
    """Defaults to True (enabled) if the cell has no checkbox widget yet —
    keeps a freshly-inserted row (before _table_set_checkbox runs) from
    reading as disabled."""
    container = table.cellWidget(row, column)
    if container is None:
        return True
    chk = container.findChild(QCheckBox)
    return chk.isChecked() if chk else True


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
        self.setMinimumSize(620, 480)
        self.resize(680, 680)
        self.setStyleSheet(_STYLE)

        self._cfg    = {}
        self._worker = None
        self._config_load_failed = False

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
            # Don't let Save persist this blank stand-in over the user's real
            # config — constants.py treats an unreadable config.json as fatal
            # for the same reason; blanking-and-allowing-save here would
            # silently clobber real settings the moment the app is re-run.
            self._config_load_failed = True

    def _save_config(self) -> bool:
        if self._config_load_failed:
            QMessageBox.critical(
                self, "Settings",
                "config.json couldn't be read when this dialog opened, so saving now "
                "would overwrite it with blank defaults. Fix or restore config.json "
                "first, then reopen Settings."
            )
            return False
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
        self._tabs.addTab(self._tab_imagegen(),  "  Image Gen  ")
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

        row += 1
        g.addWidget(_divider(), row, 0, 1, 3)

        row += 1
        g.addWidget(_section("Embeddings (optional)"), row, 0, 1, 3)

        row += 1
        g.addWidget(_lbl("Embeddings model path"), row, 0)
        self._kob_embed = QLineEdit()
        self._kob_embed.setPlaceholderText("Leave blank to disable Vector Storage / CharMemory embeddings")
        g.addWidget(self._kob_embed, row, 1)
        btn_embed = QPushButton("Browse…")
        btn_embed.setFixedWidth(72)
        btn_embed.clicked.connect(lambda: self._browse_file(self._kob_embed, "GGUF models (*.gguf);;All files (*)"))
        g.addWidget(btn_embed, row, 2)

        row += 1
        note = _lbl("A small dedicated embedding model (e.g. bge-small-en-v1.5) — needed for "
                     "SillyTavern's Vector Storage / CharMemory to work at all with KoboldCpp; "
                     "without one, embedding requests return empty.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        g.addWidget(note, row, 0, 1, 3)

        g.setRowStretch(row + 1, 1)
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
        self._model_table.setObjectName("kvTable")
        self._model_table.setHorizontalHeaderLabels(["Name", "Key", "Path"])
        self._model_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._model_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._model_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._model_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._model_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked |
                                          QTableWidget.EditTrigger.SelectedClicked)
        self._model_table.verticalHeader().setVisible(False)
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

    # ── Image Gen tab ─────────────────────────────────────────────────

    def _tab_imagegen(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        v.addWidget(_section("Checkpoint"))
        ck_row = QHBoxLayout()
        ck_row.setSpacing(6)
        self._sdxl_model = QLineEdit()
        ck_row.addWidget(self._sdxl_model, 1)
        btn = QPushButton("Browse…")
        btn.setFixedWidth(72)
        btn.clicked.connect(lambda: self._browse_file(self._sdxl_model, "Safetensors (*.safetensors)"))
        ck_row.addWidget(btn)
        v.addLayout(ck_row)

        v.addWidget(_divider())
        v.addWidget(_section("LoRAs"))

        self._lora_table = QTableWidget(0, 3)
        self._lora_table.setObjectName("kvTable")
        self._lora_table.setHorizontalHeaderLabels(["On", "Path", "Weight"])
        self._lora_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._lora_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._lora_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._lora_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._lora_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked |
                                         QTableWidget.EditTrigger.SelectedClicked)
        self._lora_table.verticalHeader().setVisible(False)
        self._lora_table.verticalHeader().setDefaultSectionSize(24)
        self._lora_table.setFont(QFont(FONT_LOG_FAMILY, 8))
        self._lora_table.setMaximumHeight(110)
        v.addWidget(self._lora_table)

        lora_btn_row = QHBoxLayout()
        lora_btn_row.setSpacing(6)
        btn_lora_add = QPushButton("Add row")
        btn_lora_add.setFixedHeight(24)
        btn_lora_add.clicked.connect(lambda: self._add_lora_row())
        btn_lora_remove = QPushButton("Remove selected")
        btn_lora_remove.setFixedHeight(24)
        btn_lora_remove.clicked.connect(lambda: _table_remove_selected(self._lora_table))
        btn_lora_browse = QPushButton("Browse path…")
        btn_lora_browse.setFixedHeight(24)
        btn_lora_browse.clicked.connect(
            lambda: _table_browse_path(self._lora_table, 1, self, "Safetensors (*.safetensors)")
        )
        lora_btn_row.addWidget(btn_lora_add)
        lora_btn_row.addWidget(btn_lora_remove)
        lora_btn_row.addWidget(btn_lora_browse)
        lora_btn_row.addStretch()
        v.addLayout(lora_btn_row)

        v.addWidget(_divider())
        v.addWidget(_section("Textual Inversions"))

        self._ti_table = QTableWidget(0, 3)
        self._ti_table.setObjectName("kvTable")
        self._ti_table.setHorizontalHeaderLabels(["On", "Path", "Token"])
        self._ti_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._ti_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._ti_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._ti_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._ti_table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked |
                                       QTableWidget.EditTrigger.SelectedClicked)
        self._ti_table.verticalHeader().setVisible(False)
        self._ti_table.verticalHeader().setDefaultSectionSize(24)
        self._ti_table.setFont(QFont(FONT_LOG_FAMILY, 8))
        self._ti_table.setMaximumHeight(110)
        v.addWidget(self._ti_table)

        ti_btn_row = QHBoxLayout()
        ti_btn_row.setSpacing(6)
        btn_ti_add = QPushButton("Add row")
        btn_ti_add.setFixedHeight(24)
        btn_ti_add.clicked.connect(lambda: self._add_ti_row())
        btn_ti_remove = QPushButton("Remove selected")
        btn_ti_remove.setFixedHeight(24)
        btn_ti_remove.clicked.connect(lambda: _table_remove_selected(self._ti_table))
        btn_ti_browse = QPushButton("Browse path…")
        btn_ti_browse.setFixedHeight(24)
        btn_ti_browse.clicked.connect(
            lambda: _table_browse_path(self._ti_table, 1, self, "Safetensors (*.safetensors);;All files (*)")
        )
        ti_btn_row.addWidget(btn_ti_add)
        ti_btn_row.addWidget(btn_ti_remove)
        ti_btn_row.addWidget(btn_ti_browse)
        ti_btn_row.addStretch()
        v.addLayout(ti_btn_row)

        v.addWidget(_divider())
        v.addWidget(_section("Upscaler"))
        up_row = QHBoxLayout()
        up_row.setSpacing(6)
        self._sdxl_upscaler = QLineEdit()
        up_row.addWidget(self._sdxl_upscaler, 1)
        btn2 = QPushButton("Browse…")
        btn2.setFixedWidth(72)
        btn2.clicked.connect(lambda: self._browse_file(self._sdxl_upscaler, "PyTorch models (*.pth);;All files (*)"))
        up_row.addWidget(btn2)
        v.addLayout(up_row)

        v.addWidget(_divider())
        v.addWidget(_section("Output Directory"))
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        self._sdxl_output_dir = QLineEdit()
        self._sdxl_output_dir.setPlaceholderText("Defaults to SDXL\\output under this app's folder")
        out_row.addWidget(self._sdxl_output_dir, 1)
        btn3 = QPushButton("Browse…")
        btn3.setFixedWidth(72)
        btn3.clicked.connect(lambda: self._browse_dir(self._sdxl_output_dir))
        out_row.addWidget(btn3)
        v.addLayout(out_row)

        v.addWidget(_divider())
        v.addWidget(_section("Generation"))

        g2 = QGridLayout()
        g2.setVerticalSpacing(8)
        g2.setHorizontalSpacing(10)

        g2.addWidget(_lbl("Width"), 0, 0)
        self._sdxl_width = QSpinBox()
        self._sdxl_width.setRange(64, 2048)
        self._sdxl_width.setSingleStep(64)
        self._sdxl_width.setFixedWidth(90)
        g2.addWidget(self._sdxl_width, 0, 1)

        g2.addWidget(_lbl("Height"), 0, 2)
        self._sdxl_height = QSpinBox()
        self._sdxl_height.setRange(64, 2048)
        self._sdxl_height.setSingleStep(64)
        self._sdxl_height.setFixedWidth(90)
        g2.addWidget(self._sdxl_height, 0, 3)

        g2.addWidget(_lbl("Steps"), 1, 0)
        self._sdxl_steps = QSpinBox()
        self._sdxl_steps.setRange(1, 150)
        self._sdxl_steps.setFixedWidth(90)
        g2.addWidget(self._sdxl_steps, 1, 1)

        g2.addWidget(_lbl("CFG scale"), 1, 2)
        self._sdxl_cfg = QDoubleSpinBox()
        self._sdxl_cfg.setRange(1.0, 30.0)
        self._sdxl_cfg.setSingleStep(0.5)
        self._sdxl_cfg.setFixedWidth(90)
        g2.addWidget(self._sdxl_cfg, 1, 3)

        g2.addWidget(_lbl("Hires scale"), 2, 0)
        self._sdxl_hires_scale = QDoubleSpinBox()
        self._sdxl_hires_scale.setRange(1.0, 4.0)
        self._sdxl_hires_scale.setSingleStep(0.1)
        self._sdxl_hires_scale.setFixedWidth(90)
        g2.addWidget(self._sdxl_hires_scale, 2, 1)

        g2.addWidget(_lbl("Hires denoise"), 2, 2)
        self._sdxl_hires_denoise = QDoubleSpinBox()
        self._sdxl_hires_denoise.setRange(0.0, 1.0)
        self._sdxl_hires_denoise.setSingleStep(0.05)
        self._sdxl_hires_denoise.setFixedWidth(90)
        g2.addWidget(self._sdxl_hires_denoise, 2, 3)

        g2.addWidget(_lbl("Scheduler"), 3, 0)
        self._sdxl_scheduler = QComboBox()
        for key, label in SDXL_SCHEDULER_CHOICES:
            self._sdxl_scheduler.addItem(label, userData=key)
        g2.addWidget(self._sdxl_scheduler, 3, 1, 1, 3)

        v.addLayout(g2)

        restore_row = QHBoxLayout()
        restore_row.addStretch()
        btn_restore_defaults = QPushButton("Restore Generation Defaults")
        btn_restore_defaults.clicked.connect(self._restore_generation_defaults)
        restore_row.addWidget(btn_restore_defaults)
        v.addLayout(restore_row)

        v.addWidget(_divider())
        v.addWidget(_section("SillyTavern API Server"))

        port_row = QHBoxLayout()
        port_row.setSpacing(10)
        port_row.addWidget(_lbl("Port"))
        self._sdxl_port = QSpinBox()
        self._sdxl_port.setRange(1024, 65535)
        self._sdxl_port.setFixedWidth(100)
        port_row.addWidget(self._sdxl_port)
        port_row.addStretch()
        v.addLayout(port_row)

        self._sdxl_st_override = QCheckBox("Allow SillyTavern to override generation settings")
        v.addWidget(self._sdxl_st_override)

        warn = QLabel(
            "When enabled, SillyTavern controls steps, CFG scale, resolution, seed, and "
            "hires-fix (including disabling it entirely) for every image it requests. "
            "Off by default so this app's own tuned settings always apply regardless of "
            "what SillyTavern sends."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color: {COLOR_STATUS_STARTING}; font-size: 8pt;")
        v.addWidget(warn)

        v.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(w)
        return scroll

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
        self._kob_embed.setText(kob.get("embeddings_model", ""))

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

        sdxl = self._cfg.get("sdxl", {})
        self._sdxl_model.setText(sdxl.get("model_path", ""))
        self._lora_table.setRowCount(0)
        for lora in sdxl.get("loras", []):
            self._add_lora_row(lora.get("path", ""), str(lora.get("weight", 1.0)), lora.get("enabled", True))
        self._ti_table.setRowCount(0)
        for ti in sdxl.get("textual_inversions", []):
            self._add_ti_row(ti.get("path", ""), ti.get("token", ""), ti.get("enabled", True))
        self._sdxl_upscaler.setText(sdxl.get("upscaler_path", ""))
        self._sdxl_output_dir.setText(sdxl.get("output_dir", ""))
        d = SDXL_GENERATION_DEFAULTS
        self._sdxl_width.setValue(int(sdxl.get("base_width", d["base_width"])))
        self._sdxl_height.setValue(int(sdxl.get("base_height", d["base_height"])))
        self._sdxl_steps.setValue(int(sdxl.get("steps", d["steps"])))
        self._sdxl_cfg.setValue(float(sdxl.get("cfg_scale", d["cfg_scale"])))
        self._sdxl_hires_scale.setValue(float(sdxl.get("hires_scale", d["hires_scale"])))
        self._sdxl_hires_denoise.setValue(float(sdxl.get("hires_denoise", d["hires_denoise"])))
        self._set_scheduler_combo(sdxl.get("scheduler", d["scheduler"]))
        self._sdxl_port.setValue(int(sdxl.get("port", 7860)))
        self._sdxl_st_override.setChecked(bool(sdxl.get("allow_st_override", False)))

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
        kob["embeddings_model"] = self._kob_embed.text().strip()

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

        sdxl = self._cfg.setdefault("sdxl", {})
        sdxl["model_path"] = self._sdxl_model.text().strip()

        loras = []
        for r in range(self._lora_table.rowCount()):
            path = (self._lora_table.item(r, 1) or QTableWidgetItem("")).text().strip()
            weight_text = (self._lora_table.item(r, 2) or QTableWidgetItem("1.0")).text().strip()
            if path:
                try:
                    weight = float(weight_text)
                except ValueError:
                    weight = 1.0
                enabled = _table_checkbox_checked(self._lora_table, r, 0)
                loras.append({"path": path, "weight": weight, "enabled": enabled})
        sdxl["loras"] = loras

        tis = []
        for r in range(self._ti_table.rowCount()):
            path  = (self._ti_table.item(r, 1) or QTableWidgetItem("")).text().strip()
            token = (self._ti_table.item(r, 2) or QTableWidgetItem("")).text().strip()
            if path and token:
                enabled = _table_checkbox_checked(self._ti_table, r, 0)
                tis.append({"path": path, "token": token, "enabled": enabled})
        sdxl["textual_inversions"] = tis

        sdxl["upscaler_path"]      = self._sdxl_upscaler.text().strip()
        sdxl["output_dir"]         = self._sdxl_output_dir.text().strip()
        sdxl["base_width"]         = self._sdxl_width.value()
        sdxl["base_height"]        = self._sdxl_height.value()
        sdxl["steps"]              = self._sdxl_steps.value()
        sdxl["cfg_scale"]          = self._sdxl_cfg.value()
        sdxl["hires_scale"]        = self._sdxl_hires_scale.value()
        sdxl["hires_denoise"]      = self._sdxl_hires_denoise.value()
        sdxl["scheduler"]          = self._sdxl_scheduler.currentData()
        sdxl["port"]               = self._sdxl_port.value()
        sdxl["allow_st_override"]  = self._sdxl_st_override.isChecked()

        cg = self._cfg.setdefault("chargen", {})
        cg["output_dir"] = self._cg_dir.text().strip()

    def _set_scheduler_combo(self, key: str):
        idx = self._sdxl_scheduler.findData(key)
        if idx < 0:
            idx = self._sdxl_scheduler.findData(SDXL_GENERATION_DEFAULTS["scheduler"])
        self._sdxl_scheduler.setCurrentIndex(max(idx, 0))

    def _restore_generation_defaults(self):
        d = SDXL_GENERATION_DEFAULTS
        self._sdxl_width.setValue(d["base_width"])
        self._sdxl_height.setValue(d["base_height"])
        self._sdxl_steps.setValue(d["steps"])
        self._sdxl_cfg.setValue(d["cfg_scale"])
        self._sdxl_hires_scale.setValue(d["hires_scale"])
        self._sdxl_hires_denoise.setValue(d["hires_denoise"])
        self._set_scheduler_combo(d["scheduler"])

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_save(self):
        self._warn_missing_imagegen_paths()
        self._warn_missing_embeddings_path()
        if self._save_config():
            self.accept()

    def _warn_missing_embeddings_path(self):
        """Same heads-up as _warn_missing_imagegen_paths(), for the Embeddings
        model path — a typo'd/stale path here silently reproduces the exact
        "KoboldCpp returned an empty embedding" confusion this field exists
        to prevent, with no clue until koboldcpp's own log at launch time."""
        path = self._kob_embed.text().strip()
        if path and not os.path.isfile(path):
            QMessageBox.warning(
                self, "Embeddings",
                f"This embeddings model path doesn't exist on disk:\n\n{path}\n\n"
                "KoboldCpp will start without embeddings support until this is fixed."
            )

    def _warn_missing_imagegen_paths(self):
        """Non-blocking heads-up for typo'd/missing Image Gen paths — without
        this, a bad path silently trains to nothing (imagegen_engine.py logs
        a warning and skips it) and the only clue is scrolling back through
        the log after wondering why a LoRA/TI didn't apply."""
        missing = []
        if self._sdxl_model.text().strip() and not os.path.isfile(self._sdxl_model.text().strip()):
            missing.append(f"Checkpoint: {self._sdxl_model.text().strip()}")
        for r in range(self._lora_table.rowCount()):
            path = (self._lora_table.item(r, 1) or QTableWidgetItem("")).text().strip()
            if path and _table_checkbox_checked(self._lora_table, r, 0) and not os.path.isfile(path):
                missing.append(f"LoRA: {path}")
        for r in range(self._ti_table.rowCount()):
            path = (self._ti_table.item(r, 1) or QTableWidgetItem("")).text().strip()
            if path and _table_checkbox_checked(self._ti_table, r, 0) and not os.path.isfile(path):
                missing.append(f"Textual inversion: {path}")
        upscaler = self._sdxl_upscaler.text().strip()
        if upscaler and not os.path.isfile(upscaler):
            missing.append(f"Upscaler: {upscaler}")

        if missing:
            QMessageBox.warning(
                self, "Image Gen",
                "These paths don't exist on disk and will be silently skipped "
                "at generation time:\n\n" + "\n".join(missing)
            )

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

    def _add_lora_row(self, path: str = "", weight: str = "1.0", enabled: bool = True):
        r = self._lora_table.rowCount()
        self._lora_table.insertRow(r)
        _table_set_checkbox(self._lora_table, r, 0, enabled)
        self._lora_table.setItem(r, 1, QTableWidgetItem(path))
        self._lora_table.setItem(r, 2, QTableWidgetItem(weight))

    def _add_ti_row(self, path: str = "", token: str = "", enabled: bool = True):
        r = self._ti_table.rowCount()
        self._ti_table.insertRow(r)
        _table_set_checkbox(self._ti_table, r, 0, enabled)
        self._ti_table.setItem(r, 1, QTableWidgetItem(path))
        self._ti_table.setItem(r, 2, QTableWidgetItem(token))

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
        _table_browse_path(self._model_table, 2, self, "GGUF models (*.gguf);;All files (*)")

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
