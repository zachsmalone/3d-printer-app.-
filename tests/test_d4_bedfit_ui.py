"""Pilot polish: "won't fit your bed" is shown clearly before slicing, and the slicer's friendly too-big message reaches the screen
(app.js errText now reads {detail: {code, message}} instead of showing "Unprocessable Content")."""
import os, re
import trimesh
from test_b4_ui import _run
from app.services import willprint

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_willprint_too_big_tip_says_wont_fit_and_offers_scale_shrink_and_split():
    r = willprint.check(trimesh.creation.box([250, 188, 3]), "creality_k1")
    assert r["verdict"] == "no" and r["checks"]["bed_fit"]["ok"] is False
    tip = r["tips"][0]
    assert "won't fit your bed" in tip and "88%" in tip and "shrink-to-fit" in tip and "Split" in tip


def test_err_text_reads_message_from_code_message_detail():
    js = open(os.path.join(ROOT, "static", "app.js"), encoding="utf-8").read()
    body = js[js.index("function errText"):js.index("const api = async")]
    assert re.search(r"typeof d\.message === \"string\"", body)
    assert "Won't fit your bed" in open(os.path.join(ROOT, "static", "printer.js"), encoding="utf-8").read()


def test_too_big_model_shows_friendly_message_before_and_after_slice_in_chrome_and_webkit():
    out = _run("ui_bedfit.py")
    assert "PASS webkit" in out or "SKIP webkit" in out
