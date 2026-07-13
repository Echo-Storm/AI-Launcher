# tests/test_smoke_full_app.py — real construction of every top-level
# dialog the app ships, against the user's ACTUAL config.json. Read-only:
# none of these constructors write to disk, so no isolation/backup fixture
# is needed. Catches import-time and construction-time breakage that
# per-module unit tests, each mocking their own narrow slice, would miss.

import constants
import imagegen_dialog
import chargen_dialog
import settings_dialog
import ui
import winjob


def test_main_window_constructs_and_api_card_matches_config(qapp):
    win = ui.MainWindow()
    win.show()
    qapp.processEvents()
    assert win.api_card.isVisible() == bool(constants.API_BASE_URL)


def test_chargen_dialog_constructs(qapp):
    chargen_dialog.CharGenDialog(
        api_base=constants.KOBOLD_API_BASE, output_dir=constants.CHARGEN_OUTPUT_DIR,
    )


def test_settings_dialog_constructs_and_real_config_loads_cleanly(qapp):
    dlg = settings_dialog.SettingsDialog()
    assert dlg._config_load_failed is False


def test_imagegen_dialog_constructs(qapp):
    imagegen_dialog.ImageGenDialog()


def test_job_object_creates_and_closes_cleanly():
    job = winjob.JobObject()
    assert job._handle
    job.close()
