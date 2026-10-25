"""Four-side show-off drawings are PNGs of the mesh, with an honest empty state when there is no file."""
import trimesh

from app.services import showoff
from tests.b1 import client


def test_render_four_sides(tmp_path, monkeypatch):
    monkeypatch.setattr(showoff.config, "DATA", tmp_path)
    stl = tmp_path / "box.stl"
    trimesh.creation.box(extents=(20, 10, 8)).export(stl)
    made = showoff.ensure("abc123", stl)
    assert [m[0] for m in made] == ["front", "right", "back", "left"]
    for _vid, _label, path in made:
        raw = path.read_bytes()
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 200
    again = showoff.ensure("abc123", stl)
    assert again[0][2].stat().st_mtime == made[0][2].stat().st_mtime


def test_missing_showcase_sides_are_not_found():
    r = client().get("/api/showcase/doesnotexist00/sides")
    assert r.status_code >= 400
