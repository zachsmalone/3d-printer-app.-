"""File names people can read and every system accepts: "Title - Printer - 0.2mm.ext".

safe_name() makes a chosen name safe on Windows, macOS, Linux, iOS and Android:
no path separators or reserved characters (<>:"/\\|?*), no control or bidi/zero-width characters,
no leading dots, no trailing dots or spaces, no Windows device names (CON, NUL, COM1...), at most 120 characters
(before the extension), so it also fits zip archives and phone file pickers. Letters from any language are kept.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

MAX_STEM = 120
_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def safe_name(name: Optional[str], default: str = "ZEIM model") -> str:
    """A safe file-name stem (no extension). Never empty."""
    s = unicodedata.normalize("NFC", str(name or ""))
    s = _BAD.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lstrip(".").rstrip(". ")
    if s.split(".")[0].strip().lower() in _RESERVED:
        s = "_" + s
    if len(s) > MAX_STEM:
        s = s[:MAX_STEM].rstrip(". ")
    return s or default


def strip_ext(name: str, ext: str) -> str:
    n = name or ""
    return n[: -len(ext) - 1] if n.lower().endswith("." + ext.lower()) else n


def fmt_layer(mm: Optional[float]) -> str:
    if not mm:
        return ""
    return f"{float(mm):.3f}".rstrip("0").rstrip(".") + "mm"


def default_stem(title: Optional[str], printer_name: Optional[str] = None, layer_mm: Optional[float] = None) -> str:
    """'Title - Printer - 0.2mm' (parts that are unknown are left out)."""
    parts = [safe_name(title, "ZEIM model")]
    if printer_name:
        parts.append(safe_name(printer_name, ""))
    lay = fmt_layer(layer_mm)
    if lay:
        parts.append(lay)
    return safe_name(" - ".join(p for p in parts if p))


def file_name(stem_or_name: Optional[str], ext: str, fallback: str = "ZEIM model") -> str:
    """Full file name with exactly one, lower-case extension."""
    stem = safe_name(strip_ext(stem_or_name or "", ext), fallback)
    return f"{stem}.{ext.lower()}"


def disposition(fname: str) -> str:
    """Content-Disposition that keeps non-ASCII names (RFC 6266 / 5987) with an ASCII fallback."""
    from urllib.parse import quote
    ascii_ = unicodedata.normalize("NFKD", fname).encode("ascii", "ignore").decode() or "download"
    ascii_ = ascii_.replace('"', "").replace("\\", "")
    return f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(fname)}"
