"""Give freed heap back to the OS after a heavy request.

glibc keeps freed memory in the process. After a large mesh the address space stays high, and the
next boolean or slice can hit the job cap or the 14 GB app container. gc + malloc_trim(0) returns it."""
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
