"""Which filament slots (Creality CFS ports / Bambu AMS slots) an export references.

ZEIM rule: only the slots the maker picks are referenced. A slot that is not used by any object is never
written into the 3MF or the G-code, so no slicer or printer has a reason to check, map or test it.

* `parse_slots("2")` / `parse_slots("1,3")`: the picked subset (1-based, sorted, de-duplicated). Default [1].
* `plan(colours, slots)`: object colour -> slot. Extra picked slots that no colour needs are dropped (never listed);
  more colours than picked slots fold into the last picked slot. Both cases give a note, never an error.

Inside a 3MF the filaments are numbered 1..n in the order of the used slots (a 3MF has no physical-slot field the
slicers are documented to read); Metadata/zeim_slots.json records filament -> slot so the maker (and ZEIM) can see it.
The physical slot is chosen in the slicer's / printer's own mapping step when the job is sent.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from xml.sax.saxutils import quoteattr

MAX_SLOT = 16          # 4 CFS units x 4 ports / 4 AMS x 4; the picker shows 4 by default


def parse_slots(raw=None) -> list[int]:
    if raw is None or raw == "" or raw == []:
        return [1]
    items = raw if isinstance(raw, (list, tuple)) else re.split(r"[,\s]+", str(raw).strip())
    out = set()
    for it in items:
        try:
            n = int(str(it).strip())
        except ValueError:
            raise ValueError(f"Slot {it!r} is not a number.")
        if not 1 <= n <= MAX_SLOT:
            raise ValueError(f"Slot {n} is out of range (1-{MAX_SLOT}).")
        out.add(n)
    return sorted(out) or [1]


def model_colours(model) -> list[str]:
    cols = []
    for b in model.bodies:
        c = (b.color or "").upper()
        if c and c not in cols:
            cols.append(c)
    return cols


def plan(colours: list[str], slots=None) -> dict:
    """{'slots': used slots, 'filament_of_colour': {colour: filament index 1..n}, 'colour_of_filament': [...], 'notes': [...]}.
    slots=None: Slot 1 for a one-colour model, Slots 1..n for an n-colour model (the default picker state)."""
    colours = [c.upper() for c in colours]
    if slots is None:
        slots = list(range(1, max(1, len(colours)) + 1))[:MAX_SLOT]
    slots = parse_slots(slots)
    notes = []
    need = max(1, len(colours))
    used = slots[:need]
    if len(slots) > need:
        unused = slots[need:]
        notes.append(f"This model has {'one colour' if need == 1 else f'{need} colours'}, so only "
                     f"slot{'s' * (len(used) > 1)} {', '.join(map(str, used))} {'are' if len(used) > 1 else 'is'} used. "
                     f"Slot{'s' * (len(unused) > 1)} {', '.join(map(str, unused))} {'are' if len(unused) > 1 else 'is'} left out of the file.")
    fil = {}
    for i, c in enumerate(colours):
        fil[c] = min(i, len(used) - 1) + 1
    if len(colours) > len(used):
        notes.append(f"This model has {len(colours)} colours but you picked {len(used)} slot{'s' * (len(used) > 1)}. "
                     f"The extra colours print from slot {used[-1]}. You can continue, or pick more slots.")
    col_of = [next((c for c in colours if fil[c] == k + 1), None) for k in range(len(used))]
    return {"slots": used, "filament_of_colour": fil, "colour_of_filament": col_of, "notes": notes}


def _object_ids(model_xml: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r"<object\b([^>]*)>", model_xml):
        a = m.group(1)
        oid = re.search(r'\bid="([^"]+)"', a)
        if not oid or re.search(r'\btype="(support|other|solidsupport)"', a):
            continue
        nm = re.search(r'\bname="([^"]*)"', a)
        out.append((oid.group(1), nm.group(1) if nm else ""))
    return out


def annotate_3mf(data: bytes, p: dict, extruder_of=None) -> bytes:
    """Add Metadata/model_settings.config (object -> filament index, the per-object 'extruder' key that Bambu Studio /
    OrcaSlicer / Creality Print are publicly documented to read) and Metadata/zeim_slots.json. extruder_of(object_id)
    -> filament index; default 1. Nothing about unused slots is written. Existing members are kept as they are."""
    zin = zipfile.ZipFile(io.BytesIO(data))
    root = zin.read("3D/3dmodel.model").decode("utf-8", "replace")
    objs = _object_ids(root)
    n = len(p["slots"])
    cfg = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    for oid, name in objs:
        e = min(max(int(extruder_of(oid) if extruder_of else 1), 1), n)
        cfg.append(f"  <object id={quoteattr(oid)}>")
        if name:
            cfg.append(f'    <metadata key="name" value={quoteattr(name)}/>')
        cfg.append(f'    <metadata key="extruder" value="{e}"/>')
        cfg.append("  </object>")
    cfg.append("</config>")
    info = {"slots": p["slots"], "filament_to_slot": {str(i + 1): s for i, s in enumerate(p["slots"])},
            "colours": p["colour_of_filament"], "notes": p["notes"]}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for it in zin.infolist():
            if it.filename in ("Metadata/model_settings.config", "Metadata/zeim_slots.json"):
                continue
            body = zin.read(it.filename)
            if it.filename == "[Content_Types].xml":
                ct = body.decode("utf-8")
                if 'Extension="config"' not in ct:
                    ct = ct.replace("</Types>", '<Default Extension="config" ContentType="text/xml"/></Types>')
                if 'Extension="json"' not in ct:
                    ct = ct.replace("</Types>", '<Default Extension="json" ContentType="application/json"/></Types>')
                body = ct.encode()
            z.writestr(it, body)
        z.writestr("Metadata/model_settings.config", "\n".join(cfg) + "\n")
        z.writestr("Metadata/zeim_slots.json", json.dumps(info, indent=1))
    return out.getvalue()


def gcode_header(p: dict) -> str:
    return (f"; ZEIM filament slots used: {','.join(map(str, p['slots']))}\n"
            "; ZEIM: single-material G-code, no tool changes. Unused slots are not referenced.\n")
