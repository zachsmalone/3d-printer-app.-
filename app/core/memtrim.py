"""Give freed heap back to the OS after a heavy request.

glibc keeps freed memory inside the process: after the FDM tab imported and sliced three big STLs the server sat at
2.5 GB resident in the 3 GB container, and the next PrusaSlicer run was OOM-killed. gc + malloc_trim(0) returns it."""
import ctypes
import gc

try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:                       # not glibc (macOS / musl): nothing to trim
    _libc = None


def trim() -> None:
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass
