"""Official multi-material add-ons for a catalog printer.

A printer row lists the units its maker documents (name, slots per unit, max units,
source URL). A unit already named in multi_color_system is the default. Any other
row starts on None, so a K1 without a CFS-C stays a one-slot printer.

The saved choice is unit id plus how many of that one unit. Mixed fleets (AMS lite
with an AMS hub, or AMS 2 Pro together with AMS HT) are separate choices: the
picker stores one kind.
"""
from __future__ import annotations

import re

from app import printers as catalog
from app.services.filament_slots import MAX_SLOT, SLOT_COUNT_BY_SYSTEM


class UnitError(ValueError):
    pass


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def units_from_profile(profile: dict) -> list[dict]:
    """Public unit list. default is true when this row already names that unit."""
    settings = profile.get("settings") or {}
    raw = (settings.get("optional_units") or {}).get("value") or []
    systems = (settings.get("multi_color_system") or {}).get("value") or []
    sources = (settings.get("multi_color_system") or {}).get("sources") or []
    out = []
    names = set()
    for item in raw:
        out.append({
            "id": item["id"],
            "name": item["name"],
            "slots_per_unit": int(item["slots_per_unit"]),
            "max_units": int(item["max_units"]),
            "source": item["source"],
            "default": item["name"] in systems,
        })
        names.add(item["name"])
    for name in systems:
        if name in names:
            continue
        out.append({
            "id": _slug(name),
            "name": name,
            "slots_per_unit": int(SLOT_COUNT_BY_SYSTEM.get(name, 4)),
            "max_units": 1,
            "source": sources[0] if sources else "",
            "default": True,
        })
    return out


def units_for(printer_id: str) -> list[dict]:
    return units_from_profile(catalog.load_printer(printer_id))


def default_slots(profile: dict, systems) -> int:
    """Slot count before the user picks. A listed unit counts as one of that unit."""
    if (profile.get("settings") or {}).get("technology", {}).get("value") == "Resin":
        return 1
    chosen = next((u for u in units_from_profile(profile) if u["default"]), None)
    if chosen:
        return chosen["slots_per_unit"]
    if not systems:
        return 1
    return max((SLOT_COUNT_BY_SYSTEM.get(str(s), 4) for s in systems), default=1)


def _count(raw, maximum: int, name: str) -> int:
    if raw in (None, ""):
        return 1
    if isinstance(raw, bool) or isinstance(raw, float):
        raise UnitError("Unit count must be a whole number.")
    try:
        count = int(str(raw).strip())
    except (TypeError, ValueError):
        raise UnitError("Unit count must be a whole number.") from None
    if count < 1:
        raise UnitError("Unit count must be a whole number.")
    if count > maximum:
        noun = "unit" if maximum == 1 else "units"
        raise UnitError(f"This printer allows up to {maximum} {name} {noun}.")
    return count


def resolve_choice(printer_id: str, unit_id, unit_count=None) -> tuple[str, int]:
    """('none' or a unit id, count). None and '' mean no unit. Unknown ids and over-max counts fail."""
    if unit_id in (None, "", "none"):
        return "none", 1
    if not isinstance(unit_id, str):
        raise UnitError("That multi-material unit is not listed for this printer.")
    found = next((u for u in units_for(printer_id) if u["id"] == unit_id), None)
    if found is None:
        raise UnitError("That multi-material unit is not listed for this printer.")
    count = _count(unit_count, found["max_units"], found["name"])
    if found["slots_per_unit"] * count > MAX_SLOT:
        raise UnitError(f"That many {found['name']} units is more than {MAX_SLOT} filament slots.")
    return found["id"], count


def effective_slots(printer_id: str, unit_id, unit_count=None) -> int:
    """Filament slots for a saved choice. No unit is 1. One listed default is that unit's slots."""
    uid, count = resolve_choice(printer_id, unit_id, unit_count)
    if uid == "none":
        return 1
    found = next(u for u in units_for(printer_id) if u["id"] == uid)
    return found["slots_per_unit"] * count
