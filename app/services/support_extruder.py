"""Support filament → PrusaSlicer extruder, only when the loaded ini really has one.

PrusaSlicer 2.9.2 (`src/libslic3r/PrintConfig.cpp`, tag version_2.9.2) keys:

* ``support_material_extruder`` — extruder for support material, raft, and skirt.
  Integer, minimum 0, default 1. 0 means the extruder that is already printing.
* ``support_material_interface_extruder`` — extruder for the support interface.
  The tooltip says this also affects the raft interface. Same 0 / 1+ rule, default 1.

2.9.2 has no separate bottom-interface extruder key.
``support_material_bottom_interface_layers`` is a layer count.

Extruder count is not its own ini key. ``PresetBundle`` takes
``min(len(nozzle_diameter), len(filament_diameter))``. One nozzle diameter is one
extruder. A filament name such as "pva" is not an extruder index.
"""
from __future__ import annotations

from dataclasses import replace

from app.services.slice_engine import merge_ini

ONE_EXTRUDER = "This printer has one extruder. Supports use the same filament as the print."
CANNOT_DRIVE = (
    "ZEIM cannot drive a second extruder on this printer. "
    "Supports use the same filament as the print."
)
_KEYS = ("support_material_extruder", "support_material_interface_extruder")


def _ini_map(text: str) -> dict[str, str]:
    out = {}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _values(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def drivable_extruder_count(ini: str) -> int:
    """How many extruders this ini gives PrusaSlicer 2.9.2. 1 when it does not really have a second."""
    keys = _ini_map(ini)
    if "nozzle_diameter" not in keys or "filament_diameter" not in keys:
        return 1
    nozzles = _values(keys["nozzle_diameter"])
    filaments = _values(keys["filament_diameter"])
    if len(nozzles) < 2 or len(nozzles) != len(filaments):
        return 1
    return len(nozzles)


def idle(filament_slots: int) -> dict:
    slots = int(filament_slots or 1)
    return {
        "can_drive": False,
        "extruder_count": 1,
        "message": ONE_EXTRUDER if slots <= 1 else CANNOT_DRIVE,
        "choices": [],
    }


def status(ini: str, filament_slots: int) -> dict:
    """Picker state for an ini ZEIM is about to load."""
    count = drivable_extruder_count(ini)
    if count < 2:
        return idle(filament_slots)
    return {
        "can_drive": True,
        "extruder_count": count,
        "message": "",
        "choices": ["same", *[str(i) for i in range(2, count + 1)]],
    }


def _slot_kind(slot) -> str:
    if slot is None or slot == "":
        return "same"
    if isinstance(slot, bool):
        return "named"
    if isinstance(slot, (int, float)):
        return "same" if int(slot) <= 0 else "index"
    text = str(slot).strip().lower()
    if text in ("", "same"):
        return "same"
    if text.isdigit() and int(text) >= 1:
        return "index"
    return "named"


def _slot_index(slot) -> int:
    if isinstance(slot, bool) or slot is None:
        raise ValueError("not an extruder index")
    if isinstance(slot, (int, float)):
        return int(slot)
    return int(str(slot).strip())


def _classify(strokes: list[dict]) -> tuple[str, int | None]:
    indexes: list[int] = []
    named = False
    for stroke in strokes or []:
        slot = stroke.get("filament_slot", stroke.get("slot", "same"))
        kind = _slot_kind(slot)
        if kind == "same":
            continue
        if kind == "named":
            named = True
            continue
        if kind == "index":
            indexes.append(_slot_index(slot))
            continue
        raise RuntimeError(f"unknown filament slot kind {kind!r}")
    if indexes and len(set(indexes)) > 1:
        return "conflict", None
    if indexes:
        return "index", indexes[0]
    if named:
        return "named", None
    return "same", None


def _blank(count: int) -> dict:
    return {
        "can_drive": count >= 2,
        "extruder_count": count,
        "applied": False,
        "extruder": None,
        "ignored": False,
        "message": "",
    }


def apply(profile, strokes: list[dict] | None, *, filament_slots: int = 1):
    """Return ``(profile, info)``. The ini gains support-extruder keys only for an extruder it has.

    ``filament_slots`` is the catalog count (AMS / MMU / CFS). It chooses the sentence when
    the ini still has one extruder. It does not invent extruders.
    """
    count = drivable_extruder_count(profile.ini)
    kind, index = _classify(strokes or [])
    info = _blank(count)
    if count < 2:
        asked_other = kind in ("named", "conflict") or (kind == "index" and index is not None and index > 1)
        if asked_other:
            info["ignored"] = True
            info["message"] = ONE_EXTRUDER if int(filament_slots) <= 1 else CANNOT_DRIVE
        return profile, info
    if kind == "conflict":
        info["ignored"] = True
        info["message"] = (
            "These paint marks ask for more than one support extruder. "
            "PrusaSlicer uses one support extruder for the whole print, so ZEIM left it unchanged."
        )
        return profile, info
    if kind == "named":
        info["ignored"] = True
        info["message"] = (
            "ZEIM cannot map a filament name to an extruder. "
            "Pick an extruder number this profile actually has."
        )
        return profile, info
    if kind == "same":
        chosen = 0
    elif kind == "index":
        if index is None or index > count:
            info["ignored"] = True
            info["message"] = (
                f"This profile has {count} extruders. Extruder {index} is not one of them, "
                "so ZEIM did not change the support extruder."
            )
            return profile, info
        chosen = index
    else:
        raise RuntimeError(f"unknown support filament request {kind!r}")
    ini = merge_ini(profile.ini, {key: str(chosen) for key in _KEYS})
    info["applied"] = True
    info["extruder"] = chosen
    return replace(profile, ini=ini), info
