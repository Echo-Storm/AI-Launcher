# AI Writing Tools Launcher

PyQt6 desktop app for Windows. Manages KoboldCpp and SillyTavern as background services, includes a built-in SillyTavern character card generator, and an in-process SDXL image generation backend with its own SillyTavern-facing API server.

**Version:** 1.4.0 (`constants.py` `APP_VERSION`)  
**Stack:** Python 3.11+ (app) / 3.13+ (SDXL image gen, needs its own CUDA torch), PyQt6, Pillow, diffusers/transformers/peft/accelerate/spandrel/safetensors (image gen only) — no other runtime deps  
**HTTP:** `urllib.request` for outbound calls only — no requests/httpx anywhere. `imagegen_server.py` is the one exception: inbound-only, stdlib `http.server`, not an outbound client.  
**Run:** `python main.py` or `launch.bat`

---

## File map

| File | Role |
|------|------|
| `main.py` | Entry point; logging setup, config check, QApplication |
| `constants.py` | Config loader; all shared constants, colors, fonts, KoboldCpp arg builder |
| `ui.py` | `MainWindow`; KoboldCpp + ST process management; API backend card; Image Gen Start/Stop/Open row |
| `chargen_dialog.py` | `CharGenDialog`; generation, expand, portrait prompt, import/export |
| `settings_dialog.py` | `SettingsDialog`; config.json editor GUI, including the Image Gen tab |
| `imagegen_engine.py` | Shared SDXL pipeline: lock-protected load/unload/generate, multi-LoRA/TI loading, ESRGAN upscale |
| `imagegen_dialog.py` | `ImageGenDialog`; manual one-button Generate UI, cooperative-cancel worker |
| `imagegen_server.py` | Minimal Automatic1111-compatible HTTP server so SillyTavern can generate through this backend |
| `config.json` | User config (gitignored — copy from config.example.json) |
| `chargen_prefs.json` | CharGen temperature + distinctive defaults (gitignored) |
| `assets/` | arrow_up.svg, arrow_down.svg (spinbox arrows) |
| `SDXL/` | Checkpoint/LoRA/TI/upscaler files + generated output (gitignored — user's own model files) |

---

## Architecture

### Process management
- KoboldCpp and SillyTavern are launched as `QProcess` children of `MainWindow`
- Ready detection is via stdout/stderr scanning against `KOBOLD_READY_STRINGS` / `SILLYTAVERN_READY_STRINGS`
- **Stops are async** — `_stop_kobold()` and `_stop_st()` issue taskkill + kill and return immediately; UI cleanup happens in the `finished` signal callbacks (`_on_kobold_finished`, `_on_st_finished`)
- Exception: `closeEvent` does a targeted `waitForFinished(2000)` per proc after stopping — acceptable to block briefly on exit
- `_kobold_stopping` / `_st_stopping` flags distinguish intentional stops from crashes (controls whether status shows Stopped vs Error)

### Worker threads
All LLM API calls run in `_GenerateWorker(QThread)`. **`finished = pyqtSignal(str)` shadows `QThread.finished`** — intentional, all `run()` code paths emit either `self.finished` or `self.error`. Cleanup: `terminate()` + `wait(2000)` (never `setParent(None)`).

### Button state invariant
`btn_generate`, `_btn_expand`, `_btn_regenerate`, `_btn_condense`, and `_btn_portrait_prompt` in CharGen must be **disabled together** at the start of any async operation and **restored together** in every completion path: `_on_done`, `_on_error`, `_on_expand_done`, `_on_portrait_prompt_done`, `_cleanup_worker`. All go through the single `_set_busy()` switch. Breaking this causes permanently stuck buttons.

### Field length control (Expand / Regenerate / Condense)
Three per-field actions share the `_expand_combo` (personality/scenario/first_mes) and all complete through `_on_expand_done`: **Expand** elaborates on the existing text, **Regenerate** discards it for a fresh alternative take (existing text deliberately withheld from the prompt so the model isn't anchored to it), **Condense** tightens it to a Short/Medium/Long word target (`_condense_length` combo) without dropping distinct details. `_FIELD_LENGTH_TARGETS` (per-field short/medium/long word counts) is the single source of truth for both Condense's target instruction and the live word-count label's green/yellow/red thresholds (`_wordcount_color()`) — deliberately tied together so "yellow" always means "past what Condense-Medium would produce."

### CharGen dialog lifecycle
`_chargen_dlg` is reused between opens — `close()` hides it, `show()` re-shows it. The dialog instance (and its state: last card, portrait path, prefs) persists for the entire app session. Only destroyed when `MainWindow` closes.

### Backend selector
The backend combo in CharGen is only created when `API_BASE_URL` is configured. When not configured, `self._combo_backend = None` — every reference to it guards with `if self._combo_backend else "local"`.

### Image Gen backend
In-process SDXL (txt2img + LoRA + TI + ESRGAN hires-fix), not an external subprocess — replaced an earlier standalone reForge install entirely (removed from the app and from disk).

- **Shared pipeline cache** (`imagegen_engine.py`): a module-level `_pipe_cache` dict guarded by a single `threading.Lock`. Three independent callers use it — `ui.py`'s Start/Stop warm-up (`_ImageGenLoadWorker`), `imagegen_dialog.py`'s manual Generate button (`ImageGenWorker`, also imported by `chargen_dialog.py`'s Portrait Prompt "Generate Image" button), and `imagegen_server.py`'s HTTP handler threads. **Always go through `with_pipeline(fn)`** for anything that touches the pipeline objects — it holds the lock for the fn's *entire* run, not just the fetch, so Stop can never unload mid-generation and two callers can never both load at once. `try_unload_pipeline()` (used by Stop) does a **non-blocking** acquire — if a generation is in flight, Stop reports "busy" and returns instead of freezing the GUI thread. `is_busy()` does the same non-blocking check for callers that just need a yes/no (e.g. `ui.py`'s `closeEvent` warns before quitting mid-generation).
- **Cooperative cancellation, not `terminate()`**: `ImageGenWorker` (imagegen_dialog.py) checks a `_cancel_requested` flag via diffusers' `callback_on_step_end` between denoising steps, raising `_Cancelled` to unwind cleanly. Never use `QThread.terminate()` on a generation thread — killing it mid-CUDA-op can corrupt the CUDA context for the whole process, and (now) would also leave `_lock` held forever since a killed thread never runs its `finally`.
- **Multi-LoRA/TI**: `config.json`'s `sdxl.loras`/`sdxl.textual_inversions` are lists (`{path, weight}` / `{path, token}`), not single fields. LoRAs load via `pipe.load_lora_weights(path, adapter_name=...)` + one `pipe.set_adapters(names, weights)` call after the loop. TIs each get their own token; loaded tokens are cached as `_pipe_cache["ti_tokens"]` and joined into the negative prompt. Duplicate tokens across TI rows are detected and skipped (with a `log.warning`) rather than left to crash diffusers' `load_textual_inversion` — the whole TI-loading loop is wrapped so one bad/duplicate entry doesn't block the rest.
- **HTTP server** (`imagegen_server.py`): minimal Automatic1111-compatible API (`POST /sdapi/v1/txt2img`, `GET /sdapi/v1/sd-models`) so SillyTavern's Image Generation extension (source="auto") can generate through this backend — ST's own Node server proxies server-to-server, no CORS/browser involved. Started/stopped alongside the pipeline warm-up (`ui.py`'s Start/Stop), not independently. Request bodies over 1MB (`_MAX_BODY_BYTES`) are rejected with 413 before being read into memory.
- **`sdxl.allow_st_override`** (default `false`): when off, the server ignores everything ST sends except prompt/negative_prompt and always uses this app's own tuned settings — deliberate, matches [[feedback_ai_launcher_curated_defaults]] in memory (curated-by-default, opt-in for power users). When on, ST's steps/cfg_scale/width/height/seed/enable_hr/hr_scale/denoising_strength take over, **including disabling hires-fix entirely**. All of these are clamped in `generate_image()` itself (`_STEPS_RANGE`, `_CFG_SCALE_RANGE`, `_DIMENSION_RANGE`, `_HIRES_SCALE_RANGE`, `_DENOISE_RANGE` — matching the Settings UI's own spinbox ranges) so validation applies regardless of caller, not just the UI widgets; `enable_hr` goes through `_to_bool()` rather than a bare `bool()` since a JSON string `"false"` is otherwise truthy in Python.
- **Scheduler presets**: `sdxl.scheduler` picks one of 4 curated diffusers schedulers (`dpmpp_2m_karras` default, `euler_a`, `dpmpp_sde_karras`, `unipc`) applied to `pipe.scheduler` once at pipeline-load time in `_load_locked()` — the `img2img` pipeline reuses the same scheduler object by reference, so it never needs setting twice. `constants.py`'s `SDXL_SCHEDULER_CHOICES` (drives the Settings UI dropdown) and `imagegen_engine.py`'s `_SCHEDULER_REGISTRY` (data-only, no diffusers import — maps each key to a class name + `from_config()` kwargs) are validated against each other **at import time**: an entry in one list without a match in the other raises `RuntimeError` immediately on startup rather than silently falling back for a real user at generation time. A key from a hand-edited or legacy `config.json` that isn't in the registry still falls back gracefully with a `log.warning`, since only that path is expected to ever see an unrecognized key. Changing the scheduler in Settings takes effect on the next pipeline load (Stop then Start the Image Gen tool, not just the next full app launch).
- **Settings UI additions**: the Image Gen tab's Generation section has a **Restore Generation Defaults** button (`settings_dialog.py`'s `_restore_generation_defaults()`) that resets exactly the 7 generation-tuning fields (width/height/steps/cfg/hires scale/hires denoise/scheduler) back to `constants.py`'s `SDXL_GENERATION_DEFAULTS` — deliberately scoped, does not touch Checkpoint/LoRA/TI/Upscaler/Output Directory/port/override checkbox. An **Output Directory** field (with Browse) writes `sdxl.output_dir` directly — without it, `SDXL_OUTPUT_DIR` still falls back to `<app dir>/SDXL/output` (see Config section) so a fresh install never crashes on an empty path, but the field makes the location visible/changeable without hand-editing `config.json`.

---

## Config (config.json)

```json
{
  "models": [{ "name": "...", "key": "writing", "path": "C:\\...\\model.gguf" }],
  "koboldcpp": { "exe": "...", "host": "127.0.0.1", "port": 5001, "gpu_layers": 40,
                 "context_size": 8192, "use_cuda": true, "use_vulkan": false,
                 "flash_attention": true, "quiet": true },
  "sillytavern": { "dir": "...", "port": 8000 },
  "api": { "base_url": "https://api.groq.com/openai", "api_key": "...", "model": "..." },
  "chargen": { "output_dir": "..." },
  "sdxl": {
    "dir": "...", "model_path": "...",
    "loras": [{ "path": "...", "weight": 1.0 }],
    "textual_inversions": [{ "path": "...", "token": "negative" }],
    "upscaler_path": "...", "output_dir": "...",
    "base_width": 1024, "base_height": 1024,
    "hires_scale": 1.5, "hires_denoise": 0.45,
    "steps": 30, "cfg_scale": 7.0, "scheduler": "dpmpp_2m_karras",
    "port": 7860, "allow_st_override": false
  }
}
```

- `use_cuda` and `use_vulkan` are mutually exclusive — `build_kobold_args` uses `if/elif`
- The `api` block is optional — omit it to hide the API card entirely
- `chargen.output_dir` defaults to `""` if not set
- `sdxl.loras`/`sdxl.textual_inversions` are lists — any number of entries, each independently weighted/tokened
- `sdxl.base_width`/`base_height` default to 1024×1024 (SDXL's native square resolution) — chosen deliberately over a portrait aspect since it generalizes across both character portraits and general in-story scene generation
- `sdxl.allow_st_override` defaults to `false` — see the Image Gen backend section above
- `sdxl.output_dir` defaults to `<sdxl.dir>/output` if `sdxl.dir` is set, else `<app dir>/SDXL/output` — never empty, so `os.makedirs()` in `generate_image()` can't crash on a fresh config that only has a checkpoint configured
- `sdxl.scheduler` defaults to `"dpmpp_2m_karras"` — one of `dpmpp_2m_karras`/`euler_a`/`dpmpp_sde_karras`/`unipc`, see the Image Gen backend section above for the registry/validation details

---

## Color system (EchoStorm dark theme)

All colors are in `constants.py`. Never hardcode color values in other files.

```python
COLOR_BG         = "#181818"    COLOR_PANEL       = "#1f1f1f"
COLOR_PANEL_ALT  = "#232323"    COLOR_HEADER_BAR  = "#2d1f00"
COLOR_ACCENT     = "#7cb342"    COLOR_ACCENT_DIM  = "#4a6b28"
COLOR_TEXT       = "#e8e8e8"    COLOR_TEXT_MUTED  = "#666666"
COLOR_BORDER     = "#2a2a2a"    COLOR_BORDER_BRIGHT = "#3a3a3a"
COLOR_BUTTON_BG  = "#282828"    COLOR_BUTTON_HOVER  = "#323232"

STATUS colors:
  STOPPED  = "#555555"   (grey — idle/inactive)
  STARTING = "#f59e0b"   (amber — in progress)
  RUNNING  = "#7cb342"   (green — active)
  ERROR    = "#e05050"   (red)
```

---

## SillyTavern card format

- **v2 spec (PNG/JSON):** `{"spec": "chara_card_v2", "spec_version": "2.0", "data": {...}}`
- Import always unwraps v2: `if card.get("spec") == "chara_card_v2": card = card["data"]`
- PNG embed: `chara` tEXt chunk = base64-encoded JSON of the full v2 wrapper
- Save JSON: merges `_to_st_card()` defaults with full `_last_card` re-overlay (preserves all imported fields; excludes `avatar` and `chat` which are ST runtime fields)
- Save PNG: always uses `_to_st_card_v2()` normalization (v2 spec compliance)

---

## Roadmap

- Screenshots for README
- Multi-model comparison — explicitly declined by user, not planned
- Image Gen: user-facing model/sampler dropdowns in SillyTavern's UI would need `/sdapi/v1/samplers`/`/sdapi/v1/schedulers`/`/sdapi/v1/upscalers` stubs (currently unimplemented — degrades gracefully to empty on ST's side, not required for generation to work)
