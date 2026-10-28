"""Failure photo doctor (Smart Fix): the maker picks what went wrong (and/or describes it in their own words, and may add
a photo); ZEIM suggests fixes in plain words mapped to real PrusaSlicer setting names.

Data: data/troubleshooting/problems.json (25 problems, symptoms, fixes) + data/smartfix/smartfix-map.json (PR #25: which
PrusaSlicer key each fix is, whether it is verified, and whether it is a slicer setting at all).
Rules: nothing is ever applied automatically. A fix can be offered for the ZEIM slicer panel only when its PrusaSlicer key
is verified and the panel has that field; the browser then asks before changing anything (before -> after shown).
ZEIM does not read the photo (no image AI yet): suggestions come from what the maker picks and types. Numbers are
starting points (estimates), not tested by ZEIM on the maker's printer."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.services import calibration as cal
from app.services import print_setup as ps

LIBRARY = Path(__file__).resolve().parents[2] / "data" / "troubleshooting" / "problems.json"
MAX_RESULTS = 3
ESTIMATE = "Suggestions are starting points (estimates). ZEIM hasn't tested them on your printer. Change one thing at a time."
PHOTO_NOTE = "ZEIM doesn't read photos yet: the suggestions come from what you picked and typed. Your photo was checked and not kept."

NAMES = {
    "nozzle_temperature": "nozzle temperature", "temperature": "nozzle temperature", "print_temperature": "nozzle temperature",
    "retraction_distance": "retraction length", "retraction_speed": "retraction speed",
    "travel_avoid_crossing_perimeters": "'avoid crossing walls' for travel moves", "bed_temperature": "bed temperature",
    "brim_width": "brim width", "part_cooling_fan": "part cooling fan", "enclosure": "an enclosure, or close the printer's door and lid",
    "print_speed": "print speed", "acceleration": "acceleration", "machine_maintenance": "belts, wheels and rails",
    "input_shaper": "input shaping / vibration calibration", "flow_ratio": "flow", "nozzle_clean_or_replace": "the nozzle (clean it or replace it)",
    "z_offset": "Z offset (nozzle height)", "first_layer_line_width": "first-layer line width",
    "elephant_foot_compensation": "elephant-foot compensation", "plate_clean": "the build plate (wash it)",
    "first_layer_speed": "first-layer speed", "seam_position": "seam position", "pressure_advance": "pressure advance",
    "outer_wall_speed": "outer wall speed", "filament_diameter": "filament diameter", "line_width": "line width",
    "filament_dry": "the filament (follow the dryer or spool box)", "bridge_flow": "bridge flow", "bridge_design": "the model (add a chamfer or support under the bridge)",
    "model_orientation": "the model's orientation on the bed", "support_material": "supports",
    "support_threshold_angle": "support overhang angle", "support_interface_layers": "support interface layers",
    "support_z_distance": "gap between supports and the model", "support_density": "support density", "support_pattern": "support pattern",
    "first_layer_flow": "first-layer flow", "hotend_cooling_fan": "the hotend cooling fan", "extruder_tension": "extruder tension",
    "filament_path": "the filament path (tangles, tight spool, PTFE tube)", "bed_adhesion": "bed adhesion (clean plate, Z offset, brim)",
    "print_monitoring": "print monitoring (camera / spaghetti detection)", "hole_expansion_compensation": "hole size compensation",
    "xy_compensation": "XY size compensation", "top_layers": "top layers", "top_infill_density": "top infill density",
    "ironing": "ironing", "infill_overlap": "infill/wall overlap", "wall_count": "walls", "infill_density": "infill",
    "power_loss_recovery": "power-loss recovery", "filament_runout_sensor": "the filament run-out sensor",
    "gcode_file_integrity": "the G-code file (slice and copy it again)", "printer_firmware": "the printer's firmware", "layer_height": "layer height",
}
VERBS = {"increase": "Raise", "decrease": "Lower", "enable": "Turn on", "adjust": "Adjust", "calibrate": "Calibrate", "change": "Change",
         "inspect": "Check", "maintenance": "Look after", "dry_filament": "Dry", "recalibrate": "Re-run", "correct": "Correct",
         "modify": "Change", "fix": "Fix", "optional": "Try", "verify": "Re-check", "update": "Update"}
# Words people type -> problem id (on top of each problem's own name + symptoms)
SYNONYMS = {
    "stringing": "string strings stringy hair hairs hairy cobweb cobwebs webbing wisps",
    "warping": "warp warped warping lift lifted lifting corner corners peel peeling",
    "layer_shift": "shift shifted shifting offset misaligned staircase",
    "under_extrusion": "under extrusion underextrusion gaps thin weak missing holes",
    "elephant_foot": "elephant foot bulge flare flared squished bottom",
    "poor_bed_adhesion": "stick sticking adhesion adhere loose detach detached",
    "blobs_zits": "blob blobs zit zits pimples bumps seam",
    "ghosting": "ghost ghosting ringing ripple ripples echo wavy",
    "over_extrusion": "over extrusion overextrusion too much excess rough",
    "layer_separation": "split splitting separate separation delaminate delamination crack cracks",
    "poor_bridging": "bridge bridges bridging sag sagging droop",
    "sagging_overhangs": "overhang overhangs droop drooping curl underside",
    "supports_hard_to_remove": "support supports stuck fused remove removal",
    "first_layer_gaps": "first layer gaps patchy lines",
    "nozzle_clog": "clog clogged clogging blocked nothing comes out",
    "heat_creep": "heat creep jam jammed stops",
    "filament_grinding": "grind grinding clicking click skipping dust chewed",
    "spaghetti_failure": "spaghetti mess tangle tangled air nest birdnest",
    "curling": "curl curling curled edges",
    "dimensional_accuracy": "size dimension dimensions fit tight loose hole holes small",
    "rough_top_surface": "top surface pillow pillowing pillowed",
    "infill_perimeter_gaps": "infill wall gap gaps hollow",
    "visible_layer_lines": "layer lines banding bands lines visible",
    "brittle_parts": "brittle weak snap snaps break breaks fragile",
    "print_stops_midway": "stop stopped stops midway halfway ended quit",
}
STOP = {"between", "lots", "layer", "layers", "the", "and", "with", "from", "that", "this", "there", "have", "into", "when", "very", "some", "print", "printed", "printing", "my", "its"}
# PrusaSlicer key -> ZEIM slicer panel field the browser may fill in (after asking). Only verified keys.
PANEL = {"temperature": ("spNozT", "°C"), "bed_temperature": ("spBedT", "°C"), "brim_width": ("spBrim", "mm"),
         "perimeters": ("spWalls", ""), "fill_density": ("spInfill", "%"), "top_solid_layers": ("spTB", ""),
         "layer_height": ("spLayer", "mm")}
CURRENT = {"temperature": "nozzle_temp", "bed_temperature": "bed_temp", "brim_width": "brim", "perimeters": "walls",
           "fill_density": "infill", "top_solid_layers": "top_bottom", "layer_height": "layer_height"}


@lru_cache(maxsize=1)
def library() -> list[dict]:
    return json.loads(LIBRARY.read_text(encoding="utf-8"))["problems"]


def problems_public() -> list[dict]:
    return [{"id": p["id"], "name": p["name"], "symptoms": p["symptoms"]} for p in library()]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) >= 3 and w not in STOP}


def match(picked: list[str], text: str) -> list[dict]:
    words = _words(text)
    scored = []
    for p in library():
        vocab = _words(p["name"] + " " + " ".join(p["symptoms"])) | set(SYNONYMS.get(p["id"], "").split())
        s = (100 if p["id"] in picked else 0) + len(words & vocab)
        if s:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    if scored and not picked:                    # own words only: drop weak side-matches (one stray shared word)
        top = scored[0][0]
        scored = [x for x in scored if x[0] * 2 >= top]
    return [p for _, p in scored[:MAX_RESULTS]]


def _first_number(amount) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", str(amount or ""))
    return float(m.group()) if m else None


def _proposal(key: str, direction: str, amount, ctx: dict | None):
    """(current, proposed) for a panel field, or None when ZEIM can't offer it safely."""
    if not ctx or key not in PANEL or direction not in ("increase", "decrease", "enable"):
        return None
    cur = ctx["settings"][CURRENT[key]]
    a = _first_number(amount)
    sign = 1 if direction == "increase" else -1
    p = ctx["printer"]
    if key == "temperature":
        new = min(max(cur + sign * (a or 5), 170), p["max_nozzle_c"] or 300)
    elif key == "bed_temperature":
        new = min(max(cur + sign * (a or 5), 0), p["max_bed_c"] or 110)
    elif key == "brim_width":
        new = min(max(cur + sign * (a or 3), 5 if sign > 0 else 0), 30)
    elif key == "perimeters":
        new = min(max(cur + sign * int(a or 1), 1), 10)
    elif key == "top_solid_layers":
        new = min(max(cur + sign * int(a or 1), 0), 20)
    elif key == "fill_density":
        new = min(max(cur + sign * int(a or 10), 0), 100)
    else:                                                         # layer height: a percentage of the current one
        lo, hi = ps.layer_range(ctx["nozzle"])
        new = round(min(max(cur * (1 + sign * (a or 10) / 100), lo), hi), 2)
    new = int(new) if key != "layer_height" else new
    return (cur, new) if new != cur else None


def _fix(f: dict, ctx: dict | None) -> dict:
    m = cal.smartfix_map().get(f["slicer_key"], {})
    key, mode, ver = m.get("prusa_key"), m.get("application_mode", "manual"), m.get("verification", "unverified")
    name = NAMES.get(f["slicer_key"], f["slicer_key"].replace("_", " "))
    verb = "Use" if f["slicer_key"] == "enclosure" else VERBS.get(f["direction"], "Adjust")
    amount = f.get("amount")
    by = f" by {amount}" if amount and f["direction"] in ("increase", "decrease") and not str(amount).startswith("needs") else \
         f" ({amount})" if amount and not str(amount).startswith("needs") else ""
    plain = re.sub(r"(\d) C\b", "\\1 °C", f"{verb} {name}{by}." + (f" {f['note']}." if f.get("note") else ""))
    out = {"slicer_key": f["slicer_key"], "prusa_key": key, "plain": plain.replace("..", "."), "direction": f["direction"], "amount": amount,
           "slicer_setting": bool(key) and mode != "manual", "verified": ver.startswith("verified"), "verification": ver,
           "needs_confirm": True, "apply": None}
    if not key or mode == "manual":
        out["where"] = "On the printer or the model, not a slicer setting."
    elif mode == "unsupported" or not out["verified"]:
        out["where"] = (f"PrusaSlicer: {key}. " if key else "") + "Not verified for PrusaSlicer yet: change it by hand only if you know the setting."
    else:
        out["where"] = f"PrusaSlicer: {key}."
        prop = _proposal(key, f["direction"], amount, ctx) if out["verified"] else None
        if prop:
            field, unit = PANEL[key]
            out["apply"] = {"field": field, "from": prop[0], "to": prop[1], "unit": unit, "label": name}
    return out


def diagnose(picked: list[str], text: str, printer_id=None, nozzle=None, material=None) -> dict:
    known = {p["id"] for p in library()}
    picked = [p for p in picked if p in known]
    ctx = None
    if printer_id or nozzle or material:
        try:
            pid, n = ps.resolve(printer_id, None if nozzle in (None, "") else float(nozzle))
            if n is not None:
                ctx = {"printer": ps.printer_public(pid), "nozzle": n,
                       "settings": ps.settings_for(pid, n, {"material": material or "PLA"})}
        except (ps.SetupError, ValueError):
            ctx = None
    found = match(picked, text)
    res = []
    for p in found:
        note = None
        if ctx:
            notes = p.get("printer_notes") or {}
            fam = "creality_k1" if ctx["printer"]["id"].startswith("creality_k1") else \
                  "bambu" if ctx["printer"]["brand"] == "Bambu Lab" else "prusa" if ctx["printer"]["brand"] == "Prusa" else None
            note = notes.get(fam) if fam else None
        res.append({"id": p["id"], "name": p["name"], "symptoms": p["symptoms"], "printer_note": note,
                    "fixes": [_fix(f, ctx) for f in p["fixes"]], "sources": p.get("sources", [])})
    if ctx:
        printer_honesty = (f"Printer notes use the catalog profile for {ctx['printer']['name']}. "
                           "ZEIM is not connected to that printer, and it does not read a failure photo.")
    else:
        printer_honesty = ("No saved printer was included, so these fixes are general. "
                           "They are not for one machine, and ZEIM does not read a failure photo.")
    return {"problems": res, "matched": bool(res), "estimate_note": ESTIMATE,
            "printer": ctx["printer"]["name"] if ctx else None,
            "printer_honesty": printer_honesty,
            "help": None if res else "We couldn't match that yet. Pick the closest problem from the list, or describe what you see (for example 'strings between parts' or 'corners lift')."}
