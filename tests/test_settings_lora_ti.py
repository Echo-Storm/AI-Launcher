# tests/test_settings_lora_ti.py — the LoRA/TI enable-checkbox + Target
# dropdown + auto-increment-token features in settings_dialog.py's Image
# Gen tab, and the interaction bugs found while building them.

import json

from PyQt6.QtWidgets import QDialog, QMessageBox, QPushButton, QTableWidget
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

import settings_dialog as sd


def _bypass_dialog(cfg: dict):
    """Constructs a SettingsDialog without going through __init__'s real
    _load_config() disk read -- for tests that only need _cfg populated
    in-memory and never call _save_config(). Mirrors the pattern used
    throughout this project's manual verification passes."""
    dlg = sd.SettingsDialog.__new__(sd.SettingsDialog)
    QDialog.__init__(dlg)
    dlg._cfg = cfg
    dlg._config_load_failed = False
    dlg._build_ui()
    dlg._populate()
    return dlg


def _intercept_warning(monkeypatch):
    """Returns a list that records every QMessageBox.warning(...) call
    (there can be more than one -- _on_save() runs several independent
    warning checks in sequence) instead of letting any of them block on a
    real modal .exec()."""
    calls = []

    def fake_warning(parent, title, text):
        calls.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(fake_warning))
    return calls


# --- Enable/disable checkbox: load + round-trip through _collect() -------

def test_lora_ti_enabled_flag_loads_and_round_trips(qapp):
    cfg = {"sdxl": {
        "loras": [
            {"path": "C:\\fake\\enabled_lora.safetensors", "weight": 0.8, "enabled": True},
            {"path": "C:\\fake\\disabled_lora.safetensors", "weight": 1.0, "enabled": False},
        ],
        "textual_inversions": [
            {"path": "C:\\fake\\enabled_ti.safetensors", "token": "tok_on", "enabled": True},
            {"path": "C:\\fake\\disabled_ti.safetensors", "token": "tok_off", "enabled": False},
        ],
    }}
    dlg = _bypass_dialog(cfg)

    assert dlg._lora_table.rowCount() == 2
    assert sd._table_checkbox_checked(dlg._lora_table, 0, 0) is True
    assert sd._table_checkbox_checked(dlg._lora_table, 1, 0) is False
    assert dlg._ti_table.rowCount() == 2
    assert sd._table_checkbox_checked(dlg._ti_table, 0, 0) is True
    assert sd._table_checkbox_checked(dlg._ti_table, 1, 0) is False

    # Flip both rows in both tables, then confirm _collect() reflects it
    dlg._lora_table.cellWidget(0, 0).findChild(sd.QCheckBox).setChecked(False)
    dlg._lora_table.cellWidget(1, 0).findChild(sd.QCheckBox).setChecked(True)
    dlg._ti_table.cellWidget(0, 0).findChild(sd.QCheckBox).setChecked(False)
    dlg._ti_table.cellWidget(1, 0).findChild(sd.QCheckBox).setChecked(True)
    dlg._collect()

    loras_out = dlg._cfg["sdxl"]["loras"]
    tis_out = dlg._cfg["sdxl"]["textual_inversions"]
    assert loras_out[0]["enabled"] is False
    assert loras_out[1]["enabled"] is True
    assert tis_out[0]["enabled"] is False
    assert tis_out[1]["enabled"] is True


def test_imagegen_engine_has_enabled_skip_guard():
    """imagegen_engine.py's _load_locked() must skip a disabled row entirely
    -- checked at the source-text level since exercising it for real means
    a GPU pipeline load (see tests/slow/)."""
    src = open("imagegen_engine.py", encoding="utf-8").read()
    assert 'not lora.get("enabled", True)' in src
    assert 'not ti.get("enabled", True)' in src


# --- Target dropdown: auto-detect + explicit + round trip ----------------

def test_guess_ti_target_heuristic():
    assert sd._guess_ti_target(r"C:\fake\negative.safetensors", "negative") == "negative"
    assert sd._guess_ti_target(r"C:\fake\SDXL_unlock_Adult_SFW.safetensors", "positive") == "positive"
    assert sd._guess_ti_target(r"C:\fake\whatever.safetensors", "some_token") == "negative"  # ambiguous


def test_guess_ti_target_uses_word_boundary_not_substring():
    """A raw substring match on "positive"/"negative" would misfire on
    words that merely CONTAIN those letters -- must match as a whole word."""
    assert sd._guess_ti_target(r"C:\fake\nonnegative_style.safetensors", "nonnegative") == "negative"
    assert sd._guess_ti_target(r"C:\fake\compositive_thing.safetensors", "compositive") == "negative"
    assert sd._guess_ti_target(r"C:\fake\my_positive_style.safetensors", "positive") == "positive"


def test_ti_target_dropdown_loads_and_round_trips(qapp):
    cfg = {"sdxl": {"textual_inversions": [
        # no "target" key at all -- legacy config, must auto-detect from token
        {"path": "C:\\fake\\negative.safetensors", "token": "negative", "enabled": True},
        # explicit target -- must be respected as-is, not re-guessed
        {"path": "C:\\fake\\unlock.safetensors", "token": "positive", "enabled": True, "target": "positive"},
    ]}}
    dlg = _bypass_dialog(cfg)

    assert dlg._ti_table.rowCount() == 2
    assert sd._table_combo_value(dlg._ti_table, 0, 3, "negative") == "negative"
    assert sd._table_combo_value(dlg._ti_table, 1, 3, "negative") == "positive"

    combo0 = dlg._ti_table.cellWidget(0, 3)
    combo0.setCurrentIndex(combo0.findData("positive"))
    dlg._collect()
    tis_out = dlg._cfg["sdxl"]["textual_inversions"]
    assert tis_out[0]["target"] == "positive"
    assert tis_out[1]["target"] == "positive"


# --- Cell-widget click-to-select-row fix (real regression, QTest-driven) --

def test_checkbox_click_selects_its_row():
    """setCellWidget swallows the click before QTableWidget's own selection
    model sees it -- clicking only the checkbox used to leave the row
    unselected, making "Remove selected"/"Browse path..." silently no-op."""
    table = QTableWidget(3, 1)
    for r in range(3):
        sd._table_set_checkbox(table, r, 0, False)
    table.show()

    assert not table.selectionModel().selectedRows()
    chk1 = table.cellWidget(1, 0).findChild(sd.QCheckBox)
    QTest.mouseClick(chk1, Qt.MouseButton.LeftButton)
    assert {i.row() for i in table.selectionModel().selectedRows()} == {1}


def test_checkbox_row_selection_survives_row_removal():
    """Selection must track the widget's CURRENT position (looked up by
    identity), not a row index captured at construction -- an earlier
    row's removal shifts every row below it."""
    table = QTableWidget(3, 1)
    for r in range(3):
        sd._table_set_checkbox(table, r, 0, False)
    table.show()

    table.removeRow(0)  # what was row 1 is now row 0
    chk_now_row0 = table.cellWidget(0, 0).findChild(sd.QCheckBox)
    QTest.mouseClick(chk_now_row0, Qt.MouseButton.LeftButton)
    assert {i.row() for i in table.selectionModel().selectedRows()} == {0}


def test_combo_change_also_selects_its_row():
    table = QTableWidget(2, 1)
    sd._table_set_combo(table, 0, 0, sd._TI_TARGET_CHOICES, "negative", default="negative")
    sd._table_set_combo(table, 1, 0, sd._TI_TARGET_CHOICES, "negative", default="negative")
    table.show()

    combo1 = table.cellWidget(1, 0)
    combo1.setCurrentIndex(1)
    assert {i.row() for i in table.selectionModel().selectedRows()} == {1}


def test_combo_fallback_uses_named_default_not_index_zero():
    """Mirrors _set_scheduler_combo's own fallback-by-key pattern -- a
    missing value should NOT silently default to whatever choice happens
    to be first in the list."""
    table = QTableWidget(1, 1)
    sd._table_set_combo(table, 0, 0, sd._TI_TARGET_CHOICES, "bogus_value", default="positive")
    assert sd._table_combo_value(table, 0, 0, "negative") == "positive"


# --- Incomplete-row warning (path xor token) ------------------------------

def test_incomplete_ti_row_warns_and_is_excluded_from_save(qapp, isolated_config, monkeypatch):
    dlg = sd.SettingsDialog()
    dlg._add_ti_row()
    dlg._ti_table.setItem(0, 1, sd.QTableWidgetItem(r"E:\fake\negative.safetensors"))
    # token deliberately left blank

    calls = _intercept_warning(monkeypatch)
    dlg._on_save()

    incomplete_warnings = [c for c in calls if "Token" in c]
    assert incomplete_warnings, f"no incomplete-row warning among: {calls}"
    assert "negative.safetensors" in incomplete_warnings[0]

    with open(isolated_config, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["sdxl"]["textual_inversions"] == []


def test_complete_ti_row_does_not_warn(qapp, isolated_config, monkeypatch):
    dlg = sd.SettingsDialog()
    dlg._add_ti_row()
    dlg._ti_table.setItem(0, 1, sd.QTableWidgetItem(r"E:\fake\negative.safetensors"))
    dlg._ti_table.setItem(0, 2, sd.QTableWidgetItem("negative"))

    calls = _intercept_warning(monkeypatch)
    dlg._warn_incomplete_ti_rows()
    assert not calls


# --- Default token: "sdxl", auto-incremented, no reserved suffix ---------

def test_add_row_button_defaults_token_to_sdxl(qapp, isolated_config):
    dlg = sd.SettingsDialog()
    add_buttons = [b for b in dlg.findChildren(QPushButton) if b.text() == "Add row"]
    assert len(add_buttons) == 3  # models, lora, ti all share the label
    for b in add_buttons:
        b.click()

    assert dlg._ti_table.rowCount() == 1
    assert dlg._ti_table.item(0, 2).text() == "sdxl"

    dlg._ti_table.setItem(0, 1, sd.QTableWidgetItem(r"E:\fake\negative.safetensors"))
    assert dlg._save_config()
    with open(isolated_config, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["sdxl"]["textual_inversions"][0]["token"] == "sdxl"


def test_default_token_auto_increments_without_reserved_suffix(qapp, isolated_config):
    """sdxl_2/sdxl_3 would collide with diffusers' own reserved
    underscore-digit convention for multi-vector embedding sub-tokens
    (token_1, token_2, ...) -- must use sdxl2/sdxl3 instead."""
    dlg = sd.SettingsDialog()
    add_buttons = [b for b in dlg.findChildren(QPushButton) if b.text() == "Add row"]
    for b in add_buttons:
        b.click()
    for b in add_buttons:
        b.click()
    for b in add_buttons:
        b.click()

    assert dlg._ti_table.rowCount() == 3
    tokens = {dlg._ti_table.item(r, 2).text() for r in range(3)}
    assert tokens == {"sdxl", "sdxl2", "sdxl3"}


def test_duplicate_enabled_token_warns_disabled_does_not(qapp, isolated_config, monkeypatch):
    dlg = sd.SettingsDialog()
    dlg._add_ti_row()
    dlg._add_ti_row()
    dlg._ti_table.setItem(0, 1, sd.QTableWidgetItem(r"E:\fake\a.safetensors"))
    dlg._ti_table.setItem(0, 2, sd.QTableWidgetItem("sdxl"))
    dlg._ti_table.setItem(1, 1, sd.QTableWidgetItem(r"E:\fake\b.safetensors"))
    dlg._ti_table.setItem(1, 2, sd.QTableWidgetItem("sdxl"))  # collides with row 0

    calls = _intercept_warning(monkeypatch)
    dlg._warn_duplicate_ti_tokens()
    assert calls
    assert "sdxl" in calls[0]

    # Disabling the duplicate row should silently stop the warning, mirroring
    # imagegen_engine.py's own enabled-filter before its duplicate check.
    dlg._ti_table.cellWidget(1, 0).findChild(sd.QCheckBox).setChecked(False)
    calls2 = _intercept_warning(monkeypatch)
    dlg._warn_duplicate_ti_tokens()
    assert not calls2
