# tests/test_winjob.py — winjob.JobObject, the structural guarantee that
# KoboldCpp/SillyTavern can't outlive their handle even if this app
# crashes. Spawns real ping.exe/python subprocesses (a few seconds each);
# no GPU or config.json involved.

import ctypes
import os
import subprocess
import sys
import time

import winjob

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_alive_tasklist(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True,
    ).stdout
    return str(pid) in out


def _is_alive_exitcode(pid: int) -> bool:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    exit_code = ctypes.wintypes.DWORD()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
    ctypes.windll.kernel32.CloseHandle(h)
    STILL_ACTIVE = 259
    return exit_code.value == STILL_ACTIVE


def test_terminate_kills_the_assigned_process():
    job = winjob.JobObject()
    assert job._handle, "job object failed to create"
    proc = subprocess.Popen(
        ["ping", "-n", "60", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    assert _is_alive_tasklist(proc.pid), "test child process never started"
    assert job.assign(proc.pid)

    job.terminate()
    time.sleep(0.5)
    assert not _is_alive_tasklist(proc.pid)
    job.close()


def test_close_also_kills_a_still_running_process():
    """KILL_ON_JOB_CLOSE fires on ANY last-handle-closed event, not just
    process death specifically -- close() while something is still
    running in the job kills it too (a feature, not a bug: it's what makes
    an unexpected app crash still clean up)."""
    job = winjob.JobObject()
    proc = subprocess.Popen(
        ["ping", "-n", "60", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    assert _is_alive_tasklist(proc.pid)
    assert job.assign(proc.pid)

    job.close()
    time.sleep(0.5)
    assert not _is_alive_tasklist(proc.pid)


def test_parent_hard_crash_still_kills_the_child():
    """THE critical guarantee this whole mechanism exists for: spawn a
    fresh python process that creates a job, assigns a grandchild ping,
    then hard-exits via os._exit() with ZERO cleanup (no close()/
    terminate() call) -- simulating this app crashing or being
    Task-Manager-killed. The grandchild must still die once the OS tears
    down that process's handle table."""
    script = (
        "import subprocess, time, sys, os\n"
        f"sys.path.insert(0, {_PROJECT_ROOT!r})\n"
        "from winjob import JobObject\n"
        "job = JobObject()\n"
        "proc = subprocess.Popen(['ping', '-n', '60', '127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "time.sleep(0.5)\n"
        "job.assign(proc.pid)\n"
        "print(proc.pid, flush=True)\n"
        "os._exit(1)\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=10)
    grandchild_pid = int(result.stdout.strip())
    time.sleep(1.0)
    assert not _is_alive_tasklist(grandchild_pid), (
        "grandchild ping survived the parent's hard crash -- job object did not protect it"
    )


def test_subtree_sweep_catches_a_pre_existing_child():
    """AssignProcessToJobObject only ever affects the exact PID given --
    Windows does NOT retroactively pull in a child that already existed at
    assignment time (this is exactly the koboldcpp.exe bootloader/worker
    topology: the bootloader can spawn its real worker before we ever get
    a chance to assign the bootloader's PID). assign() must sweep the full
    descendant subtree, not just the one PID."""
    parent_script = (
        "import subprocess, time\n"
        "p = subprocess.Popen(['ping.exe', '-n', '60', '127.0.0.1'])\n"
        "print(p.pid, flush=True)\n"
        "time.sleep(60)\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_script],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        # Give the parent a moment to actually spawn its child before we
        # assign -- reproduces the "child already exists" gap.
        time.sleep(1.5)
        child_pid = int(parent.stdout.readline().strip())

        job = winjob.JobObject()
        assert job._handle
        assert job.assign(parent.pid), "root assignment should succeed"

        descendants = winjob._descendants(parent.pid)
        assert child_pid in descendants, f"pre-existing child {child_pid} not found in {descendants}"

        job.terminate()
        time.sleep(1.5)
        assert not _is_alive_exitcode(parent.pid), "parent (bootloader stand-in) survived terminate()"
        assert not _is_alive_exitcode(child_pid), (
            "pre-existing child survived terminate() -- the subtree-sweep bug is back"
        )
        job.close()
    finally:
        if parent.poll() is None:
            parent.kill()
