"""Universal export API: /api/export hints + sized 3MF/STL for the chosen printer."""
from pathlib import Path

import pytest
import trimesh

from tests.b1 import client, ADULT, photo_build
from app.services import settings, universal_export as ue
from app.services import print_setup as ps

ROOT = Path(__file__).resolve().parent.parent


def test_open_in_hints_mark_official_slicer():
    hints = ue.get_open_in_hints("creality_k1")
    assert len(hints) == 5
    assert {h["id"] for h in hints} == {"creality", "bambustudio", "orcaslicer", "prusaslicer", "cura"}
    assert all(h.get("steps") and h.get("url") for h in hints)
    creality = next(h for h in hints if h["id"] == "creality")
    assert creality["recommended"] is True
    bambu = ue.get_open_in_hints("bambu_x1c")
    assert next(h for h in bambu if h["id"] == "bambustudio")["recommended"] is True


def test_hints_endpoint():
    j = client().get("/api/export/hints").json()
    assert j["count"] == 5 and len(j["hints"]) == 5
    j2 = client().get("/api/export/hints", params={"printer_id": "prusa_mk4"}).json()
    assert next(h for h in j2["hints"] if h["id"] == "prusaslicer")["recommended"] is True


def test_export_info_and_download_sized_for_printer():
    c = client(ADULT)
    bid = photo_build(c)
    info = c.get(f"/api/export/{bid}", params={"printer_id": "bambu_a1_mini"}).json()
    assert info["printer"]["id"] == "bambu_a1_mini"
    assert info["printer"]["bed_mm"][:2] == [180, 180] or info["printer"]["bed_mm"][:2] == [180.0, 180.0]
    assert info["downloads"]["3mf"].startswith(f"/api/export/{bid}/download")
    assert "bambu_a1_mini" in info["filename"]
    assert len(info["open_in_hints"]) == 5

    # Photo builds are ~50 mm wide by default — still centered on the chosen bed.
    r = c.get(f"/api/export/{bid}/download", params={"format": "3mf", "printer_id": "creality_k1"})
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.headers.get("X-Export-Printer") == "creality_k1"
    assert r.headers.get("X-Export-Format") in ("3mf", "stl")

    stl = c.get(f"/api/export/{bid}/download", params={"format": "stl", "printer_id": "creality_k1"})
    assert stl.status_code == 200 and stl.headers.get("X-Export-Format") == "stl"
    m = trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl")
    assert m.bounds[0][2] == pytest.approx(0, abs=1e-3)
    # Centered on K1 bed (220 x 220)
    cx = (m.bounds[0][0] + m.bounds[1][0]) / 2
    cy = (m.bounds[0][1] + m.bounds[1][1]) / 2
    assert cx == pytest.approx(110, abs=0.5)
    assert cy == pytest.approx(110, abs=0.5)


def test_export_uses_account_printer_and_scales_oversized():
    c = client(ADULT)
    assert c.put("/api/me/printer", json={"printer_id": "bambu_a1_mini", "nozzle": 0.4}).status_code == 200
    # Edit-upload a box larger than the mini bed so prepare_mesh scales it.
    big = trimesh.creation.box((250, 100, 40)).export(file_type="stl")
    up = c.post("/api/edit/new", files={"file": ("big.stl", big, "model/stl")})
    assert up.status_code == 200, up.text
    bid = up.json()["id"]
    info = c.get(f"/api/export/{bid}").json()
    assert info["printer"]["id"] == "bambu_a1_mini"
    stl = c.get(f"/api/export/{bid}/download", params={"format": "stl"})
    assert stl.status_code == 200, stl.text
    m = trimesh.load(trimesh.util.wrap_as_stream(stl.content), file_type="stl")
    assert max(m.extents) <= 180 * 1.001
    assert m.bounds[0][2] == pytest.approx(0, abs=1e-3)


def test_export_owner_only_and_bad_printer_falls_back():
    owner, other = client(ADULT), client({**ADULT, "display_name": "Bob Other"})
    bid = photo_build(owner)
    assert other.get(f"/api/export/{bid}").status_code == 404
    assert other.get(f"/api/export/{bid}/download").status_code == 404
    # Invalid printer_id falls back to default K1 rather than 500.
    j = owner.get(f"/api/export/{bid}", params={"printer_id": "not_a_printer"}).json()
    assert j["printer"]["id"] == ps.DEFAULT_PRINTER


def test_effective_slicer_follows_account_printer():
    s = {"default_slicer": "auto", "printers": []}
    assert settings.effective_slicer(s) == "prusaslicer"
    assert settings.effective_slicer(s, user_printer="bambu_x1c") == "bambustudio"
    assert settings.effective_slicer(s, user_printer="creality_k1") == "creality"
    assert settings.effective_slicer(s, user_printer="prusa_mk4") == "prusaslicer"
    assert settings.effective_slicer({"default_slicer": "cura", "printers": []}, user_printer="bambu_x1c") == "cura"


def test_print_links_effective_slicer_uses_profile_printer():
    # Other tests may leave settings.json default_slicer non-auto; pin it so account printer can win.
    settings.save_from_client({"default_slicer": "auto", "printers": settings.load().get("printers", [])})
    c = client(ADULT)
    assert c.put("/api/me/printer", json={"printer_id": "bambu_p1s", "nozzle": 0.4}).json()["stored"] == "profile"
    bid = photo_build(c)
    j = c.get(f"/api/print/{bid}/links").json()
    assert j["default_slicer"] == "auto" and j["effective_slicer"] == "bambustudio"


def test_filename_sanitized():
    assert ue.format_export_filename("abc", "My Cool Vase!", "creality_k1", "3mf") == "My_Cool_Vase_creality_k1.3mf"
    assert ue.format_export_filename("abc", "untitled", "creality_k1", "stl").startswith("photo3d_abc")
