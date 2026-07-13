# tests/test_config_hardening.py — constants.py must not crash the whole
# app at import time on a malformed config.json; a hand-edited or
# partially-written file should degrade gracefully instead.
#
# constants.py reads config.json via a hardcoded path relative to itself,
# so this can only be tested by actually writing the real file (a fresh
# subprocess re-imports constants.py fresh each time) -- real_config_backup
# guarantees it's restored afterward even if an assertion fails.

import json
import os
import subprocess
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PYTHON = os.path.join(_PROJECT_ROOT, "venv", "Scripts", "python.exe")


def _import_constants_with(config_path: str, text: str):
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(text)
    return subprocess.run(
        [_PYTHON, "-c", "import constants; print('IMPORT_OK', len(constants.MODELS))"],
        cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=15,
    )


def test_null_koboldcpp_section_does_not_crash_import(real_config_backup):
    config_path, base = real_config_backup
    base = dict(base)
    base["koboldcpp"] = None
    r = _import_constants_with(config_path, json.dumps(base))
    assert "IMPORT_OK" in r.stdout, f"{r.stdout}\n{r.stderr}"


def test_malformed_models_entries_are_filtered_not_crashed_on(real_config_backup):
    config_path, base = real_config_backup
    base = dict(base)
    base["models"] = [
        {"name": "Good", "key": "good", "path": "C:\\fake.gguf"},
        "just_a_string",
        {"key": "no_name_or_path"},
    ]
    r = _import_constants_with(config_path, json.dumps(base))
    assert "IMPORT_OK 1" in r.stdout, f"{r.stdout}\n{r.stderr}"


def test_non_object_top_level_config_gives_clear_fatal_error(real_config_backup):
    config_path, _base = real_config_backup
    r = _import_constants_with(config_path, "[1, 2, 3]")
    assert r.returncode != 0
    assert "must be a JSON object" in (r.stdout + r.stderr), f"{r.stdout}\n{r.stderr}"


def test_real_config_still_imports_fine(real_config_backup):
    """Sanity check that the isolation itself works: after real_config_backup
    reads the real file, re-writing that SAME content back must still
    import cleanly."""
    config_path, base = real_config_backup
    r = _import_constants_with(config_path, json.dumps(base))
    assert "IMPORT_OK" in r.stdout, f"{r.stdout}\n{r.stderr}"
