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


# ---- CR-5: photo-permission acknowledgement --------------------------------------------------------------------------------
ACK_REFUSED = ("Please tick the box that says this is your photo or you have permission from everyone in it, then try again.")


def _sample_hash() -> str:
    import hashlib
    from ..config import STATIC
    try:
        return hashlib.sha256((STATIC / "sample.png").read_bytes()).hexdigest()
    except OSError:
        return ""


def is_builtin_sample(raw: bytes) -> bool:
    import hashlib
    h = _sample_hash()
    return bool(h) and hashlib.sha256(raw).hexdigest() == h


def builtin_title(raw: bytes) -> str:
    """'Sample photo' / 'Sample vase' when the bytes are ZEIM's own sample files, else ''. (A title is NEVER taken from a person's file name.)"""
    import hashlib
    from ..config import STATIC
    h = hashlib.sha256(raw).hexdigest()
    for fn, title in (("sample.png", "Sample photo"), ("sample_model.stl", "Sample vase")):
        try:
            if hashlib.sha256((STATIC / fn).read_bytes()).hexdigest() == h:
                return title
        except OSError:
            pass
    return ""


def check_ack(raw: bytes, ack: bool):
    """Every uploaded photo needs the permission box ticked (config.PHOTO_ACK_REQUIRED); ZEIM's own sample photo does not.
    Returns what to record in meta.json: True (ticked), 'sample' (built-in sample) or False (check switched off). Raises ImageRefused."""
    from .. import config
    if is_builtin_sample(raw):
        return "sample"
    if config.PHOTO_ACK_REQUIRED and not ack:
        raise ImageRefused(ACK_REFUSED)
    return bool(ack)
