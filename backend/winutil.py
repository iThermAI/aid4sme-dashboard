"""Windows-only safety nets. Every function is a no-op on other platforms.

* A job object with KILL_ON_JOB_CLOSE: if the Python server dies for any
  reason, Windows kills every FFmpeg child with it - no orphaned recorders.
* SetThreadExecutionState: the capture PC cannot go to sleep mid-recording.
"""
import logging
import os

log = logging.getLogger("aid4sme")

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_job = None

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BASIC),
                    ("IoInfo", _IO),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.SetThreadExecutionState.restype = wintypes.DWORD
    _k32.SetThreadExecutionState.argtypes = [wintypes.DWORD]


def attach_to_kill_job(proc):
    """Tie a subprocess.Popen to the server's lifetime. Returns True on success."""
    global _job
    if os.name != "nt":
        return False
    try:
        if _job is None:
            job = _k32.CreateJobObjectW(None, None)
            if not job:
                raise OSError(ctypes.get_last_error())
            info = _EXTENDED()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise OSError(ctypes.get_last_error())
            _job = job
        if not _k32.AssignProcessToJobObject(_job, int(proc._handle)):
            # Windows 7 has no nested jobs: fails if Python itself already runs inside one.
            raise OSError(ctypes.get_last_error())
        return True
    except Exception as e:  # noqa
        log.warning("Could not attach pid %s to kill-on-close job (%s); "
                    "FFmpeg may outlive a crashed server", proc.pid, e)
        return False


def prevent_sleep(on):
    """Must be called from a thread that lives for the whole recording."""
    if os.name != "nt":
        return
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    _k32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
