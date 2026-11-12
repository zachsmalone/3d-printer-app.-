"""Filament slot for each part.

A part keeps the colour read from the file. The slot is which CFS, AMS, MMU, or ACE
port prints it. The slicer's slot colours are the configured colours. On import, a
detected colour maps to the nearest of those. With one slot, every part uses slot 1.

A multi-slot 3MF export writes each part's slot. The FDM slice uses those slots
when the printer has a multi-material unit. One slot, or a printer that cannot
drive them, still slices as one colour. A multi-slot print says it is not yet
tested on a printer.
"""
from __future__ import annotations

import copy
import json
import math

# Same starting colours as the FDM filament slots (static/printer.js).
DEFAULT_SLOT_COLOURS = (
    "#FFFFFF", "#FF0000", "#00AA00", "#0066FF",
    "#FFD000", "#FF00AA", "#00DDDD", "#222222",
)
MAX_SLOT = 16

UNIT_NOTE = "Multi-color needs a multi-material unit. Every part uses slot 1."
PRINT_NOTE = "Each part slices on its filament slot. Not yet tested on a printer."
SINGLE_NOTE = (
    "Single slot is on, and these parts use more than one slot. "
    "The slot choices stay as they are."
)


class SlotError(ValueError):
    pass


def clamp_count(value) -> int:
    """How many slots this printer offers, kept inside 1..16."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise SlotError("Slot count must be a whole number.")
    if isinstance(value, bool) or n < 1:
        return 1
    return min(n, MAX_SLOT)


def parse_colours(raw):
    """A list of #RRGGBB colours, or None when the caller did not send any."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list):
        return None
    return raw


def _norm(value) -> str | None:
    if not isinstance(value, str):
        return None
    h = value.strip()
    if not h.startswith("#"):
        return None
    hexes = h[1:]
    if len(hexes) == 8:
        hexes = hexes[:6]
    if len(hexes) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hexes):
        return None
    return "#" + hexes.upper()


def palette_for(slot_count: int, colours=None) -> list[str]:
    """One colour per slot. Missing entries use the slicer's starting colours."""
    count = clamp_count(slot_count)
    got = []
    for item in colours or []:
        norm = _norm(item)
        if norm:
            got.append(norm)
    if not got:
        got = list(DEFAULT_SLOT_COLOURS)
    while len(got) < count:
        got.append(DEFAULT_SLOT_COLOURS[len(got) % len(DEFAULT_SLOT_COLOURS)])
    return got[:count]


def _linear(channel: float) -> float:
    c = channel / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _lab(hex_color: str) -> tuple[float, float, float]:
    """sRGB #RRGGBB to CIE L*a*b* (D65). Used only for nearest-slot matching."""
    h = hex_color[1:]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    R, G, B = _linear(r), _linear(g), _linear(b)
    x = (R * 0.4124564 + G * 0.3575761 + B * 0.1804375) / 0.95047
    y = R * 0.2126729 + G * 0.7151522 + B * 0.0721750
    z = (R * 0.0193339 + G * 0.1191920 + B * 0.9503041) / 1.08883

    def f(t: float) -> float:
        if t > 0.008856:
            return t ** (1.0 / 3.0)
        return 7.787 * t + 16.0 / 116.0

    fx, fy, fz = f(x), f(y), f(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def color_distance(a: str, b: str) -> float:
    """CIE76 distance. Lower is closer. Same hex is 0."""
    la, aa, ba = _lab(a)
    lb, ab, bb = _lab(b)
    return math.sqrt((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2)


def nearest_slot(color, palette: list[str]) -> int:
    """1-based slot whose colour is nearest. No colour, or an empty palette, is slot 1.
    A tie keeps the earlier slot."""
    if not palette:
        return 1
    norm = _norm(color)
    if not norm:
        return 1
    best_i, best_d = 1, None
    for i, col in enumerate(palette, start=1):
        dist = color_distance(norm, col)
        if best_d is None or dist < best_d:
            best_d = dist
            best_i = i
    return best_i


def display_color(part: dict | None, colours=None) -> str | None:
    """The colour to draw: the slot's filament, or the detected colour when no slot is set."""
    if not part:
        return None
    slot = part.get("slot")
    need = slot if type(slot) is int and slot > 0 else 1
    width = max(need, len(colours) if colours else len(DEFAULT_SLOT_COLOURS), 1)
    palette = palette_for(width, colours)
    if type(slot) is int and slot >= 1:
        idx = slot - 1
        if idx < len(palette):
            return palette[idx]
    return _norm(part.get("color"))


def _copy(parts: list[dict]) -> list[dict]:
    return [copy.deepcopy(p) for p in parts]


def _flag(part: dict, was, now: int) -> dict:
    name = part.get("name") or part.get("id") or "Part"
    return {
        "id": part.get("id"),
        "name": name,
        "was": was,
        "slot": now,
        "message": f"Slot {was} on {name} is outside this printer. It is now slot {now}.",
    }


def _clear_flag(part: dict) -> None:
    part.pop("slot_clamped", None)


def prepare(parts: list[dict], slot_count, colours=None) -> tuple[list[dict], list[dict]]:
    """Fill a missing slot from the detected colour, and clamp a slot this printer does not have.

    A slot the user already chose is left alone when it still fits. One slot means every part
    is slot 1.
    """
    count = clamp_count(slot_count)
    palette = palette_for(count, colours)
    flags = []
    out = []
    for part in _copy(parts):
        slot = part.get("slot")
        if type(slot) is int and not 1 <= slot <= count:
            now = count if slot > count else 1
            flags.append(_flag(part, slot, now))
            part["slot"] = now
            part["slot_clamped"] = True
        elif type(slot) is not int:
            part["slot"] = 1 if count <= 1 else nearest_slot(part.get("color"), palette)
            _clear_flag(part)
        out.append(part)
    return out, flags


def assign(parts: list[dict], ids, slot, slot_count) -> tuple[list[dict], list[dict]]:
    """Set the selected parts to one slot. A slot past this printer is clamped and flagged."""
    if not ids:
        raise SlotError("Select a part first.")
    if type(slot) is not int:
        raise SlotError("Slot must be a whole number.")
    count = clamp_count(slot_count)
    known = {p.get("id") for p in parts}
    if any(i not in known for i in ids):
        raise SlotError("That part is not on this model.")
    now = min(max(slot, 1), count)
    flags = []
    chosen = set(ids)
    out = []
    for part in _copy(parts):
        if part.get("id") in chosen:
            if slot != now:
                flags.append(_flag(part, slot, now))
                part["slot_clamped"] = True
            else:
                _clear_flag(part)
            part["slot"] = now
        out.append(part)
    return out, flags


def reset(parts: list[dict], ids, slot_count, colours=None) -> tuple[list[dict], list[dict]]:
    """Put the selected parts back on the slot nearest their detected colour. No ids resets all."""
    count = clamp_count(slot_count)
    palette = palette_for(count, colours)
    known = {p.get("id") for p in parts}
    chosen = set(ids) if ids else set(known)
    if ids and any(i not in known for i in ids):
        raise SlotError("That part is not on this model.")
    out = []
    for part in _copy(parts):
        if part.get("id") in chosen:
            part["slot"] = 1 if count <= 1 else nearest_slot(part.get("color"), palette)
            _clear_flag(part)
        out.append(part)
    return out, []


def apply(parts: list[dict], action, *, ids=None, slot=None, slot_count=1, colours=None):
    kind = action or "prepare"
    if kind == "prepare":
        return prepare(parts, slot_count, colours)
    if kind == "assign":
        return assign(parts, ids or [], slot, slot_count)
    if kind == "reset":
        return reset(parts, ids or [], slot_count, colours)
    raise SlotError("Action must be prepare, assign, or reset.")


def same(a: list[dict], b: list[dict]) -> bool:
    if len(a) != len(b):
        return False
    for left, right in zip(a, b):
        if left.get("id") != right.get("id"):
            return False
        if left.get("slot") != right.get("slot"):
            return False
        if (left.get("slot_clamped") is True) != (right.get("slot_clamped") is True):
            return False
    return True


def distinct_slots(parts: list[dict]) -> list[int]:
    found = []
    for part in parts:
        slot = part.get("slot")
        if type(slot) is int and slot not in found:
            found.append(slot)
    return found


def notes(parts: list[dict], slot_count, single_slot: bool = False) -> dict:
    """Sentences for the editor. Each one is omitted when it would not be true."""
    count = clamp_count(slot_count)
    multi = len(distinct_slots(parts)) > 1
    return {
        "unit": None if count > 1 else UNIT_NOTE,
        "print": PRINT_NOTE if multi else None,
        "single": SINGLE_NOTE if single_slot and multi else None,
    }
