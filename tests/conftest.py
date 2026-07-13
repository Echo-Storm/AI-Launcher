# tests/conftest.py — shared fixtures for the AI Launcher test suite.
#
# Two isolation strategies, matched to what each test actually needs:
#
# - `isolated_config` monkeypatches settings_dialog._CONFIG_PATH to a
#   tmp_path file, so SettingsDialog._load_config()/_save_config() never
#   touch the user's real config.json. Covers the large majority of tests
#   here, since they exercise SettingsDialog's own _cfg dict + _collect()/
#   _populate() logic, not the constants.py-derived module globals.
#
# - constants.py loads config.json ONCE at import time into module-level
#   globals (SDXL_MODEL_PATH, SDXL_LORAS, API_BASE_URL, ...) that other
#   modules (imagegen_engine.py) bind via `from constants import X` at
#   THEIR OWN import time. Monkeypatching a path after that point can't
#   retroactively change already-bound globals without an
#   importlib.reload() chain that mutates process-wide state — not worth
#   the cross-test contamination risk for the fast suite. Tests that
#   genuinely need those globals to reflect specific values (real SDXL
#   pipeline loads) live under tests/slow/ and use the real_config_backup
#   fixture instead, matching the backup-then-restore pattern already
#   proven safe during manual verification.

import json
import os
import shutil
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from PyQt6.QtWidgets import QApplication

_REAL_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.json")

# Baseline config used by isolated_config -- deliberately minimal but
# structurally complete (every top-level section a real config.json has),
# so tests that only care about e.g. sdxl.textual_inversions don't also
# have to hand-construct koboldcpp/api/models sections themselves.
_BASELINE_CONFIG = {
    "models": [],
    "koboldcpp": {
        "exe": "", "host": "127.0.0.1", "port": 5001, "gpu_layers": 0,
        "context_size": 4096, "use_cuda": True, "use_vulkan": False,
        "flash_attention": True, "quiet": True, "embeddings_model": "",
    },
    "sillytavern": {"dir": "", "port": 8000},
    "api": {"base_url": "", "api_key": "", "model": ""},
    "chargen": {"output_dir": ""},
    "sdxl": {
        "dir": "", "model_path": "",
        "loras": [], "textual_inversions": [],
        "upscaler_path": "", "output_dir": "",
        "base_width": 1024, "base_height": 1024,
        "hires_scale": 1.5, "hires_denoise": 0.45,
        "steps": 30, "cfg_scale": 7.0, "scheduler": "dpmpp_2m_karras",
        "port": 7860, "allow_st_override": False,
    },
}


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test session -- PyQt6 doesn't support
    multiple instances per process, and tests don't need window isolation
    from each other (each constructs its own dialog instance)."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_config(qapp, tmp_path, monkeypatch):
    """Redirects settings_dialog's config.json I/O to a throwaway tmp_path
    file seeded with _BASELINE_CONFIG, so tests can freely load/save
    without any risk to the user's real config.json. Returns the path."""
    import settings_dialog

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(_BASELINE_CONFIG, indent=2), encoding="utf-8")
    monkeypatch.setattr(settings_dialog, "_CONFIG_PATH", str(cfg_path))
    return str(cfg_path)


@pytest.fixture
def real_config_backup():
    """For tests/slow/ only: backs up the real config.json and restores it
    unconditionally afterward, even if the test raises. Use when a test
    needs constants.py's module-level globals (SDXL_MODEL_PATH, SDXL_LORAS,
    ...) to reflect specific values, which requires writing the real file
    since those globals are bound at import time (see module docstring)."""
    if not os.path.isfile(_REAL_CONFIG_PATH):
        pytest.skip("no real config.json present -- can't run this test here")
    backup_path = _REAL_CONFIG_PATH + ".bak_pytest"
    shutil.copy(_REAL_CONFIG_PATH, backup_path)
    try:
        with open(_REAL_CONFIG_PATH, encoding="utf-8") as f:
            original = json.load(f)
        yield _REAL_CONFIG_PATH, original
    finally:
        shutil.copy(backup_path, _REAL_CONFIG_PATH)
        os.remove(backup_path)
