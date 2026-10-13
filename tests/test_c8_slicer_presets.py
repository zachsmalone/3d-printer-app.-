"""Slicer panel: the Advanced fields start from (and follow) the preset the maker picked (2026-10-13).
Bug fixed: Advanced always showed - and sent - Standard's numbers (2 walls, 15 % grid, 80 mm/s), so picking Strong or Fine in Advanced
silently sliced with Standard's settings. Now the catalog carries each preset's numbers, the panel fills them in, and sending the
preset's numbers from Advanced slices exactly like Beginner does."""
import json
import re
import shutil
import subprocess
from pathlib import Path
import pytest
from app.services import print_setup as ps

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static" / "printer.js").read_text()
FIELDS = ("walls", "top_bottom", "infill", "speed")


def _fdm():
    return [p for p in ps.public()["printers"] if p["technology"] != "Resin" and p["nozzles"]]


def test_catalog_presets_carry_their_own_numbers():
    pub = {p["id"]: p for p in ps.public()["presets"]}
    assert set(pub) == set(ps.PRESETS) and ps.public()["default_preset"] in pub
    for k, v in ps.PRESETS.items():
        for f in ("label", "help", "layer_frac", "pattern") + FIELDS:
            assert pub[k][f] == v[f], (k, f)
        assert pub[k]["pattern"] in ps.PATTERNS


def test_advanced_with_the_presets_numbers_slices_exactly_like_beginner_on_every_printer_and_nozzle():
    for p in _fdm():
        for n in p["nozzles"]:
            for k, v in ps.PRESETS.items():
                beginner = ps.settings_for(p["id"], n, {"preset": k})
                advanced = ps.settings_for(p["id"], n, {"preset": k, "layer_height": ps.preset_layer(n, k), "infill_pattern": v["pattern"],
                                                         **{f: v[f] for f in FIELDS}})
                assert advanced == beginner, (p["id"], n, k)


def test_beginner_path_needs_no_expert_fields():
    s = ps.settings_for("creality_k1", 0.4, {})
    assert s["preset"] == ps.DEFAULT_PRESET and s["walls"] == ps.PRESETS["standard"]["walls"] and s["supports"] == "off"


def test_presets_really_differ_so_the_choice_matters():
    s = {k: ps.settings_for("creality_k1", 0.4, {"preset": k}) for k in ps.PRESETS}
    assert s["strong"]["walls"] > s["standard"]["walls"] and s["strong"]["infill"] > s["standard"]["infill"]
    assert s["fine"]["layer_height"] < s["standard"]["layer_height"] < s["draft"]["layer_height"]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_the_panels_layer_formula_matches_the_server_for_every_nozzle_and_preset():
    m = re.search(r"export const presetLayer = (\(pv, rec, lo, hi\) => [^;]+);", JS)
    assert m, "presetLayer() missing from printer.js"
    cases = []
    for n in sorted({n for p in _fdm() for n in p["nozzles"]}):
        lo, hi = ps.layer_range(n)
        rec = ps.nozzle_spec(n)["layer_height_mm"]["recommended"]
        for k, v in ps.PRESETS.items():
            cases.append({"pv": {"layer_frac": v["layer_frac"]}, "rec": rec, "lo": lo, "hi": hi, "want": ps.preset_layer(n, k), "n": n, "k": k})
    src = f"const f = {m.group(1)}; const cs = {json.dumps(cases)}; console.log(JSON.stringify(cs.map(c => f(c.pv, c.rec, c.lo, c.hi))));"
    got = json.loads(subprocess.run(["node", "-e", src], capture_output=True, text=True, check=True, timeout=30).stdout)
    for c, g in zip(cases, got):
        assert abs(g - c["want"]) < 1e-9, (c["n"], c["k"], g, c["want"])


def test_panel_fills_advanced_from_the_preset_and_follows_the_app_level():
    assert ("presetOf(wantPreset)" in JS or "presetOf(P.cat.default_preset)" in JS) and 'pv.walls ?? 2' in JS and 'pv.pattern || "grid"' in JS
    wire = JS.split("export function wirePanel", 1)[1]
    assert '[name=spPreset]' in wire
    for f in ("spWalls", "spTB", "spInfill", "spPattern", "spSpeed", "spLayer"):
        assert f in wire.split("[name=spPreset]", 1)[1].split("$(\"#spGo\")", 1)[0], f
    assert 'localStorage.level !== "expert"' in JS          # Experienced users open the slicer on Advanced until they choose
    assert re.search(r"data-rec=", JS)
