"""One-slot FDM output for printers that can carry a filament box.

What ZEIM's own files contain today (PrusaSlicer 2.9, one extruder in every catalog profile):

* Start G-code on the FDM path is heat, wait, and G28. It does not call START_PRINT.
* The Moonraker K1 preset (``app/profiles/creality_k1.ini``) does call
  ``START_PRINT EXTRUDER_TEMP=… BED_TEMP=…`` and then waits on M109. That preset is a
  different path. This module does not change that file.
* A one-colour slice has a single ``; filament_colour`` value (no semicolon list), no T
  command, and no M600 / M701 / M702. The 3MF has one ``<base>`` and one extruder in
  ``Metadata/model_settings.config``. ``Metadata/zeim_slots.json`` lists only the used slot.
  There is no Creality Print / Bambu ``project_settings.config`` filament map.

What that means for the slot loop:

* The published K1 ``START_PRINT`` macro (CrealityOfficial/K1_Series_Klipper
  ``config/K1_CR4CU220812S12_1/gcode_macro.cfg``) takes ``EXTRUDER_TEMP`` and ``BED_TEMP``
  and, when ``prepare`` is 0, always runs ``CX_PRINT_LEVELING_CALIBRATION``. It has no
  parameter that skips leveling, and it does not take a slot.
* Creality Print's K1 machine start G-code (CrealityOfficial/CrealityPrint
  ``Creality K1 0.4 nozzle.json``) is that same ``START_PRINT`` plus
  ``T[initial_no_support_extruder]``. The profile is ``single_extruder_multi_material``.
  Slot 1 is T0, slot 4 is T3.
* A CFS scan of empty slots is not in that published macro. Owners report the printer
  walking unused CFS ports and restarting the file even when the G-code has no tool
  change. That program is on the printer. A file cannot switch it off.

This module, when the Filament-tab option is on, writes a start that heats, homes, and
names one slot, and does not call START_PRINT, G29, G80, or BED_MESH_CALIBRATE.
``hardware_verified`` stays false until someone prints it.
"""
from __future__ import annotations

import re
from dataclasses import replace

from app import printers as catalog
from app.services.slice_engine import merge_ini

LABEL = "Single slot: skip calibration and unused-slot checks"

# Catalog rows omit multi_color_system for these models ("missing means unknown").
# CFS is an optional box, not a claim that every unit has one.
# K1 machine profile: CrealityOfficial/CrealityPrint Creality K1 0.4 nozzle.json
# (single_extruder_multi_material, T[initial_no_support_extruder]).
# K2 / Hi Combo are the other Creality ids in this catalog whose product line ships CFS.
CREALITY_CFS_IDS = frozenset({
    "creality_k1", "creality_k1_max", "creality_k1c", "creality_k1_se",
    "creality_k2", "creality_k2_plus", "creality_k2_pro", "creality_hi",
})

_SYSTEM_FAMILY = {
    "CFS": "creality_cfs",
    "AMS": "bambu_ams",
    "AMS lite": "bambu_ams",
    "MMU3": "prusa_mmu",
    "ACE Pro": "anycubic_ace",
}

_SLOT_COUNT = {"creality_cfs": 4, "bambu_ams": 4, "prusa_mmu": 5, "anycubic_ace": 4}

_UI_NOTE = {
    "creality_cfs": (
        "On for a one-colour print. Slot 1 is CFS port A and slot 4 is port D. "
        "The file heats the nozzle and the bed, homes, then sends one tool command for that slot. "
        "It does not call START_PRINT. Creality's published K1 START_PRINT macro always runs bed leveling "
        "(CX_PRINT_LEVELING_CALIBRATION), and this file leaves that call out. "
        "The CFS program inside the printer is not in the file, so it can still look at empty slots and start the file again. "
        "ZEIM has not printed this on a K1. Turn this off if the spool is on the side holder. "
        "A tool command can stop a printer that has no filament box."
    ),
    "bambu_ams": (
        "On for a one-colour print. The file heats the nozzle and the bed, homes, and names one slot on the first AMS "
        "(M620, one T command, M621). Slot 1 is T0. It does not contain a G29 bed-level command. "
        "The printer can still level from its own screen. A file that did not come from Bambu Studio may ignore the AMS lines "
        "and use the filament already in the nozzle. ZEIM has not printed this on a Bambu."
    ),
    "prusa_mmu": (
        "On for a one-colour print. The file heats the nozzle and the bed, homes, and sends one MMU tool command. "
        "Slot 1 is T0. An MMU3 has five slots. It does not contain G29 or G80, the mesh commands in Prusa start G-code. "
        "Other slots are not named. ZEIM has not printed this on an MMU."
    ),
    "anycubic_ace": (
        "On for a one-colour print. The file heats the nozzle and the bed, homes, and sends one tool command. "
        "Slot 1 is T0. It does not contain a bed-mesh command. ACE firmware can still check the other slots on its own. "
        "ZEIM has not printed this on an ACE."
    ),
}

_FILE_NOTE = {
    "creality_cfs": (
        "START_PRINT is not in this file. The published K1 macro always runs CX_PRINT_LEVELING_CALIBRATION. "
        "CFS firmware may still scan empty slots."
    ),
    "bambu_ams": (
        "No G29 bed-level command is in this file. The printer can still level on its own. "
        "AMS lines may be ignored if the file was not made by Bambu Studio."
    ),
    "prusa_mmu": "No G29 or G80 mesh command is in this file. Other MMU slots are not named.",
    "anycubic_ace": "No bed-mesh command is in this file. ACE firmware may still check other slots.",
}

_CALIB = (
    re.compile(r"^G29\b", re.I),
    re.compile(r"^BED_MESH_CALIBRATE\b", re.I),
    re.compile(r"^CX_PRINT_LEVELING_CALIBRATION\b", re.I),
    re.compile(r"^PRINT_CALIBRATION\b", re.I),
    re.compile(r"^START_PRINT\b", re.I),
)
_G80 = re.compile(r"^G80(\s|$)", re.I)
_TOOL = re.compile(r"^T(\d+)\b", re.I)
_M620 = re.compile(r"^M620(\s|$)", re.I)
_M621 = re.compile(r"^M621(\s|$)", re.I)
# PrusaSlicer writes these as comments. A semicolon list is how a multi-extruder profile names every slot.
_FILAMENT_META = re.compile(
    r"^;\s*(filament_colour|filament_type|filament_multi_colour|filament_ids)\s*=\s*(.+?)\s*$",
    re.I,
)


def family_id(printer_id: str) -> str | None:
    """Family key, or None when this model has no filament-box path we know how to write."""
    if printer_id in CREALITY_CFS_IDS:
        return "creality_cfs"
    try:
        profile = catalog.load_printer(printer_id)
    except catalog.ProfileValidationError:
        return None
    systems = profile["settings"].get("multi_color_system", {}).get("value") or []
    found = {_SYSTEM_FAMILY[s] for s in systems if s in _SYSTEM_FAMILY}
    if not found:
        return None
    if len(found) != 1:
        return None
    return next(iter(found))


def option_for(printer_id: str) -> dict | None:
    """Catalog payload for the Filament tab. None keeps the tab as it is."""
    fam = family_id(printer_id)
    if fam is None:
        return None
    return {
        "family": fam,
        "slots": _SLOT_COUNT[fam],
        "default_on": True,
        "label": LABEL,
        "note": _UI_NOTE[fam],
        "hardware_verified": False,
    }


def parse_flag(raw) -> bool | None:
    """None = omitted (the server default). True / False = the Filament checkbox."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text == "":
        return None
    if text in ("1", "true", "on", "yes"):
        return True
    if text in ("0", "false", "off", "no"):
        return False
    raise ValueError("Single slot must be on or off.")


def resolve(printer_id: str, slot_plan: dict, flag: bool | None) -> dict | None:
    """The file change for this slice, or None when the option does not apply.

    Omitted flag: on for a one-slot job on a known family. Explicit off stays off.
    More than one slot stays off (those slots are in use).
    """
    fam = family_id(printer_id)
    slots = list(slot_plan.get("slots") or [])
    if fam is None or len(slots) != 1:
        return None
    if flag is False:
        return None
    slot = int(slots[0])
    limit = _SLOT_COUNT[fam]
    if not 1 <= slot <= limit:
        raise ValueError(f"Slot {slot} is outside this printer's list (1–{limit}).")
    tool_index = slot - 1
    return {
        "family": fam,
        "slot": slot,
        "tool_index": tool_index,
        "tool": f"T{tool_index}",
        "hardware_verified": False,
        "firmware_note": _FILE_NOTE[fam],
        "ui_note": _UI_NOTE[fam],
        "ini": _ini(fam, tool_index),
        "load_lines": _load_lines(fam, tool_index),
    }


def apply_profile(prof, spec: dict):
    """PrinterProfile with this family's start G-code merged in."""
    return replace(prof, ini=merge_ini(prof.ini, spec["ini"]))


def plan_fields(spec: dict) -> dict:
    """Keys merged into the slot plan, the G-code header, and zeim_slots.json."""
    return {
        "single_slot": True,
        "family": spec["family"],
        "tool": spec["tool"],
        "hardware_verified": False,
        "firmware_note": spec["firmware_note"],
        "notes": [spec["ui_note"]],
    }


def finish_gcode(text: str, spec: dict) -> str:
    """Drop leveling macros and every tool command except the chosen slot. Insert the load if the slicer left it out."""
    tool = spec["tool"]
    index = spec["tool_index"]
    family = spec["family"]
    seen_tool = False
    seen_m620 = False
    seen_m621 = False
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        line = _one_filament_comment(line)
        bare = line.split(";", 1)[0].strip()
        if not bare:
            kept.append(line)
            continue
        if _is_calibration(bare, family):
            continue
        if _TOOL.match(bare):
            if bare.upper().startswith(tool.upper()) and not seen_tool:
                seen_tool = True
                kept.append(_nl(line))
            continue
        if family == "bambu_ams" and (_M620.match(bare) or _M621.match(bare)):
            got = _s_index(bare)
            if got != index:
                continue
            if _M620.match(bare):
                if seen_m620:
                    continue
                seen_m620 = True
            else:
                if seen_m621:
                    continue
                seen_m621 = True
            kept.append(_nl(line))
            continue
        if _M620.match(bare) or _M621.match(bare):
            continue
        kept.append(line)
    if not seen_tool:
        kept = _insert(kept, spec["load_lines"])
    elif family == "bambu_ams" and not seen_m620:
        kept = _wrap_ams(kept, tool, index)
    return "".join(kept)


def _ini(family: str, tool_index: int) -> dict:
    lines = [
        "M140 S[first_layer_bed_temperature]",
        "M104 S[first_layer_temperature]",
        "M190 S[first_layer_bed_temperature]",
        "M109 S[first_layer_temperature]",
        "G28",
        *_load_lines(family, tool_index),
        "M83",
        "G92 E0",
    ]
    out = {"start_gcode": r"\n".join(lines)}
    if family in ("creality_cfs", "anycubic_ace"):
        # Klipper flavour refuses emit_to_gcode. time_estimate_only is the K1 preset's setting.
        out["gcode_flavor"] = "klipper"
        out["machine_limits_usage"] = "time_estimate_only"
    if family == "creality_cfs":
        out["end_gcode"] = "END_PRINT"
    return out


def _load_lines(family: str, tool_index: int) -> list[str]:
    tool = f"T{tool_index}"
    if family == "bambu_ams":
        # Bambu Studio names an AMS slot as M620 S<n>A … T<n> … M621 S<n>A. A is the first AMS. n is 0-based.
        return [f"M620 S{tool_index}A", tool, f"M621 S{tool_index}A"]
    if family == "creality_cfs":
        return [tool]
    if family == "prusa_mmu":
        return [tool]
    if family == "anycubic_ace":
        return [tool]
    raise ValueError(f"Unknown single-slot family {family!r}.")


def _one_filament_comment(line: str) -> str:
    """A multi-slot colour list in a comment becomes the first value only."""
    body = line.rstrip("\n")
    found = _FILAMENT_META.match(body)
    if not found:
        return line
    first = found.group(2).split(";")[0].strip()
    return f"; {found.group(1)} = {first}\n"


def _is_calibration(bare: str, family: str) -> bool:
    if any(pat.match(bare) for pat in _CALIB):
        return True
    return family == "prusa_mmu" and _G80.match(bare) is not None


def _s_index(bare: str) -> int | None:
    found = re.search(r"\bS(\d+)\b", bare, re.I)
    if not found:
        return None
    return int(found.group(1))


def _nl(line: str) -> str:
    return line if line.endswith("\n") else line + "\n"


def _insert(lines: list[str], load: list[str]) -> list[str]:
    block = [row + "\n" for row in load]
    last = None
    for i, line in enumerate(lines[:250]):
        bare = line.split(";", 1)[0].strip().upper()
        if bare.startswith(("G28", "M109", "M190")):
            last = i
    at = 0 if last is None else last + 1
    return lines[:at] + block + lines[at:]


def _wrap_ams(lines: list[str], tool: str, index: int) -> list[str]:
    out: list[str] = []
    wrapped = False
    for line in lines:
        bare = line.split(";", 1)[0].strip()
        if not wrapped and bare.upper().startswith(tool.upper()):
            out.append(f"M620 S{index}A\n")
            out.append(_nl(line))
            out.append(f"M621 S{index}A\n")
            wrapped = True
            continue
        out.append(line)
    return out
