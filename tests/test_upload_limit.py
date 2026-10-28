"""Mesh import ceiling: 500 MiB per file, with the same headroom the 50/55/56 MB stack used.

Photos stay at 25 MB. A direct STL posted to /api/slice stays at 50 MB (that path
does not apply the triangle cap). Triangle and 3MF expansion caps are unchanged.
"""
from pathlib import Path

from app.api.slice import MAX_UPLOAD_BYTES
from app.config import MAX_UPLOAD
from app.core import meshedit
from app.main import MAX_MULTIPART_BODY
from app.services import editproj
from app.services.uploadsafe import MAX_ARCHIVE_BYTES, MAX_BYTES, MAX_FACES
from tests.b1 import box_stl, client

ROOT = Path(__file__).resolve().parents[1]
MIB = 1024 * 1024


def test_mesh_import_ceiling_and_proxy_headroom():
    assert editproj.MAX_UPLOAD_EDIT == 500 * MIB
    assert MAX_MULTIPART_BODY == 560 * MIB
    # 550 MiB is the old 55 MB Caddy slot: above one max file, below the app body cap.
    caddy = 550 * MIB
    assert editproj.MAX_UPLOAD_EDIT < caddy < MAX_MULTIPART_BODY
    prod = (ROOT / "reports/deploy/Caddyfile").read_text(encoding="utf-8")
    local = (ROOT / "reports/deploy/local-https/Caddyfile.local").read_text(encoding="utf-8")
    assert "max_size 550MiB" in prod and "max_size 550MiB" in local
    assert "max_size 55MB" not in prod and "max_size 55MB" not in local


def test_client_copy_matches_the_mesh_ceiling_and_photos_stay_small():
    edit = (ROOT / "static/edit.js").read_text(encoding="utf-8")
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    repair = (ROOT / "static/repair.html").read_text(encoding="utf-8")
    assert "file.size > 500 * 1024 * 1024" in edit
    assert "over 50 MB" not in edit
    assert "MULTI_MAX_BYTES = 500 * 2 ** 20, MULTI_TOTAL_BYTES = 550 * 2 ** 20" in edit
    assert "over 500 MB" in edit and "over 550 MB together" in edit
    assert "up to 25 MB" in html and "up to 500 MB" in html and "up to 50 MB" not in html
    assert "Up to 500 MB." in repair
    assert "file.size > 25 * 1024 * 1024" in edit
    for name in ("static/cad.js", "static/repair.js", "static/torchc0.js"):
        assert "500 * 1024 * 1024" in (ROOT / name).read_text(encoding="utf-8")


def test_unchanged_guards_still_bound_what_500_mb_does_not():
    assert MAX_UPLOAD == 25 * MIB
    assert MAX_BYTES == 25 * MIB
    assert MAX_UPLOAD_BYTES == 50 * MIB
    assert MAX_FACES == meshedit.MAX_FACES == 3_000_000
    assert MAX_ARCHIVE_BYTES == 128 * MIB
    caps = client().get("/api/edit/capabilities").json()
    assert caps["max_upload_mb"] == 500


def test_small_mesh_still_imports():
    r = client().post("/api/edit/new", files={"file": ("cube.stl", box_stl(), "model/stl")})
    assert r.status_code == 200, r.text
    assert r.json()["id"]


def test_a_mesh_over_the_old_50_mb_cap_is_not_refused_for_size():
    # Just past 50 MiB, far under 500. Not a real STL, so the size gate must let it through to sniff.
    payload = b"\0" * (50 * MIB + 1)
    r = client().post("/api/edit/new", files={"file": ("big.stl", payload, "model/stl")})
    assert r.status_code == 415, r.text
    assert "too large" not in r.text.lower()
    assert "50 MB" not in r.text


def test_photo_over_25_mb_is_still_refused():
    payload = b"\0" * (25 * MIB + 1)
    r = client().post("/api/edit/new", files={"file": ("big.jpg", payload, "image/jpeg")})
    assert r.status_code == 413, r.text
    assert r.json()["detail"] == "Photo too large (max 25 MB)."


def test_mesh_over_the_configured_cap_is_413_on_edit_repair_and_multi(monkeypatch):
    monkeypatch.setattr(editproj, "MAX_UPLOAD_EDIT", 2 * MIB)
    blob = b"x" * (2 * MIB + 1)
    c = client()
    edit = c.post("/api/edit/new", files={"file": ("a.stl", blob, "model/stl")})
    assert edit.status_code == 413 and edit.json()["detail"] == "File too large (max 2 MB)."
    repair = c.post("/api/repair", files={"file": ("a.stl", blob, "model/stl")})
    assert repair.status_code == 413 and repair.json()["detail"] == "File too large (max 2 MB)."
    multi = c.post("/api/edit/multi", files=[("files", ("a.stl", blob, "model/stl"))], data={"mode": "separate"})
    assert multi.status_code == 413 and "max 2 MB" in multi.json()["detail"]


def test_multipart_body_over_the_cap_is_refused_before_parsing():
    c = client()
    r = c.post(
        "/api/edit/new",
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(MAX_MULTIPART_BODY + 1)},
    )
    assert r.status_code == 413
    assert r.json()["detail"] == "That file is too large."
