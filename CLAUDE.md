# AI Writing Tools Launcher

PyQt6 desktop app for Windows. Manages KoboldCpp and SillyTavern as background services and includes a built-in SillyTavern character card generator.

**Version:** 1.2.0 (`constants.py` `APP_VERSION`)  
**Stack:** Python 3.11+, PyQt6, Pillow — no other runtime deps  
**HTTP:** `urllib.request` only — no requests/httpx anywhere  
**Run:** `python main.py` or `launch.bat`

---

## File map

| File | Role |
|------|------|
| `main.py` | Entry point; logging setup, config check, QApplication |
| `constants.py` | Config loader; all shared constants, colors, fonts, KoboldCpp arg builder |
| `ui.py` | `MainWindow`; KoboldCpp + ST process management; API backend card |
| `chargen_dialog.py` | `CharGenDialog`; generation, expand, portrait prompt, import/export |
| `settings_dialog.py` | `SettingsDialog`; config.json editor GUI |
| `config.json` | User config (gitignored — copy from config.example.json) |
| `chargen_prefs.json` | CharGen temperature + distinctive defaults (gitignored) |
| `assets/` | arrow_up.svg, arrow_down.svg (spinbox arrows) |

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
`btn_generate`, `_btn_expand`, and `_btn_portrait_prompt` in CharGen must be **disabled together** at the start of any async operation and **restored together** in every completion path: `_on_done`, `_on_error`, `_on_expand_done`, `_on_portrait_prompt_done`, `_cleanup_worker`. Breaking this causes permanently stuck buttons.

### CharGen dialog lifecycle
`_chargen_dlg` is reused between opens — `close()` hides it, `show()` re-shows it. The dialog instance (and its state: last card, portrait path, prefs) persists for the entire app session. Only destroyed when `MainWindow` closes.

### Backend selector
The backend combo in CharGen is only created when `API_BASE_URL` is configured. When not configured, `self._combo_backend = None` — every reference to it guards with `if self._combo_backend else "local"`.

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
  "chargen": { "output_dir": "..." }
}
```

- `use_cuda` and `use_vulkan` are mutually exclusive — `build_kobold_args` uses `if/elif`
- The `api` block is optional — omit it to hide the API card entirely
- `chargen.output_dir` defaults to `""` if not set

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

- Per-field Regenerate buttons in the Output tab (regenerate one field without touching the rest)
- Multi-model comparison (generate same concept with two backends side by side)
- Screenshots for README
