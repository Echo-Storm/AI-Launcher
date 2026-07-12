# chargen_dialog.py — Character card generator dialog

import base64
import json
import os
import re

from PyQt6.QtCore    import Qt, QThread, pyqtSignal
from PyQt6.QtGui     import QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox, QComboBox, QDialog, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QSlider, QStyle, QStyleOptionSlider, QTabWidget, QWidget,
    QFileDialog, QMessageBox, QScrollArea,
)

from constants import (
    COLOR_BG, COLOR_PANEL, COLOR_BORDER, COLOR_BORDER_BRIGHT,
    COLOR_TEXT, COLOR_TEXT_MUTED, COLOR_ACCENT, COLOR_ACCENT_DIM,
    COLOR_BUTTON_BG, COLOR_BUTTON_HOVER,
    COLOR_STATUS_ERROR, COLOR_STATUS_RUNNING, COLOR_STATUS_STARTING,
    FONT_UI_FAMILY, FONT_UI_SIZE, FONT_LOG_FAMILY, FONT_LOG_SIZE,
    API_BASE_URL, API_KEY, API_MODEL, SDXL_MODEL_PATH,
)
from imagegen_dialog import ImageGenWorker

# ---------------------------------------------------------------------------
# Prompt templates — 4 composable variants
# ---------------------------------------------------------------------------

_BASE = (
    "You are CharGen, an expert SillyTavern character card creator. "
    "Generate a complete, detailed character card as a single valid JSON object "
)

_DISTINCTIVE = (
    "Prioritize genuine originality: avoid overused archetypes and clichés. "
    "Give the character internal contradictions, specific idiosyncrasies, a distinct speech "
    "register, and at least one surprising detail that makes them feel unmistakably real. "
)

_SFW_SAFE = (
    "Keep all content strictly safe-for-work: no explicit sexual content and no graphic "
    "violence or gore. Mature themes (danger, conflict, romance) are fine as long as they "
    "stay tasteful and non-explicit. "
)

_NSFW_ALLOWED = (
    "Mature and adult content is permitted where it fits the character concept, including "
    "explicit sexual content, graphic violence, and other NSFW themes — write without "
    "holding back for a general audience. "
)

_OUTPUT = (
    "Output ONLY the raw JSON object — no markdown fences, no commentary, no preamble."
)

# ---------------------------------------------------------------------------
# Expand-field configuration — system prompt + user instruction per field
# ---------------------------------------------------------------------------

_EXPAND_CONFIG = {
    "personality": (
        "You are a character card editor. Expand the personality field of the provided "
        "SillyTavern character card to be detailed and vivid. "
        "Return only the new personality text — no JSON, no field labels, no explanation.",
        "Rewrite the personality field to be significantly more detailed — aim for 3-5 "
        "substantial paragraphs covering: speech register and vocabulary, specific behavioral "
        "mannerisms, emotional tendencies and triggers, internal contradictions, and how "
        "they present themselves in conversation.",
    ),
    "scenario": (
        "You are a character card editor. Expand the scenario field of the provided "
        "SillyTavern character card to be detailed and immersive. "
        "Return only the new scenario text — no JSON, no field labels, no explanation.",
        "Rewrite the scenario field to be significantly more detailed — describe the setting, "
        "circumstances, and atmosphere with specific sensory details. Make the world feel real "
        "and give a clear sense of how and where interactions with this character take place.",
    ),
    "first_mes": (
        "You are a character card editor. Rewrite the first_mes field of the provided "
        "SillyTavern character card. "
        "Return only the new first message text — no JSON, no field labels, no explanation.",
        "Rewrite the first_mes field — write a compelling, in-character opening message that "
        "immediately establishes the character's voice, sets the scene, and draws the reader in. "
        "Aim for 2-3 paragraphs.",
    ),
}

# ---------------------------------------------------------------------------
# Regenerate-field configuration — same fields as Expand, but instructs a fresh
# alternative take instead of elaborating on the existing text. The current value
# of the target field is deliberately withheld from the prompt (see
# _regenerate_field) so the model isn't anchored to it.
# ---------------------------------------------------------------------------

_REGENERATE_CONFIG = {
    "personality": (
        "You are a character card editor. Write a fresh, alternative personality field for "
        "the provided SillyTavern character card, taking a different creative angle than "
        "whatever was there before. Return only the new personality text — no JSON, no field "
        "labels, no explanation.",
        "Write a new personality field from scratch based on the character's name, "
        "description, and other fields shown below. Take a different creative angle — "
        "different mannerisms, tone, and emotional register than a typical take on this "
        "concept would produce.",
    ),
    "scenario": (
        "You are a character card editor. Write a fresh, alternative scenario field for "
        "the provided SillyTavern character card, taking a different creative angle than "
        "whatever was there before. Return only the new scenario text — no JSON, no field "
        "labels, no explanation.",
        "Write a new scenario field from scratch based on the character's name, description, "
        "and other fields shown below. Take a different creative angle on the setting or "
        "circumstances than a typical take on this concept would produce.",
    ),
    "first_mes": (
        "You are a character card editor. Write a fresh, alternative first_mes field for "
        "the provided SillyTavern character card, taking a different creative angle than "
        "whatever was there before. Return only the new first message text — no JSON, no "
        "field labels, no explanation.",
        "Write a new first_mes field from scratch based on the character's name, "
        "description, and other fields shown below. Take a different opening angle — a "
        "different situation, tone, or hook than a typical take on this concept would "
        "produce. Aim for 2-3 paragraphs.",
    ),
}

# ---------------------------------------------------------------------------
# Condense-field configuration — tightens an existing field instead of adding
# to it (Expand) or replacing it wholesale (Regenerate). Word targets below
# double as the green/yellow/red thresholds for the live word-count label —
# "yellow" means "past what Condense would consider Medium", "red" means
# "past what Condense would even consider Long".
# ---------------------------------------------------------------------------

_REQUIRED_OUTPUT_FIELDS = ("name", "description")

_FIELD_LENGTH_TARGETS = {
    "personality": {"short": 100, "medium": 200, "long": 350},
    "scenario":    {"short": 80,  "medium": 150, "long": 275},
    "first_mes":   {"short": 80,  "medium": 150, "long": 250},
}

_CONDENSE_CONFIG = {
    "personality": (
        "You are a character card editor. Condense the personality field of the provided "
        "SillyTavern character card — cut filler, repetition, and redundant descriptors "
        "while preserving every distinct trait and detail. Return only the condensed "
        "personality text — no JSON, no field labels, no explanation.",
        "Rewrite the personality field to be significantly tighter, aiming for "
        "approximately {target} words. Keep every distinct trait, mannerism, and voice "
        "detail — cut repeated ideas, throat-clearing, and vague filler phrases instead "
        "of removing substance.",
    ),
    "scenario": (
        "You are a character card editor. Condense the scenario field of the provided "
        "SillyTavern character card — cut filler and repetition while preserving the "
        "essential setting and circumstances. Return only the condensed scenario text — "
        "no JSON, no field labels, no explanation.",
        "Rewrite the scenario field to be significantly tighter, aiming for approximately "
        "{target} words. Keep the essential setting, circumstances, and atmosphere — cut "
        "redundant scene-setting and filler description.",
    ),
    "first_mes": (
        "You are a character card editor. Condense the first_mes field of the provided "
        "SillyTavern character card — cut filler and repetition while preserving the "
        "character's voice and the opening hook. Return only the condensed first message "
        "text — no JSON, no field labels, no explanation.",
        "Rewrite the first_mes field to be significantly tighter, aiming for approximately "
        "{target} words. Keep the character's voice and the opening hook — cut redundant "
        "description and filler dialogue.",
    ),
}


def _word_count(text: str) -> int:
    return len(text.split())


def _wordcount_color(field_key: str, count: int) -> str:
    targets = _FIELD_LENGTH_TARGETS.get(field_key)
    if not targets:
        return COLOR_TEXT_MUTED
    if count <= targets["medium"]:
        return COLOR_STATUS_RUNNING
    if count <= targets["long"]:
        return COLOR_STATUS_STARTING
    return COLOR_STATUS_ERROR


def _build_system_prompt(
    distinctive: bool = False,
    scenario: bool = True,
    first_mes: bool = True,
    mes_example: bool = False,
    nsfw: bool = False,
) -> str:
    fields = ["name", "description", "personality"]
    if scenario:
        fields.append("scenario")
    if first_mes:
        fields.append("first_mes")
    if mes_example:
        fields.append("mes_example")

    notes = []
    if first_mes:
        notes.append("The first_mes field should be the character's opening message (1-2 paragraphs). ")
    if mes_example:
        notes.append(
            r"The mes_example field must contain exactly ONE example exchange using "
            r"<START>\n{{user}}: ...\n{{char}}: ... format — keep each side to 2-3 sentences. "
        )

    return (
        _BASE
        + "with these exact fields: " + ", ".join(fields) + ". "
        + "".join(notes)
        + (_DISTINCTIVE if distinctive else "")
        + (_NSFW_ALLOWED if nsfw else _SFW_SAFE)
        + _OUTPUT
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


def _merge_last_card(base: dict, last_card: dict) -> dict:
    """Overlay last_card's fields onto an ST-normalized base, preserving fields
    (creator_notes, system_prompt, tags, extensions, etc.) that _to_st_card() zeroes
    out. Excludes 'name' so the fallback-aware name from base isn't clobbered by an
    explicit-but-empty name in last_card."""
    merged = dict(base)
    merged.update({k: v for k, v in last_card.items() if k not in ("avatar", "chat", "name")})
    return merged


def _to_st_card_v2(data: dict, fallback_name: str = "") -> dict:
    v1 = _merge_last_card(_to_st_card(data, fallback_name), data)
    data_fields = {k: v for k, v in v1.items() if k not in ("avatar", "chat")}
    data_fields.setdefault("extensions", {})
    return {
        "spec":         "chara_card_v2",
        "spec_version": "2.0",
        "data":         data_fields,
    }


def _make_png_with_chara(card_v2: dict, portrait_path: str | None, output_path: str):
    from PIL import Image, PngImagePlugin

    if portrait_path and os.path.isfile(portrait_path):
        img = Image.open(portrait_path).convert("RGBA")
        if img.width > 1024 or img.height > 1024:
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    else:
        img = Image.new("RGBA", (512, 512), (26, 17, 40, 255))

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

    def __init__(self, api_base: str, messages: list, temperature: float,
                 api_key: str = "", model: str = "", max_tokens: int = 4096, parent=None):
        super().__init__(parent)
        self._api_base    = api_base
        self._messages    = messages
        self._temperature = temperature
        self._api_key     = api_key
        self._model       = model
        self._max_tokens  = max_tokens

    def run(self):
        import urllib.request
        import urllib.error

        payload_dict = {
            "messages":    self._messages,
            "max_tokens":  self._max_tokens,
            "temperature": self._temperature,
            "stream":      False,
        }
        if self._model:
            payload_dict["model"] = self._model

        headers = {
            "Content-Type": "application/json",
            "User-Agent":   "python-requests/2.31.0",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            req = urllib.request.Request(
                f"{self._api_base}/v1/chat/completions",
                data=json.dumps(payload_dict).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
                text = data["choices"][0]["message"]["content"] or ""
                self.finished.emit(text)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.error.emit("API error 401 — invalid API key.")
            else:
                self.error.emit(f"API error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            if self._api_key:
                self.error.emit(f"Connection failed — check URL and API key. ({e.reason})")
            else:
                self.error.emit(f"Connection failed — is KoboldCpp running? ({e.reason})")
        except (KeyError, IndexError):
            self.error.emit("Unexpected API response format.")
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Custom slider — draws a "Std" reference notch at value 75 (0.75)
# ---------------------------------------------------------------------------

class _TempSlider(QSlider):
    _MARKER = 75

    def paintEvent(self, event):
        super().paintEvent(event)
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider, opt,
            QStyle.SubControl.SC_SliderGroove, self,
        )
        px = QStyle.sliderPositionFromValue(
            self.minimum(), self.maximum(), self._MARKER,
            groove.width(), False,
        ) + groove.x()

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        pen = QPen(QColor(COLOR_TEXT_MUTED))
        pen.setWidth(1)
        p.setPen(pen)
        tick_y = groove.bottom() + 3
        p.drawLine(px, tick_y, px, tick_y + 5)

        p.setFont(QFont(FONT_UI_FAMILY, 6))
        fm = p.fontMetrics()
        label = "Std"
        tw = fm.horizontalAdvance(label)
        p.setPen(QColor(COLOR_TEXT_MUTED))
        p.drawText(px - tw // 2, tick_y + 15, label)
        p.end()


# ---------------------------------------------------------------------------
# Prefs persistence  (temperature + distinctive defaults)
# ---------------------------------------------------------------------------

_PREFS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chargen_prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_PREFS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> bool:
    try:
        with open(_PREFS_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
        return True
    except Exception:
        return False


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
QSlider::groove:horizontal {{
    height: 4px;
    background: {COLOR_BORDER_BRIGHT};
    border-radius: 2px;
    margin: 0px;
}}
QSlider::handle:horizontal {{
    background: {COLOR_ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    border: none;
}}
QSlider::sub-page:horizontal {{
    background: {COLOR_ACCENT_DIM};
    border-radius: 2px;
}}
QSlider::handle:horizontal:hover {{
    background: {COLOR_ACCENT};
    border: 2px solid {COLOR_TEXT};
}}
QComboBox {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    border-radius: 4px;
    padding: 2px 6px;
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
    width: 16px;
}}
QComboBox QAbstractItemView {{
    background: {COLOR_PANEL};
    color: {COLOR_TEXT};
    border: 1px solid {COLOR_BORDER_BRIGHT};
    selection-background-color: {COLOR_ACCENT_DIM};
    outline: none;
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


def _lbl_section(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(
        f"color: {COLOR_ACCENT}; font-size: 8pt; font-weight: bold;"
        f" padding-top: 4px;"
    )
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
        self.setMinimumSize(680, 620)
        self.resize(740, 680)
        self.setStyleSheet(_STYLE)

        self._api_base          = api_base
        self._output_dir        = output_dir
        self._worker            = None
        self._last_card         = None
        self._portrait_path     = None
        self._current_api_model = API_MODEL
        self._expanding_field   = "personality"
        self._expanding_verb    = "expanded"
        self._last_hint_key     = None

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

        # --- Generation settings ---
        form_vbox.addWidget(_lbl_section("Generation Settings"))
        form_vbox.addSpacing(4)

        # Backend selector — only visible when API is configured in config.json
        if API_BASE_URL:
            backend_row = QHBoxLayout()
            backend_row.setSpacing(8)
            backend_row.addWidget(_lbl("Backend"))
            self._combo_backend = QComboBox()
            self._combo_backend.setFixedHeight(24)
            self._combo_backend.addItem("Local  (KoboldCpp)", userData="local")
            api_label = f"API  —  {API_MODEL}" if API_MODEL else "API  (remote)"
            self._combo_backend.addItem(api_label, userData="api")
            backend_row.addWidget(self._combo_backend, 1)
            form_vbox.addLayout(backend_row)
            form_vbox.addSpacing(6)
        else:
            self._combo_backend = None

        # Temperature slider
        temp_row = QHBoxLayout()
        temp_row.setSpacing(6)
        temp_row.addWidget(_lbl("Creativity"))
        temp_row.addSpacing(4)
        lbl_safe = QLabel("Safe")
        lbl_safe.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 7pt;")
        temp_row.addWidget(lbl_safe)
        self._slider_temp = _TempSlider(Qt.Orientation.Horizontal)
        self._slider_temp.setRange(60, 120)
        self._slider_temp.setValue(85)
        self._slider_temp.setTickInterval(10)
        self._slider_temp.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider_temp.setFixedHeight(28)
        self._slider_temp.valueChanged.connect(self._on_temp_changed)
        temp_row.addWidget(self._slider_temp, 1)
        lbl_creative = QLabel("Creative")
        lbl_creative.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 7pt;")
        temp_row.addWidget(lbl_creative)
        temp_row.addSpacing(6)
        self._lbl_temp_val = QLabel("0.85")
        self._lbl_temp_val.setFixedWidth(34)
        self._lbl_temp_val.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_temp_val.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 8pt; font-weight: bold;"
        )
        temp_row.addWidget(self._lbl_temp_val)
        form_vbox.addLayout(temp_row)
        form_vbox.addSpacing(6)

        # Distinctive / NSFW toggles + Set as default
        dist_row = QHBoxLayout()
        dist_row.setSpacing(8)
        self.chk_distinctive = QCheckBox("Distinctive character  (stronger creative direction)")
        self.chk_distinctive.setChecked(False)
        self.chk_distinctive.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        dist_row.addWidget(self.chk_distinctive)
        self.chk_nsfw = QCheckBox("NSFW-aware  (allow mature/explicit content)")
        self.chk_nsfw.setChecked(False)
        self.chk_nsfw.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        dist_row.addWidget(self.chk_nsfw)
        dist_row.addStretch(1)
        self._btn_set_default = QPushButton("Set as default")
        self._btn_set_default.setFixedHeight(20)
        self._btn_set_default.setFixedWidth(100)
        self._btn_set_default.setStyleSheet(
            f"font-size: 7pt; color: {COLOR_TEXT_MUTED};"
            f" background: transparent; border: 1px solid {COLOR_BORDER_BRIGHT};"
            f" border-radius: 3px; padding: 1px 6px;"
        )
        self._btn_set_default.clicked.connect(self._save_defaults)
        dist_row.addWidget(self._btn_set_default)
        form_vbox.addLayout(dist_row)

        # Load saved defaults
        _prefs = _load_prefs()
        try:
            if "temperature" in _prefs:
                self._slider_temp.setValue(int(float(_prefs["temperature"]) * 100))
            if "distinctive" in _prefs:
                self.chk_distinctive.setChecked(bool(_prefs["distinctive"]))
            if "nsfw" in _prefs:
                self.chk_nsfw.setChecked(bool(_prefs["nsfw"]))
        except (TypeError, ValueError):
            pass

        # Separator
        form_vbox.addSpacing(10)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {COLOR_BORDER_BRIGHT}; border: none;")
        form_vbox.addWidget(sep)
        form_vbox.addSpacing(8)

        # --- Character fields ---
        form_vbox.addWidget(_lbl_section("Character Details"))
        form_vbox.addSpacing(4)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Optional — model will invent one if blank")
        _field("Name", self.edit_name)

        self.edit_concept = _multi(
            "Required. Describe the character — who they are, their role, setting, tone, "
            "any key details. The more specific the better.",
            4,
        )
        _field("Concept / Description  *", self.edit_concept)

        self.edit_personality = _multi(
            "Personality traits, speech patterns, quirks, motivations (optional)", 3)
        _field("Personality", self.edit_personality)

        # Optional toggles
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

        # Card fields — edited directly (no raw JSON shown to the user). Each
        # widget is plain text bound to one key in self._last_card, so there is
        # no way to type something that breaks JSON syntax; _sync_output_field
        # writes straight into the dict on every keystroke.
        fields_header = QHBoxLayout()
        fields_header.addWidget(_lbl_section("Card Fields"))
        fields_header.addStretch()
        self._lbl_card_valid = QLabel("")
        self._lbl_card_valid.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt; font-weight: bold;")
        fields_header.addWidget(self._lbl_card_valid)
        out_vbox.addLayout(fields_header)
        out_vbox.addSpacing(4)

        def _out_field(label, widget, field_key):
            out_vbox.addWidget(_lbl(label))
            out_vbox.addSpacing(2)
            out_vbox.addWidget(widget)
            out_vbox.addSpacing(6)
            self._output_field_widgets[field_key] = widget
            widget.textChanged.connect(lambda: self._sync_output_field(field_key))

        self._output_field_widgets = {}

        self.out_name = QLineEdit()
        self.out_name.setPlaceholderText("Name will appear here after generation")
        _out_field("Name", self.out_name, "name")

        self.out_description = _multi("Description will appear here after generation", 4)
        _out_field("Description", self.out_description, "description")

        self.out_personality = _multi("Personality will appear here after generation", 4)
        _out_field("Personality", self.out_personality, "personality")

        self.out_scenario = _multi("Scenario will appear here after generation", 3)
        _out_field("Scenario", self.out_scenario, "scenario")

        self.out_first_mes = _multi("First message will appear here after generation", 3)
        _out_field("First Message", self.out_first_mes, "first_mes")

        self.out_mes_example = _multi("Dialogue examples will appear here after generation", 3)
        _out_field("Dialogue Examples", self.out_mes_example, "mes_example")

        # Only shown when the model's response fails to parse as JSON — there's
        # no structured card to populate the fields above with, so the raw
        # response is surfaced here instead of being lost. Editable so a
        # small formatting mistake can be hand-fixed and re-copied, same
        # intent the old read-only view's error message always claimed
        # ("...or edit manually") but never actually allowed.
        self._lbl_raw_fallback = _lbl("Raw output (could not parse as a card — edit and copy manually, or try again):")
        self._lbl_raw_fallback.setVisible(False)
        out_vbox.addWidget(self._lbl_raw_fallback)
        self._raw_fallback = QPlainTextEdit()
        self._raw_fallback.setFont(QFont(FONT_LOG_FAMILY, FONT_LOG_SIZE))
        self._raw_fallback.setFixedHeight(120)
        self._raw_fallback.setVisible(False)
        out_vbox.addWidget(self._raw_fallback)

        # Expand / Regenerate field row
        expand_row = QHBoxLayout()
        expand_row.setSpacing(6)
        expand_row.addWidget(_lbl("Field:"))
        self._expand_combo = QComboBox()
        self._expand_combo.setFixedHeight(24)
        self._expand_combo.setFixedWidth(112)
        self._expand_combo.addItem("Personality",   userData="personality")
        self._expand_combo.addItem("Scenario",      userData="scenario")
        self._expand_combo.addItem("First Message", userData="first_mes")
        expand_row.addWidget(self._expand_combo)
        expand_row.addSpacing(4)
        expand_row.addWidget(_lbl("Must include:"))
        self._edit_must_include = QLineEdit()
        self._edit_must_include.setPlaceholderText("traits, details to include (optional)")
        expand_row.addWidget(self._edit_must_include, 1)
        self._btn_expand = QPushButton("Expand")
        self._btn_expand.setFixedHeight(26)
        self._btn_expand.setEnabled(False)
        self._btn_expand.setToolTip("Make the current field text more detailed, keeping its direction.")
        self._btn_expand.clicked.connect(self._expand_field)
        expand_row.addWidget(self._btn_expand)
        self._btn_regenerate = QPushButton("Regenerate")
        self._btn_regenerate.setFixedHeight(26)
        self._btn_regenerate.setEnabled(False)
        self._btn_regenerate.setToolTip("Discard the current field and write a fresh alternative take.")
        self._btn_regenerate.clicked.connect(self._regenerate_field)
        expand_row.addWidget(self._btn_regenerate)
        out_vbox.addLayout(expand_row)

        # Word count / Condense row
        condense_row = QHBoxLayout()
        condense_row.setSpacing(6)
        self._lbl_wordcount = QLabel("")
        self._lbl_wordcount.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        condense_row.addWidget(self._lbl_wordcount)
        condense_row.addStretch()
        condense_row.addWidget(_lbl("Length:"))
        self._condense_length = QComboBox()
        self._condense_length.setFixedHeight(24)
        self._condense_length.setFixedWidth(90)
        self._condense_length.addItem("Short",  userData="short")
        self._condense_length.addItem("Medium", userData="medium")
        self._condense_length.addItem("Long",   userData="long")
        self._condense_length.setCurrentIndex(1)
        condense_row.addWidget(self._condense_length)
        self._btn_condense = QPushButton("Condense")
        self._btn_condense.setFixedHeight(26)
        self._btn_condense.setEnabled(False)
        self._btn_condense.setToolTip("Tighten the current field to the selected target length, keeping its substance.")
        self._btn_condense.clicked.connect(self._condense_field)
        condense_row.addWidget(self._btn_condense)
        out_vbox.addLayout(condense_row)

        self._expand_combo.currentIndexChanged.connect(self._update_field_wordcount)

        # Portrait prompt row
        pp_row = QHBoxLayout()
        self._btn_portrait_prompt = QPushButton("Portrait Prompt")
        self._btn_portrait_prompt.setFixedHeight(26)
        self._btn_portrait_prompt.setEnabled(False)
        self._btn_portrait_prompt.clicked.connect(self._get_portrait_prompt)
        pp_row.addWidget(self._btn_portrait_prompt)
        pp_row.addStretch()
        out_vbox.addLayout(pp_row)

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
            "Optional — if none selected, a dark placeholder\n"
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

        out_scroll = QScrollArea()
        out_scroll.setWidgetResizable(True)
        out_scroll.setWidget(out_widget)
        self._tabs.addTab(out_scroll, "  Output  ")

        # ── Bottom controls ───────────────────────────────────────────

        ctrl = QHBoxLayout()
        self._lbl_status = QLabel("Fill in a concept and click Generate.")
        self._lbl_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        ctrl.addWidget(self._lbl_status, 1)

        self._btn_import = QPushButton("Import Card")
        self._btn_import.setFixedHeight(28)
        self._btn_import.clicked.connect(self._import_card)
        ctrl.addWidget(self._btn_import)

        self.btn_generate = QPushButton("Generate")
        self.btn_generate.setObjectName("accent")
        self.btn_generate.setFixedHeight(28)
        self.btn_generate.clicked.connect(self._generate)
        ctrl.addWidget(self.btn_generate)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(28)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_generation)
        ctrl.addWidget(self.btn_cancel)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setFixedHeight(28)
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        ctrl.addWidget(self.btn_copy)

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
    # Public API
    # ------------------------------------------------------------------

    def set_model_hint(self, model_key: str | None):
        """Called by MainWindow each time the dialog is shown. Only reacts when
        the model/backend actually changed since the last call — otherwise
        simply reopening the cached dialog would repeatedly stomp a
        meaningful status (e.g. "Generation complete...") with this hint."""
        backend = self._backend_kind()
        hint_key = (model_key, backend)
        if hint_key == self._last_hint_key:
            return
        self._last_hint_key = hint_key

        if backend == "api":
            if self._last_card is None:
                self._set_status("Fill in a concept and click Generate.", COLOR_TEXT_MUTED)
            return
        if model_key and model_key != "chargen":
            self._set_status(
                "Note: general model loaded — CharGen model gives better card results.",
                COLOR_STATUS_STARTING,
            )
        elif self._last_card is None:
            self._set_status("Fill in a concept and click Generate.", COLOR_TEXT_MUTED)

    def set_api_model(self, model: str):
        """Called by MainWindow when the API model selection changes."""
        self._current_api_model = model
        if self._combo_backend:
            idx = self._combo_backend.findData("api")
            if idx >= 0:
                label = f"API  —  {model}" if model else "API  (remote)"
                self._combo_backend.setItemText(idx, label)

    def auto_select_backend(self, api_ready: bool, kobold_ready: bool):
        """Switch backend combo to the only available backend when there's no ambiguity."""
        if not self._combo_backend:
            return
        if api_ready and not kobold_ready:
            idx = self._combo_backend.findData("api")
            if idx >= 0:
                self._combo_backend.setCurrentIndex(idx)
        elif kobold_ready and not api_ready:
            idx = self._combo_backend.findData("local")
            if idx >= 0:
                self._combo_backend.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._cleanup_worker()
        event.accept()

    def _cleanup_worker(self):
        if self._worker is None:
            return
        if self._worker.isRunning():
            try:
                self._worker.finished.disconnect()
                self._worker.error.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._worker.terminate()
            self._worker.wait(2000)
            self._set_status("Generation cancelled.", COLOR_TEXT_MUTED)
            self._set_busy(False)
        self._worker = None

    def _cancel_generation(self):
        self._cleanup_worker()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool):
        """Central button-state switch for any in-flight worker (generate/expand/
        condense/portrait prompt). Keeps btn_generate, _btn_expand, _btn_regenerate,
        _btn_condense, _btn_portrait_prompt, _btn_import, and btn_cancel in sync so
        no completion path can leave one out of step. _btn_import is included so
        importing a card can't race a still-running worker's completion handler
        into overwriting the freshly-imported card with stale results."""
        has_card = self._last_card is not None
        self.btn_generate.setEnabled(not busy)
        self._btn_expand.setEnabled(has_card and not busy)
        self._btn_regenerate.setEnabled(has_card and not busy)
        self._btn_condense.setEnabled(has_card and not busy)
        self._btn_portrait_prompt.setEnabled(has_card and not busy)
        self._btn_import.setEnabled(not busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_cancel.setVisible(busy)

    def _backend_kind(self) -> str:
        return self._combo_backend.currentData() if self._combo_backend else "local"

    def _resolve_backend(self):
        """Returns (api_base, api_key, model) for whichever backend is currently
        active — shared by every action that talks to _GenerateWorker instead of
        each one re-deriving it independently."""
        if self._backend_kind() == "api":
            return API_BASE_URL, API_KEY, self._current_api_model
        return self._api_base, "", ""

    def _content_rating_suffix(self) -> str:
        return _NSFW_ALLOWED if self.chk_nsfw.isChecked() else _SFW_SAFE

    def _launch_worker(self, messages: list, on_done, max_tokens: int = 4096):
        """Resolves backend/temperature, constructs and wires a _GenerateWorker,
        and stores it on self._worker — shared by every generate/expand/
        regenerate/condense/portrait-prompt action."""
        api_base, api_key, model = self._resolve_backend()
        temperature = self._slider_temp.value() / 100.0
        self._worker = _GenerateWorker(
            api_base, messages, temperature,
            api_key=api_key, model=model, max_tokens=max_tokens, parent=self,
        )
        self._worker.finished.connect(on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _set_status(self, text: str, color: str = COLOR_TEXT_MUTED):
        self._lbl_status.setText(text)
        self._lbl_status.setStyleSheet(f"color: {color}; font-size: 8pt;")

    def _update_field_wordcount(self):
        """Live word count for whichever field is selected in the Expand/Condense
        combo — colored green/yellow/red against _FIELD_LENGTH_TARGETS so it's
        obvious at a glance when a field has ballooned past a reasonable length."""
        if not self._last_card:
            self._lbl_wordcount.setText("")
            return
        field_key = self._expand_combo.currentData()
        text = str(self._last_card.get(field_key, "") or "")
        count = _word_count(text)
        color = _wordcount_color(field_key, count)
        self._lbl_wordcount.setText(f"{count} words")
        self._lbl_wordcount.setStyleSheet(f"color: {color}; font-size: 8pt; font-weight: bold;")

    def _populate_output_fields(self):
        """Refreshes the editable Output-tab widgets from self._last_card (or
        clears them if there's no card). Signals are blocked during the refresh
        so setting these values doesn't loop back into _sync_output_field."""
        card = self._last_card or {}
        for field_key, widget in self._output_field_widgets.items():
            # str() guards against a malformed imported card where a field is
            # e.g. a list instead of a string — .setText()/.setPlainText()
            # would otherwise raise on a non-str value.
            text = str(card.get(field_key, "") or "")
            widget.blockSignals(True)
            if isinstance(widget, QLineEdit):
                widget.setText(text)
            else:
                widget.setPlainText(text)
            widget.blockSignals(False)
        self._lbl_raw_fallback.setVisible(False)
        self._raw_fallback.setVisible(False)
        self._update_card_validity()

    def _sync_output_field(self, field_key: str):
        """Writes a manually-edited Output-tab field straight back into
        self._last_card on every keystroke, so Expand/Regenerate/Condense/
        Save always see the latest manually-typed text. Since each widget only
        ever holds a plain string bound to one dict key, there is no way for a
        manual edit to produce invalid JSON — unlike editing raw JSON text
        directly would risk."""
        if self._last_card is None:
            return
        widget = self._output_field_widgets[field_key]
        text = widget.text() if isinstance(widget, QLineEdit) else widget.toPlainText()
        self._last_card[field_key] = text
        self._update_field_wordcount()
        self._update_card_validity()

    def _update_card_validity(self):
        """Simple health check for the editable Output fields. Syntactic JSON
        validity is guaranteed by construction now (the user only ever types
        into plain-text field boxes, never raw JSON), so this instead flags
        the more useful question: does the card have the minimum SillyTavern
        actually needs to be useful."""
        if self._last_card is None:
            self._lbl_card_valid.setText("")
            return
        missing = []
        for field_key in _REQUIRED_OUTPUT_FIELDS:
            widget = self._output_field_widgets[field_key]
            text = widget.text() if isinstance(widget, QLineEdit) else widget.toPlainText()
            if not text.strip():
                missing.append(field_key)
        if missing:
            self._lbl_card_valid.setText(f"●  Missing {', '.join(missing)}")
            self._lbl_card_valid.setStyleSheet(
                f"color: {COLOR_STATUS_ERROR}; font-size: 8pt; font-weight: bold;"
            )
        else:
            self._lbl_card_valid.setText("●  Card valid")
            self._lbl_card_valid.setStyleSheet(
                f"color: {COLOR_STATUS_RUNNING}; font-size: 8pt; font-weight: bold;"
            )

    def _safe_name(self) -> str:
        name = (self._last_card or {}).get("name") or self.edit_name.text().strip() or "Unknown"
        return re.sub(r'[\\/:*?"<>|]', "_", str(name))

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select output folder", self._output_dir)
        if d:
            self._output_dir = d
            self._lbl_outdir.setText(d)

    def _on_temp_changed(self, v: int):
        self._lbl_temp_val.setText(f"{v / 100:.2f}")

    def _save_defaults(self):
        ok = _save_prefs({
            "temperature": self._slider_temp.value() / 100.0,
            "distinctive": self.chk_distinctive.isChecked(),
            "nsfw": self.chk_nsfw.isChecked(),
        })
        if ok:
            self._set_status("Generation defaults saved.", COLOR_STATUS_RUNNING)
        else:
            self._set_status("Could not save defaults — check file permissions.", COLOR_STATUS_ERROR)

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

        use_scenario    = self.chk_scenario.isChecked()
        use_first_mes   = self.chk_first_mes.isChecked()
        use_examples    = self.chk_mes_example.isChecked()
        use_distinctive = self.chk_distinctive.isChecked()
        use_nsfw        = self.chk_nsfw.isChecked()

        system = _build_system_prompt(
            distinctive=use_distinctive,
            scenario=use_scenario,
            first_mes=use_first_mes,
            mes_example=use_examples,
            nsfw=use_nsfw,
        )

        fields = {
            "name":        self.edit_name.text().strip(),
            "concept":     concept,
            "personality": self.edit_personality.toPlainText().strip(),
            "scenario":    self.edit_scenario.toPlainText().strip() if use_scenario else "",
            "first_mes":   self.edit_first_mes.toPlainText().strip() if use_first_mes else "",
            "mes_example": self.edit_mes_example.toPlainText().strip() if use_examples else "",
        }

        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": _build_user_prompt(fields)},
        ]

        self.btn_copy.setEnabled(False)
        self.btn_save_json.setEnabled(False)
        self.btn_save_png.setEnabled(False)
        self._set_busy(True)
        self._set_status("Generating… this may take a minute.", COLOR_STATUS_STARTING)

        # Full-card generation can populate up to 6 fields at once (more with
        # Distinctive/NSFW encouraging longer prose) — a bigger budget than the
        # single-field edit actions below need, so it doesn't risk truncating
        # mid-JSON the way the shared 4096 default would.
        self._launch_worker(messages, self._on_done, max_tokens=8192)

    def _on_done(self, raw: str):
        self._worker = None
        self._last_card = _extract_json(raw)

        if self._last_card:
            self._populate_output_fields()
            self.btn_save_json.setEnabled(True)
            self.btn_save_png.setEnabled(True)
            self._set_status(
                "Generation complete. Save as PNG (with portrait) or JSON.",
                COLOR_STATUS_RUNNING,
            )
        elif raw:
            # No structured card to show in the field boxes — surface the raw
            # response in the fallback view instead of losing it, and let the
            # user hand-fix/copy it (previously "read-only", so "edit
            # manually" in this message was never actually possible).
            self._lbl_raw_fallback.setVisible(True)
            self._raw_fallback.setVisible(True)
            self._raw_fallback.setPlainText(raw)
            self._update_card_validity()
            self._set_status(
                "Could not parse JSON — raw output shown below. Try regenerating or edit manually.",
                COLOR_STATUS_ERROR,
            )
        else:
            self._populate_output_fields()
            self._set_status(
                "No content returned — model may have refused or been rate-limited.",
                COLOR_STATUS_ERROR,
            )

        self.btn_copy.setEnabled(bool(self._last_card or raw))
        self._update_field_wordcount()
        self._tabs.setCurrentIndex(1)
        self._set_busy(False)

    def _on_error(self, msg: str):
        self._worker = None
        self._set_status(f"Error: {msg}", COLOR_STATUS_ERROR)
        self._set_busy(False)

    def _expand_field(self):
        if not self._last_card:
            return

        field_key = self._expand_combo.currentData()
        sys_prompt, user_instruction = _EXPAND_CONFIG[field_key]
        sys_prompt += self._content_rating_suffix()
        must_include = self._edit_must_include.text().strip()

        user_content = (
            f"Character card:\n{json.dumps(self._last_card, indent=2, ensure_ascii=False)}\n\n"
            + user_instruction
        )
        if must_include:
            user_content += f"\n\nThese specific elements must be present: {must_include}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": user_content},
        ]

        self._expanding_field = field_key
        self._expanding_verb  = "expanded"
        self._set_busy(True)
        self._set_status(
            f"Expanding {self._expand_combo.currentText().lower()}…",
            COLOR_STATUS_STARTING,
        )
        self._launch_worker(messages, self._on_expand_done)

    def _regenerate_field(self):
        """Discard the current value of the selected field and request a fresh
        alternative take, grounded in the rest of the card but not anchored to the
        text being replaced (which is deliberately omitted from the prompt)."""
        if not self._last_card:
            return

        field_key = self._expand_combo.currentData()
        sys_prompt, user_instruction = _REGENERATE_CONFIG[field_key]
        sys_prompt += self._content_rating_suffix()
        must_include = self._edit_must_include.text().strip()

        context_card = {k: v for k, v in self._last_card.items() if k != field_key}
        user_content = (
            f"Character card (other fields, for context):\n"
            f"{json.dumps(context_card, indent=2, ensure_ascii=False)}\n\n"
            + user_instruction
        )
        if must_include:
            user_content += f"\n\nThese specific elements must be present: {must_include}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": user_content},
        ]

        self._expanding_field = field_key
        self._expanding_verb  = "regenerated"
        self._set_busy(True)
        self._set_status(
            f"Regenerating {self._expand_combo.currentText().lower()}…",
            COLOR_STATUS_STARTING,
        )
        self._launch_worker(messages, self._on_expand_done)

    def _condense_field(self):
        """Tighten the current field to the selected target length instead of
        elaborating (Expand) or replacing it wholesale (Regenerate) — same
        full-card-context shape as _expand_field since condensing benefits from
        the rest of the card for keeping voice/detail consistent."""
        if not self._last_card:
            return

        field_key = self._expand_combo.currentData()
        length_key = self._condense_length.currentData()
        sys_prompt, user_template = _CONDENSE_CONFIG[field_key]
        sys_prompt += self._content_rating_suffix()
        target = _FIELD_LENGTH_TARGETS[field_key][length_key]
        user_instruction = user_template.format(target=target)
        must_include = self._edit_must_include.text().strip()

        user_content = (
            f"Character card:\n{json.dumps(self._last_card, indent=2, ensure_ascii=False)}\n\n"
            + user_instruction
        )
        if must_include:
            user_content += f"\n\nThese specific elements must be present: {must_include}"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": user_content},
        ]

        self._expanding_field = field_key
        self._expanding_verb  = "condensed"
        self._set_busy(True)
        self._set_status(
            f"Condensing {self._expand_combo.currentText().lower()} (~{target} words)…",
            COLOR_STATUS_STARTING,
        )
        self._launch_worker(messages, self._on_expand_done)

    def _on_expand_done(self, raw: str):
        self._worker = None
        raw = raw.strip()
        if not raw or self._last_card is None:
            self._set_status("No content returned — try again.", COLOR_STATUS_ERROR)
            self._set_busy(False)
            return
        self._last_card[self._expanding_field] = raw
        self._populate_output_fields()
        # Look up the label for the field actually edited (self._expanding_field,
        # captured at kickoff) rather than re-reading the combo live — if the
        # user switched Field to something else while this request was in
        # flight, the combo's current selection is no longer the field that was
        # just written, and would report the wrong name here.
        combo_idx = self._expand_combo.findData(self._expanding_field)
        label = self._expand_combo.itemText(combo_idx) if combo_idx >= 0 else self._expanding_field
        self._set_status(f"{label} {self._expanding_verb}.", COLOR_STATUS_RUNNING)
        self._update_field_wordcount()
        self._set_busy(False)

    def _get_portrait_prompt(self):
        if not self._last_card:
            return

        portrait_sys_prompt = (
            "You are an expert at writing image generation prompts for AI art tools "
            "like Stable Diffusion and Midjourney. You write detailed, evocative portrait "
            "prompts using comma-separated descriptors. "
        ) + self._content_rating_suffix()

        messages = [
            {"role": "system", "content": portrait_sys_prompt},
            {"role": "user", "content": (
                f"Character card:\n{json.dumps(self._last_card, indent=2, ensure_ascii=False)}\n\n"
                "Write a detailed portrait prompt for an AI image generator. Include: physical "
                "appearance (face, hair, eyes, skin, build), clothing and accessories, art style "
                "suited to the character's nature, mood and expression, lighting, color palette, "
                "and composition. Use comma-separated descriptors suitable for Stable Diffusion. "
                "Return only the prompt — no explanation, no preamble, no labels."
            )},
        ]

        self._set_busy(True)
        self._set_status("Generating portrait prompt…", COLOR_STATUS_STARTING)
        self._launch_worker(messages, self._on_portrait_prompt_done)

    def _on_portrait_prompt_done(self, raw: str):
        self._worker = None
        raw = raw.strip()
        self._set_busy(False)

        if not raw:
            self._set_status("No prompt returned — try again.", COLOR_STATUS_ERROR)
            return

        QApplication.clipboard().setText(raw)
        self._set_status("Portrait prompt generated — copied to clipboard.", COLOR_STATUS_RUNNING)

        dlg = QDialog(self)
        dlg.setWindowTitle("Portrait Prompt")
        dlg.setMinimumWidth(520)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setStyleSheet(_STYLE)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(8)

        hint = QLabel(
            "Stable Diffusion / image generation prompt — copied to clipboard.\n"
            "Edit before use if needed."
        )
        hint.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        hint.setWordWrap(True)
        vbox.addWidget(hint)

        edit = QPlainTextEdit()
        edit.setPlainText(raw)
        edit.setFont(QFont(FONT_LOG_FAMILY, FONT_LOG_SIZE))
        edit.setMinimumHeight(120)
        vbox.addWidget(edit)

        # -- Generate Image, using this app's own in-process Image Gen backend --

        gen_state = {"worker": None, "image_path": None}

        gen_status = QLabel(
            "" if SDXL_MODEL_PATH else
            "Image Gen isn't configured — set a checkpoint in Settings first."
        )
        gen_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
        gen_status.setWordWrap(True)
        vbox.addWidget(gen_status)

        gen_preview = QLabel()
        gen_preview.setFixedSize(220, 220)
        gen_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gen_preview.setStyleSheet(_PORTRAIT_PLACEHOLDER_STYLE)
        gen_preview.setVisible(False)
        vbox.addWidget(gen_preview, alignment=Qt.AlignmentFlag.AlignHCenter)

        btn_generate_image = QPushButton("Generate Image")
        btn_generate_image.setFixedHeight(26)
        btn_generate_image.setEnabled(bool(SDXL_MODEL_PATH))
        btn_cancel_gen = QPushButton("Cancel")
        btn_cancel_gen.setFixedHeight(26)
        btn_cancel_gen.setVisible(False)
        btn_use_portrait = QPushButton("Use as Portrait")
        btn_use_portrait.setFixedHeight(26)
        btn_use_portrait.setEnabled(False)

        def set_gen_busy(busy: bool):
            btn_generate_image.setEnabled(not busy and bool(SDXL_MODEL_PATH))
            btn_cancel_gen.setVisible(busy)
            btn_cancel_gen.setEnabled(busy)
            edit.setEnabled(not busy)

        def on_gen_progress(text: str):
            gen_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
            gen_status.setText(text)

        def on_gen_done(path: str):
            gen_state["image_path"] = path
            gen_preview.setPixmap(QPixmap(path).scaled(
                220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))
            gen_preview.setVisible(True)
            gen_status.setStyleSheet(f"color: {COLOR_STATUS_RUNNING}; font-size: 8pt;")
            gen_status.setText("Done.")
            set_gen_busy(False)
            btn_use_portrait.setEnabled(True)
            gen_state["worker"] = None

        def on_gen_error(message: str):
            gen_status.setStyleSheet(f"color: {COLOR_STATUS_ERROR}; font-size: 8pt;")
            gen_status.setText(f"Error: {message}")
            set_gen_busy(False)
            gen_state["worker"] = None

        def on_gen_cancelled():
            gen_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
            gen_status.setText("Cancelled.")
            set_gen_busy(False)
            gen_state["worker"] = None

        def start_generate():
            if gen_state["worker"] is not None:
                return
            prompt = edit.toPlainText().strip()
            if not prompt:
                return
            set_gen_busy(True)
            gen_status.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 8pt;")
            gen_status.setText("Starting...")
            # Parented to self (the persistent CharGenDialog), not dlg — dlg
            # is WA_DeleteOnClose and transient, so a worker parented to it
            # would risk Qt destroying a still-running QThread if the popup
            # is closed mid-generation.
            worker = ImageGenWorker(prompt, parent=self)
            worker.progress.connect(on_gen_progress)
            worker.finished.connect(on_gen_done)
            worker.error.connect(on_gen_error)
            worker.cancelled.connect(on_gen_cancelled)
            gen_state["worker"] = worker
            worker.start()

        def cancel_generate():
            if gen_state["worker"] is not None:
                gen_status.setText("Cancelling...")
                gen_state["worker"].request_cancel()

        def use_as_portrait():
            path = gen_state["image_path"]
            if not path:
                return
            px = QPixmap(path)
            if px.isNull():
                return
            self._portrait_path = path
            self._portrait_preview.setPixmap(
                px.scaled(96, 96,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
            self._portrait_preview.setText("")
            self._btn_clear_portrait.setEnabled(True)
            dlg.accept()

        btn_generate_image.clicked.connect(start_generate)
        btn_cancel_gen.clicked.connect(cancel_generate)
        btn_use_portrait.clicked.connect(use_as_portrait)

        gen_btn_row = QHBoxLayout()
        gen_btn_row.addWidget(btn_generate_image)
        gen_btn_row.addWidget(btn_cancel_gen)
        gen_btn_row.addWidget(btn_use_portrait)
        gen_btn_row.addStretch()
        vbox.addLayout(gen_btn_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_copy = QPushButton("Copy")
        btn_copy.setFixedHeight(26)
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(edit.toPlainText()))
        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_close)
        vbox.addLayout(btn_row)

        def on_dlg_close(event):
            # This popup is transient (WA_DeleteOnClose) but the worker is
            # parented to self, not dlg, so it survives the popup closing
            # and keeps running/cancelling in the background. Its signal
            # closures (on_gen_done etc.) touch this popup's own widgets
            # though, which WILL be destroyed once dlg closes — disconnect
            # first so a signal firing after close can't touch dead widgets.
            worker = gen_state["worker"]
            if worker is not None:
                try:
                    worker.progress.disconnect()
                    worker.finished.disconnect()
                    worker.error.disconnect()
                    worker.cancelled.disconnect()
                except (RuntimeError, TypeError):
                    pass
                worker.request_cancel()
            event.accept()
        dlg.closeEvent = on_dlg_close

        dlg.exec()

    def _import_card(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Character Card", "",
            "Character cards (*.png *.json);;PNG files (*.png);;JSON files (*.json)"
        )
        if not path:
            return

        try:
            if path.lower().endswith(".png"):
                from PIL import Image
                img = Image.open(path)
                chara_b64 = img.info.get("chara", "")
                if not chara_b64:
                    QMessageBox.warning(
                        self, "Import",
                        "No character data found in this PNG.\n"
                        "This may not be a SillyTavern character card."
                    )
                    return
                card = json.loads(base64.b64decode(chara_b64).decode("utf-8"))
            else:
                with open(path, encoding="utf-8") as fh:
                    card = json.load(fh)
            # Unwrap v2 spec wrapper for both PNG and JSON
            if isinstance(card, dict) and card.get("spec") == "chara_card_v2":
                card = card.get("data", card)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Could not read card:\n{e}")
            return

        if not isinstance(card, dict):
            QMessageBox.warning(self, "Import", "File does not contain a valid character card.")
            return

        self._last_card = card
        self._populate_output_fields()
        self.btn_copy.setEnabled(True)
        self.btn_save_json.setEnabled(True)
        self.btn_save_png.setEnabled(True)
        self._update_field_wordcount()
        self._set_busy(False)
        self._set_status(f"Imported: {os.path.basename(path)}", COLOR_STATUS_RUNNING)
        self._tabs.setCurrentIndex(1)

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _copy_to_clipboard(self):
        if self._last_card:
            text = json.dumps(self._last_card, indent=2, ensure_ascii=False)
        else:
            # Parse-failure fallback path — no structured card, copy whatever
            # raw text is shown there instead.
            text = self._raw_fallback.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._set_status("Copied to clipboard.", COLOR_STATUS_RUNNING)

    # ------------------------------------------------------------------
    # Save — JSON
    # ------------------------------------------------------------------

    def _save_json(self):
        if not self._last_card:
            return
        fallback = self.edit_name.text().strip()
        card = _merge_last_card(_to_st_card(self._last_card, fallback), self._last_card)
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
