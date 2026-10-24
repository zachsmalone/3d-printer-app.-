"""Which filament slots (Creality CFS ports / Bambu AMS slots / Prusa MMU / ACE) an export or slice references.

ZEIM rule: only the slots the maker picks are referenced. A slot that is not used by any object is never
written into the 3MF or the G-code, so no slicer or printer has a reason to check, map, heat, prime or purge it.

* `parse_slots("2")` / `parse_slots("1,3")`: the picked subset (1-based, sorted, de-duplicated). Default [1].
* `plan(colours, slots)`: object colour -> slot. Extra picked slots that no colour needs are dropped (never listed);
  more colours than picked slots fold into the last picked slot. Both cases give a note, never an error.
* `plan_heads(slots, materials, colours)`: FDM Slicer per-slot filament + colour. Only the turned-on slots appear.

Inside a 3MF the filaments are numbered 1..n in the order of the used slots (a 3MF has no physical-slot field the
slicers are documented to read); Metadata/zeim_slots.json records filament -> slot so the maker (and ZEIM) can see it.
The physical slot is chosen in the slicer's / printer's own mapping step when the job is sent.

Multi-head UI lives only in the FDM Slicer. Lithophane / Studio / CAD / TorchC0 do not show nozzle or slot pickers.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from xml.sax.saxutils import quoteattr

MAX_SLOT = 16          # 4 CFS units x 4 ports / 4 AMS x 4; the picker shows 4 by default

# Sourced multi_color_system values in the printer catalog -> how many physical slots the UI offers.
SLOT_COUNT_BY_SYSTEM = {
    "AMS": 4,
    "AMS lite": 4,
    "MMU3": 5,
    "ACE Pro": 4,
    "CFS": 4,
}


def slot_count_for_systems(systems) -> int:
    """How many filament slots to offer for this printer. 1 = single-head (no multi-slot UI)."""
    if not systems:
        return 1
    if isinstance(systems, str):
        systems = [systems]
    return max((SLOT_COUNT_BY_SYSTEM.get(str(s), 4) for s in systems), default=1)


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
    return {"slots": used, "filament_of_colour": fil, "colour_of_filament": col_of,
            "materials": ["PLA"] * len(used), "colours": col_of, "notes": notes}


def _align_list(raw, slots: list[int], default):
    """Align a JSON list / comma string / dict-by-slot to the used slots list."""
    if raw is None or raw == "":
        return [default] * len(slots)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("[") or s.startswith("{"):
            try:
                raw = json.loads(s)
            except json.JSONDecodeError:
                raw = re.split(r"[,\s]+", s)
        else:
            raw = re.split(r"[,\s]+", s)
    if isinstance(raw, dict):
        return [raw.get(str(s), raw.get(s, default)) or default for s in slots]
    if isinstance(raw, (list, tuple)):
        out = []
        for i, s in enumerate(slots):
            out.append(raw[i] if i < len(raw) and raw[i] not in (None, "") else default)
        return out
    return [default] * len(slots)


def plan_heads(slots=None, materials=None, colours=None) -> dict:
    """FDM Slicer plan: only the turned-on slots, each with a filament material and colour.
    Unused ports are never listed — G-code / 3MF must not heat, prime or purge them."""
    used = parse_slots(slots)
    mats = [str(m or "PLA") for m in _align_list(materials, used, "PLA")]
    cols = []
    for c in _align_list(colours, used, "#FFFFFF"):
        c = str(c or "#FFFFFF").strip()
        if not c.startswith("#"):
            c = "#" + c
        cols.append(c.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", c) else "#FFFFFF")
    notes = []
    if len(used) == 1:
        notes.append(f"Only slot {used[0]} is used. Other AMS/CFS/MMU ports are not heated, primed or purged.")
    else:
        notes.append(f"Slots {', '.join(map(str, used))} are used. Other ports are not heated, primed or purged.")
    return {"slots": used, "materials": mats, "colours": cols, "colour_of_filament": cols,
            "filament_of_colour": {cols[i]: i + 1 for i in range(len(used))}, "notes": notes}


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
            "colours": p.get("colour_of_filament") or p.get("colours"),
            "materials": p.get("materials"), "notes": p["notes"]}
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
    used = ",".join(map(str, p["slots"]))
    lines = [f"; ZEIM filament slots used: {used}"]
    mats = p.get("materials") or []
    cols = p.get("colours") or p.get("colour_of_filament") or []
    for i, s in enumerate(p["slots"]):
        mat = mats[i] if i < len(mats) and mats[i] else "PLA"
        col = cols[i] if i < len(cols) and cols[i] else ""
        bit = f"; ZEIM slot {s}: {mat}" + (f" {col}" if col else "")
        lines.append(bit)
    if len(p["slots"]) == 1:
        lines.append("; ZEIM: single-material G-code, no tool changes. Unused slots are not referenced.")
    lines.append("; ZEIM: only listed slots are heated, primed or purged. Unused ports are not referenced.")
    return "\n".join(lines) + "\n"


_TOOL_LINE = re.compile(
    r"^(?:T(?P<t>\d+)\b"                                    # tool change
    r"|M10[49]\b[^\n]*\bT(?P<mt>\d+)"                       # M104/M109 … T n
    r"|M104\b[^\n]*\bS(?P<heat>\d+)"                        # bare heat (kept; strip_unused only drops tool-tagged)
    r"|M6(?:00|01|0[12]|701|702)\b"                          # filament change / load / unload macros
    r")",
    re.M | re.I,
)


def strip_unused_heads(gcode: str, p: dict) -> str:
    """Drop heat / prime / purge / tool-change lines that target a slot not in the plan.

    Single used slot (the common ZEIM path): strip every tool-change and filament-change macro so unused
    AMS/CFS/MMU ports are never selected, heated with a tool index, primed or purged. Bare M104/M109
    without a T index stay (single-extruder start G-code).

    Several used slots: keep T / M104 T / M109 T only when the tool index matches a used slot as
    0-based (T0 = slot 1) or 1-based (T1 = slot 1).
    """
    used = set(p["slots"])
    used_0 = {s - 1 for s in used}
    single = len(used) == 1

    def tool_ok(t: int) -> bool:
        return t in used or t in used_0

    out = []
    for line in gcode.splitlines(keepends=True):
        bare = line.split(";", 1)[0].strip()
        if re.match(r"^T\d+\b", bare, re.I):
            if single:
                continue
            t = int(re.match(r"^T(\d+)", bare, re.I).group(1))
            if not tool_ok(t):
                continue
            out.append(line)
            continue
        if re.match(r"^M10[49]\b", bare, re.I):
            tm = re.search(r"\bT(\d+)\b", bare, re.I)
            if tm and (single or not tool_ok(int(tm.group(1)))):
                continue
            out.append(line)
            continue
        if re.match(r"^(M600|M601|M602|M701|M702)\b", bare, re.I):
            if single:
                continue
            tm = re.search(r"\bT(\d+)\b", bare, re.I)
            if not tm or not tool_ok(int(tm.group(1))):
                continue
            out.append(line)
            continue
        out.append(line)
    return "".join(out)
