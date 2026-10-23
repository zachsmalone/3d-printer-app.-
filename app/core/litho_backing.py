"""Lithophane backing colour: what sits behind the print (a bulb's light, a white diffuser, a sheet of paper).
Saved with the build so re-opening it shows the same backlit preview. Browser twin: BACKINGS in static/lithlight.js."""
import re

# name -> (label, "#rrggbb" colour of the light that reaches the print through the backing)
BACKINGS = {
    "warm": ("Warm white", "#ffe2b8"),
    "cool": ("Cool white", "#e3ecff"),
    "paper": ("Paper", "#f3e8cf"),
}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize(v) -> str:
    """'' (none chosen), a preset name, or a lower-case '#rrggbb'. Anything else is a ValueError."""
    v = str(v or "").strip()
    if v in ("", "none"):
        return ""
    if v in BACKINGS:
        return v
    if _HEX.match(v):
        return v.lower()
    raise ValueError("backing must be warm, cool, paper or a #rrggbb colour")


def rgb(v) -> tuple:
    """0..1 RGB of a backing ('' -> plain white)."""
    v = normalize(v)
    h = BACKINGS[v][1] if v in BACKINGS else (v or "#ffffff")
    n = int(h[1:], 16)
    return ((n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255)
