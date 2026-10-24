"""Beginner mode: pick every parameter from (mode, size, preset) + image analysis.

Returns (params, notes). `notes` is a list of {label, value, why} the UI shows so
the user can see exactly what was chosen automatically.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

PRESETS = ("thin", "standard", "thick")


def _analyse(im: Image.Image):
    g = np.asarray(im.convert("L").resize((128, max(2, round(128 * im.height / im.width)))), float) / 255
    p1, p99 = np.percentile(g, [1, 99])
    noise = float(np.std(g - ndimage.median_filter(g, 3)))
    ncol = len(np.unique((np.asarray(im.resize((64, 64))) // 32).reshape(-1, 3), axis=0))
    return dict(contrast=float(p99 - p1), noise=noise, colors=ncol)


# Lithophane starting points per printer type, indexed by preset (thin, standard, thick).
# Resin cures in ~0.05 mm layers with a fine XY pixel, so walls can be thinner and detail finer.
# These are starting suggestions only: real light transmission varies a lot by filament / resin brand and colour.
LITHO_MATERIALS = {
    "filament": dict(thick=[(0.6, 2.4), (0.8, 3.2), (1.0, 4.0)], pitch=0.35, nozzle="matched to a 0.4 mm nozzle"),
    "resin": dict(thick=[(0.5, 2.5), (0.5, 2.8), (0.6, 3.0)], pitch=0.2, nozzle="resin printers resolve finer detail"),
}


def autotune(im: Image.Image, mode: str, width_mm: float, preset: str = "standard", material: str = "filament"):
    preset = preset if preset in PRESETS else "standard"
    material = material if material in LITHO_MATERIALS else "filament"
    mat = LITHO_MATERIALS[material]
    k = PRESETS.index(preset)
    a = _analyse(im)
    notes, P = [], {"width_mm": float(width_mm)}

    def note(label, value, why):
        notes.append({"label": label, "value": str(value), "why": why})

    note("Size", f"{width_mm:g} mm wide", "from your size choice")
    pitch_target = {"lithophane": mat["pitch"], "relief": 0.5, "bust": 0.45, "popart": 0.8}[mode]
    res = int(np.clip(round(width_mm / pitch_target), 100, 500))
    if res > im.width:
        res = max(100, im.width)
        why = "limited by your photo's pixel width (no point upsampling)"
    else:
        why = f"~{pitch_target} mm per pixel, " + (mat["nozzle"] if mode == "lithophane" else "matched to a 0.4 mm nozzle")
    P["resolution"] = res
    note("Detail", f"{res} px across", why)

    noisy = a["noise"] > 0.03
    P["smooth"] = 1.2 if noisy else (0.7 if mode != "relief" else 1.0)
    note("Smoothing", P["smooth"], "photo looks noisy/grainy - smoothing more" if noisy
         else "light smoothing to avoid stair-steps on the print")
    P["auto_contrast"] = a["contrast"] < 0.85
    note("Auto contrast", "on" if P["auto_contrast"] else "off",
         "photo is flat/low-contrast, stretching tones" if P["auto_contrast"]
         else "photo already uses the full tonal range")
    P["gamma"] = 1.0
    P["invert"] = False

    if mode == "lithophane":
        tmin, tmax = mat["thick"][k]
        if material == "resin":
            note("Printer type", "Resin", "thinner walls and finer detail; a starting suggestion, test-print a strip first")
        P.update(min_thickness=tmin, max_thickness=tmax, border_mm=3.0 if width_mm >= 60 else 2.0)
        note("Thickness", f"{tmin}-{tmax} mm", f"'{preset}' preset: {tmin} mm lets the most light through, "
             f"{tmax} mm is the darkest shade")
        note("Frame", f"{P['border_mm']:g} mm border", "adds a sturdy full-thickness frame")
    elif mode == "relief":
        rel = round(width_mm * [0.04, 0.07, 0.11][k], 1)
        P.update(base_mm=[1.5, 2.0, 3.0][k], relief_mm=rel)
        note("Relief height", f"{rel} mm", f"'{preset}' preset = {[4, 7, 11][k]}% of the width")
        note("Base plate", f"{P['base_mm']} mm", "solid backing for strength")
    elif mode == "bust":
        rel = round(width_mm * [0.08, 0.10, 0.13][k], 1)
        ped = [8.0, 12.0, 16.0][k]
        P.update(base_mm=ped, relief_mm=rel, base_style="round", base_margin=8.0)
        note("Face depth", f"{rel} mm", f"'{preset}' preset ≈ {[8, 10, 13][k]}% of the width")
        note("Pedestal", f"{ped:g} mm round base", "clean stand under the bust so it sits on the bed")
        note("Tip", "trace head & shoulders", "Select mode gives a classical bust silhouette; whole photo still works")
    else:
        levels = [3, 4, 5][k]
        lm = round(max(0.6, width_mm * [0.008, 0.012, 0.016][k]), 1)
        P.update(levels=levels, layer_mm=lm, base_mm=2.0, style="posterize", multi_body=True,
                 halftone_cell=6.0)
        note("Colour layers", levels, f"'{preset}' preset; dominant colours are found automatically")
        note("Layer step", f"{lm} mm", "each layer stands this far above the one below")
        note("Bodies", "one per colour layer", "ready for multi-colour printing / filament swaps")
    return P, notes
