# tests/slow/test_kobold_job_integration.py — the real-world case the
# Job Object subsystem exists for: koboldcpp.exe is a PyInstaller
# bootloader that spawns its own worker child. Killing ONLY the
# bootloader PID (simulating AV or Task Manager ending just that row)
# must not orphan the worker -- job.terminate() has to catch it too.
#
# Launches the real koboldcpp binary from the user's real config and a
# real model file, so this needs both configured and takes ~20-30s.

import subprocess
import time

import pytest
from PyQt6.QtWidgets import QMainWindow

import constants
import ui

pytestmark = pytest.mark.slow


def _children_of(pid):
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f'(Get-CimInstance Win32_Process -Filter "ParentProcessId={pid}").ProcessId'],
        capture_output=True, text=True,
    ).stdout
    return [int(x) for x in out.split() if x.strip().isdigit()]


def _is_alive(pid):
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


class _FakeStatus:
    def set_starting(self): pass
    def set_running(self): pass
    def set_stopped(self): pass
    def set_error(self): pass


class _FakeButton:
    def setEnabled(self, *a): pass


class _FakeLabel:
    def setText(self, *a): pass
    def setVisible(self, *a): pass


class _FakeCard:
    def __init__(self):
        self.status = _FakeStatus()
        self.lbl_subtitle = _FakeLabel()
        self.btn_start = _FakeButton()
        self.btn_stop = _FakeButton()
        self.model_combo = None


def test_killing_only_the_bootloader_still_kills_its_child(qapp, monkeypatch):
    if not constants.MODELS:
        pytest.skip("real config.json needs at least one model configured")

    win = ui.MainWindow.__new__(ui.MainWindow)
    QMainWindow.__init__(win)
    win._kobold_proc = None
    win._kobold_job = None
    win._kobold_stopping = False
    win._kobold_ready = False
    win._current_model_key = None
    win.kobold_card = _FakeCard()
    win._log_kobold = lambda *a, **k: None
    win._update_tools = lambda: None

    finished_fired = {"unexpected": False}
    orig_on_finished = ui.MainWindow._on_kobold_finished

    def wrapped_on_finished(self, exit_code, exit_status):
        finished_fired["unexpected"] = not self._kobold_stopping
        return orig_on_finished(self, exit_code, exit_status)
    monkeypatch.setattr(ui.MainWindow, "_on_kobold_finished", wrapped_on_finished)

    win._start_kobold(constants.MODELS[0]["key"])

    deadline = time.time() + 20
    bootloader_pid = None
    child_pids = []
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.1)
        if win._kobold_proc and win._kobold_proc.processId():
            bootloader_pid = win._kobold_proc.processId()
            kids = _children_of(bootloader_pid)
            if kids:
                child_pids = kids
                break

    try:
        assert bootloader_pid, "koboldcpp bootloader never got a PID"
        assert child_pids, "bootloader never spawned a child process"
        child_pid = child_pids[0]

        # Give the job-object assignment (wired via proc.started) a moment to run
        time.sleep(1.0)
        qapp.processEvents()
        assert win._kobold_job is not None, "no JobObject was created"

        subprocess.run(
            ["taskkill", "/F", "/PID", str(bootloader_pid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + 15
        while time.time() < deadline and not finished_fired["unexpected"]:
            qapp.processEvents()
            time.sleep(0.1)

        assert finished_fired["unexpected"], "_on_kobold_finished never fired for the unexpected bootloader death"

        time.sleep(1.0)
        assert not _is_alive(child_pid), f"child PID {child_pid} survived the bootloader's death"
    finally:
        if win._kobold_proc and win._kobold_proc.processId() and _is_alive(win._kobold_proc.processId()):
            subprocess.run(
                ["taskkill", "/F", "/PID", str(win._kobold_proc.processId())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        for pid in child_pids:
            if _is_alive(pid):
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
