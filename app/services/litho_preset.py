"""Bambu lithophane print preset, embedded in an exported 3MF (original code).

Bambu Studio reads per-object print settings from Metadata/model_settings.config (<object><metadata key=... value=...>),
using the same key names as its print profiles. We add a small, common-sense lithophane set there so the file opens
ready to slice, and a readable Metadata/zeim_print_preset.json saying what was set and why.
Not tested on a real Bambu printer or checked in every Bambu Studio version: the slicer may ignore or rename keys."""
from __future__ import annotations

import io
import json
import re
import zipfile

PRESET_ID = "bambu_litho"
UPRIGHT = ("globe", "cup", "nightlight", "curve")      # printed standing up: a brim helps them stay put
NOTE = "Not tested on a real Bambu printer yet. Check the settings in Bambu Studio before you print."

# key -> (value, why). Keys follow Bambu Studio's print profile names.
BASE = {
    "layer_height": ("0.12", "Fine layers give smoother shading."),
    "wall_loops": ("3", "Solid outline around the picture."),
    "sparse_infill_density": ("100%", "A lithophane is read by light through solid plastic, so no gaps."),
    "sparse_infill_pattern": ("zig-zag", "Even, solid fill."),
    "outer_wall_speed": ("60", "Slower outer wall for a cleaner surface (mm/s)."),
    "inner_wall_speed": ("80", "mm/s."),
    "sparse_infill_speed": ("100", "mm/s."),
    "seam_position": ("back", "Keeps the seam off the picture where possible."),
    "enable_support": ("0", "No supports needed."),
    "ironing_type": ("no ironing", "Ironing would change the thickness, which is the picture."),
}
UPRIGHT_EXTRA = {
    "brim_type": ("outer_only", "Standing shapes are tall and thin: a brim helps them stay on the bed."),
    "brim_width": ("5", "mm."),
}


def settings_for(shape: str) -> dict:
    s = dict(BASE)
    if (shape or "rect") in UPRIGHT:
        s.update(UPRIGHT_EXTRA)
    return s


def add_bambu(data: bytes, shape: str, printer_id: str = "") -> bytes:
    """Return the 3MF with the lithophane settings on every object. Other members are kept as they are."""
    s = settings_for(shape)
    zin = zipfile.ZipFile(io.BytesIO(data))
    names = zin.namelist()
    cfg = zin.read("Metadata/model_settings.config").decode("utf-8") if "Metadata/model_settings.config" in names else None
    if cfg is None:                                   # no per-object config yet: one entry per object in the model
        root = zin.read("3D/3dmodel.model").decode("utf-8", "replace")
        ids = re.findall(r'<object\b[^>]*\bid="(\d+)"', root)
        cfg = '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(f'  <object id="{i}">\n  </object>\n' for i in ids) + "</config>\n"
    lines = "".join(f'    <metadata key="{k}" value="{v}"/>\n' for k, (v, _) in s.items())
    cfg = re.sub(r'(<object\b[^>]*>\n)', lambda m: m.group(1) + lines, cfg)
    info = {"preset": PRESET_ID, "for": "Bambu Studio", "shape": shape or "rect", "printer_id": printer_id,
            "tested_on_hardware": False, "note": NOTE,
            "settings": {k: {"value": v, "why": w} for k, (v, w) in s.items()}}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for it in zin.infolist():
            if it.filename in ("Metadata/model_settings.config", "Metadata/zeim_print_preset.json"):
                continue
            body = zin.read(it.filename)
            if it.filename == "[Content_Types].xml":
                ct = body.decode("utf-8")
                for ext, typ in (("config", "text/xml"), ("json", "application/json")):
                    if f'Extension="{ext}"' not in ct:
                        ct = ct.replace("</Types>", f'<Default Extension="{ext}" ContentType="{typ}"/></Types>')
                body = ct.encode()
            z.writestr(it, body)
        z.writestr("Metadata/model_settings.config", cfg)
        z.writestr("Metadata/zeim_print_preset.json", json.dumps(info, indent=1))
    return out.getvalue()
