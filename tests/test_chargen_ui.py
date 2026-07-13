# tests/test_chargen_ui.py — CharGenDialog UI behaviors: checkbox label
# wording, checkbox-prefs round-trip, alternate_greetings <-> text-box sync,
# and single-level Condense Undo.
#
# _PREFS_PATH is read/written fresh on every _load_prefs()/_save_prefs()
# call (not bound at some other module's import time like constants.py's
# config globals), so a simple monkeypatch of chargen_dialog._PREFS_PATH to
# a tmp_path file is enough to keep this off the real chargen_prefs.json.

import json

import chargen_dialog as cd


def _dialog(tmp_path, monkeypatch):
    monkeypatch.setattr(cd, "_PREFS_PATH", str(tmp_path / "chargen_prefs.json"))
    return cd.CharGenDialog(api_base="http://127.0.0.1:5001", output_dir=str(tmp_path))


def test_checkbox_label_matches_actual_default_off_behavior(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    assert "(check to include)" in dlg.chk_scenario.text()
    assert "(uncheck to skip)" not in dlg.chk_scenario.text()


def test_checkbox_prefs_persist_to_disk(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    dlg.chk_scenario.setChecked(True)
    dlg.chk_first_mes.setChecked(True)
    dlg.chk_mes_example.setChecked(False)
    dlg._save_defaults()

    with open(cd._PREFS_PATH, encoding="utf-8") as f:
        prefs = json.load(f)
    assert prefs["scenario"] is True
    assert prefs["first_mes"] is True
    assert prefs["mes_example"] is False


def test_fresh_dialog_restores_checkboxes_from_prefs(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    dlg.chk_scenario.setChecked(True)
    dlg.chk_first_mes.setChecked(True)
    dlg.chk_mes_example.setChecked(False)
    dlg._save_defaults()

    dlg2 = _dialog(tmp_path, monkeypatch)
    assert dlg2.chk_scenario.isChecked() is True
    assert dlg2.chk_first_mes.isChecked() is True
    assert dlg2.chk_mes_example.isChecked() is False


def test_alternate_greetings_list_populates_into_box_delimited(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    dlg._last_card = {
        "name": "Test", "description": "A test.",
        "alternate_greetings": ["Hi there!", "Yo, what's up?"],
    }
    dlg._populate_output_fields()
    text = dlg.out_alternate_greetings.toPlainText()
    assert "Hi there!" in text
    assert "Yo, what's up?" in text
    assert "---" in text


def test_editing_box_writes_back_a_list_to_last_card(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    dlg._last_card = {"name": "Test", "description": "A test.", "alternate_greetings": []}
    dlg._populate_output_fields()
    dlg.out_alternate_greetings.setPlainText("First greeting\n---\nSecond greeting\n---\nThird greeting")
    dlg._sync_alternate_greetings()
    assert dlg._last_card["alternate_greetings"] == ["First greeting", "Second greeting", "Third greeting"]


def test_undo_condense_restores_original_text_and_disables_itself(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    dlg._last_card = {
        "name": "Jill", "description": "desc",
        "personality": "A very long personality description that will get condensed down to something much shorter.",
    }
    dlg._populate_output_fields()
    dlg._expand_combo.setCurrentIndex(dlg._expand_combo.findData("personality"))
    assert dlg._btn_undo_condense.isEnabled() is False, "should start disabled, nothing to undo yet"

    original_text = dlg._last_card["personality"]
    dlg._expanding_field = "personality"
    dlg._expanding_verb = "condensed"
    dlg._condense_undo = ("personality", original_text)

    dlg._on_expand_done("Short personality.")
    assert dlg._last_card["personality"] == "Short personality."
    assert dlg._btn_undo_condense.isEnabled() is True, "Undo should be enabled after a successful condense"

    dlg._undo_condense()
    assert dlg._last_card["personality"] == original_text, "Undo did not restore the original text"
    assert dlg._btn_undo_condense.isEnabled() is False, "Undo should disable itself after firing (single-level)"
    assert dlg._condense_undo is None


def test_completed_expand_clears_a_stale_condense_undo(qapp, tmp_path, monkeypatch):
    dlg = _dialog(tmp_path, monkeypatch)
    dlg._last_card = {"name": "Jill", "description": "desc", "personality": "some text"}
    dlg._populate_output_fields()

    dlg._condense_undo = ("personality", "some stale text")
    dlg._expanding_field = "personality"
    dlg._expanding_verb = "expanded"
    dlg._on_expand_done("Expanded personality text.")
    assert dlg._condense_undo is None, "a completed Expand should clear any pending condense-undo"
