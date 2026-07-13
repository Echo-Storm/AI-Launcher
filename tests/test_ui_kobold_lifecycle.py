# tests/test_ui_kobold_lifecycle.py — ui.py's KoboldCpp QProcess lifecycle:
# errorOccurred handling, buffered ready-string detection, Job Object
# assignment warnings, and async vs. synchronous stop.
#
# Constructs MainWindow via __new__ (bypassing __init__/_build_ui, which
# need a real config.json and would build the whole widget tree) with
# only the specific attributes each test touches stubbed in -- the same
# pattern used throughout this project's manual verification passes.
# Importing ui.py pulls in imagegen_engine -> torch at module scope, so
# the first test file to import it pays that cost once per session.

import subprocess
import time

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QMainWindow

import ui
import winjob


def _bare_window():
    win = ui.MainWindow.__new__(ui.MainWindow)
    QMainWindow.__init__(win)
    return win


class _FakeStatus:
    def __init__(self):
        self.state = None
    def set_starting(self): self.state = "starting"
    def set_running(self): self.state = "running"
    def set_stopped(self): self.state = "stopped"
    def set_error(self): self.state = "error"


class _FakeButton:
    def __init__(self):
        self.enabled = False
    def setEnabled(self, v):
        self.enabled = v


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


# --- errorOccurred: FailedToStart must reset the UI, other errors must not ---

def test_failed_to_start_resets_ui_via_finished_handler(qapp):
    win = _bare_window()
    win._kobold_proc = None
    win._kobold_job = None
    win._kobold_stopping = False
    win._kobold_ready = True  # pretend it was "ready" before
    win._current_model_key = "writing"
    win.kobold_card = _FakeCard()
    win._log_kobold = lambda *a, **k: None
    win._update_tools = lambda: None
    win.kobold_card.btn_start.setEnabled(False)
    win.kobold_card.btn_stop.setEnabled(True)

    win._on_kobold_error(QProcess.ProcessError.FailedToStart)

    assert win.kobold_card.status.state == "error"
    assert win.kobold_card.btn_start.enabled is True
    assert win.kobold_card.btn_stop.enabled is False
    assert win._kobold_ready is False


def test_non_failed_to_start_error_is_logged_but_does_not_reset_ui(qapp):
    win = _bare_window()
    win._kobold_stopping = False
    logged = []
    win._log_kobold = lambda msg: logged.append(msg)

    def _should_not_be_called(*a):
        raise AssertionError("_on_kobold_finished should not be called for non-FailedToStart errors")
    win._on_kobold_finished = _should_not_be_called

    win._on_kobold_error(QProcess.ProcessError.Crashed)
    assert any("Process error" in m for m in logged)


# --- Ready-string detection buffered across split stdout/stderr reads ----

def test_ready_marker_split_across_two_chunks_is_detected(qapp):
    win = _bare_window()
    win._kobold_ready = False
    win._kobold_ready_buf = ""
    win._current_model_key = "writing"
    win._kobold_proc = None  # falsy -> skips the second job-assign attempt
    win._log_kobold = lambda *a, **k: None
    win._update_tools = lambda: None
    win.kobold_card = _FakeCard()

    marker = "please connect to custom endpoint"
    assert marker in ui.KOBOLD_READY_STRINGS
    half = len(marker) // 2
    chunk1, chunk2 = marker[:half], marker[half:]

    win._check_kobold_ready("some preamble... " + chunk1)
    assert win._kobold_ready is False, "should not be ready yet, marker is incomplete"
    win._check_kobold_ready(chunk2 + " ...more output")
    assert win._kobold_ready is True, "buffered check should have caught the marker split across chunks"


# --- Job Object assignment: warn on failure, silent on success -----------

def test_failed_job_assignment_logs_a_warning(qapp):
    win = _bare_window()
    logged = []
    win._log_kobold = lambda msg: logged.append(msg)

    class _FakeProc:
        def processId(self): return 999999999  # bogus PID -> assign() fails

    job = winjob.JobObject()
    win._assign_job_or_warn(job, _FakeProc(), win._log_kobold)
    assert any("WARNING" in m and "Job Object" in m for m in logged), logged


def test_successful_job_assignment_logs_nothing(qapp):
    win = _bare_window()
    logged = []
    win._log_kobold = lambda msg: logged.append(msg)

    proc = subprocess.Popen(
        ["ping", "-n", "5", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)

        class _RealProc:
            def processId(self): return proc.pid

        job = winjob.JobObject()
        win._assign_job_or_warn(job, _RealProc(), win._log_kobold)
        assert logged == []
        job.terminate()
        job.close()
    finally:
        if proc.poll() is None:
            proc.kill()


# --- Stop is async by default, synchronous only for wait=True ------------

class _FakeProcState:
    def __init__(self):
        self._state = QProcess.ProcessState.Running
        self.killed = False
    def state(self): return self._state
    def processId(self): return 424242
    def kill(self):
        self.killed = True
        self._state = QProcess.ProcessState.NotRunning


def test_stop_kobold_default_is_async_not_blocking(qapp, monkeypatch):
    win = _bare_window()
    win._kobold_proc = _FakeProcState()
    win._kobold_job = None  # falsy -> falls through to the _tree_kill fallback path
    win.kobold_card = type("C", (), {"btn_stop": _FakeButton()})()
    win._kobold_stopping = False
    win._kobold_ready = True

    calls = {"count": 0}
    def slow_run(args, **kwargs):
        calls["count"] += 1
        time.sleep(2)
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(subprocess, "run", slow_run)

    t0 = time.time()
    win._stop_kobold()  # default wait=False
    elapsed = time.time() - t0
    assert elapsed < 0.5, f"_stop_kobold() blocked for {elapsed:.2f}s with default wait=False"

    time.sleep(2.5)  # let the background thread actually run taskkill
    assert calls["count"] == 1, "background thread never actually ran taskkill"


def test_stop_kobold_wait_true_is_synchronous(qapp, monkeypatch):
    win = _bare_window()
    win._kobold_proc = _FakeProcState()
    win._kobold_job = None  # falsy -> falls through to the _tree_kill fallback path
    win.kobold_card = type("C", (), {"btn_stop": _FakeButton()})()
    win._kobold_stopping = False
    win._kobold_ready = True

    calls = {"count": 0}
    def fast_run(args, **kwargs):
        calls["count"] += 1
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(subprocess, "run", fast_run)

    win._stop_kobold(wait=True)
    assert calls["count"] == 1, "wait=True didn't call taskkill synchronously"
    assert win._kobold_proc.killed, "kill() fallback didn't run"


def test_stop_st_uses_the_same_async_helper(qapp, monkeypatch):
    win = _bare_window()
    win._st_proc = _FakeProcState()
    win._st_job = None  # falsy -> falls through to the _tree_kill fallback path
    win._st_ready = True
    win.btn_st_stop = _FakeButton()
    win.btn_st_open = _FakeButton()

    calls = {"count": 0}
    def slow_run(args, **kwargs):
        calls["count"] += 1
        time.sleep(1)
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(subprocess, "run", slow_run)

    t0 = time.time()
    win._stop_st()
    elapsed = time.time() - t0
    assert elapsed < 0.5, f"_stop_st() blocked for {elapsed:.2f}s with default wait=False"

    time.sleep(1.5)
    assert calls["count"] == 1
