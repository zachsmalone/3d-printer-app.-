"""Every uploaded or camera-captured photo goes through here before it is used or stored (CR-2, S-08, iPhone HEIC fix).

* HEIC/HEIF (what iPhones/iPads send) is converted when `pillow-heif` is installed (it is pinned in requirements.txt).
* EXIF orientation is applied, then ALL metadata (EXIF/GPS/XMP/ICC/text chunks) is dropped by re-encoding from pixels only.
* The stored format comes from the SNIFFED content, never from the file name: JPEG stays JPEG, everything else becomes PNG.
* Huge images are refused (pixel cap) or scaled down (long side <= MAX_SIDE) so one upload cannot exhaust memory/disk.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps

try:                                    # optional at import time so the app still starts without it; HEIC then gets the friendly error
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:                       # pragma: no cover - only when the wheel/system library is missing
    HEIF_OK = False

MAX_PIXELS = 100_000_000      # refuse anything bigger than this before decoding it fully
MAX_SIDE = 4096               # stored images are scaled down to this long side (models are capped at ~600 px anyway)
ALLOWED = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "MPO", "HEIF"}
UNREADABLE = "We couldn't open that photo. Try a JPG or PNG."
TOO_BIG = "That photo is very large. Try a smaller one (JPG or PNG)."


class ImageRefused(ValueError):
    """Message is safe to show to the user as-is."""


def sniff(data: bytes) -> str | None:
    """Format name from the bytes (not the file name), or None."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.format
    except Exception:
        return None


def sanitize(data: bytes) -> tuple[bytes, str, Image.Image]:
    """-> (clean_bytes, extension 'jpg'|'png', RGB PIL image). Raises ImageRefused."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2          # PIL's own bomb guard stays on as a second line
    try:
        im = Image.open(io.BytesIO(data))
        fmt = im.format
        w, h = im.size
    except Exception:
        raise ImageRefused(UNREADABLE)
    if fmt not in ALLOWED:
        raise ImageRefused(UNREADABLE)
    if w * h > MAX_PIXELS:
        raise ImageRefused(TOO_BIG)
    try:
        if fmt == "JPEG":
            im.draft("RGB", (MAX_SIDE, MAX_SIDE))      # cheap decode-time downscale for big camera JPEGs
        im.load()
        im = ImageOps.exif_transpose(im)               # honour the camera's rotation BEFORE the metadata is dropped
        if im.mode in ("RGBA", "LA", "P", "PA"):       # flatten transparency on white (same as geometry.load_image)
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        im = im.convert("RGB")
    except ImageRefused:
        raise
    except Exception:
        raise ImageRefused(UNREADABLE)
    if max(im.size) > MAX_SIDE:
        s = MAX_SIDE / max(im.size)
        im = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.LANCZOS)
    clean = Image.new("RGB", im.size)                  # fresh image: nothing but pixels is carried over
    clean.paste(im)
    out = io.BytesIO()
    if fmt in ("JPEG", "MPO", "HEIF"):                 # photos stay compact
        clean.save(out, "JPEG", quality=92, optimize=True)
        return out.getvalue(), "jpg", clean
    clean.save(out, "PNG", optimize=True)
    return out.getvalue(), "png", clean
