r"""Opt-in startup timing for the desktop app (``DOCENT_STARTUP_LOG``).

Set the variable to a file path before launching::

    $env:DOCENT_STARTUP_LOG = "$env:TEMP\\docent-startup.log"
    dist\\curation-app-lite\\curation-app-lite.exe

Every :func:`mark` call appends one tab-separated line::

    total_ms    module_ms    phase

``total_ms`` is measured from the Windows process creation time, so it
includes the PyInstaller bootloader and interpreter start-up; ``module_ms``
is measured from this module's import. On non-Windows platforms the
process-start column is ``-``.

The probe is inert unless the variable is set: each mark costs one
environment lookup, and the process-creation timestamp (a ctypes call) is
only fetched on the first mark of an enabled run.
"""

from __future__ import annotations

import os
import sys
import time

_T0 = time.perf_counter()
_HEADER_WRITTEN = False
_PROCESS_START: float | bool | None = None  # False = looked up and unavailable


def enabled() -> bool:
    """Return True when startup logging is requested for this run."""
    return bool(os.environ.get("DOCENT_STARTUP_LOG"))


def _process_start_epoch() -> float | None:
    """Unix timestamp of this process's creation (Windows), or None."""
    global _PROCESS_START
    if _PROCESS_START is not None:
        return _PROCESS_START or None
    _PROCESS_START = False
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        times = [wintypes.FILETIME() for _ in range(4)]
        ok = kernel32.GetProcessTimes(
            kernel32.GetCurrentProcess(),
            *(ctypes.byref(t) for t in times),
        )
        if ok:
            created = times[0]
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            # FILETIME is 100 ns ticks since 1601-01-01 (UTC).
            _PROCESS_START = ticks / 10_000_000 - 11_644_473_600
    except Exception:
        _PROCESS_START = False
    return _PROCESS_START or None


def mark(label: str) -> None:
    """Append one startup phase to the log file (no-op when disabled)."""
    path = os.environ.get("DOCENT_STARTUP_LOG")
    if not path:
        return
    try:
        now = time.perf_counter()
        module_ms = (now - _T0) * 1000.0
        started = _process_start_epoch()
        total = f"{(time.time() - started) * 1000.0:.0f}" if started else "-"
        global _HEADER_WRITTEN
        with open(path, "a", encoding="utf-8") as fh:
            if not _HEADER_WRITTEN:
                _HEADER_WRITTEN = True
                fh.write("# Dataverse Docent startup timing\n")
                fh.write(f"# run: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                fh.write("# total_ms\tmodule_ms\tphase\n")
            fh.write(f"{total}\t{module_ms:.0f}\t{label.replace(chr(9), ' ')}\n")
    except Exception:
        # Timing must never break a launch.
        pass
