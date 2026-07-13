# constants.py — AI Writing Tools Launcher

import json
import os

APP_NAME     = "AI Writing Tools"
APP_VERSION  = "1.8.3"
LOG_FILENAME = "AI_Launcher_Log.txt"

# ---------------------------------------------------------------------------
# Load config.json from the same directory as this file
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "config.json")

try:
    with open(_CONFIG_PATH, encoding="utf-8") as _f:
        _cfg = json.load(_f)
except FileNotFoundError:
    raise SystemExit(f"ERROR: config.json not found at {_CONFIG_PATH}")
except json.JSONDecodeError as _e:
    raise SystemExit(f"ERROR: config.json is invalid JSON: {_e}")

if not isinstance(_cfg, dict):
    raise SystemExit(f"ERROR: config.json must be a JSON object, got {type(_cfg).__name__}")


def _dict_section(key: str) -> dict:
    """A section present but with the wrong type (e.g. hand-edited to null)
    falls back to {} — same graceful-default treatment as a missing section
    — rather than crashing the whole app before the window ever shows."""
    val = _cfg.get(key, {})
    return val if isinstance(val, dict) else {}


_kob = _dict_section("koboldcpp")
_st  = _dict_section("sillytavern")
_cg  = _dict_section("chargen")
_api = _dict_section("api")
_sdxl = _dict_section("sdxl")

# ---------------------------------------------------------------------------
# Models list — first entry is the startup default
# ---------------------------------------------------------------------------

_raw_models = _cfg.get("models", [])
if not isinstance(_raw_models, list):
    _raw_models = []
MODELS: list[dict] = []
for _m in _raw_models:
    if isinstance(_m, dict) and _m.get("name") and _m.get("path"):
        MODELS.append(_m)
    else:
        print(f"WARNING: skipping malformed models entry in config.json: {_m!r}")

# ---------------------------------------------------------------------------
# KoboldCpp
# ---------------------------------------------------------------------------

KOBOLD_EXE       = _kob.get("exe", "")
KOBOLD_HOST      = _kob.get("host", "127.0.0.1")
KOBOLD_PORT      = int(_kob.get("port", 5001))
KOBOLD_API_BASE  = f"http://{KOBOLD_HOST}:{KOBOLD_PORT}"
EMBEDDINGS_MODEL = _kob.get("embeddings_model", "")


def build_kobold_args(model_path: str) -> list[str]:
    args = [
        "--model",       model_path,
        "--gpulayers",   str(_kob.get("gpu_layers",   40)),
        "--contextsize", str(_kob.get("context_size", 6144)),
        "--port",        str(KOBOLD_PORT),
        "--host",        KOBOLD_HOST,
    ]
    if _kob.get("use_cuda", True):
        args.append("--usecublas")
    elif _kob.get("use_vulkan", False):
        args.append("--usevulkan")
    if _kob.get("flash_attention", True):
        args.append("--flashattention")
    if _kob.get("quiet", True):
        args.append("--quiet")
    if EMBEDDINGS_MODEL and os.path.isfile(EMBEDDINGS_MODEL):
        args += ["--embeddingsmodel", EMBEDDINGS_MODEL]
    return args


KOBOLD_READY_STRINGS = ["please connect to custom endpoint", "starting kobold api on port"]

# ---------------------------------------------------------------------------
# SillyTavern
# ---------------------------------------------------------------------------

SILLYTAVERN_DIR  = _st.get("dir", "")
SILLYTAVERN_ARGS = ["server.js"]
SILLYTAVERN_URL  = f"http://127.0.0.1:{_st.get('port', 8000)}"
SILLYTAVERN_READY_STRINGS = ["sillytavern is listening", "listening on"]

# ---------------------------------------------------------------------------
# SDXL (in-process diffusers backend — txt2img + LoRA + TI + ESRGAN hires-fix)
# ---------------------------------------------------------------------------

# Scheduler presets offered in the Settings UI — key -> display label.
# imagegen_engine.py maps each key to a diffusers scheduler class/kwargs.
SDXL_SCHEDULER_CHOICES = [
    ("dpmpp_2m_karras",  "DPM++ 2M Karras"),
    ("euler_a",          "Euler a"),
    ("dpmpp_sde_karras", "DPM++ SDE Karras"),
    ("unipc",            "UniPC"),
]

# Single source of truth for both config.json fallbacks and the Settings UI's
# "Restore Defaults" button (settings_dialog.py's Image Gen tab).
SDXL_GENERATION_DEFAULTS = {
    "base_width":    1024,
    "base_height":   1024,
    "steps":         30,
    "cfg_scale":     7.0,
    "hires_scale":   1.5,
    "hires_denoise": 0.45,
    "scheduler":     "dpmpp_2m_karras",
}

SDXL_DIR            = _sdxl.get("dir", "")
SDXL_MODEL_PATH     = _sdxl.get("model_path", "")
SDXL_LORAS: list[dict] = _sdxl.get("loras", [])
SDXL_TEXTUAL_INVERSIONS: list[dict] = _sdxl.get("textual_inversions", [])
SDXL_UPSCALER_PATH  = _sdxl.get("upscaler_path", "")
# Falls back to a path under this app's own folder (not just SDXL_DIR) so it's
# never empty even when the user has only ever set a checkpoint via the
# Settings UI's Output Directory field and never touched sdxl.dir.
SDXL_OUTPUT_DIR     = _sdxl.get("output_dir") or (
    os.path.join(SDXL_DIR, "output") if SDXL_DIR else os.path.join(_HERE, "SDXL", "output")
)
SDXL_BASE_WIDTH     = int(_sdxl.get("base_width", SDXL_GENERATION_DEFAULTS["base_width"]))
SDXL_BASE_HEIGHT    = int(_sdxl.get("base_height", SDXL_GENERATION_DEFAULTS["base_height"]))
SDXL_HIRES_SCALE    = float(_sdxl.get("hires_scale", SDXL_GENERATION_DEFAULTS["hires_scale"]))
SDXL_HIRES_DENOISE  = float(_sdxl.get("hires_denoise", SDXL_GENERATION_DEFAULTS["hires_denoise"]))
SDXL_STEPS          = int(_sdxl.get("steps", SDXL_GENERATION_DEFAULTS["steps"]))
SDXL_CFG_SCALE      = float(_sdxl.get("cfg_scale", SDXL_GENERATION_DEFAULTS["cfg_scale"]))
SDXL_SCHEDULER      = _sdxl.get("scheduler", SDXL_GENERATION_DEFAULTS["scheduler"])
SDXL_API_PORT       = int(_sdxl.get("port", 7860))
SDXL_ALLOW_ST_OVERRIDE = bool(_sdxl.get("allow_st_override", False))

# ---------------------------------------------------------------------------
# CharGen
# ---------------------------------------------------------------------------

CHARGEN_OUTPUT_DIR = _cg.get("output_dir", "")

# ---------------------------------------------------------------------------
# Remote API backend (OpenRouter, Groq, LM Studio, Ollama, etc.)
# Optional — leave "api" block out of config.json to disable.
# ---------------------------------------------------------------------------

API_BASE_URL = _api.get("base_url", "").rstrip("/")
API_KEY      = _api.get("api_key",  "")
API_MODEL    = _api.get("model",    "")

# ---------------------------------------------------------------------------
# EchoStorm dark theme
# ---------------------------------------------------------------------------

COLOR_BG            = "#181818"
COLOR_PANEL         = "#1f1f1f"
COLOR_PANEL_ALT     = "#232323"
COLOR_HEADER_BAR    = "#2d1f00"
COLOR_ACCENT        = "#7cb342"
COLOR_ACCENT_DIM    = "#4a6b28"
COLOR_TEXT          = "#e8e8e8"
COLOR_TEXT_MUTED    = "#666666"
COLOR_BUTTON_BG     = "#282828"
COLOR_BUTTON_HOVER  = "#323232"
COLOR_BORDER        = "#2a2a2a"
COLOR_BORDER_BRIGHT = "#3a3a3a"

COLOR_STATUS_STOPPED  = "#555555"
COLOR_STATUS_STARTING = "#f59e0b"
COLOR_STATUS_RUNNING  = "#7cb342"
COLOR_STATUS_ERROR    = "#e05050"

COLOR_DANGER_BG       = "#3d1a1a"
COLOR_DANGER_BG_HOVER = "#5a2020"
COLOR_DONATE_LINK     = "#c0665a"
COLOR_LOG_KOBOLD      = "#7c6fcd"
COLOR_LOG_ST          = "#5ba0c8"
COLOR_LOG_IMAGEGEN    = "#c77dd4"
COLOR_LOG_API         = "#4a9edd"

FONT_UI_FAMILY  = "Segoe UI"
FONT_UI_SIZE    = 9
FONT_LOG_FAMILY = "Consolas"
FONT_LOG_SIZE   = 8
