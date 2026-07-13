# winjob.py — Windows Job Object wrapper for guaranteed child-process cleanup
#
# taskkill /T can only reach a process tree while its root PID is still alive
# to walk from, and only runs at all if our own code executes it — neither
# holds if this app crashes, is force-killed, or the machine loses power.
# A Job Object with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE closes both gaps: the
# OS itself terminates every process ever assigned to it (plus any children
# they spawn, which inherit job membership automatically) the moment our
# handle to the job is released — including on process death, not just a
# clean Python-level exit — and TerminateJobObject() kills by handle, so it
# still works even after the originally-assigned PID has already exited.

import ctypes
from ctypes import wintypes

_JobObjectExtendedLimitInformation = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_TH32CS_SNAPPROCESS = 0x00000002
_MAX_PATH = 260


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * _MAX_PATH),
    ]


def _pid_to_ppid_snapshot() -> dict:
    """One-shot snapshot of every running process's PID -> parent PID, via
    the same Toolhelp32 API Task Manager itself uses — no subprocess spawn
    (unlike shelling out to WMIC/PowerShell), so this is cheap enough to
    call every time we need to find a process's current descendants."""
    mapping = {}
    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return mapping
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not ctypes.windll.kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return mapping
        while True:
            mapping[entry.th32ProcessID] = entry.th32ParentProcessID
            if not ctypes.windll.kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        ctypes.windll.kernel32.CloseHandle(snap)
    return mapping


def _descendants(root_pid: int) -> list:
    """Every process currently descended from root_pid (children,
    grandchildren, ...), found via one process snapshot rather than
    walking live handles. Needed because AssignProcessToJobObject only
    affects the exact PID given — a child the target process spawned
    *before* we get around to assigning it is never swept in retroactively,
    only children spawned *after* automatically inherit job membership."""
    pid_to_ppid = _pid_to_ppid_snapshot()
    found = []
    frontier = [root_pid]
    while frontier:
        parent = frontier.pop()
        children = [pid for pid, ppid in pid_to_ppid.items() if ppid == parent]
        found.extend(children)
        frontier.extend(children)
    return found


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JobObject:
    """One Job Object per managed service (KoboldCpp, SillyTavern, ...).

    Create fresh per launch, assign() the started process's PID, and close()
    it once that service has fully and cleanly stopped. Kept alive for the
    service's whole lifetime: while this object (and its handle) lives, if
    this app's own process ever dies for any reason, Windows tears down
    everything assigned to the job automatically."""

    def __init__(self):
        self._handle = None
        try:
            handle = ctypes.windll.kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            ok = ctypes.windll.kernel32.SetInformationJobObject(
                handle, _JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info),
            )
            if not ok:
                ctypes.windll.kernel32.CloseHandle(handle)
                return
            self._handle = handle
        except OSError:
            self._handle = None

    def _assign_one(self, pid: int) -> bool:
        if not self._handle or not pid:
            return False
        try:
            hproc = ctypes.windll.kernel32.OpenProcess(
                _PROCESS_TERMINATE | _PROCESS_SET_QUOTA, False, pid,
            )
            if not hproc:
                return False
            try:
                return bool(ctypes.windll.kernel32.AssignProcessToJobObject(self._handle, hproc))
            finally:
                ctypes.windll.kernel32.CloseHandle(hproc)
        except OSError:
            return False

    def assign(self, pid: int) -> bool:
        """Adds the given PID, AND every process currently descended from it
        (children, grandchildren, ...), to this job. Returns False (non-fatal
        — caller still has taskkill as a fallback) only if the root PID's own
        assignment fails; a descendant that can't be opened/assigned (e.g. it
        already exited) is skipped silently, since the root is what matters
        for the warning log.

        Sweeping descendants matters because AssignProcessToJobObject only
        ever affects the exact PID given — a child process spawned *before*
        this call (e.g. a PyInstaller bootloader's real worker, already
        running by the time our 'started' signal fires) is never retroactively
        pulled in; only children spawned *after* the parent joins automatically
        inherit membership. Call this again later (e.g. once a ready string is
        seen in the process's output) to catch children that spawn shortly
        after startup."""
        root_ok = self._assign_one(pid)
        for child_pid in _descendants(pid):
            self._assign_one(child_pid)
        return root_ok

    def terminate(self):
        """Kills every process currently in this job, by handle — works even
        if the originally-assigned PID has already exited on its own, unlike
        a PID-based taskkill /T."""
        if self._handle:
            try:
                ctypes.windll.kernel32.TerminateJobObject(self._handle, 1)
            except OSError:
                pass

    def close(self):
        """Releases our handle to the job. Important: KILL_ON_JOB_CLOSE fires
        whenever the LAST handle closes, whether that's an explicit close()
        call or this whole app dying — since we're always the only handle
        holder, calling close() while something is still running in the job
        kills it too (a feature, not a bug, for a stray leftover child; call
        terminate() first if you specifically want an immediate, deliberate
        kill before releasing the handle)."""
        if self._handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self._handle)
            except OSError:
                pass
            self._handle = None

    def __del__(self):
        self.close()
