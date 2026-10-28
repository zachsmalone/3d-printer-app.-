"""Batch 4: sculpt protects a thin wall, remesh is named as subdivision, printer
upload is accepted / start requested / confirmed, and the doctor does not invent a printer."""
from __future__ import annotations

import numpy as np
import trimesh

from app.core import cadops, sculptws
from app.services import doctor, printers
from app.services.printers import _print_confirmed


def _plate(size, thick, n=4):
    m = trimesh.creation.box((size, size, thick))
    for _ in range(n):
        m = m.subdivide()
    return m


def test_live_sculpt_keeps_the_back_of_a_thin_wall_and_the_size_outside_the_brush():
    m = _plate(30, 2)
    center = np.array([0.0, 0.0, 1.0])
    i = int(np.linalg.norm(m.vertices - center, axis=1).argmin())
    before = m.vertices.copy()
    out, rep = sculptws.op_sculpt_stroke(m, {
        "brush": "carve", "points": [center.tolist()], "normal": [0, 0, 1], "radius": 6, "strength": 1,
    })
    back = before[:, 2] < 0
    far = np.linalg.norm(before - center, axis=1) > 8
    assert np.allclose(out.vertices[back], before[back])
    assert np.allclose(out.vertices[far], before[far])
    assert out.vertices[i, 2] < before[i, 2] - 0.2
    assert "back of a thin wall" in rep["message"] and rep["thin_wall_protected"] is True
    assert np.array_equal(m.vertices, before)


def test_a_deep_carve_does_not_pinch_a_thin_wall_below_the_floor_or_move_the_back():
    m = _plate(24, 0.8)
    before = m.vertices.copy()
    out, rep = sculptws.op_sculpt_stroke(m, {
        "brush": "carve", "points": [[0, 0, 0.4]], "normal": [0, 0, 1], "radius": 8, "strength": 1,
    })
    back = before[:, 2] < 0
    assert np.allclose(out.vertices[back], before[back])
    assert rep["thin_wall_clamped"] > 0
    moved = np.linalg.norm(out.vertices - before, axis=1) > 1e-6
    # the back face sits at z=-0.4; a held front vertex stays at least ~0.4 mm above it
    assert out.vertices[moved, 2].min() > -0.05


def test_remesh_is_labelled_uniform_subdivision():
    box = trimesh.creation.box((20, 20, 20))
    out, rep = sculptws.op_remesh(box, {"edge": 4})
    assert len(out.faces) > len(box.faces)
    assert "Uniform subdivision" in rep["message"] and "does not build a new surface" in rep["message"]
    assert sculptws.label("remesh", {"edge": 2}).startswith("Uniform subdivision")
    assert "Fillet 1 mm (1 edges)" in cadops.label("round_edges", {"style": "fillet", "radius": 1, "edges": [[[0, 0, 0], [1, 0, 0]]]})
    assert "approximate mesh" in cadops.label("round_edges", {"style": "fillet", "radius": 1, "body": 0})
    face = cadops.label("face_offset", {"distance": 2})
    assert face.startswith("Face offset 2") and "not a solid offset" in face


def test_print_confirmed_only_when_the_printer_says_printing():
    assert _print_confirmed({"ok": True, "state": "printing", "job_name": "photo3d_demo.gcode"}, "photo3d_demo.gcode")
    assert not _print_confirmed({"ok": True, "state": "standby", "job_name": "photo3d_demo.gcode"}, "photo3d_demo.gcode")
    assert not _print_confirmed({"ok": False, "state": "printing"}, "a.gcode")
    assert not _print_confirmed({"ok": True, "state": "printing", "job_name": "other.gcode"}, "a.gcode")


def test_octoprint_upload_with_start_is_a_request_until_status_confirms(tmp_path, monkeypatch):
    from tests.test_real_print_send import _free_port, _mock_octo_upload
    monkeypatch.delenv("ZEIM_ENV", raising=False)
    port = _free_port()
    _mock_octo_upload(port)
    pr = {"id": "o1", "name": "Octo", "type": "octoprint", "url": f"http://127.0.0.1:{port}", "api_key": "k"}
    gcode = tmp_path / "a.gcode"
    gcode.write_text("G28\n")
    out = printers.send(pr, gcode, "a.gcode", start=True)
    assert out["ok"] is True and out["transfer"] == "accepted" and out["start"] == "requested"
    assert "not confirmed" in out["message"] and "started the print" not in out["message"]
    idle = printers.send(pr, gcode, "a.gcode", start=False)
    assert idle["start"] == "not_requested" and "not started" in idle["message"]


def test_doctor_without_a_saved_printer_stays_general():
    out = doctor.diagnose(["stringing"], "", None, None, None)
    assert out["printer"] is None
    assert "not for one machine" in out["printer_honesty"]
    assert "does not read a failure photo" in out["printer_honesty"]


def test_existing_tool_copy_is_honest_in_source():
    cad = open("static/cad.js", encoding="utf-8").read()
    assert "from \"/static/pickgeom.js\"" in cad
    assert "disposeObj" in cad and "clearGroup" in cad
    assert "Subdivide evenly" in cad and "back of a thin wall stays" in cad
    assert "Shapr3D" not in cad
    send = open("static/send.js", encoding="utf-8").read()
    assert "reference shape, not an editable solid" in send
    html = open("static/index.html", encoding="utf-8").read()
    assert "not precise solid geometry" in html
    assert "editBusyCancel" in html
    app = open("static/app.js", encoding="utf-8").read()
    assert "Start requested, not confirmed" in app and "Print confirmed by the printer" in app
    doc = open("static/doctor.js", encoding="utf-8").read()
    assert "troubleshootingPrinterLabel" in doc and "P.chosen" in doc
