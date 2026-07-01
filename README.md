# AI Launcher

A PyQt6 desktop launcher for local AI writing sessions — manages KoboldCpp and SillyTavern as background services, with a built-in character card generator.

![Python](https://img.shields.io/badge/python-3.11+-blue) ![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green) ![Version](https://img.shields.io/badge/version-1.1.0-violet) ![License](https://img.shields.io/badge/license-MIT-purple)

---

## What it does

- **One-click launch** — Start KoboldCpp and SillyTavern together. SillyTavern waits automatically until KoboldCpp signals ready before opening.
- **Model switching** — Configure multiple GGUF models in `config.json`. The launcher handles the right model for the right task.
- **Character Card Generator** — Built-in dialog for generating SillyTavern character cards using a local model. Exports as ST-native PNG (with embedded portrait) or flat JSON. Hitting the Card Generator button automatically loads the configured CharGen model.
- **Dark violet theme** — Styled UI, not a bare window.

---

## Requirements

- Python 3.11+
- [KoboldCpp](https://github.com/LostRuins/koboldcpp) installed separately
- [SillyTavern](https://github.com/SillyTavern/SillyTavern) installed separately
- Node.js (for SillyTavern)
- A GGUF model for writing (tested with Cydonia 24B Q4_K_M)
- Optionally: [CharGen v3](https://huggingface.co/thedrummer) for the card generator

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

All paths and settings live in `config.json` (not committed — copy from `config.example.json`).

```json
{
    "models": [
        { "name": "My Writing Model", "key": "writing", "path": "C:\\...\\model.gguf" },
        { "name": "CharGen v3",       "key": "chargen", "path": "C:\\...\\chargen.gguf" }
    ],
    "koboldcpp": {
        "exe": "C:\\...\\koboldcpp.exe",
        "gpu_layers": 40,
        "context_size": 8192,
        "port": 5001,
        "use_cuda": true,
        "flash_attention": true
    },
    "chargen": {
        "output_dir": "C:\\...\\SillyTavern\\data\\default-user\\characters"
    },
    "sillytavern": {
        "dir": "C:\\...\\SillyTavern",
        "port": 8000
    }
}
```

The `key` field on each model entry is how the launcher tells which model to load for which purpose — `"chargen"` is reserved for the card generator.

---

## Character Card Generator

Accessed via the **Card Generator** button on the KoboldCpp card. Works with any model currently loaded — the CharGen model produces the best results, but Cydonia or any other GGUF will also work. When clicking while KoboldCpp is stopped, it auto-loads the `chargen` model from config.

- **Creativity slider** — controls temperature (0.60 Safe to 1.20 Creative, default 0.85)
- **Distinctive character toggle** — enables a stronger system prompt that discourages clichés and pushes for unique voices
- Fill in a character concept — the more specific, the better
- Scenario, First Message, and Dialogue Examples are optional toggles (off by default)
- Pick a portrait image or leave blank for a dark placeholder
- **Copy** — copies raw generated output to clipboard (works even if JSON parsing fails)
- Save as **PNG** (embedded `chara` tEXt chunk — ST's native format, shows portrait in the character browser) or **JSON** (flat v1 card for manual editing)

---

## Notes

- `config.json` is gitignored — your model paths stay local.
- Log file writes to `AI_Launcher_Log.txt` next to the executable on each run.
- The Card Generator can use any loaded model, but the `chargen` key in config marks the preferred model for auto-loading when KoboldCpp is stopped.
