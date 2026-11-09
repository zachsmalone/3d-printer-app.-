"""DragonFruit writes .ctb. .goo stays on mslicer. Nothing here was printed."""
from __future__ import annotations

import os
import time

import numpy as np
import pytest
import trimesh

from tests.test_mslicer_engine import _ctb_v4_view

from app.core import resin, resin_slice
from app.services import dragonfruit_engine, mslicer_engine, resin_engine


def test_goo_stays_on_mslicer_and_ctb_follows_the_switch(monkeypatch):
    assert resin_slice.writer_for("goo") == "mslicer"
    assert resin_slice.writer_for("lumen") == "lumen"
    monkeypatch.setenv("ZEIM_RESIN_ENGINE", "mslicer")
    assert resin_slice.writer_for("ctb") == "mslicer"
    monkeypatch.setenv("ZEIM_RESIN_ENGINE", "dragonfruit")
    if dragonfruit_engine.dragonfruit_bin() is None:
        assert resin_slice.writer_for("ctb") == "mslicer"
    else:
        assert resin_slice.writer_for("ctb") == "dragonfruit"
        assert resin_slice.writer_for("nanodlp") == "dragonfruit"


def test_y_flag_matches_mslicer_unless_the_catalog_mirror_is_set():
    plain = {"name": "Jupiter", "mirror_x": False, "mirror_y": False}
    assert dragonfruit_engine.cli_mirrors(plain) == (False, True)
    flipped = {"name": "Jupiter SE", "mirror_x": False, "mirror_y": True}
    assert dragonfruit_engine.cli_mirrors(flipped) == (False, False)
    both = {"name": "Both", "mirror_x": True, "mirror_y": True}
    assert dragonfruit_engine.cli_mirrors(both) == (True, False)
    with pytest.raises(dragonfruit_engine.DragonFruitError):
        dragonfruit_engine.cli_mirrors({"name": "Unset", "mirror_x": None, "mirror_y": False})


def test_uncertain_mirror_is_still_refused():
    plate = {
        "name": "Mystery", "kind": "upstream-geometry", "native_format": ".ctb",
        "native_version": "v5", "width_px": 100, "height_px": 100,
        "mirror_x": "yes", "mirror_y": False,
    }
    reason = resin_slice.block_reason(plate, "ctb")
    assert "not true or false" in reason


@pytest.mark.skipif(
    dragonfruit_engine.dragonfruit_bin() is None or mslicer_engine.mslicer_bin() is None,
    reason="both slicer binaries are required",
)
def test_orientation_matches_mslicer_on_an_asymmetric_part(tmp_path):
    """The +Y tab lands on the same side of the image as mslicer's file."""
    plate = {
        "id": "parity", "name": "Parity", "kind": "inspection",
        "native_format": ".ctb", "native_version": "",
        "width_px": 160, "height_px": 120,
        "build_width_um": 80000, "build_depth_um": 60000, "build_height_um": 40000,
        "mirror_x": False, "mirror_y": False,
    }
    bar = trimesh.creation.box(extents=[20, 8, 2])
    bar.apply_translation([40, 30, 1])
    tab = trimesh.creation.box(extents=[6, 8, 6])
    tab.apply_translation([40, 40, 3])
    mesh = trimesh.util.concatenate([bar, tab])
    stl = tmp_path / "tab.stl"
    stl.write_bytes(mesh.export(file_type="stl"))
    settings = resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"})
    ms_out = tmp_path / "ms.ctb"
    df_out = tmp_path / "df.ctb"
    mslicer_engine.slice_file(stl, ms_out, plate, settings, "ctb", aa=False, placed=True)
    report = dragonfruit_engine.slice_file(stl, df_out, plate, settings, "ctb", aa=False, placed=True)
    assert report["engine"] == "dragonfruit"
    assert report["y_convention"] == "mslicer"
    assert report["triangles"] == len(mesh.faces)
    ms = _ctb_v4_view(ms_out.read_bytes())
    df = _ctb_v4_view(df_out.read_bytes())
    assert ms["plate"][2] == pytest.approx(40, abs=0.05)
    assert df["plate"][2] == pytest.approx(40, abs=0.05)
    high_ms = [layer for layer in ms["layers"] if layer["z"] > 4 and layer["end"][0] >= 0]
    high_df = [layer for layer in df["layers"] if layer["z"] > 4 and layer["end"][0] >= 0]
    assert high_ms and high_df
    ms_mid = (high_ms[0]["origin"][1] + high_ms[0]["end"][1]) / 2
    df_mid = (high_df[0]["origin"][1] + high_df[0]["end"][1]) / 2
    assert df_mid == pytest.approx(ms_mid, abs=3)
    assert ms_mid > ms["height"] / 2
    assert df_mid > df["height"] / 2


@pytest.mark.skipif(dragonfruit_engine.dragonfruit_bin() is None, reason="dragonfruit CLI is not built")
def test_supported_mesh_is_the_mesh_dragonfruit_slices(tmp_path):
    box = trimesh.creation.box(extents=[12, 10, 6])
    bed = (40.0, 40.0, 80.0)
    bare, _ = resin.prepare(box, resin.settings({
        "hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2",
    }), bed)
    held, rep = resin.prepare(box, resin.settings({
        "hollow": "false", "supports": "true", "tilt_deg": "0", "layer_mm": "0.2",
    }), bed)
    assert rep["support"]["supports"] > 0
    assert len(held.faces) > len(bare.faces)
    stl = tmp_path / "supported.stl"
    stl.write_bytes(held.export(file_type="stl"))
    plate = {
        "id": "support-plate", "name": "Support plate", "kind": "inspection",
        "native_format": ".ctb", "native_version": "v4",
        "width_px": 200, "height_px": 200,
        "build_width_um": 40000, "build_depth_um": 40000, "build_height_um": 80000,
        "mirror_x": False, "mirror_y": False,
    }
    out = tmp_path / "supported.ctb"
    report = dragonfruit_engine.slice_file(
        stl, out, plate, resin.settings({"hollow": "false", "supports": "true", "tilt_deg": "0", "layer_mm": "0.2"}),
        "ctb", aa=False, placed=True,
    )
    assert report["triangles"] == len(held.faces)
    assert report["triangles_sent"] == len(held.faces)


@pytest.mark.skipif(dragonfruit_engine.dragonfruit_bin() is None, reason="dragonfruit CLI is not built")
def test_saturn2_ctb_uses_dragonfruit(tmp_path):
    """Saturn 2 is the second plate. Its catalog mirror_y is applied, and the file is encrypted v5."""
    plate = resin_slice.plate_by_id("elegoo-saturn-2-ctb")
    assert plate["mirror_y"] is True and plate["native_version"] == "v5enc"
    assert resin_slice.block_reason(plate, "ctb") == ""
    mesh = resin.orient(trimesh.creation.box(extents=[8, 8, 1.0]), 0, 0, resin_slice.plate_bed_mm(plate))
    stl = tmp_path / "box.stl"
    stl.write_bytes(mesh.export(file_type="stl"))
    out = tmp_path / "saturn.ctb"
    report = dragonfruit_engine.slice_file(
        stl, out, plate,
        resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"}),
        "ctb", aa=False, placed=True,
    )
    assert report["engine"] == "dragonfruit"
    assert report["mirror_applied"] is True and report["mirror_y"] is True
    assert report["file_magic"] == "CTB-v5"
    assert report["ctb_container"] == "v5enc"
    assert out.read_bytes()[:4] == b"\x07\x01\xfd\x12"


def test_fallback_records_mslicer_when_dragonfruit_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("ZEIM_RESIN_ENGINE", "dragonfruit")
    monkeypatch.setattr(resin_slice, "dragonfruit_bin", lambda: tmp_path / "dragonfruit-cli")
    (tmp_path / "dragonfruit-cli").write_bytes(b"#!/bin/sh\nexit 1\n")
    os.chmod(tmp_path / "dragonfruit-cli", 0o755)

    def boom(*_args, **_kwargs):
        raise dragonfruit_engine.DragonFruitError("DragonFruit failed: boom")

    monkeypatch.setattr(dragonfruit_engine, "slice_file", boom)
    monkeypatch.setattr(dragonfruit_engine, "dragonfruit_bin", lambda: tmp_path / "dragonfruit-cli")
    plate = resin_slice.plate_by_id("zeim-inspection")
    stl = tmp_path / "box.stl"
    stl.write_bytes(trimesh.creation.box(extents=[8, 8, 1]).export(file_type="stl"))
    out = tmp_path / "out.ctb"
    if mslicer_engine.mslicer_bin() is None:
        pytest.skip("mslicer binary is not built")
    report = resin_engine.slice_printer_file(
        stl, out, plate, resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"}),
        "ctb", aa=False, placed=False,
    )
    assert report["engine"] == "mslicer"
    assert report["engine_requested"] == "dragonfruit"
    assert "boom" in report["engine_fallback"]


def _heavy(grid: int = 476) -> trimesh.Trimesh:
    xs = np.linspace(-24.0, 24.0, grid, dtype=np.float64)
    ys = np.linspace(-20.0, 20.0, grid, dtype=np.float64)
    x, y = np.meshgrid(xs, ys, indexing="ij")
    z = 4.0 + 6.0 * np.sin(x / 6.5) ** 2 * np.cos(y / 5.5)
    z = z - z.min()
    z = z / z.max() * 20.0
    n = grid - 1
    x00, x10, x11, x01 = x[:-1, :-1], x[1:, :-1], x[1:, 1:], x[:-1, 1:]
    y00, y10, y11, y01 = y[:-1, :-1], y[1:, :-1], y[1:, 1:], y[:-1, 1:]
    z00, z10, z11, z01 = z[:-1, :-1], z[1:, :-1], z[1:, 1:], z[:-1, 1:]

    def pack(a, b, c):
        return np.stack((a, b, c), axis=-1)

    top = np.concatenate((
        np.stack((pack(x00, y00, z00), pack(x10, y10, z10), pack(x11, y11, z11)), axis=-2),
        np.stack((pack(x00, y00, z00), pack(x11, y11, z11), pack(x01, y01, z01)), axis=-2),
    ), axis=0).reshape(-1, 3, 3)
    zero = np.zeros_like(z00)
    bot = np.concatenate((
        np.stack((pack(x00, y00, zero), pack(x01, y01, zero), pack(x11, y11, zero)), axis=-2),
        np.stack((pack(x00, y00, zero), pack(x11, y11, zero), pack(x10, y10, zero)), axis=-2),
    ), axis=0).reshape(-1, 3, 3)
    tris = np.concatenate((top, bot), axis=0).astype(np.float32)
    assert len(tris) >= 900_000
    return trimesh.Trimesh(vertices=tris.reshape(-1, 3), faces=np.arange(len(tris) * 3).reshape(-1, 3), process=False)


@pytest.mark.skipif(dragonfruit_engine.dragonfruit_bin() is None, reason="dragonfruit CLI is not built")
def test_heavy_mesh_slices_on_jupiter(tmp_path):
    """906k triangles, the scale of the bench sculpt. Records the wall time."""
    mesh = _heavy()
    stl = tmp_path / "heavy.stl"
    stl.write_bytes(mesh.export(file_type="stl"))
    plate = resin_slice.plate_by_id("elegoo-jupiter-ctb")
    out = tmp_path / "heavy.ctb"
    started = time.monotonic()
    report = dragonfruit_engine.slice_file(
        stl, out, plate,
        resin.settings({"hollow": "false", "supports": "false", "tilt_deg": "0", "layer_mm": "0.2"}),
        "ctb", aa=False, placed=False,
    )
    elapsed = time.monotonic() - started
    assert report["engine"] == "dragonfruit"
    assert report["triangles"] == len(mesh.faces)
    assert report["layers"] > 50
    assert elapsed < 180, elapsed
    print(f"heavy mesh {len(mesh.faces)} triangles in {elapsed:.2f}s")
