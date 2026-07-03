# Setup Guide

This app wires together several independent pieces — KoboldCpp, SillyTavern, an SDXL
image pipeline — that each have their own install story. The README covers what the
app *does*; this doc covers getting it actually running from a clean checkout,
including the gotchas that aren't obvious until you hit them.

Everything here targets **Windows**, since that's the only platform this app runs on.

---

## What you end up with

One Python process (`main.py`) that can optionally drive:
- **KoboldCpp** — a separate `.exe` you download, pointed at a GGUF model file you also download
- **SillyTavern** — a separate Node.js app you clone and `npm install` yourself
- **An API backend** — just an API key, no local install
- **Image Gen** — an SDXL checkpoint (and optionally LoRAs/embeddings/an upscaler) you download, run in-process by this app itself

None of KoboldCpp, SillyTavern, or SDXL model weights ship with this repo — you bring
your own, and `config.json` just points at where you put them. Skip any piece you
don't want; the app degrades gracefully (see "Minimal configs" below).

---

## Prerequisites

| Need | Required for |
|---|---|
| **Python 3.13+** | Everything. One venv runs the whole app — see "the Python version gotcha" below for why it's 3.13+ even if you don't want Image Gen. |
| **Git** | Cloning this repo (and SillyTavern, if you want it) |
| **An NVIDIA GPU + recent driver** | Image Gen only. SDXL generation needs CUDA; there's no CPU fallback path in this app. |
| **~10 GB free disk space** | Image Gen only — an SDXL checkpoint alone is typically 6-7 GB |
| **Node.js (LTS)** | SillyTavern only |
| **KoboldCpp.exe** | Local GGUF inference only — skip if you're going API-only |
| **A GGUF model file** | Same as above |

If you only want the Character Card Generator against a remote API (OpenRouter, Groq,
etc.), you can skip KoboldCpp, SillyTavern, the GPU, and Image Gen entirely — see
"Minimal configs" below.

### The Python version gotcha

The whole app — KoboldCpp process management, SillyTavern management, CharGen, Image
Gen — runs in **one Python process** out of **one virtual environment**. `requirements.txt`
pins `torch==2.12.1` for Image Gen, and that build needs Python 3.13+. Since Image Gen's
imports happen at module load time in files the rest of the app imports too, **the venv
needs to be 3.13+ even if you never touch Image Gen** — there's no way to run KoboldCpp
management on 3.11 and Image Gen on 3.13 side by side in this app as structured.

Check what you've got:
```
python --version
```
If it's older than 3.13, install a current Python from [python.org](https://www.python.org/downloads/)
before continuing. On Windows, if you have multiple Python versions installed, use
`py -3.13 -m venv venv` in the steps below to be explicit about which one creates the venv.

---

## Step 1 — Clone and create the virtual environment

```
git clone https://github.com/YOUR_USERNAME/ai-writing-tools.git
cd ai-writing-tools
python -m venv venv
venv\Scripts\activate
```

Your prompt should now show `(venv)`. Everything below assumes it's activated.

---

## Step 2 — Install dependencies

**If you want Image Gen** (SDXL image generation), install CUDA-enabled `torch`
**before** the rest of `requirements.txt` — otherwise pip grabs the plain CPU-only
build from PyPI and generation will either fail or fall back to unusably slow CPU
inference:

```
pip install torch --index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
```

The second command sees `torch` already satisfies the pin and won't touch it — it
just installs everything else (`diffusers`, `transformers`, `peft`, `accelerate`,
`safetensors`, `spandrel`, plus PyQt6/Pillow for the app itself).

**If you don't want Image Gen**, `pip install -r requirements.txt` alone still works —
it'll install the CPU-only `torch` and the rest of the Image Gen stack, they just
won't be used for anything. (There's currently no lighter requirements file that
skips them entirely — see Roadmap in the README.)

> **Don't use `launch.bat` for this first install if you want Image Gen.** It
> auto-creates the venv and runs a plain `pip install -r requirements.txt` with no
> CUDA index URL, so it'll silently install CPU-only torch. Do the two-command
> install above manually once; `launch.bat` is fine for every launch after that.

---

## Step 3 — KoboldCpp (optional — skip if API-only)

1. Download the latest release from [github.com/LostRuins/koboldcpp](https://github.com/LostRuins/koboldcpp) — grab `koboldcpp.exe` (or the CUDA-specific build if offered separately).
2. Put it somewhere permanent, e.g. `D:\Applications\KoboldCpp\koboldcpp.exe`.
3. Get a GGUF model file — [Hugging Face](https://huggingface.co/models?library=gguf) has thousands; a Q4_K_M quant of a 7B-24B model is a reasonable starting point depending on your VRAM. Note the full path to the `.gguf` file.

You'll point `config.json`'s `koboldcpp.exe` and `models[].path` at these in Step 6.

---

## Step 4 — SillyTavern (optional — skip if you don't want the chat frontend)

1. Install [Node.js LTS](https://nodejs.org/) if you don't have it.
2. Clone SillyTavern somewhere, e.g.:
   ```
   git clone https://github.com/SillyTavern/SillyTavern.git D:\Applications\SillyTavern
   cd D:\Applications\SillyTavern
   npm install
   ```
3. Do **not** run `start.bat` yourself — this app launches `server.js` directly and manages the process. Just note the install directory for Step 6.

---

## Step 5 — Image Gen assets (optional)

Skip this whole step if you're not using Image Gen.

### Get a checkpoint

You need one **SDXL** checkpoint in `.safetensors` format (not SD1.5 — this app's
pipeline is hardcoded to `StableDiffusionXLPipeline`). [CivitAI](https://civitai.com/)
and [Hugging Face](https://huggingface.co/models?other=stable-diffusion-xl) both have
plenty; any SDXL base or SDXL-based merge works.

### Suggested folder layout

Not required, but this is the layout the app's own testing used and it maps cleanly
onto the Settings UI's fields:

```
SDXL\
├── Model\
│   └── model.safetensors        ← sdxl.model_path
├── Lora\
│   └── your-lora.safetensors     ← one entry in sdxl.loras
├── Embeddings\
│   └── negative.safetensors      ← one entry in sdxl.textual_inversions
├── Upscaler\
│   └── upscaler.pth              ← sdxl.upscaler_path (optional)
└── output\                       ← generated images land here (auto-created)
```

Put this folder wherever you like (it's gitignored if placed inside the repo) —
`config.json`'s `sdxl.dir` just needs to point at its parent.

### LoRAs (optional)

Any SDXL LoRA `.safetensors` file. Add as many as you want via the Settings UI's LoRA
table (path + weight per row) — no manual JSON editing needed.

### Textual Inversions (optional)

**Must be the dual `clip_l`/`clip_g` SDXL embedding format** — a single-encoder SD1.5
textual inversion will not load correctly. The file should contain both `clip_l` and
`clip_g` keys; check the file's source (CivitAI listings usually say if it's SDXL).

### Upscaler (optional)

Any ESRGAN-family model spandrel can load (`.pth`). Without one, the hires-fix pass
just resizes instead of running a dedicated upscale first — still works, just less
sharp.

---

## Step 6 — Create config.json

```
copy config.example.json config.json
```

Open it and fill in the paths from Steps 3-5. You don't need every block — see
"Minimal configs" below. Full schema and every field's meaning: README's
[Configuration reference](README.md#configuration-reference).

Alternative: launch the app once with a bare-bones `config.json` (or even a `{}`),
then use the **Settings** GUI to fill in paths interactively instead of hand-editing
JSON — every field in the schema has a corresponding widget, including file/folder
Browse buttons.

### Minimal configs

**API-only (no local anything):**
```json
{
    "models": [],
    "api": {
        "base_url": "https://api.groq.com/openai",
        "api_key": "gsk_...",
        "model": "llama-3.3-70b-versatile"
    }
}
```
This gets you the API Backend card and CharGen working through it. KoboldCpp,
SillyTavern, and Image Gen cards just show as unconfigured/disabled — nothing errors.

**KoboldCpp + CharGen, no SillyTavern or Image Gen:**
```json
{
    "models": [
        {"name": "My Model", "key": "writing", "path": "C:\\path\\to\\model.gguf"}
    ],
    "koboldcpp": {
        "exe": "C:\\path\\to\\koboldcpp.exe",
        "gpu_layers": 40,
        "context_size": 8192
    }
}
```

Add `sillytavern` and/or `sdxl` blocks whenever you're ready for those pieces — you
don't have to configure everything on day one.

---

## Step 7 — First launch

```
python main.py
```
or double-click `launch.bat` (after Step 2's manual install if you need CUDA torch).

If `config.json` is missing, you'll get a dialog telling you so and pointing at
`config.example.json` — the app won't auto-create it for you.

### Verification checklist

Work through whichever of these apply to your config:

- [ ] **KoboldCpp**: click Start on the KoboldCpp card. Status should go Stopped → Starting → Running within a few seconds to a couple minutes (model-size dependent). If it goes to Error, check `AI_Launcher_Log.txt` next to `main.py`.
- [ ] **API Backend**: click Activate. Status should show a model count if `/v1/models` responds, or just "Activated" if the endpoint doesn't support that route.
- [ ] **SillyTavern**: with a backend running, click Start on the SillyTavern row, then Open ST once it's ready.
- [ ] **CharGen**: with a backend running, click Open CharGen, fill in a concept, click Generate.
- [ ] **Image Gen**: click Start on the Image Gen row. First load takes ~10-30s (checkpoint + LoRA/TI onto the GPU). Once Running, click Open and generate a test image.

---

## Troubleshooting

**"No module named 'torch'" / import errors on startup, but only when Image Gen is touched**
The venv's Python is probably older than 3.13, or `pip install -r requirements.txt` ran
before the venv existed / against the wrong interpreter. Recreate the venv (`python
--version` should read 3.13+ first) and reinstall per Step 2.

**Image Gen generation is extremely slow (minutes per image)**
You likely have the CPU-only `torch` build installed instead of the CUDA one. Reinstall
per Step 2's exact command order (CUDA torch **before** `requirements.txt`) — check
`AI_Launcher_Log.txt` or the app's Output log for a CUDA-availability warning.

**Image Gen crashes on first generation with a path-related error**
Make sure `sdxl.model_path` (or the Settings UI's Checkpoint field) actually points at
an existing `.safetensors` file. `sdxl.output_dir` can be left blank — it falls back to
a folder under the app's own directory automatically.

**A Textual Inversion silently doesn't apply**
It's probably not in the dual `clip_l`/`clip_g` SDXL format — see Step 5. Check
`AI_Launcher_Log.txt` for a skip warning naming the file.

**SillyTavern's Image Generation extension can't reach this app**
Confirm the extension's source is set to "Automatic1111" (or "auto") and the URL is
`http://localhost:<port>` matching `sdxl.port` (7860 by default) — and that the Image
Gen row shows Running, not just the checkpoint loaded (the HTTP server starts
alongside the pipeline, not independently).

**Port already in use (KoboldCpp, SillyTavern, or Image Gen won't start)**
Another process (a previous crashed run, or a real instance of that same tool) is
already bound to the configured port. Change the port in `config.json`/Settings, or
close whatever's already using it.

**"config.json not found" every time, even after copying it**
Make sure it's named exactly `config.json` (not `config.example.json` or
`config.example - Copy.json`) and sits directly next to `main.py`, not in a
subfolder.

---

## Where to go next

- [README.md](README.md) — full feature list, Deep Dive sections for CharGen and Image Gen, complete config schema
- [CLAUDE.md](CLAUDE.md) — internal architecture notes, if you're modifying the code
