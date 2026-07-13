# tests/test_singleinstance.py — the named-mutex single-instance guard.
# Spawns real separate python subprocesses to properly exercise
# cross-process mutex semantics (a single process can always re-open its
# own mutex, so that alone wouldn't prove anything).

import os
import subprocess
import sys

import singleinstance

_TIMEOUT = 10
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _acquire_in_subprocess(name: str) -> str:
    script = (
        "import sys\n"
        f"sys.path.insert(0, {_PROJECT_ROOT!r})\n"
        "import singleinstance\n"
        f'print("ACQUIRED" if singleinstance.acquire({name!r}) else "REJECTED", flush=True)\n'
    )
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=_TIMEOUT)
    return r.stdout


def test_first_acquire_in_this_process_succeeds():
    assert singleinstance.acquire("AILauncherTest_FirstAcquire") is True


def test_second_process_is_rejected_while_first_holds_it():
    name = "AILauncherTest_SecondRejected"
    assert singleinstance.acquire(name) is True
    assert "REJECTED" in _acquire_in_subprocess(name)


def test_mutex_releases_when_holding_process_exits():
    """Can't easily release mid-process without CloseHandle, so verify via
    real subprocess lifecycle instead: one process acquires then exits,
    then a follow-up process must be able to acquire the same name."""
    name = "AILauncherTest_ReleaseOnExit"
    assert "ACQUIRED" in _acquire_in_subprocess(name)
    assert "ACQUIRED" in _acquire_in_subprocess(name)
