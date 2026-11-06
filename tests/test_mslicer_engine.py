"""mslicer writes .goo and .ctb. The file checks read magic and, for GOO, the layer count.

Nothing here was sent to a printer.
"""
import struct
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import trimesh

from tests.b1 import ADULT, client

from app.core import resin, resin_fileid
from app.services import mslicer_engine

pytestmark = pytest.mark.skipif(mslicer_engine.mslicer_bin() is None, reason="mslicer binary is not built")


def _stl():
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    return mesh.export(file_type="stl")


def _wait(c, job_id):
    deadline = time.time() + 60
    status = {"status": "queued"}
    while time.time() < deadline and status["status"] in ("queued", "running"):
        time.sleep(0.05)
        status = c.get(f"/api/resin/jobs/{job_id}").json()
    return status


def test_goo_roundtrip_and_independent_layer_count():
    c = client(ADULT)
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("box.stl", _stl(), "model/stl")})
    assert prep.status_code == 200, prep.text
    rid = prep.json()["export"]["rid"]
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection", "file_format": "goo", "anti_alias": "false"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    assert status["report"]["engine"] == "mslicer"
    assert status["report"]["layers"] == 5
    assert status["report"]["hardware_tested"] is False
    assert status["report"]["native_format_written"] is False
    down = c.get(status["download"])
    assert down.status_code == 200
    assert down.headers["content-disposition"].endswith('.goo"') or ".goo" in down.headers["content-disposition"]
    ident = resin_fileid.identify(down.content, "goo")
    assert ident["magic"] == "GOO" and ident["layers_in_file"] == 5
    assert struct.unpack_from(">I", down.content, resin_fileid.GOO_LAYER_COUNT_OFFSET)[0] == 5


def test_ctb_v4_and_v5_magics():
    c = client(ADULT)
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("box.stl", _stl(), "model/stl")})
    rid = prep.json()["export"]["rid"]
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "zeim-inspection", "file_format": "ctb"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    assert status["report"]["ctb_container"] == "legacy"
    data = c.get(status["download"]).content
    assert resin_fileid.identify(data, "ctb")["magic"] == "CTB-v4"
    assert struct.unpack_from("<I", data, 0)[0] == resin_fileid.CTB_V4

    plate = {
        "id": "synthetic-v5", "name": "Synthetic v5", "kind": "upstream-geometry",
        "native_format": ".ctb", "native_version": "v5enc",
        "width_px": 64, "height_px": 48,
        "build_width_um": 32000, "build_depth_um": 24000, "build_height_um": 40000,
    }
    stl = Path(tempfile.mkdtemp()) / "box.stl"
    stl.write_bytes(_stl())
    out = stl.with_suffix(".ctb")
    report = mslicer_engine.slice_file(
        stl, out, plate, resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"}),
        "ctb", aa=False,
    )
    assert report["ctb_container"] == "v5"
    assert resin_fileid.identify(out.read_bytes(), "ctb")["magic"] == "CTB-v5"


def _cli(stl: Path, out: Path, extents):
    binary = mslicer_engine.mslicer_bin()
    mesh = trimesh.creation.box(extents=extents)
    stl.write_bytes(mesh.export(file_type="stl"))
    proc = subprocess.run(
        [str(binary), "--quiet",
         "--platform-resolution", "64, 48",
         "--platform-size", "32, 24, 40",
         "--layer-height", "0.2",
         "--ctb", "legacy",
         "--mesh", str(stl), str(out)],
        capture_output=True, text=True, check=False,
    )
    return proc


def _runs(data):
    """GOO layer runs. Independent of the slicer's own summary line."""
    color = 0
    off = 0
    n = len(data)
    while off < n:
        head = data[off]
        kind = head >> 6
        width_bits = (head >> 4) & 0x03
        length = 0
        if kind == 0:
            color = 0
        elif kind == 1:
            off += 1
            color = data[off]
        elif kind == 2:
            diff_type = (head >> 4) & 0x03
            diff = head & 0x0F
            if diff_type & 1:
                off += 1
                length = data[off]
            else:
                length = 1
            color = (color - diff) & 255 if diff_type & 2 else (color + diff) & 255
        else:
            color = 255
        if kind != 2:
            base = head & 0x0F
            if width_bits == 0:
                length = base
            elif width_bits == 1:
                length = base + (data[off + 1] << 4)
                off += 1
            elif width_bits == 2:
                length = base + (data[off + 1] << 12) + (data[off + 2] << 4)
                off += 2
            else:
                length = base + (data[off + 1] << 20) + (data[off + 2] << 12) + (data[off + 3] << 4)
                off += 3
        off += 1
        yield length, color


def _goo_layers(blob):
    assert blob[4:12] == bytes([0x07, 0x00, 0x00, 0x00, 0x44, 0x4C, 0x50, 0x00])
    count = struct.unpack_from(">I", blob, resin_fileid.GOO_LAYER_COUNT_OFFSET)[0]
    pos = 0x2FB95
    layers = []
    for _ in range(count):
        floats = struct.unpack_from(">15f", blob, pos + 2)
        assert blob[pos + 64:pos + 66] == b"\r\n"
        data_len = struct.unpack_from(">I", blob, pos + 66)[0] - 2
        assert blob[pos + 70] == 0x55
        payload = blob[pos + 71:pos + 71 + data_len]
        end = pos + 71 + data_len
        assert blob[end + 1:end + 3] == b"\r\n"
        lit = sum(length for length, color in _runs(payload) if color)
        layers.append({"z": floats[1], "exposure": floats[2], "lift": floats[7], "lit": lit})
        pos = end + 3
    return layers


def test_first_layer_is_the_slab_above_the_bed(tmp_path):
    """A round solid sitting on z=0 used to get an empty first layer: the plane was the bed, and the flat bottom was dropped."""
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=5.0)
    stl = tmp_path / "ball.stl"
    stl.write_bytes(mesh.export(file_type="stl"))
    out = tmp_path / "ball.goo"
    proc = subprocess.run(
        [str(mslicer_engine.mslicer_bin()), "--quiet",
         "--platform-resolution", "64, 48",
         "--platform-size", "32, 24, 40",
         "--layer-height", "0.5",
         "--first-layers", "2",
         "--transition-layers", "0",
         "--exposure-time", "2.5",
         "--first-exposure-time", "30",
         "--lift-distance", "6",
         "--first-lift-distance", "6",
         "--lift-speed", "65",
         "--first-lift-speed", "65",
         "--retract-speed", "65",
         "--first-retract-speed", "65",
         "--ctb", "legacy",
         "--mesh", str(stl), str(out)],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    layers = _goo_layers(out.read_bytes())
    assert len(layers) == 20
    assert all(layer["lit"] > 0 for layer in layers)
    assert layers[0]["z"] == pytest.approx(0.5, abs=1e-3)
    assert layers[-1]["z"] == pytest.approx(10.0, abs=1e-3)
    assert layers[0]["exposure"] == pytest.approx(30, abs=1e-3)
    assert layers[2]["exposure"] == pytest.approx(2.5, abs=1e-3)
    assert layers[0]["lift"] == pytest.approx(6, abs=1e-3)
    # The mask is the interior of the slab, so the bed layer is smaller than the equator and larger than a point.
    assert layers[0]["lit"] > 4
    assert max(layer["lit"] for layer in layers) > layers[0]["lit"]


def test_jupiter_ctb_is_reachable_through_the_api():
    c = client(ADULT)
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0)
    prep = c.post("/api/resin/prepare", data={"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"},
                  files={"file": ("box.stl", mesh.export(file_type="stl"), "model/stl")})
    assert prep.status_code == 200, prep.text
    body = prep.json()
    assert body["triangles"] == 12 and body["simplified"] is False
    rid = body["export"]["rid"]
    blocked = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "lumen"})
    assert blocked.status_code == 400
    started = c.post(f"/api/resin/{rid}/slice", data={"plate_id": "elegoo-jupiter-ctb", "file_format": "ctb"})
    assert started.status_code == 200, started.text
    status = _wait(c, started.json()["job_id"])
    assert status["status"] == "done", status
    report = status["report"]
    assert report["hardware_tested"] is False and report["native_format_written"] is True
    assert report["file_magic"] == "CTB-v5"
    assert "not printed" in report["note"].lower()
    data = c.get(status["download"]).content
    assert resin_fileid.identify(data, "ctb")["magic"] == "CTB-v5"


def test_volume_warning_uses_the_placed_mesh(tmp_path):
    """A model that fits must not be reported as cut off. One that does not fit must be."""
    fits = _cli(tmp_path / "fits.stl", tmp_path / "fits.goo", (8, 8, 1))
    assert fits.returncode == 0, fits.stderr
    assert "cut off" not in fits.stdout
    assert '"layers":5' in fits.stdout
    hangs = _cli(tmp_path / "hangs.stl", tmp_path / "hangs.goo", (40, 8, 1))
    assert hangs.returncode == 0, hangs.stderr
    assert "cut off" in hangs.stdout
