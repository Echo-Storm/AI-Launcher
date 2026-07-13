# tests/test_settings_load_guard.py — a corrupt config.json at Settings-open
# time must not get silently overwritten with blank defaults on Save.

from PyQt6.QtWidgets import QMessageBox

import settings_dialog as sd


def test_save_is_refused_after_a_load_failure(qapp, isolated_config, monkeypatch):
    # Corrupt the (isolated) config.json before opening the dialog
    with open(isolated_config, "w", encoding="utf-8") as f:
        f.write("{not valid json!!!")

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

    dlg = sd.SettingsDialog()
    assert dlg._config_load_failed, "_config_load_failed should be True after a corrupt config.json"

    assert dlg._save_config() is False, "_save_config() should refuse to save after a load failure"

    with open(isolated_config, encoding="utf-8") as f:
        content = f.read()
    assert content == "{not valid json!!!", "config.json was overwritten despite the load failure"
