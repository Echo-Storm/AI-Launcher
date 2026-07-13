# singleinstance.py — one-copy-running guard via a named Win32 mutex
#
# The AI Launcher was observed running as two independent, uncoordinated
# processes at once (root cause not fully pinned down — happened below our
# own code, since main.py has no self-relaunch logic and launch.bat only
# invokes pythonw.exe once). Whatever the exact trigger, two copies each
# managing their own KoboldCpp/SillyTavern QProcess children means Kill All
# in one window can never touch what the other one started. A named mutex
# is the standard, simple way to guarantee only one copy proceeds past
# startup, regardless of how a second one gets spawned.

import ctypes
from ctypes import wintypes

_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)

# Held for the process's entire lifetime — module-level so it's never
# garbage-collected/closed until the interpreter exits, which is exactly
# when the mutex should release.
_mutex_handle = None


def acquire(name: str) -> bool:
    """Returns True if this process is the only one holding the named mutex
    (i.e. safe to proceed with startup). Returns False if another process
    already holds it — the mutex handle this call created is closed again
    immediately in that case, since this process has no claim to it."""
    global _mutex_handle
    handle = _kernel32.CreateMutexW(None, False, name)
    if not handle:
        # Couldn't even create the mutex (extremely unlikely) — fail open
        # rather than block the user from ever starting the app.
        return True
    already_exists = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
    if already_exists:
        _kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def focus_existing_window(title: str):
    """Best-effort: bring the already-running instance's window to the
    front instead of leaving the user to hunt for it. Silently does
    nothing if the window can't be found (e.g. it's still on the splash/
    config-check screen and hasn't set its title yet)."""
    hwnd = _user32.FindWindowW(None, title)
    if hwnd:
        _user32.ShowWindow(hwnd, _SW_RESTORE)
        _user32.SetForegroundWindow(hwnd)
        return True
    return False


def notify_already_running(title: str):
    """Native MessageBoxW so this path doesn't need PyQt6 imported at all —
    keeps the reject-and-exit path fast and light."""
    _user32.MessageBoxW(
        None,
        f"{title} is already running.\n\nCheck your taskbar or open windows — "
        "bringing the existing one to the front now if it can be found.",
        title,
        0x00000040,  # MB_ICONINFORMATION
    )
