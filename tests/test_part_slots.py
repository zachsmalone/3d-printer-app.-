"""Filament slot on each part: auto-map, override, clamp, and the single-slot warning.

Slicing still receives one mesh. A multi-slot 3MF export carries the slots.
The warning is a sentence. Turning single slot on does not rewrite the slots.
"""
import io
import json

import trimesh
from fastapi.testclient import TestClient

from app.core import partslots
from app.main import app
from app.services import editproj
from app.services.history import store
from tests.test_mesh_parts import _coloured_3mf


def _clear(client):
    for build in client.get("/api/builds").json()["builds"]:
        client.delete("/api/builds/" + build["id"])


def _drop_caches(bid):
    editproj._BASES.clear()
    editproj._STATES.clear()
    store.cache.pop(bid, None)


def test_nearest_colour_and_one_slot():
    palette = ["#FFFFFF", "#FF0000", "#00AA00"]
    assert partslots.color_distance("#112233", "#112233") == 0
    assert partslots.nearest_slot("#FF0000", palette) == 2
    assert partslots.nearest_slot("#FE0101", palette) == 2
    assert partslots.nearest_slot(None, palette) == 1
    red = {"id": "p1", "name": "Red", "color": "#FF0000", "slot": None}
    blue = {"id": "p2", "name": "Blue", "color": "#0000FF", "slot": None}
    out, flags = partslots.prepare([red, blue], 1, palette)
    assert [p["slot"] for p in out] == [1, 1] and flags == []
    note = partslots.notes(out, 1, True)
    assert note["unit"] == partslots.UNIT_NOTE
    assert note["print"] is None and note["single"] is None


def test_auto_map_override_reset_and_clamp():
    colours = list(partslots.DEFAULT_SLOT_COLOURS)
    parts = [
        {"id": "p1", "name": "Red", "color": "#FF0000", "slot": None},
        {"id": "p2", "name": "Green", "color": "#00FF00", "slot": None},
        {"id": "p3", "name": "Blue", "color": "#0000FF", "slot": None},
    ]
    mapped, _flags = partslots.prepare(parts, 4, colours)
    assert [p["slot"] for p in mapped] == [2, 3, 4]
    assigned, flags = partslots.assign(mapped, ["p1", "p3"], 1, 4)
    assert flags == []
    assert [p["slot"] for p in assigned] == [1, 3, 1]
    reset, _flags = partslots.reset(assigned, ["p1"], 4, colours)
    assert [p["slot"] for p in reset] == [2, 3, 1]
    clamped, flags = partslots.prepare(mapped, 2, colours)
    assert [p["slot"] for p in clamped] == [2, 2, 2]
    assert clamped[0].get("slot_clamped") is not True
    assert clamped[1]["slot_clamped"] is True and clamped[2]["slot_clamped"] is True
    assert {f["was"] for f in flags} == {3, 4}
    assert "outside this printer" in flags[0]["message"]


def test_single_slot_warning_does_not_change_assignments():
    parts = [
        {"id": "p1", "name": "A", "color": "#FF0000", "slot": 1},
        {"id": "p2", "name": "B", "color": "#00FF00", "slot": 3},
    ]
    on = partslots.notes(parts, 4, True)
    assert on["single"] == partslots.SINGLE_NOTE
    assert on["print"] == partslots.PRINT_NOTE
    off = partslots.notes(parts, 4, False)
    assert off["single"] is None and off["print"] == partslots.PRINT_NOTE
    again, flags = partslots.prepare(parts, 4, None)
    assert [p["slot"] for p in again] == [1, 3] and flags == []


def test_api_persists_slots_through_save_clamp_and_cad():
    client = TestClient(app)
    _clear(client)
    colours = list(partslots.DEFAULT_SLOT_COLOURS)
    opened = client.post("/api/edit/new", data={
        "printer_id": "bambu_x1c",
        "slot_colours": json.dumps(colours),
    }, files={"file": ("colour.3mf", _coloured_3mf(), "model/3mf")})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    bid = body["id"]
    assert [p["slot"] for p in body["parts"]] == [2, 3, 2, 4]
    assert body["parts"][0]["color"] == "#FF0000"
    ids = [body["parts"][0]["id"], body["parts"][3]["id"]]
    assigned = client.put(f"/api/edit/{bid}/parts/slots", json={
        "action": "assign", "ids": ids, "slot": 1, "slot_count": 4, "colours": colours,
    })
    assert assigned.status_code == 200, assigned.text
    assert [p["slot"] for p in assigned.json()["parts"]] == [1, 3, 2, 1]
    _drop_caches(bid)
    again = client.get(f"/api/edit/{bid}")
    assert again.status_code == 200
    assert [p["slot"] for p in again.json()["parts"]] == [1, 3, 2, 1]

    warned = client.put(f"/api/edit/{bid}/parts/slots", json={
        "action": "prepare", "slot_count": 4, "colours": colours, "single_slot": True,
    })
    assert warned.status_code == 200, warned.text
    assert [p["slot"] for p in warned.json()["parts"]] == [1, 3, 2, 1]
    assert warned.json()["parts_notes"]["single"] == partslots.SINGLE_NOTE
    assert warned.json()["parts_notes"]["print"] == partslots.PRINT_NOTE
    assert warned.json()["slot_flags"] == []

    clamped = client.put(f"/api/edit/{bid}/parts/slots", json={
        "action": "prepare", "slot_count": 2, "colours": colours, "single_slot": True,
    })
    assert clamped.status_code == 200, clamped.text
    assert [p["slot"] for p in clamped.json()["parts"]] == [1, 2, 2, 1]
    assert {f["was"] for f in clamped.json()["slot_flags"]} == {3}
    assert clamped.json()["parts"][1]["slot_clamped"] is True
    assert "Peg" in clamped.json()["slot_flags"][0]["message"]
    _drop_caches(bid)
    saved = client.get(f"/api/edit/{bid}").json()["parts"]
    assert [p["slot"] for p in saved] == [1, 2, 2, 1]
    scene = client.get(f"/api/cad/{bid}/scene")
    assert scene.status_code == 200, scene.text
    assert [p["slot"] for p in scene.json()["parts"]] == [1, 2, 2, 1]
    stl = client.get(f"/api/download/{bid}/stl")
    assert stl.status_code == 200
    exported = trimesh.load(io.BytesIO(stl.content), file_type="stl", force="mesh")
    assert len(exported.faces) == body["analysis"]["triangles"]
    _clear(client)
