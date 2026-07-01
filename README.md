# AI Writing Tools

A dark-themed Windows desktop app for running local AI writing sessions. Manages **KoboldCpp** and **SillyTavern** as background services, switches seamlessly between local GGUF inference and remote API backends, and includes a full **SillyTavern character card generator** with portrait embedding and personality expansion.

![Python](https://img.shields.io/badge/python-3.11+-blue) ![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green) ![Version](https://img.shields.io/badge/version-1.2.0-violet) ![License](https://img.shields.io/badge/license-MIT-purple) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

> If this saves you time: [☕ Ko-fi](https://ko-fi.com/xechostormx)

---

## Screenshots

> *Screenshots coming soon. In the meantime: dark panel UI, two backend cards side by side (KoboldCpp + API), a Tools section below with SillyTavern and CharGen rows, and a log pane at the bottom.*

---

## What problem this solves

Running a local AI writing setup usually means juggling multiple terminal windows — one for KoboldCpp, one for SillyTavern, manually watching logs to know when things are ready, and switching to a browser to open the UI. When you want to switch to a cloud API for a faster model, that means changing config files and restarting things.

This app puts all of it in one place. You pick a model, hit Start, watch the log in the same window, and Open ST when the ready signal comes in. If you want to switch to OpenRouter or Groq instead, click Activate on the API card. The character card generator is built in — no browser tab needed.

---

## Features

### Backends

**KoboldCpp — Local GGUF Inference**
- Select from a named model list defined in your config
- Start/Stop with status badge (Stopped / Starting / Running / Error)
- Displays the active model name once loaded
- GPU configuration: CUDA, Vulkan, Flash Attention, GPU layer count, context size
- Reads KoboldCpp's stdout/stderr and detects the ready signal automatically
- Subtree kill via `taskkill /F /T` — terminates child processes cleanly

**API Backend — Any OpenAI-Compatible Endpoint**
- Works with OpenRouter, Groq, LM Studio, Ollama, or any local/remote endpoint that speaks the OpenAI chat completions API
- One-click Activate/Deactivate — no restart required
- Fetches the model list from `/v1/models` on connect and populates a dropdown
- Falls back to a completion probe if the models endpoint isn't available
- Deactivate at any time; re-activate with a different model mid-session

Both backends can coexist — if both are active, tools prefer API but you can switch manually.

### Tools

**SillyTavern**
- Start / Stop / Open buttons in a single row
- Start button highlights green when a backend is ready — clear visual cue for sequencing
- Detects SillyTavern's ready signal from its log output
- Open launches your browser to the configured ST port
- Subtree kill included

**Character Card Generator** *(see deep-dive section below)*

**Kill All**
- Force-terminates KoboldCpp and SillyTavern in one click
- Useful when processes get stuck or you want a clean reset

### Settings GUI

Full config editor — no manual JSON editing required:

- **KoboldCpp tab** — executable path, host, port, GPU layers, context size, CUDA/Vulkan/Flash Attention toggles, quiet mode
- **SillyTavern tab** — directory path, port
- **API tab** — base URL, API key (with show/hide toggle), default model, live Test Connection button
- **Models tab** — editable table of KoboldCpp models with name, key, and path; browse for GGUF files directly
- **App tab** — CharGen output directory

Changes take effect on next launch.

---

## Character Card Generator — Deep Dive

The built-in CharGen produces SillyTavern-compatible character cards with more control than most web-based generators. It uses whatever backend is active — local KoboldCpp or a remote API — and doesn't require an internet connection if you're running locally.

### Generation settings

**Backend selector**
Only shown when an API is configured. Switch between Local (KoboldCpp) and API per-generation. Automatically selects the only available backend when there's no ambiguity.

**Creativity slider**
Temperature from 0.60 (Safe — consistent, predictable) to 1.20 (Creative — more surprising, higher variance). Default 0.85. A reference notch marks 0.75, which is a common "standard" temperature for character work. The value updates live as you drag.

**Distinctive mode**
Adds a stronger creative direction prompt that specifically discourages clichés and overused archetypes — pushes for internal contradictions, specific speech register, idiosyncratic details. Useful when you're tired of getting the same brooding warrior or cheerful healer.

**Set as default**
Saves your current temperature and Distinctive state to `chargen_prefs.json`. Restored on next open.

### Character fields

| Field | Required | Notes |
|-------|----------|-------|
| Name | No | Model invents one if blank |
| Concept / Description | **Yes** | The core prompt — be specific |
| Personality | No | Notes for tone, speech, quirks |
| Scenario | Toggle | Off by default; enabling includes it in both the system prompt and the user prompt |
| First Message | Toggle | Off by default; model writes the character's opening message |
| Dialogue Examples | Toggle | Off by default; model writes one example exchange in ST format |

Optional fields are **actually optional** — unchecked fields are removed from the system prompt entirely, so the model doesn't generate them and token budget goes toward what you asked for.

### Expand Personality

After a card is generated, the **Expand Personality** button sends a dedicated second call focused entirely on the personality field. The full character card is included as context so the expansion stays coherent, but the model's attention isn't split across all fields at once.

The **Must include** field (next to the button) lets you specify traits, quirks, or details that must appear in the expanded personality — for example: *"fear of enclosed spaces, dry self-deprecating humor, compulsive need to categorize things"*. Leave it blank for a free expansion.

The result merges directly back into the card — the JSON output updates in place. You can expand multiple times.

### Output and saving

**Output tab** shows the generated JSON. If parsing fails (model wrapped in markdown, etc.), the raw text is shown so you can copy and fix manually.

**Save as PNG** — SillyTavern-native format. The portrait image (or a dark placeholder if none selected) is embedded alongside a base64-encoded `chara` tEXt metadata chunk containing the full v2 card spec. Drop it into ST's character folder and it appears in the character browser with portrait intact.

**Save as JSON** — Flat v1 card format. Useful for importing into other tools or editing manually.

**Copy** — copies whatever is in the output box, parsed or raw.

**Portrait** — pick any PNG/JPG/WEBP. Preview shown at 96x96. Images larger than 1024px are thumbnailed before embedding. Leave blank for a dark purple placeholder (ST will show the placeholder, card still works fine).

---

## Requirements

- **Python 3.11+**
- **PyQt6** and **Pillow** — see `requirements.txt`
- **[KoboldCpp](https://github.com/LostRuins/koboldcpp)** (optional — for local inference)
- **[SillyTavern](https://github.com/SillyTavern/SillyTavern)** + **Node.js** (optional — for the chat frontend)
- A **GGUF model file** — tested with Cydonia 24B Q4_K_M, Mistral variants, and dedicated CharGen models
- An **API key** from OpenRouter, Groq, or similar (optional — for remote inference)

You can run with API-only and skip KoboldCpp and SillyTavern entirely if you just want the character card generator with a remote model.

---

## Installation

```
git clone https://github.com/YOUR_USERNAME/ai-writing-tools.git
cd ai-writing-tools
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
```

Edit `config.json` with your paths (or use the Settings GUI after first launch — it will prompt you if config.json is missing).

Then run:
```
python main.py
```
or double-click `launch.bat`.

---

## Configuration reference

`config.json` lives next to `main.py` and is gitignored. All fields are editable via the Settings GUI.

```json
{
    "models": [
        {
            "name": "My Writing Model",
            "key":  "writing",
            "path": "C:\\path\\to\\model.gguf"
        },
        {
            "name": "CharGen v3",
            "key":  "chargen",
            "path": "C:\\path\\to\\chargen.gguf"
        }
    ],
    "koboldcpp": {
        "exe":             "C:\\path\\to\\koboldcpp.exe",
        "host":            "127.0.0.1",
        "port":            5001,
        "gpu_layers":      40,
        "context_size":    8192,
        "use_cuda":        true,
        "use_vulkan":      false,
        "flash_attention": true,
        "quiet":           true
    },
    "sillytavern": {
        "dir":  "C:\\path\\to\\SillyTavern",
        "port": 8000
    },
    "api": {
        "base_url": "https://api.groq.com/openai",
        "api_key":  "gsk_...",
        "model":    "llama-3.3-70b-versatile"
    },
    "chargen": {
        "output_dir": "C:\\path\\to\\SillyTavern\\data\\default-user\\characters"
    }
}
```

**Notes:**
- `models` — first entry is the startup default. `key` is an internal identifier (no spaces). Any number of models.
- `koboldcpp` — `gpu_layers` depends on your GPU VRAM and model size. `context_size` in tokens.
- `api` — the entire block is optional. Omit it to hide the API card entirely. `base_url` should not have a trailing slash.
- `chargen.output_dir` — set this to your ST characters folder so PNG saves drop straight into the browser.

---

## Typical workflow

**Local session:**
1. Launch the app
2. Select a model from the KoboldCpp dropdown, click **Start**
3. Watch the log — when "Running" appears, the **Start** button on SillyTavern highlights green
4. Click **Start** on SillyTavern, then **Open ST** when it's ready
5. Write. When done, **Kill All** or close the app (processes are terminated on exit)

**API session:**
1. Launch the app
2. Click **Activate** on the API card — it connects, fetches the model list, and goes green
3. Select a model from the dropdown
4. Open SillyTavern (or just use CharGen directly)

**Character card:**
1. Start a backend (either one)
2. Click **Open CharGen**
3. Fill in a concept — be specific, the model can't invent what you don't hint at
4. Adjust creativity and toggle Distinctive if you want something more original
5. Enable Scenario/First Message if you want those fields
6. Click **Generate**
7. On the Output tab: if personality feels thin, optionally add must-include notes and click **Expand Personality**
8. Pick a portrait, click **Save PNG** — it drops directly to your ST characters folder

---

## Roadmap

Features under consideration for future versions:

- **Expand other fields** — dedicated second-call expansion for Scenario and First Message, using the same must-include pattern as personality
- **Import existing card** — load a `.png` or `.json` character card, display its fields, re-generate or expand specific fields without starting from scratch
- **Per-field regeneration** — "Regenerate this field only" buttons in the output tab, keeping everything else intact
- **Multi-model comparison** — generate the same concept with two models side by side
- **Screenshot documentation** — in-app screenshots in this README

Contributions and suggestions welcome via issues.

---

## Notes

- `config.json` is gitignored — paths and API keys stay local
- `chargen_prefs.json` stores your temperature and distinctive defaults — also gitignored
- `AI_Launcher_Log.txt` is written next to the script on each run (overwritten, not appended)
- Settings changes take effect on next launch — constants are loaded at import time
- The API Test Connection button in Settings uses the field values as typed, before saving, so you can verify credentials before committing

---

## License

MIT — do whatever you want with it.
