# tests/test_vram_indicator.py — the header VRAM label: nvidia-smi parsing,
# graceful fallback when it's unavailable, and the green/yellow/red
# thresholds. Real MainWindow construction (via qapp) so the label actually
# exists on self, not a bare-window stub — construction itself calls
# _query_vram() once, which is why every test here mocks it first.

import subprocess

import ui


def test_query_vram_parses_real_nvidia_smi_output(monkeypatch):
    def fake_run(*a, **k):
        return type("R", (), {"returncode": 0, "stdout": "2209, 16376\n", "stderr": ""})()
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ui._query_vram() == (2209, 16376)


def test_query_vram_returns_none_when_nvidia_smi_missing(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError("nvidia-smi not found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ui._query_vram() is None


def test_query_vram_returns_none_on_nonzero_exit(monkeypatch):
    def fake_run(*a, **k):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "no devices found"})()
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ui._query_vram() is None


def test_vram_color_thresholds():
    assert ui._vram_color(1000, 16000) == ui.COLOR_STATUS_RUNNING   # ~6%
    assert ui._vram_color(13000, 16000) == ui.COLOR_STATUS_STARTING  # ~81%
    assert ui._vram_color(15500, 16000) == ui.COLOR_STATUS_ERROR     # ~97%


def test_label_hides_and_stops_polling_when_nvidia_smi_unavailable(qapp, monkeypatch):
    monkeypatch.setattr(ui, "_query_vram", lambda: None)
    win = ui.MainWindow()
    assert win.vram_label.isVisible() is False


def test_label_shows_formatted_text_and_color_when_available(qapp, monkeypatch):
    monkeypatch.setattr(ui, "_query_vram", lambda: (2209, 16376))
    win = ui.MainWindow()
    win.show()
    qapp.processEvents()
    assert win.vram_label.isVisible() is True
    assert win.vram_label.text() == "VRAM 2.2/16.0GB"
    assert ui.COLOR_STATUS_RUNNING in win.vram_label.styleSheet()
