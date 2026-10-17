"""Keep the booth from starving GSPro of CPU.

OCR (onnxruntime) is the heavy part and defaults to every core, so on a shared sim PC its bursts
can stutter GSPro's game loop. Running the booth below normal priority lets GSPro win contention;
an optional core cap bounds the booth's reach outright. Windows only; a no-op elsewhere.
"""

import ctypes
import logging
import os
import sys

log = logging.getLogger(__name__)

_PRIORITY = {"idle": 0x40, "below_normal": 0x4000, "normal": 0x20}


def tune(priority: str = "below_normal", max_cores: int | None = None) -> None:
    if sys.platform != "win32":
        return
    try:
        k32 = ctypes.windll.kernel32
        k32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
        handle = k32.GetCurrentProcess()
        if priority in _PRIORITY:
            k32.SetPriorityClass(handle, _PRIORITY[priority])
        total = os.cpu_count() or 1
        if max_cores and max_cores < total:
            n = max(1, max_cores)
            mask = ((1 << n) - 1) << (total - n)  # the top n cores, leaving the rest for GSPro
            k32.SetProcessAffinityMask(handle, mask)
        log.info("Perf: priority=%s, cores=%s of %s", priority, max_cores or total, total)
    except Exception:
        log.exception("Perf tuning failed; continuing at default priority")
