# tests/test_st_browser.py — _open_st()'s optional dedicated-browser path
# (e.g. a portable LibreWolf install): launched with its own -profile dir
# and -no-remote so it never touches another browser's profile, falling
# back to the system default browser when unconfigured or missing.

import os

from PyQt6.QtCore import QProcess

import ui


def _bare_window():
    from PyQt6.QtWidgets import QMainWindow
    win = ui.MainWindow.__new__(ui.MainWindow)
    QMainWindow.__init__(win)
    win._log_kobold = lambda *a, **k: None
    win._log_st = lambda *a, **k: None
    return win


def test_falls_back_to_system_browser_when_unconfigured(qapp, monkeypatch):
    monkeypatch.setattr(ui, "SILLYTAVERN_BROWSER_PATH", "")
    calls = []
    monkeypatch.setattr(ui.webbrowser, "open", lambda url: calls.append(url))
    monkeypatch.setattr(QProcess, "startDetached", staticmethod(lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("startDetached should not be called when unconfigured"))))

    win = _bare_window()
    win._open_st()

    assert calls == [ui.SILLYTAVERN_URL]


def test_falls_back_and_warns_when_configured_path_missing(qapp, monkeypatch, tmp_path):
    missing_path = str(tmp_path / "does_not_exist.exe")
    monkeypatch.setattr(ui, "SILLYTAVERN_BROWSER_PATH", missing_path)
    calls = []
    warnings = []
    monkeypatch.setattr(ui.webbrowser, "open", lambda url: calls.append(url))

    win = _bare_window()
    win._log_st = lambda msg: warnings.append(msg)
    win._open_st()

    assert calls == [ui.SILLYTAVERN_URL]
    assert any("not found" in w for w in warnings)


def test_launches_configured_browser_with_dedicated_profile_and_no_remote(qapp, monkeypatch, tmp_path):
    fake_browser = tmp_path / "fakebrowser.exe"
    fake_browser.write_text("not a real exe, just needs to exist")
    monkeypatch.setattr(ui, "SILLYTAVERN_BROWSER_PATH", str(fake_browser))

    captured = {}
    def fake_start_detached(path, args):
        captured["path"] = path
        captured["args"] = args
        return True
    monkeypatch.setattr(QProcess, "startDetached", staticmethod(fake_start_detached))

    opened_default = []
    monkeypatch.setattr(ui.webbrowser, "open", lambda url: opened_default.append(url))

    win = _bare_window()
    win._open_st()

    assert opened_default == [], "should not fall back to the system browser when the custom one launches fine"
    assert captured["path"] == str(fake_browser)
    assert "-no-remote" in captured["args"]
    assert captured["args"][-1] == ui.SILLYTAVERN_URL
    assert "-profile" in captured["args"]
    profile_dir = captured["args"][captured["args"].index("-profile") + 1]
    assert os.path.basename(profile_dir) == "browser_profile"


def test_falls_back_when_configured_browser_fails_to_launch(qapp, monkeypatch, tmp_path):
    fake_browser = tmp_path / "fakebrowser.exe"
    fake_browser.write_text("not a real exe")
    monkeypatch.setattr(ui, "SILLYTAVERN_BROWSER_PATH", str(fake_browser))
    monkeypatch.setattr(QProcess, "startDetached", staticmethod(lambda *a, **k: False))

    calls = []
    monkeypatch.setattr(ui.webbrowser, "open", lambda url: calls.append(url))

    win = _bare_window()
    win._open_st()

    assert calls == [ui.SILLYTAVERN_URL]
