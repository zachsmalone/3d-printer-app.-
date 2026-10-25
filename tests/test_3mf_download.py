"""3MF downloads are a zip package with a model content type, never an HTML error page or a silent STL."""
import io

import trimesh

from app.core.exporters import mesh_3mf
from app.services import universal_export as ue
from tests.b1 import client, photo_build


def test_mesh_3mf_is_a_zip_package():
    m = trimesh.creation.box(extents=(20, 10, 5))
    data = mesh_3mf(m.vertices, m.faces)
    assert data[:2] == b"PK"
    back = trimesh.load(io.BytesIO(data), file_type="3mf", force="mesh")
    assert back.is_watertight


def test_export_download_3mf_is_not_html():
    c = client()
    bid = photo_build(c)
    r = c.get(f"/api/export/{bid}/download?format=3mf")
    assert r.status_code == 200, r.text[:200]
    assert r.content[:2] == b"PK"
    ctype = r.headers.get("content-type", "")
    assert "html" not in ctype
    assert "3mf" in ctype
    data, ext, mime = ue.export_mesh_data(trimesh.creation.box(), "3mf")
    assert ext == "3mf" and mime == "model/3mf" and data[:2] == b"PK"
