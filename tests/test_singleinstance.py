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


def test_release_allows_reacquire_in_same_process():
    name = "AILauncherTest_ReleaseThenReacquire"
    assert singleinstance.acquire(name) is True
    singleinstance.release()
    assert singleinstance.acquire(name) is True


def test_release_unblocks_a_concurrently_running_second_process():
    """The actual bug release() exists to fix: ui.py's _restart_app() spawns
    a fresh instance BEFORE this process has finished tearing down its Qt
    event loop and actually exiting, so a naive fix would still have this
    process alive (not exited) when the new one starts. Without an explicit
    release, the new process's own acquire() would race the OS reclaiming
    the handle at this process's eventual exit and could easily lose,
    surfacing a spurious "already running" rejection. release() must free
    the name up for a concurrent second process immediately -- proven here
    by never exiting this process at all before the subprocess acquires."""
    name = "AILauncherTest_ReleaseUnblocksLiveSecondProcess"
    assert singleinstance.acquire(name) is True
    singleinstance.release()
    assert "ACQUIRED" in _acquire_in_subprocess(name)
