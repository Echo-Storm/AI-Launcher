# constants.py — AI Writing Tools Launcher

import json
import os

APP_NAME     = "AI Writing Tools"
APP_VERSION  = "1.2.0"
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

_kob = _cfg.get("koboldcpp", {})
_st  = _cfg.get("sillytavern", {})
_cg  = _cfg.get("chargen", {})
_api = _cfg.get("api", {})

# ---------------------------------------------------------------------------
# Models list — first entry is the startup default
# ---------------------------------------------------------------------------

MODELS: list[dict] = _cfg.get("models", [])

# ---------------------------------------------------------------------------
# KoboldCpp
# ---------------------------------------------------------------------------

KOBOLD_EXE      = _kob.get("exe", "")
KOBOLD_HOST     = _kob.get("host", "127.0.0.1")
KOBOLD_PORT     = int(_kob.get("port", 5001))
KOBOLD_API_BASE = f"http://{KOBOLD_HOST}:{KOBOLD_PORT}"


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
    if _kob.get("use_vulkan", False):
        args.append("--usevulkan")
    if _kob.get("flash_attention", True):
        args.append("--flashattention")
    if _kob.get("quiet", True):
        args.append("--quiet")
    return args


KOBOLD_READY_STRINGS = ["please connect to custom endpoint", "starting kobold api on port"]

# ---------------------------------------------------------------------------
# SillyTavern
# ---------------------------------------------------------------------------

SILLYTAVERN_DIR  = _st.get("dir", "")
SILLYTAVERN_ARGS = ["server.js"]
SILLYTAVERN_URL  = f"http://127.0.0.1:{_st.get('port', 8000)}"
SILLYTAVERN_READY_STRINGS = ["sillytavern is listening", "listening on", f":{_st.get('port', 8000)}"]

# ---------------------------------------------------------------------------
# CharGen
# ---------------------------------------------------------------------------

CHARGEN_OUTPUT_DIR = _cg.get(
    "output_dir",
    r"D:\Applications\SillyTavern\data\default-user\characters",
)

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

FONT_UI_FAMILY  = "Segoe UI"
FONT_UI_SIZE    = 9
FONT_LOG_FAMILY = "Consolas"
FONT_LOG_SIZE   = 8
