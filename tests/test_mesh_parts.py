"""Imported meshes keep separate parts (name, colour, source material, slot).

Slicing and the other single-mesh tools still receive the parts concatenated.
An older project with no parts list is one part covering the whole mesh.
"""
import io
import json
import zipfile

import numpy as np
import trimesh
from fastapi.testclient import TestClient

from app.core import meshedit, meshparts
from app.main import app
from app.services import editproj
from app.services.history import store


def _box(size, shift):
    m = trimesh.creation.box(extents=size)
    m.apply_translation(shift)
    return m


def _3mf(objects, items, materials=None, extra=""):
    body = (materials or "") + "".join(objects) + extra
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
           f"<resources>{body}</resources><build>{''.join(items)}</build></model>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("_rels/.rels", "<Relationships/>")
        z.writestr("3D/3dmodel.model", xml)
    return buf.getvalue()


def _mesh_xml(mesh, oid, name, pid=None, index=None):
    verts = "".join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in mesh.vertices)
    tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
    paint = f' pid="{pid}" pindex="{index}"' if pid is not None else ""
    return (f'<object id="{oid}" type="model" name="{name}"{paint}>'
            f"<mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh></object>")


def _coloured_3mf():
    box, peg, ball = _box((20, 20, 10), (0, 0, 0)), trimesh.creation.cylinder(radius=6, height=15, sections=16), trimesh.creation.icosphere(subdivisions=1, radius=8)
    mats = ('<basematerials id="10">'
            '<base name="Red" displaycolor="#FF0000FF"/>'
            '<base name="Green" displaycolor="#00FF00FF"/>'
            '<base name="Blue" displaycolor="#0000FFFF"/>'
            "</basematerials>")
    objects = [
        _mesh_xml(box, 1, "Box", 10, 0),
        _mesh_xml(peg, 2, "Peg", 10, 1),
        _mesh_xml(ball, 3, "Ball", 10, 2),
        '<object id="4" name="Asm" type="model"><components>'
        '<component objectid="1" transform="1 0 0 0 1 0 0 0 1 0 0 0"/>'
        '<component objectid="2" transform="1 0 0 0 1 0 0 0 1 0 0 12"/>'
        "</components></object>",
    ]
    items = [
        '<item objectid="4" transform="1 0 0 0 1 0 0 0 1 50 50 0"/>',
        '<item objectid="3" transform="1 0 0 0 1 0 0 0 1 0 0 30"/>',
        '<item objectid="1" transform="2 0 0 0 2 0 0 0 1 -40 0 0"/>',
    ]
    return _3mf(objects, items, mats)


def _obj_with_groups():
    base, cap = _box((10, 10, 10), (0, 0, 0)), _box((4, 4, 4), (30, 0, 0))
    lines = ["mtllib demo.mtl"]
    offset = 0
    for name, mesh in (("Base", base), ("Cap", cap)):
        lines.append(f"o {name}")
        lines.append(f"g {name}_grp")
        lines.append(f"usemtl mat_{name}")
        lines.extend(f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in mesh.vertices)
        for face in mesh.faces + 1:
            lines.append("f " + " ".join(str(int(i + offset)) for i in face))
        offset += len(mesh.vertices)
    obj = ("\n".join(lines) + "\n").encode()
    mtl = b"newmtl mat_Base\nKd 1 0 0\nnewmtl mat_Cap\nKd 0 0 1\n"
    return obj, mtl


def _two_shell_stl():
    mesh = trimesh.util.concatenate([_box((10, 10, 10), (0, 0, 0)), _box((4, 4, 4), (30, 0, 0))])
    return mesh.export(file_type="stl")


def _clear(client):
    for build in client.get("/api/builds").json()["builds"]:
        client.delete("/api/builds/" + build["id"])


def test_3mf_keeps_each_build_item_colour_and_name():
    data = _coloured_3mf()
    mesh, parts, warnings = meshedit.load_document(data, "3mf", split_shells=True)
    assert not any("not kept" in w for w in warnings)
    assert [p["name"] for p in parts] == ["Box", "Peg", "Box", "Ball"]
    assert [p["color"] for p in parts] == ["#FF0000", "#00FF00", "#FF0000", "#0000FF"]
    assert [p["material"] for p in parts] == ["10:0", "10:1", "10:0", "10:2"]
    assert all(p["slot"] is None for p in parts)
    assert sum(p["mesh"]["runs"][0][1] for p in parts) == len(mesh.faces)
    flat, flat_warnings = meshedit.load_mesh(data, "3mf")
    assert len(flat.faces) == len(mesh.faces)
    assert any("not kept" in w for w in flat_warnings)
    one = meshparts.merged_mesh(mesh, parts)
    assert len(one.faces) == len(mesh.faces)


def test_colorgroup_colour_is_kept():
    box = _box((8, 8, 8), (0, 0, 0))
    xml_objects = [
        '<colorgroup id="3"><color color="#112233FF"/></colorgroup>',
        _mesh_xml(box, 1, "Tint", 3, 0),
    ]
    # colorgroup must live in resources; _3mf puts the first arg's strings there, so pass it as materials
    data = _3mf([], ['<item objectid="1"/>'], "".join(xml_objects))
    _mesh, parts, _warnings = meshedit.load_document(data, "3mf", split_shells=True)
    assert len(parts) == 1
    assert parts[0]["name"] == "Tint"
    assert parts[0]["color"] == "#112233"
    assert parts[0]["material"] == "3:0"


def test_obj_groups_read_mtl_kd():
    obj, mtl = _obj_with_groups()
    mesh, parts, warnings = meshedit.load_document(obj, "obj", mtl=mtl, split_shells=True)
    assert not any("not kept" in w for w in warnings)
    assert [(p["name"], p["color"], p["material"], p["slot"]) for p in parts] == [
        ("Base", "#FF0000", "mat_Base", None),
        ("Cap", "#0000FF", "mat_Cap", None),
    ]
    assert sum(sum(c for _, c in p["mesh"]["runs"]) for p in parts) == len(mesh.faces)
    without, = [meshedit.load_document(obj, "obj", split_shells=True)[1]]
    assert [p["name"] for p in without] == ["Base", "Cap"]
    assert all(p["color"] is None for p in without)


def test_stl_stays_one_part_until_detect():
    data = _two_shell_stl()
    mesh, parts, _warnings = meshedit.load_document(data, "stl", split_shells=True)
    assert len(parts) == 1 and parts[0]["color"] is None and parts[0]["slot"] is None
    found = meshparts.detect(mesh)
    assert len(found) == 2
    assert sum(sum(c for _, c in p["mesh"]["runs"]) for p in found) == len(mesh.faces)
    assert found[0]["name"] == "Part 1" and found[1]["name"] == "Part 2"


def test_auto_split_only_for_a_small_ungrouped_mesh(monkeypatch):
    shells = [trimesh.creation.box((2, 2, 2))]
    for i in range(1, 20):
        piece = trimesh.creation.box((2, 2, 2))
        piece.apply_translation((i * 10, 0, 0))
        shells.append(piece)
    blob = trimesh.util.concatenate(shells)
    data = _3mf([_mesh_xml(blob, 1, "Blob")], ['<item objectid="1"/>'])
    _mesh, parts, _warnings = meshedit.load_document(data, "3mf", split_shells=True)
    assert len(parts) == 1

    two = _3mf([_mesh_xml(trimesh.util.concatenate([
        _box((10, 10, 10), (0, 0, 0)), _box((4, 4, 4), (30, 0, 0))]), 1, "Blob")], ['<item objectid="1"/>'])
    _mesh, parts, _warnings = meshedit.load_document(two, "3mf", split_shells=True)
    assert len(parts) == 2

    called = []
    real = meshparts.shell_groups

    def spy(mesh):
        called.append(len(mesh.faces))
        return real(mesh)

    monkeypatch.setattr(meshparts, "shell_groups", spy)
    monkeypatch.setattr(meshparts, "AUTO_MAX_FACES", 10)
    meshedit.load_document(two, "3mf", split_shells=True)
    assert called == []
    meshedit.load_mesh(two, "3mf")
    assert called == []


def test_old_project_without_parts_is_one_part():
    mesh = _box((10, 12, 14), (0, 0, 0))
    assert meshparts.resolve(None, len(mesh.faces), "Vase")[0]["name"] == "Vase"
    assert meshparts.resolve(None, len(mesh.faces), "Vase")[0]["slot"] is None
    assert meshparts.worth_storing(meshparts.single(len(mesh.faces))) is False
    broken = [{"id": "p1", "name": "Nope", "color": None, "material": None, "slot": None,
               "mesh": {"runs": [[0, 1]]}}]
    assert len(meshparts.resolve(broken, len(mesh.faces), "Vase")) == 1


def test_edit_api_round_trip_keeps_parts():
    client = TestClient(app)
    _clear(client)
    data = _coloured_3mf()
    opened = client.post("/api/edit/new", files={"file": ("colour.3mf", data, "model/3mf")})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert [p["color"] for p in body["parts"]] == ["#FF0000", "#00FF00", "#FF0000", "#0000FF"]
    assert all(p["slot"] == 1 for p in body["parts"])
    assert not any("not kept" in w or "Colours" in w for w in body["warnings"])
    editproj._BASES.clear()
    editproj._STATES.clear()
    store.cache.pop(body["id"], None)
    again = client.get(f"/api/edit/{body['id']}")
    assert again.status_code == 200, again.text
    assert again.json()["parts"] == body["parts"]
    saved = json.loads((store.dir(body["id"]) / "meta.json").read_text())
    assert saved["parts"][0]["slot"] == 1 and saved["parts"][1]["material"] == "10:1"
    scene = client.get(f"/api/cad/{body['id']}/scene")
    assert scene.status_code == 200, scene.text
    assert [p["name"] for p in scene.json()["parts"]] == ["Box", "Peg", "Box", "Ball"]
    stl = client.get(f"/api/download/{body['id']}/stl")
    assert stl.status_code == 200
    exported = trimesh.load(io.BytesIO(stl.content), file_type="stl", force="mesh")
    assert len(exported.faces) == body["analysis"]["triangles"] == sum(p["triangles"] for p in body["parts"])

    obj, mtl = _obj_with_groups()
    opened = client.post("/api/edit/new", files={
        "file": ("groups.obj", obj, "model/obj"),
        "mtl": ("demo.mtl", mtl, "text/plain"),
    })
    assert opened.status_code == 200, opened.text
    obj_body = opened.json()
    assert [(p["name"], p["color"]) for p in obj_body["parts"]] == [("Base", "#FF0000"), ("Cap", "#0000FF")]
    editproj._BASES.clear(); editproj._STATES.clear(); store.cache.pop(obj_body["id"], None)
    assert client.get(f"/api/edit/{obj_body['id']}").json()["parts"] == obj_body["parts"]

    stl_up = client.post("/api/edit/new", files={"file": ("two.stl", _two_shell_stl(), "model/stl")})
    assert stl_up.status_code == 200, stl_up.text
    stl_body = stl_up.json()
    assert len(stl_body["parts"]) == 1
    detected = client.post(f"/api/edit/{stl_body['id']}/parts/detect")
    assert detected.status_code == 200, detected.text
    assert len(detected.json()["parts"]) == 2
    assert detected.json()["analysis"]["triangles"] == stl_body["analysis"]["triangles"]
    editproj._BASES.clear(); editproj._STATES.clear(); store.cache.pop(stl_body["id"], None)
    assert len(client.get(f"/api/edit/{stl_body['id']}").json()["parts"]) == 2

    # A project saved before parts existed still opens as one part.
    meta = store.get(stl_body["id"])
    meta.pop("parts", None)
    store.save(meta)
    legacy = client.get(f"/api/edit/{stl_body['id']}").json()
    assert len(legacy["parts"]) == 1 and legacy["parts"][0]["slot"] is None
    _clear(client)
