"""Failure photo doctor (Smart Fix): pick/describe what went wrong (+ optional photo) -> plain-words fixes with real
PrusaSlicer keys from the Smart Fix map. Never auto-applied: only verified keys the ZEIM panel has get an offer, the
browser asks first. Photos go through the normal upload checks and are not kept."""
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config
from app.main import app
from app.services import calibration as cal
from app.services import doctor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
c = TestClient(app)
K1 = {"printer_id": "creality_k1", "nozzle": "0.4", "material": "PLA"}


def _png(exif=False):
    b = io.BytesIO(); im = Image.new("RGB", (64, 48), (200, 80, 40))
    if exif:
        ex = Image.Exif(); ex[0x010F] = "SecretCam"; im.save(b, "JPEG", exif=ex.tobytes())
    else:
        im.save(b, "PNG")
    return b.getvalue()


def test_problem_list_is_the_library():
    j = c.get("/api/doctor/problems").json()
    assert len(j["problems"]) == 25 and {"id", "name", "symptoms"} <= set(j["problems"][0])


@pytest.mark.parametrize("text,want", [("lots of hairy strings between the towers", "stringing"), ("corners lift off the bed", "warping"),
                                       ("layers shifted halfway up", "layer_shift"), ("a big spaghetti mess", "spaghetti_failure"),
                                       ("the part snaps easily", "brittle_parts"), ("bottom edges bulge out, elephant foot", "elephant_foot")])
def test_own_words_find_the_problem(text, want):
    j = c.post("/api/doctor/diagnose", data={"text": text, **K1}).json()
    assert want in [p["id"] for p in j["problems"]], j["problems"]


def test_fixes_are_plain_words_with_real_keys_and_honest_labels():
    j = c.post("/api/doctor/diagnose", data={"problems": "stringing,warping", **K1}).json()
    assert [p["id"] for p in j["problems"]][:2] == ["stringing", "warping"]
    keys = cal.smartfix_map()
    for p in j["problems"]:
        for f in p["fixes"]:
            assert f["plain"].endswith(".") and "_" not in f["plain"]           # no raw keys in the sentence
            assert f["prusa_key"] == keys[f["slicer_key"]]["prusa_key"]
            assert f["needs_confirm"] is True
            if f["apply"]:
                assert f["verified"] and f["slicer_setting"]
    s = {f["slicer_key"]: f for f in j["problems"][0]["fixes"]}
    assert s["nozzle_temperature"]["apply"] == {"field": "spNozT", "from": 210, "to": 205, "unit": "°C", "label": "nozzle temperature"}
    assert "°C" in s["nozzle_temperature"]["plain"] and "PrusaSlicer: temperature" in s["nozzle_temperature"]["where"]
    w = {f["slicer_key"]: f for f in j["problems"][1]["fixes"]}
    assert not w["part_cooling_fan"]["verified"] and w["part_cooling_fan"]["apply"] is None and "Not verified" in w["part_cooling_fan"]["where"]
    assert not w["enclosure"]["slicer_setting"] and "not a slicer setting" in w["enclosure"]["where"]
    assert w["brim_width"]["apply"]["to"] == 5
    assert "estimate" in j["estimate_note"]


def test_offers_never_go_past_the_printer():
    j = c.post("/api/doctor/diagnose", data={"problems": "layer_separation", "printer_id": "creality_k1", "material": "PC"}).json()
    t = next(f for f in j["problems"][0]["fixes"] if f["slicer_key"] == "nozzle_temperature")
    assert t["apply"] is None or t["apply"]["to"] <= 300
    j = c.post("/api/doctor/diagnose", data={"problems": "warping", "printer_id": "elegoo_neptune4_max", "material": "PETG"}).json()
    b = next(f for f in j["problems"][0]["fixes"] if f["slicer_key"] == "bed_temperature")
    assert b["apply"] is None                                                    # already at the 85 °C maximum


def test_without_a_printer_there_is_nothing_to_apply():
    j = c.post("/api/doctor/diagnose", data={"problems": "stringing"}).json()
    assert all(f["apply"] is None for p in j["problems"] for f in p["fixes"])
    j = c.post("/api/doctor/diagnose", data={"problems": "stringing", "printer_id": "elegoo_mars4"}).json()     # resin: no FDM offers
    assert all(f["apply"] is None for p in j["problems"] for f in p["fixes"])


def test_nothing_to_go_on_is_a_plain_error_and_unknown_is_a_hint():
    assert c.post("/api/doctor/diagnose", data={}).status_code == 400
    j = c.post("/api/doctor/diagnose", data={"text": "xyzzy plugh"}).json()
    assert not j["matched"] and "Pick the closest problem" in j["help"]
    assert c.post("/api/doctor/diagnose", data={"text": "x" * 501}).status_code == 400
    j = c.post("/api/doctor/diagnose", data={"problems": "../../etc,stringing"}).json()
    assert [p["id"] for p in j["problems"]] == ["stringing"]


def test_photo_goes_through_the_upload_checks_and_is_not_kept(monkeypatch):
    before = sorted(str(p) for p in config.DATA.rglob("*")) if config.DATA.exists() else []
    r = c.post("/api/doctor/diagnose", data={"problems": "stringing", "photo_ack": "true", **K1}, files={"photo": ("f.jpg", _png(exif=True), "image/jpeg")})
    assert r.status_code == 200 and r.json()["photo"] == {"checked": True, "kept": False, "note": doctor.PHOTO_NOTE}
    after = sorted(str(p) for p in config.DATA.rglob("*")) if config.DATA.exists() else []
    assert [p for p in after if p not in before and not p.endswith((".json", ".lock", ".tmp"))] == []
    assert c.post("/api/doctor/diagnose", data={"problems": "stringing"}, files={"photo": ("x.png", b"not an image", "image/png")}).status_code == 415
    monkeypatch.setattr(config, "PHOTO_ACK_REQUIRED", True)
    assert c.post("/api/doctor/diagnose", data={"problems": "stringing"}, files={"photo": ("f.png", _png(), "image/png")}).status_code == 415
    from app.community import imagemod
    monkeypatch.setattr(imagemod, "review_upload", lambda data, meta=None: imagemod.REJECT)
    assert c.post("/api/doctor/diagnose", data={"problems": "stringing", "photo_ack": "true"}, files={"photo": ("f.png", _png(), "image/png")}).status_code == 415


def test_page_wiring_and_confirm_before_apply():
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "static", "doctor.js"), encoding="utf-8").read()
    pj = open(os.path.join(ROOT, "static", "printer.js"), encoding="utf-8").read()
    assert 'id="docOpen"' in html and 'id="docBox"' in html and "/static/doctor.js" in html and 'for="docText"' in html and 'for="docPhoto"' in html
    assert "askConfirm(" in js and "if (!yes) return;" in js
    assert "applySmartFix();" in pj and "spSmartUndo" in pj


def test_doctor_in_a_real_browser():
    from test_b4_ui import _run
    out = _run("ui_doctor.py")
    assert "PASS webkit" in out, out
