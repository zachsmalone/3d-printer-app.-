"""LUMEN slices: real layer masks, the upstream decoder, and an independent HEAD reader.

Generated-file checks only. Nothing here was printed on a resin printer.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path

import pytest
import trimesh

from tests.b1 import ADULT, client

from app.core import lumen_head, resin, resin_slice
from app.services import resin_jobs

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "tools" / "zeim-lumen" / "target" / "release" / "zeim-lumen"


def _stl(mesh):
    return mesh.export(file_type="stl")


def _cube(size=10.0):
    return resin.orient(trimesh.creation.box(extents=[size, size, size]), 0)


def _settings(**extra):
    base = {"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2",
            "exposure_s": "2.5", "bottom_exposure_s": "30", "bottom_layers": "4",
            "lift_mm": "6", "lift_speed_mm_min": "65"}
    base.update(extra)
    return resin.settings(base)


@pytest.fixture
def c():
    return client(ADULT)


def _inspect(path: Path) -> dict:
    out = subprocess.check_output([str(BIN), "inspect", str(path)], text=True)
    return json.loads(out)


def test_encoder_is_built():
    assert BIN.is_file(), "build tools/zeim-lumen (cargo build --release) before this test"


def test_independent_head_rejects_zip_and_garbage():
    with pytest.raises(lumen_head.LumenHeadError):
        lumen_head.read_head(b"PK\x03\x04" + b"\x00" * 40)
    with pytest.raises(lumen_head.LumenHeadError):
        lumen_head.read_head(b"not a lumen file at all")


def test_rejected_formats_name_the_format():
    for fmt, needle in (("lys", "Lychee"), ("ctbx", ".ctbx"), ("zip", "zip"), ("photon", "Photon")):
        with pytest.raises(resin_slice.ResinSliceError) as exc:
            resin_slice.reject_format(fmt)
        assert needle.lower() in str(exc.value).lower()
    resin_slice.reject_format("lumen")
    resin_slice.reject_format("goo")
    resin_slice.reject_format("ctb")
    resin_slice.reject_format("")


def test_cube_roundtrip_matches_decoder_and_independent_head(tmp_path):
    mesh = _cube(10)
    settings = _settings()
    plate = resin_slice.plate_by_id("zeim-inspection")
    # Baseline: the estimate does no raster and writes no file.
    t0 = time.perf_counter()
    estimate = resin.estimate(float(mesh.extents[2]), float(abs(mesh.volume)), settings)
    baseline_s = time.perf_counter() - t0
    out = tmp_path / "cube.lumen"
    t1 = time.perf_counter()
    report = resin_slice.slice_mesh(mesh, settings, plate, out, aa=False)
    treatment_s = time.perf_counter() - t1
    print(f"\nLUMEN baseline estimate {baseline_s:.4f}s  treatment slice {treatment_s:.4f}s  "
          f"raster {report['seconds_raster']}s  bytes {report['bytes']}  layers {report['layers']}")
    assert baseline_s < treatment_s
    assert treatment_s < 30
    assert report["layers"] == 50
    assert report["layer_height_um"] == 200
    assert report["normal_exposure_ms"] == 2500
    assert report["bottom_exposure_ms"] == 30000
    assert report["bottom_layer_count"] == 4
    assert report["lift_slow_distance_um"] == 6000
    assert report["lift_slow_speed_um_min"] == 65000
    assert report["retract_fast_distance_um"] == 6000
    assert report["native_format_written"] is False and report["hardware_tested"] is False
    assert len(set(report["lit"])) == 1
    # 10 mm / 0.5 mm = 20 px. The binary fill includes the boundary, so 21×21 = 441.
    assert report["lit"][0] == 441
    data = out.read_bytes()
    assert data[:4] == b"LUMN" and data[:2] != b"PK" and data[-8:-4] == b"LEND"
    head = lumen_head.read_head(data)
    info = _inspect(out)
    for key in ("width", "height", "layers", "layer_height_um", "build_width_um", "build_depth_um", "build_height_um"):
        assert head[key] == info[key] == report["head"][key]
    assert info["strict"] is True and info["encrypted"] is False
    assert info["normal_exposure_ms"] == 2500
    assert info["lift_slow_distance_um"] == 6000
    assert info["sha256"] == report["sha256"]
    assert info["preview_png"] > 8
    assert estimate["layers"] == 50


def test_anti_alias_writes_gray_edge_pixels(tmp_path):
    mesh = resin.orient(trimesh.creation.box(extents=[10.3, 9.7, 2.0]), 0)
    settings = _settings()
    plate = resin_slice.plate_by_id("zeim-inspection")
    binary = tmp_path / "bin.lumen"
    smooth = tmp_path / "aa.lumen"
    resin_slice.slice_mesh(mesh, settings, plate, binary, aa=False)
    resin_slice.slice_mesh(mesh, settings, plate, smooth, aa=True, aa_level=4)
    b = _inspect(binary)
    a = _inspect(smooth)
    assert b["layers"] == a["layers"] == 10
    assert b["lit"][0] == b["solid"][0]
    assert a["lit"][0] > a["solid"][0]
    assert a["anti_aliasing"]["enabled"] is True and a["anti_aliasing"]["level"] == 4
    assert a["anti_aliasing"]["mode"] == "coverage"


def test_mars_4_dlp_geometry_encodes_lumen_not_goo(tmp_path):
    """Plate numbers come from the MIT Elegoo plugin. The file is still .lumen."""
    plate = resin_slice.plate_by_id("elegoo-mars-4-dlp-goo")
    assert plate["width_px"] == 2560 and plate["height_px"] == 1440
    assert plate["native_format"] == ".goo"
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    out = tmp_path / "mars.lumen"
    t0 = time.perf_counter()
    report = resin_slice.slice_mesh(mesh, _settings(), plate, out, aa=False)
    elapsed = time.perf_counter() - t0
    print(f"\nMars 4 DLP geometry slice {elapsed:.3f}s raster {report['seconds_raster']}s bytes {report['bytes']}")
    assert report["layers"] == 5
    assert report["width_px"] == 2560 and report["height_px"] == 1440
    assert report["native_format_written"] is False and report["hardware_tested"] is False
    # 8 mm / 0.051875 mm ≈ 154.2 px. Boundary fill lands on 155×155.
    assert report["lit"][0] == 155 * 155
    assert out.read_bytes()[:4] == b"LUMN"
    assert elapsed < 30


def test_oversized_plate_is_rejected_and_not_relabelled():
    plate = resin_slice.plate_by_id("elegoo-mars-5-ultra-ctb")
    assert plate["native_format"] == ".ctb"
    assert plate["pixels"] > resin_slice.MAX_PIXELS
    with pytest.raises(resin_slice.ResinSliceError) as exc:
        resin_slice.slice_mesh(_cube(5), _settings(), plate, Path("/tmp/should-not-write.lumen"))
    text = str(exc.value)
    assert "does not write" in text and ".ctb" in text
    assert not Path("/tmp/should-not-write.lumen").exists()


def test_model_larger_than_plate_is_rejected(tmp_path):
    with pytest.raises(resin_slice.ResinSliceError) as exc:
        resin_slice.slice_mesh(_cube(40), _settings(), resin_slice.plate_by_id("zeim-inspection"), tmp_path / "big.lumen")
    assert "40" in str(exc.value) or "mm" in str(exc.value)


def test_api_slice_download_and_layer_preview(c):
    mesh = _stl(_cube(10))
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("cube.stl", mesh, "model/stl")})
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert "lumen" in body["estimate"]["slice_note"].lower()
    rid = body["export"]["rid"]
    bad = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection", "file_format": "lys"})
    assert bad.status_code == 400 and "Lychee" in bad.json()["detail"]
    assert bad.content[:2] != b"PK"
    mismatch = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-mars-5-goo", "file_format": "ctb"})
    assert mismatch.status_code == 400 and ".goo" in mismatch.json()["detail"]
    huge = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-mars-5-ultra-ctb", "file_format": "lumen"})
    assert huge.status_code == 400 and ".ctb" in huge.json()["detail"]
    cat = c.get("/api/resin/catalog").json()
    assert cat["lumen"]["hardware_tested"] is False
    assert any(p["id"] == "zeim-inspection" for p in cat["lumen_plates"])
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection", "anti_alias": "false", "file_format": "lumen"})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    deadline = time.time() + 30
    status = started.json()
    while time.time() < deadline and status["status"] in ("queued", "running"):
        time.sleep(0.05)
        status = c.get(f"/api/resin/jobs/{job_id}").json()
    assert status["status"] == "done", status
    assert status["report"]["layers"] == 50
    assert status["report"]["hardware_tested"] is False
    assert status["report"]["native_format_written"] is False
    down = c.get(status["download"])
    assert down.status_code == 200
    assert down.content[:4] == b"LUMN" and down.content[:2] != b"PK"
    assert down.headers["content-type"].startswith("application/vnd.openresin.lumen")
    assert down.headers["content-disposition"].endswith('.lumen"') or ".lumen" in down.headers["content-disposition"]
    layer = c.get(f"/api/resin/jobs/{job_id}/layer/0.png")
    assert layer.status_code == 200 and layer.content[:8] == b"\x89PNG\r\n\x1a\n"
    missing = c.get(f"/api/resin/jobs/{job_id}/layer/999.png")
    assert missing.status_code == 404


def test_cancel_stops_a_running_slice(c, monkeypatch):
    mesh = _stl(_cube(8))
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("cube.stl", mesh, "model/stl")})
    rid = prep.json()["export"]["rid"]
    started_flag = {"on": False}

    def hang(mesh, settings, plate, out_path, **kwargs):
        started_flag["on"] = True
        cancel = kwargs.get("cancel")
        while cancel is None or not cancel.is_set():
            time.sleep(0.02)
        raise resin_slice.ResinSliceCancelled("Slice cancelled.")

    monkeypatch.setattr(resin_jobs.resin_slice, "slice_mesh", hang)
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection"})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]
    deadline = time.time() + 5
    while time.time() < deadline and not started_flag["on"]:
        time.sleep(0.02)
    assert started_flag["on"]
    cancelled = c.post(f"/api/resin/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    deadline = time.time() + 5
    status = cancelled.json()
    while time.time() < deadline and status["status"] in ("queued", "running"):
        time.sleep(0.02)
        status = c.get(f"/api/resin/jobs/{job_id}").json()
    assert status["status"] == "cancelled"
    assert c.get(f"/api/resin/jobs/{job_id}/print.lumen").status_code == 404


def test_cli_refuses_other_formats():
    proc = subprocess.run([str(BIN), "ctb"], capture_output=True, text=True)
    assert proc.returncode != 0 and ".lumen" in proc.stderr and "ctb" in proc.stderr


def test_layer_mask_sha_is_stable(tmp_path):
    """The same cube encodes to the same pixels twice. Container bytes may differ by timestamp."""
    mesh = _cube(4)
    settings = _settings(layer_mm="0.2")
    plate = resin_slice.plate_by_id("zeim-inspection")
    a = resin_slice.slice_mesh(mesh, settings, plate, tmp_path / "a.lumen")
    b = resin_slice.slice_mesh(mesh, settings, plate, tmp_path / "b.lumen")
    assert a["sha256"] == b["sha256"]
    assert a["layers"] == 20
    assert hashlib.sha256(a["sha256"][0].encode()).hexdigest()  # hashes are real hex
    int(a["sha256"][0], 16)
