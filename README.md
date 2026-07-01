# AI Writing Tools

A PyQt6 desktop launcher for local AI writing sessions — manages KoboldCpp and SillyTavern as background services, with a remote API backend option and a built-in character card generator.

![Python](https://img.shields.io/badge/python-3.11+-blue) ![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green) ![Version](https://img.shields.io/badge/version-1.2.0-violet) ![License](https://img.shields.io/badge/license-MIT-purple)

> If this is useful to you: [☕ Ko-fi](https://ko-fi.com/xechostormx)

---

## What it does

**Backends** — pick one or use both:
- **KoboldCpp** — local GGUF inference. Select a model from your config list, hit Start, watch the log for ready signal.
- **API** — any OpenAI-compatible remote endpoint (OpenRouter, Groq, LM Studio, Ollama, etc.). Hit Activate to connect and populate available models. Deactivates without restarting the app.

**Tools** — work with whichever backend is active:
- **SillyTavern** — Start/Stop/Open buttons. The Start button highlights when a backend is ready to signal it's a good time to launch.
- **Character Card Generator** — built-in dialog for generating SillyTavern character cards. Exports as ST-native PNG (portrait embedded in `chara` tEXt chunk) or flat JSON.
- **Kill All** — force-terminates KoboldCpp and SillyTavern in one click.

**Settings GUI** — configure everything without touching JSON: paths, ports, GPU options, API credentials, model list, output directory.

---

## Requirements

- Python 3.11+
- PyQt6, Pillow (see `requirements.txt`)
- [KoboldCpp](https://github.com/LostRuins/koboldcpp) — for local inference
- [SillyTavern](https://github.com/SillyTavern/SillyTavern) + Node.js — for the chat frontend
- A GGUF model (tested with Cydonia 24B Q4_K_M)
- Optionally: a CharGen-specific model (e.g. CharGen v3) for better card output

API mode requires no local models — just a URL and key.

---

## Setup

1. Clone the repo
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Copy `config.example.json` to `config.json` and fill in your paths
5. Run:
   ```
   python main.py
   ```
   or double-click `launch.bat`

---

## Config

All paths and settings live in `config.json` (gitignored — copy from `config.example.json`). Everything in this file is also editable via the **Settings** button in the app header.

```json
{
    "models": [
        { "name": "My Writing Model", "key": "writing", "path": "C:\\...\\model.gguf" },
        { "name": "CharGen v3",       "key": "chargen", "path": "C:\\...\\chargen.gguf" }
    ],
    "koboldcpp": {
        "exe":             "C:\\...\\koboldcpp.exe",
        "port":            5001,
        "host":            "127.0.0.1",
        "gpu_layers":      40,
        "context_size":    8192,
        "use_cuda":        true,
        "use_vulkan":      false,
        "flash_attention": true,
        "quiet":           true
    },
    "sillytavern": {
        "dir":  "C:\\...\\SillyTavern",
        "port": 8000
    },
    "api": {
        "base_url": "https://api.groq.com/openai",
        "api_key":  "gsk_...",
        "model":    "llama-3.3-70b-versatile"
    },
    "chargen": {
        "output_dir": "C:\\...\\SillyTavern\\data\\default-user\\characters"
    }
}
```

The `api` block is optional — omit it to disable the API backend entirely.

---

## Character Card Generator

Accessed via **Open CharGen** in the Tools section. Works with KoboldCpp or API — the backend selector auto-switches to whichever is active when there's no ambiguity.

- **Creativity slider** — temperature 0.60 (Safe) to 1.20 (Creative), default 0.85. A reference notch marks 0.75 (standard).
- **Distinctive toggle** — stronger system prompt that discourages clichés and pushes for unique voices.
- **Set as default** — saves temperature + distinctive state to `chargen_prefs.json`.
- Scenario, First Message, and Dialogue Examples are optional toggles (off by default).
- Pick a portrait image or leave blank for a dark placeholder.
- Save as **PNG** (ST-native, portrait embedded, shows in character browser) or **JSON** (flat v1 card).
- **Copy** copies raw output even if JSON parsing fails.

---

## Notes

- `config.json` is gitignored — paths and API keys stay local.
- Log writes to `AI_Launcher_Log.txt` next to the script on each run.
- Settings changes take effect on next launch (constants are loaded at import time). The API tab has a live **Test Connection** button that uses field values before saving.
