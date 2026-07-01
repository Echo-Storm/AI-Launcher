# chargen_dialog.py — Character card generator dialog

import base64
import json
import os
import re

from PyQt6.QtCore    import Qt, QThread, pyqtSignal
from PyQt6.QtGui     import QFont, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QTabWidget, QWidget, QFileDialog, QMessageBox,
    QScrollArea,
)

from constants import (
    COLOR_BG, COLOR_PANEL, COLOR_BORDER, COLOR_BORDER_BRIGHT,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_ACCENT_DIM,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER,
    COLOR_STATUS_ERROR, COLOR_STATUS_RUNNING, COLOR_STATUS_STARTING,
    FONT_UI_FAMILY, FONT_UI_SIZE, FONT_LOG_FAMILY, FONT_LOG_SIZE,
)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are CharGen, an expert SillyTavern character card creator. "
    "Generate a complete, detailed character card as a single valid JSON object "
    "with these exact fields: name, description, personality, scenario, first_mes. "
    "The first_mes field should be the character's opening message (1-2 paragraphs). "
    "Output only the JSON object — no markdown fences, no commentary."
)

_SYSTEM_PROMPT_WITH_EXAMPLES = (
    "You are CharGen, an expert SillyTavern character card creator. "
    "Generate a complete, detailed character card as a single valid JSON object "
    "with these exact fields: name, description, personality, scenario, first_mes, mes_example. "
    "The first_mes field should be the character's opening message (1-2 paragraphs). "
    r"The mes_example field must contain exactly ONE example exchange using "
    r"<START>\n{{user}}: ...\n{{char}}: ... format — keep each side to 2-3 sentences. "
    "Output only the JSON object — no markdown fences, no commentary."
)


def _build_user_prompt(fields: dict) -> str:
    lines = []
    if fields.get("name"):
        lines.append(f"Name: {fields['name']}")
    if fields.get("concept"):
        lines.append(f"Character concept: {fields['concept']}")
    if fields.get("personality"):
        lines.append(f"Personality notes: {fields['personality']}")
    if fields.get("scenario"):
        lines.append(f"Scenario: {fields['scenario']}")
    if fields.get("first_mes"):
        lines.append(f"Opening message hint: {fields['first_mes']}")
    if fields.get("mes_example"):
        lines.append(f"Dialogue style notes: {fields['mes_example']}")
    lines.append("\nGenerate the complete character card JSON.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | None:
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        text = m.group(1).strip()
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _to_st_card(data: dict, fallback_name: str = "") -> dict:
    """Flat v1 card — used for JSON export."""
    return {
        "name":                      data.get("name") or fallback_name or "Unknown",
        "description":               data.get("description") or data.get("concept", ""),
        "personality":               data.get("personality", ""),
        "scenario":                  data.get("scenario", ""),
        "first_mes":                 data.get("first_mes", ""),
        "mes_example":               data.get("mes_example", ""),
        "creator_notes":             "",
        "system_prompt":             "",
        "post_history_instructions": "",
        "tags":                      [],
        "creator":                   "CharGen v3",
        "character_version":         "",
        "avatar":                    "none",
        "chat":                      "",
    }


def _to_st_card_v2(data: dict, fallback_name: str = "") -> dict:
    """Spec v2 card — used for PNG export (the ST-native format)."""
    v1 = _to_st_card(data, fallback_name)
    data_fields = {k: v for k, v in v1.items() if k not in ("avatar", "chat")}
    data_fields["extensions"] = {}
    return {
        "spec":         "chara_card_v2",
        "spec_version": "2.0",
        "data":         data_fields,
    }


def _make_png_with_chara(card_v2: dict, portrait_path: str | None, output_path: str):
    """Save card_v2 embedded in a PNG tEXt 'chara' chunk."""
    from PIL import Image, PngImagePlugin

    if portrait_path and os.path.isfile(portrait_path):
        img = Image.open(portrait_path).convert("RGBA")
        # Cap at 1024×1024 so the file stays manageable
        if img.width > 1024 or img.height > 1024:
            img.thumbnail((1024, 1024), Image.LANCZOS)
    else:
        img = Image.new("RGBA", (512, 512), (26, 17, 40, 255))  # app header colour

    chara_b64 = base64.b64encode(
        json.dumps(card_v2, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    meta = PngImagePlugin.PngInfo()
    meta.add_text("chara", chara_b64)
    img.save(output_path, "PNG", pnginfo=meta)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class _GenerateWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, api_base: str, messages: list, parent=None):
        super().__init__(parent)
        self._api_base = api_base
        self._messages = messages

    def run(self):
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "messages":    self._messages,
            "max_tokens":  6144,
            "temperature": 0.75,
            "top_p":       0.92,
            "stream":      False,
        }).encode()

        try:
            req = urllib.request.Request(
                f"{self._api_base}/v1/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"]
                self.finished.emit(text)
        except urllib.error.HTTPError as e:
            self.error.emit(f"API error {e.code} {e.reason}")
        except urllib.error.URLError as e:
            self.error.emit(f"Connection failed — is KoboldCpp running? ({e.reason})")
        except (KeyError, IndexError):
            self.error.emit("Unexpected API response format.")
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

_STYLE = f"""
QDialog {{
    background: {COLOR_BG};
}}
QWidget {{
    background: {COLOR_BG};
    font-family: {FONT_UI_FAMILY};
    font-size: {FONT_UI_SIZE}pt;
    color: {COLOR_TEXT};
}}
QLabel {{
    color: {COLOR_TEXT};
    background: transparent;
}}
QLineEdit, QPlainTextEdit {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 3px 6px;
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border-color: {COLOR_ACCENT_DIM};
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
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    background: {COLOR_BG};
}}
QTabBar::tab {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT_MUTED};
    border: 1px solid {COLOR_BORDER};
    padding: 4px 18px;
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
"""

_PORTRAIT_PLACEHOLDER_STYLE = (
    f"border: 1px solid {COLOR_BORDER_BRIGHT};"
    f"background: {COLOR_PANEL};"
    f"color: {COLOR_TEXT_MUTED};"
    "font-size: 7pt;"
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _lbl(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
    return l


def _multi(placeholder: str, lines: int) -> QPlainTextEdit:
    w = QPlainTextEdit()
    w.setPlaceholderText(placeholder)
    w.setFixedHeight(lines * 19 + 14)
    return w


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class CharGenDialog(QDialog):
    def __init__(self, api_base: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Character Card Generator")
        self.setMinimumSize(660, 600)
        self.resize(720, 660)
        self.setStyleSheet(_STYLE)

        self._api_base      = api_base
        self._output_dir    = output_dir
        self._worker        = None
        self._last_card     = None
        self._portrait_path = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        # ── Tab 1: Input ──────────────────────────────────────────────

        form_inner = QWidget()
        form_vbox  = QVBoxLayout(form_inner)
        form_vbox.setContentsMargins(10, 10, 10, 10)
        form_vbox.setSpacing(4)

        def _field(label, widget):
            form_vbox.addWidget(_lbl(label))
            form_vbox.addSpacing(2)
            form_vbox.addWidget(widget)
            form_vbox.addSpacing(6)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Optional — model will invent one if blank")
        _field("Name", self.edit_name)

        self.edit_concept = _multi(
            "Required. Describe the character — who they are, their role, setting, tone, "
            "any key details. The more you write here, the better the output.",
            4,
        )
        _field("Concept / Description  *", self.edit_concept)

        self.edit_personality = _multi(
            "Personality traits, speech patterns, quirks, motivations (optional)", 3)
        _field("Personality", self.edit_personality)

        def _optional_field(attr, placeholder, lines, label):
            chk = QCheckBox(f"{label}  (uncheck to skip)")
            chk.setChecked(False)
            chk.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
            form_vbox.addWidget(chk)
            form_vbox.addSpacing(2)
            widget = _multi(placeholder, lines)
            widget.setEnabled(False)
            chk.toggled.connect(widget.setEnabled)
            form_vbox.addWidget(widget)
            form_vbox.addSpacing(6)
            setattr(self, attr, widget)
            return chk

        self.chk_scenario = _optional_field(
            "edit_scenario",
            "The situation or setting context for interactions",
            3, "Scenario",
        )
        self.chk_first_mes = _optional_field(
            "edit_first_mes",
            "Hint for the character's opening message — mood, situation, first words",
            3, "First Message",
        )
        self.chk_mes_example = _optional_field(
            "edit_mes_example",
            "Dialogue style notes — tone, vocabulary, how the character talks (optional)",
            3, "Dialogue Examples",
        )

        form_vbox.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_inner)
        self._tabs.addTab(scroll, "  Input  ")

        # ── Tab 2: Output ─────────────────────────────────────────────

        out_widget = QWidget()
        out_vbox   = QVBoxLayout(out_widget)
        out_vbox.setContentsMargins(10, 10, 10, 10)
        out_vbox.setSpacing(6)

        out_vbox.addWidget(_lbl("Generated character card (JSON):"))

        self.edit_output = QPlainTextEdit()
        self.edit_output.setReadOnly(True)
        self.edit_output.setFont(QFont(FONT_LOG_FAMILY, FONT_LOG_SIZE))
        self.edit_output.setPlaceholderText("Generated output will appear here…")
        out_vbox.addWidget(self.edit_output, 1)

        # Portrait row
        portrait_row = QHBoxLayout()
        portrait_row.setSpacing(10)

        self._portrait_preview = QLabel()
        self._portrait_preview.setFixedSize(96, 96)
        self._portrait_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._portrait_preview.setStyleSheet(_PORTRAIT_PLACEHOLDER_STYLE)
        self._portrait_preview.setText("No portrait\nselected")
        portrait_row.addWidget(self._portrait_preview)

        portrait_btns = QVBoxLayout()
        portrait_btns.setSpacing(4)
        self._btn_pick_portrait = QPushButton("Pick Portrait…")
        self._btn_pick_portrait.setFixedHeight(26)
        self._btn_pick_portrait.clicked.connect(self._pick_portrait)
        self._btn_clear_portrait = QPushButton("Clear")
        self._btn_clear_portrait.setFixedHeight(26)
        self._btn_clear_portrait.setEnabled(False)
        self._btn_clear_portrait.clicked.connect(self._clear_portrait)
        portrait_btns.addWidget(self._btn_pick_portrait)
        portrait_btns.addWidget(self._btn_clear_portrait)
        portrait_lbl = _lbl(
            "Optional — if none is selected, a dark placeholder\n"
            "will be used when saving as PNG."
        )
        portrait_lbl.setWordWrap(True)
        portrait_btns.addWidget(portrait_lbl)
        portrait_btns.addStretch()
        portrait_row.addLayout(portrait_btns)
        out_vbox.addLayout(portrait_row)

        # Save-to row
        dir_row = QHBoxLayout()
        dir_row.addWidget(_lbl("Save to:"))
        self._lbl_outdir = QLabel(self._output_dir)
        self._lbl_outdir.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        self._lbl_outdir.setWordWrap(True)
        dir_row.addWidget(self._lbl_outdir, 1)
        self._btn_browse = QPushButton("Browse…")
        self._btn_browse.setFixedWidth(72)
        self._btn_browse.clicked.connect(self._browse)
        dir_row.addWidget(self._btn_browse)
        out_vbox.addLayout(dir_row)

        self._tabs.addTab(out_widget, "  Output  ")

        # ── Bottom controls ───────────────────────────────────────────

        ctrl = QHBoxLayout()
        self._lbl_status = QLabel("Fill in a concept and click Generate.")
        self._lbl_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        ctrl.addWidget(self._lbl_status, 1)

        self.btn_generate = QPushButton("Generate")
        self.btn_generate.setObjectName("accent")
        self.btn_generate.setFixedHeight(28)
        self.btn_generate.clicked.connect(self._generate)
        ctrl.addWidget(self.btn_generate)

        self.btn_save_json = QPushButton("Save JSON")
        self.btn_save_json.setFixedHeight(28)
        self.btn_save_json.setEnabled(False)
        self.btn_save_json.clicked.connect(self._save_json)
        ctrl.addWidget(self.btn_save_json)

        self.btn_save_png = QPushButton("Save PNG")
        self.btn_save_png.setObjectName("accent")
        self.btn_save_png.setFixedHeight(28)
        self.btn_save_png.setEnabled(False)
        self.btn_save_png.clicked.connect(self._save_png)
        ctrl.addWidget(self.btn_save_png)

        root.addLayout(ctrl)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._cleanup_worker()
        event.accept()

    def _cleanup_worker(self):
        if self._worker and self._worker.isRunning():
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
            except RuntimeError:
                pass
            self._worker.setParent(None)
            self._worker = None
            self.btn_generate.setEnabled(True)
            self._set_status("Generation cancelled.", COLOR_TEXT_MUTED)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str, color: str = COLOR_TEXT_MUTED):
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(f"color: {color}; font-size: 8pt;")

    def _safe_name(self) -> str:
        name = (self._last_card or {}).get("name") or self.edit_name.text().strip() or "Unknown"
        return re.sub(r'[\\/:*?"<>|]', "_", name)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select output folder", self._output_dir)
        if d:
            self._output_dir = d
            self._lbl_outdir.setText(d)

    # ------------------------------------------------------------------
    # Portrait
    # ------------------------------------------------------------------

    def _pick_portrait(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Portrait Image", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if not path:
            return
        px = QPixmap(path)
        if px.isNull():
            QMessageBox.warning(self, "Portrait", "Could not load that image file.")
            return
        self._portrait_path = path
        self._portrait_preview.setPixmap(
            px.scaled(96, 96,
                      Qt.AspectRatioMode.KeepAspectRatio,
                      Qt.TransformationMode.SmoothTransformation)
        )
        self._portrait_preview.setText("")
        self._btn_clear_portrait.setEnabled(True)

    def _clear_portrait(self):
        self._portrait_path = None
        self._portrait_preview.clear()
        self._portrait_preview.setText("No portrait\nselected")
        self._btn_clear_portrait.setEnabled(False)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate(self):
        concept = self.edit_concept.toPlainText().strip()
        if not concept:
            self._set_status("Concept/Description is required.", COLOR_STATUS_ERROR)
            self._tabs.setCurrentIndex(0)
            self.edit_concept.setFocus()
            return

        use_examples = self.chk_mes_example.isChecked()
        fields = {
            "name":        self.edit_name.text().strip(),
            "concept":     concept,
            "personality": self.edit_personality.toPlainText().strip(),
            "scenario":    self.edit_scenario.toPlainText().strip() if self.chk_scenario.isChecked() else "",
            "first_mes":   self.edit_first_mes.toPlainText().strip() if self.chk_first_mes.isChecked() else "",
            "mes_example": self.edit_mes_example.toPlainText().strip() if use_examples else "",
        }

        system = _SYSTEM_PROMPT_WITH_EXAMPLES if use_examples else _SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": _build_user_prompt(fields)},
        ]

        self.btn_generate.setEnabled(False)
        self.btn_save_json.setEnabled(False)
        self.btn_save_png.setEnabled(False)
        self._set_status("Generating… this may take a minute.", COLOR_STATUS_STARTING)

        self._worker = _GenerateWorker(self._api_base, messages, self)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, raw: str):
        self._last_card = _extract_json(raw)

        if self._last_card:
            pretty = json.dumps(self._last_card, indent=2, ensure_ascii=False)
            self.edit_output.setPlainText(pretty)
            self.btn_save_json.setEnabled(True)
            self.btn_save_png.setEnabled(True)
            self._set_status(
                "Generation complete. Save as PNG (with portrait) or JSON.",
                COLOR_STATUS_RUNNING,
            )
        else:
            self.edit_output.setPlainText(raw)
            self._set_status(
                "Could not parse JSON — raw output shown. Try regenerating or edit manually.",
                COLOR_STATUS_ERROR,
            )

        self._tabs.setCurrentIndex(1)
        self.btn_generate.setEnabled(True)

    def _on_error(self, msg: str):
        self._set_status(f"Error: {msg}", COLOR_STATUS_ERROR)
        self.btn_generate.setEnabled(True)

    # ------------------------------------------------------------------
    # Save — JSON
    # ------------------------------------------------------------------

    def _save_json(self):
        if not self._last_card:
            return
        card = _to_st_card(self._last_card, self.edit_name.text().strip())
        default_path = os.path.join(self._output_dir, f"{self._safe_name()}.json")

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Character Card (JSON)", default_path, "JSON files (*.json)"
        )
        if not path:
            return

        try:
            if dir_part := os.path.dirname(path):
                os.makedirs(dir_part, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(card, fh, indent=2, ensure_ascii=False)
            self._set_status(f"Saved: {os.path.basename(path)}", COLOR_STATUS_RUNNING)
        except OSError as e:
            QMessageBox.critical(self, "Save Error", str(e))

    # ------------------------------------------------------------------
    # Save — PNG
    # ------------------------------------------------------------------

    def _save_png(self):
        if not self._last_card:
            return
        card_v2 = _to_st_card_v2(self._last_card, self.edit_name.text().strip())
        default_path = os.path.join(self._output_dir, f"{self._safe_name()}.png")

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Character Card (PNG)", default_path, "PNG files (*.png)"
        )
        if not path:
            return

        try:
            if dir_part := os.path.dirname(path):
                os.makedirs(dir_part, exist_ok=True)
            _make_png_with_chara(card_v2, self._portrait_path, path)
            self._set_status(f"Saved: {os.path.basename(path)}", COLOR_STATUS_RUNNING)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
