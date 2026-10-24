"""Optional print settings a creator attaches to a Showcase model.

Structured fields feed the existing printer / material / supports filters.
Free-text notes go through the chat filter at the API layer. No GPL/AGPL.
"""
from __future__ import annotations

PRINTERS = ("fdm", "resin", "")
MATERIALS = ("pla", "petg", "abs", "asa", "tpu", "nylon", "resin", "")
SUPPORTS = ("yes", "no", "")
NOTES_MAX = 400
PRINTER_NAME_MAX = 60


class Bad(ValueError):
    pass


def _num(v, *, lo: float, hi: float, label: str, as_int: bool = False):
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise Bad(f"{label} must be a number.")
    if n < lo or n > hi:
        raise Bad(f"{label} must be between {lo:g} and {hi:g}.")
    return int(round(n)) if as_int else round(n, 3)


def check(raw) -> dict:
    """Validate and normalize. None / {} / missing -> empty settings (cleared)."""
    if raw is None or raw == "" or raw == {}:
        return {}
    if not isinstance(raw, dict):
        raise Bad("Print settings must be a set of fields.")
    printer = str(raw.get("printer") or "").strip().lower()
    if printer not in PRINTERS:
        raise Bad("Printer type must be FDM, resin, or left blank.")
    material = str(raw.get("material") or "").strip().lower()
    if material not in MATERIALS:
        raise Bad("Pick a known material, or leave it blank.")
    supports = str(raw.get("supports") or "").strip().lower()
    if supports not in SUPPORTS:
        raise Bad("Supports must be yes, no, or blank.")
    printer_name = str(raw.get("printer_name") or "").strip()[:PRINTER_NAME_MAX]
    notes = str(raw.get("notes") or "").strip()
    if len(notes) > NOTES_MAX:
        raise Bad(f"Notes can be at most {NOTES_MAX} characters.")
    out = {
        "printer": printer,
        "printer_name": printer_name,
        "material": material,
        "layer_height_mm": _num(raw.get("layer_height_mm"), lo=0.05, hi=1.0, label="Layer height"),
        "infill_pct": _num(raw.get("infill_pct"), lo=0, hi=100, label="Infill", as_int=True),
        "supports": supports,
        "nozzle_mm": _num(raw.get("nozzle_mm"), lo=0.1, hi=1.2, label="Nozzle"),
        "notes": notes,
    }
    # Drop empties so storage stays small; callers treat missing as unset.
    return {k: v for k, v in out.items() if v not in (None, "")}


def apply_to_listing(item: dict, settings: dict) -> None:
    """Mirror structured fields onto listing metadata used by Showcase filters."""
    item["print_settings"] = dict(settings)
    if settings.get("printer"):
        item["printer"] = settings["printer"]
        item["printer_type"] = settings["printer"]
    if settings.get("material"):
        item["material"] = settings["material"]
    if settings.get("supports") == "yes":
        item["needs_supports"] = True
        item["supports_level"] = "needed"
    elif settings.get("supports") == "no":
        item["needs_supports"] = False
        item["supports_level"] = "none"


def public(settings) -> dict:
    """Compact public view; always a dict (possibly empty)."""
    if not isinstance(settings, dict):
        return {}
    try:
        return check(settings)
    except Bad:
        return {}
