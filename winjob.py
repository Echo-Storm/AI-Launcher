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

    def assign(self, pid: int) -> bool:
        """Adds the given PID to this job. Returns False (non-fatal — caller
        still has taskkill as a fallback) if the job failed to create, the
        PID can't be opened, or assignment itself fails."""
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
