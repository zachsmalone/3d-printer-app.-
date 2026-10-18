"""Upload checks (app/services/uploadsafe.py): content-sniffed types, size limits,
mesh-complexity caps, image decompression-bomb limits. Fixtures are built in-test."""
import io
import struct
import zipfile

import pytest

from app.services import uploadsafe


# ------------------------------------------------------------------ fixtures
def png(w=4, h=3) -> bytes:
    """Minimal PNG-shaped file with an IHDR claiming w x h (IDAT empty — header shape only)."""
    import zlib
    ihdr = struct.pack(">II", w, h) + b"\x08\x00\x00\x00\x00"
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", b"") + chunk(b"IEND", b""))


def jpg(w=16, h=12) -> bytes:
    """SOI + APP0 + a SOF0 frame claiming w x h (header shape only, not a real JPEG)."""
    sof = bytes([0xFF, 0xC0, 0x00, 11, 8]) + struct.pack(">HH", h, w) + bytes([3, 1, 0x22, 0, 2, 0x22, 0])
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def binary_stl(faces=2) -> bytes:
    return b"solid name".ljust(80, b"\x00") + struct.pack("<I", faces) + b"\x00" * (faces * 50)


def ascii_stl(faces=2) -> bytes:
    tri = (b"facet normal 0 0 1\n outer loop\n  vertex 0 0 0\n  vertex 1 0 0\n  vertex 0 1 0\n endloop\n endfacet\n")
    return b"solid m\n" + tri * faces + b"endsolid m\n"


def obj(v=3, f=1) -> bytes:
    verts = b"".join(b"v %d 0 0\n" % i for i in range(v))
    faces = b"".join(b"f %d %d %d\n" % (i + 1, i + 2, i + 3) for i in range(f))
    return b"# obj\n" + verts + faces


def stl3mf(triangles=2, vertices=3) -> bytes:
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
           '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
           '<resources><object id="1"><mesh>'
           f'<vertices>{"".join("<vertex x=\"0\" y=\"0\" z=\"0\"/>" for _ in range(vertices))}</vertices>'
           f'<triangles>{"".join("<triangle v1=\"0\" v2=\"1\" v3=\"2\"/>" for _ in range(triangles))}</triangles>'
           '</mesh></object></resources>'
           '<build><item objectid="1"/></build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("3D/3dmodel.model", xml)
    return buf.getvalue()


def comp3mf(mesh_triangles=5, mesh_vertices=6, instances=3) -> bytes:
    """A 3MF that multiplies one mesh through a component + build items."""
    mesh_obj = (f'<object id="1"><mesh><vertices>{"".join("<vertex/>" for _ in range(mesh_vertices))}</vertices>'
                f'<triangles>{"".join("<triangle/>" for _ in range(mesh_triangles))}</triangles></mesh></object>')
    comp_obj = '<object id="2"><components><component objectid="1"/></components></object>'
    build = "".join(f'<item objectid="2"/>' for _ in range(instances))
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
           f'<resources>{mesh_obj}{comp_obj}</resources><build>{build}</build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", xml)
    return buf.getvalue()


# ------------------------------------------------------------------ sniffing: content, never the name
@pytest.mark.parametrize("data, kind, fmt", [
    (png(), "image", "png"), (jpg(), "image", "jpg"), (b"GIF89a" + b"\x00" * 5, "image", "gif"),
    (binary_stl(), "mesh", "stl"), (ascii_stl(), "mesh", "stl"), (obj(), "mesh", "obj"),
    (stl3mf(), "mesh", "3mf"),
])
def test_sniff_by_content(data, kind, fmt):
    assert uploadsafe.sniff(data) == (kind, fmt)


def test_sniff_ignores_wrong_extension_and_unknown_content():
    # an STL named photo.png is still an STL; random bytes are nothing
    assert uploadsafe.sniff(png()[:0] + binary_stl()) == ("mesh", "stl")
    assert uploadsafe.sniff(b"\x00" * 100) is None
    assert uploadsafe.sniff(b"") is None
    assert uploadsafe.sniff(b"plain text file") is None


# ------------------------------------------------------------------ images
def test_image_dimensions_read_from_header():
    c = uploadsafe.check(png(w=640, h=480))
    assert c.kind == "image" and c.format == "png"
    assert c.image == {"width": 640, "height": 480, "pixels": 640 * 480}
    assert c.to_dict()["image"]["pixels"] == 640 * 480


def test_decompression_bomb_refused_before_decode():
    # a 29-byte header claiming a gigapixel canvas: refused on header math, no decode
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(png(w=40000, h=40000))
    assert e.value.reason == "image_too_many_pixels"
    assert uploadsafe.check(png(w=10000, h=10000)).image["pixels"] == 100_000_000  # at the cap


def test_damaged_image_headers():
    with pytest.raises(uploadsafe.Rejected):
        uploadsafe.check(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)          # truncated IHDR
    with pytest.raises(uploadsafe.Rejected):
        uploadsafe.check(b"\xff\xd8\xff" + b"\x00" * 50)              # JPEG with no SOF


# ------------------------------------------------------------------ real images via PIL
def test_gif_frame_larger_than_logical_screen_is_bounded():
    # a GIF whose logical screen says 10x10 but whose first frame descriptor claims
    # 4000x4000 must be measured at the frame size — the max of screen and frame
    buf = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (10, 10), "red").save(buf, "GIF")
    gif = bytearray(buf.getvalue())
    j = gif.index(0x2C)
    gif[j + 5:j + 9] = struct.pack("<HH", 4000, 4000)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(bytes(gif), max_pixels=1_000_000)
    assert e.value.reason == "image_too_many_pixels"


def test_gif_every_frame_is_bounded_even_behind_extensions():
    # block-walking, not first-descriptor-only: an oversized frame preceded by an
    # extension block, and an oversized SECOND frame, are both caught
    buf = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (10, 10), "red").save(buf, "GIF")
    gif = bytearray(buf.getvalue())
    j = gif.index(0x2C)
    # splice a comment extension (0x21 0x01 + sub-blocks) in front of the frame
    ext = bytes([0x21, 0x01, 5]) + b"hello" + bytes([0x00])
    gif = gif[:j] + bytearray(ext) + gif[j:]
    j2 = gif.index(0x2C)                                    # same frame, now behind the extension
    gif[j2 + 5:j2 + 9] = struct.pack("<HH", 4000, 4000)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(bytes(gif), max_pixels=1_000_000)
    assert e.value.reason == "image_too_many_pixels"
    # and an oversized SECOND frame: insert a descriptor before the trailer
    buf2 = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf2, "GIF")
    gif2 = bytearray(buf2.getvalue())
    assert gif2[-1] == 0x3B                                 # trailer
    second = bytes([0x2C]) + struct.pack("<HHHH", 0, 0, 5000, 5000) + bytes([0x00]) + bytes([0x00])
    gif2 = gif2[:-1] + bytearray(second) + bytearray([0x3B])
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(bytes(gif2), max_pixels=1_000_000)
    assert e.value.reason == "image_too_many_pixels"


def test_gif_unknown_block_is_refused():
    # a GIF-shaped file with a block that isn't a descriptor/extension/trailer is
    # refused, not silently measured at the logical-screen size
    buf = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (10, 10), "red").save(buf, "GIF")
    gif = bytearray(buf.getvalue())
    j = gif.index(0x2C)
    gif[j] = 0x77                                            # not a valid block introducer
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(bytes(gif))
    assert e.value.reason == "image_bad_header"


@pytest.mark.parametrize("fmt", ["png", "jpeg", "gif", "bmp"])
def test_real_images_round_trip(fmt):
    """Real encoder output (not header-shaped bytes) is sniffed with its true dimensions."""
    from PIL import Image
    im = Image.new("RGB", (37, 23), "red")
    buf = io.BytesIO()
    im.save(buf, fmt.upper() if fmt != "jpeg" else "JPEG")
    c = uploadsafe.check(buf.getvalue())
    assert c.kind == "image" and c.format == ({"jpeg": "jpg"}.get(fmt, fmt))
    assert c.image == {"width": 37, "height": 23, "pixels": 37 * 23}


def test_real_webp_if_encoder_available():
    """WEBP only when PIL was built with it; skipped (reported) when not."""
    pytest.importorskip("PIL._webp")
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (11, 7), "blue").save(buf, "WEBP")
    c = uploadsafe.check(buf.getvalue())
    assert c.format == "webp" and c.image["pixels"] == 77


def test_truncated_gif_and_bmp():
    with pytest.raises(uploadsafe.Rejected, match="damaged"):
        uploadsafe.check(b"GIF89a" + b"\x00" * 2)        # header claims GIF, no dimensions
    assert uploadsafe.sniff(b"BM\x00" * 4) is None        # too short to be a BMP: unknown content


# ------------------------------------------------------------------ meshes
def test_binary_stl_face_count_from_header():
    c = uploadsafe.check(binary_stl(faces=12))
    assert c.mesh == {"vertices": 36, "faces": 12}


def test_ascii_stl_counted():
    c = uploadsafe.check(ascii_stl(faces=3))
    assert c.mesh["faces"] == 3 and c.mesh["vertices"] == 9


def test_ascii_stl_case_and_whitespace_not_a_bypass():
    # the loader (trimesh) accepts uppercase STL — so counting must too, or an
    # uppercase file reports zero complexity and slips past the caps
    up = ascii_stl(faces=4).upper()
    c = uploadsafe.check(up)
    assert c.mesh["faces"] == 4 and c.mesh["vertices"] == 12
    with pytest.raises(uploadsafe.Rejected) as e:      # and the cap sees the real count
        uploadsafe.check(up, max_faces=3)
    assert e.value.reason == "too_many_faces"
    # tab-separated vertices count as well (whitespace-tolerant, like the loader)
    tabs = (b"solid m\n" + b"facet normal 0 0 1\n\touter loop\n\t\tvertex\t0\t0\t0\n\t\tvertex\t1\t0\t0\n\t\tvertex\t0\t1\t0\n\tendloop\n endfacet\n" * 2
            + b"endsolid m\n")
    assert uploadsafe.check(tabs).mesh["faces"] == 2


def test_obj_counted():
    c = uploadsafe.check(obj(v=4, f=2))
    assert c.mesh == {"vertices": 4, "faces": 2}


def test_obj_polygon_triangulated():
    # a quad counts as 2 triangles, a hexagon as 4 — the count a loader would build
    data = (b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 2 1 0\n"
            b"f 1 2 3 4\nf 1 2 3 4 5 6\nf 1/1 2/2 3/3\n")
    c = uploadsafe.check(data)
    assert c.mesh == {"vertices": 5, "faces": 2 + 4 + 1}
    with pytest.raises(uploadsafe.Rejected) as e:      # and the cap sees the triangulated count
        uploadsafe.check(data, max_faces=5)
    assert e.value.reason == "too_many_faces"


def test_stl_count_mismatch_is_not_stl():
    # a file with an STL-ish header but a wrong face count is unknown content, not a mesh
    bad = b"solid".ljust(80, b"\x00") + struct.pack("<I", 5) + b"\x00" * 100
    with pytest.raises(uploadsafe.Rejected, match="isn't supported"):
        uploadsafe.check(bad)


def test_face_limit_enforced():
    # a default-cap STL (3M faces, 150 MB) trips the SIZE cap first, so the limit is
    # exercised with an explicit override — same code path, both guards
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(binary_stl(faces=10), max_faces=5)
    assert e.value.reason == "too_many_faces"
    assert uploadsafe.check(binary_stl(faces=5), max_faces=5).mesh["faces"] == 5  # at the cap passes
    # and at the real defaults the size guard fires first (proved with a tiny override,
    # not by building a real 150 MB fixture)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(binary_stl(faces=4), max_bytes=100)
    assert e.value.reason == "too_big"


def test_vertex_limit_enforced():
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(obj(v=10, f=1), max_vertices=5)
    assert e.value.reason == "too_many_vertices"
    assert uploadsafe.check(obj(v=5, f=1), max_vertices=5).mesh["vertices"] == 5


def test_face_limit_matches_meshedit():
    from app.core import meshedit
    assert uploadsafe.MAX_FACES == meshedit.MAX_FACES       # upload cap == editor cap


# ------------------------------------------------------------------ 3MF archives
def test_3mf_archive_stats_and_mesh_counts():
    c = uploadsafe.check(stl3mf(triangles=7, vertices=9))
    assert c.format == "3mf" and c.mesh == {"vertices": 9, "faces": 7}
    assert c.archive["members"] == 2 and c.archive["total_uncompressed_bytes"] > 0


def test_3mf_components_and_instances_expanded():
    # 3 build items, each placing a component that wraps a 5-triangle mesh -> 15, not 5
    c = uploadsafe.check(comp3mf(mesh_triangles=5, mesh_vertices=6, instances=3))
    assert c.mesh == {"vertices": 18, "faces": 15}
    with pytest.raises(uploadsafe.Rejected) as e:      # the cap sees the expanded count
        uploadsafe.check(comp3mf(instances=3), max_faces=10)
    assert e.value.reason == "too_many_faces"


def test_3mf_component_cycle_refused():
    xml = ('<?xml version="1.0"?><model><resources>'
           '<object id="1"><components><component objectid="2"/></components></object>'
           '<object id="2"><components><component objectid="1"/></components></object>'
           '</resources><build><item objectid="1"/></build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", xml)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue())
    assert e.value.reason == "archive_bad"


def test_3mf_missing_component_target_refused():
    xml = ('<?xml version="1.0"?><model><resources>'
           '<object id="1"><components><component objectid="99"/></components></object>'
           '</resources><build><item objectid="1"/></build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", xml)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue())
    assert e.value.reason == "archive_bad"


def test_3mf_malformed_xml_refused_cleanly():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", "<model><mesh>not closed")
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue())
    assert e.value.reason == "archive_bad"


def test_3mf_entity_expansion_bomb_refused():
    # exponential DTD entity expansion — the stdlib parser's amplification limit
    # turns it into a ParseError, which the module maps to archive_bad
    ents = '<!ENTITY e0 "xxxxxxxxxx">'
    for i in range(1, 8):                        # 8 levels of 10x = 10^8 chars from ~470 bytes
        ents += f'<!ENTITY e{i} "' + (f'&e{i - 1};' * 10) + '">'
    bomb = f'<?xml version="1.0"?><!DOCTYPE model [{ents}]><model><mesh>&e7;</mesh></model>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", bomb)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue())
    assert e.value.reason == "archive_bad"


def test_3mf_unsupported_compression_refused_cleanly(monkeypatch):
    # a member the reader cannot decompress (unsupported codec) must be a clean
    # Rejected, not an uncaught NotImplementedError — exercised directly on a valid archive
    def _boom(self, name, pwd=None):
        raise NotImplementedError("that compression method is not supported")
    monkeypatch.setattr(zipfile.ZipFile, "read", _boom)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(stl3mf())
    assert e.value.reason == "archive_bad"


def test_3mf_deep_component_chain_refused_not_recursion_error():
    # a long narrow chain would blow the Python recursion limit; the depth bound refuses it
    depth = 5000
    objs = ['<object id="0"><mesh><vertices/><triangles><triangle/></triangles></mesh></object>']
    for i in range(1, depth):
        objs.append(f'<object id="{i}"><components><component objectid="{i - 1}"/></components></object>')
    xml = ('<?xml version="1.0"?><model><resources>' + "".join(objs) +
           '</resources><build><item objectid="' + str(depth - 1) + '"/></build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", xml)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue())
    assert e.value.reason == "archive_bad" and "nesting too deep" in str(e.value.detail)


def test_3mf_every_model_part_is_counted():
    # a small first .model part can't conceal a big second one: counts are summed,
    # and the summed count is what the face cap enforces
    def model_part(triangles):
        return ('<model><resources><object id="1"><mesh><vertices/>'
                f'<triangles>{"<triangle/>" * triangles}</triangles></mesh></object></resources>'
                '<build><item objectid="1"/></build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", model_part(2))
        z.writestr("other.model", model_part(3))
    c = uploadsafe.check(buf.getvalue())
    assert c.mesh["faces"] == 5 and c.archive["members"] == 2
    with pytest.raises(uploadsafe.Rejected) as e:      # 2+3 > 4: the cap sees the SUM
        uploadsafe.check(buf.getvalue(), max_faces=4)
    assert e.value.reason == "too_many_faces"


def test_3mf_empty_components_object_counts_zero():
    # an object with a <components> wrapper but no children is degenerate, not a crash
    xml = ('<?xml version="1.0"?><model><resources>'
           '<object id="1"><components/></object>'
           '</resources><build><item objectid="1"/></build></model>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", xml)
    c = uploadsafe.check(buf.getvalue())
    assert c.mesh == {"vertices": 0, "faces": 0}


def test_3mf_without_a_model_is_refused():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hi")
    with pytest.raises(uploadsafe.Rejected):
        uploadsafe.check(buf.getvalue())


def test_3mf_bomb_refused_before_any_inflation(monkeypatch):
    # a zip whose entries CLAIM to expand past the cap is refused from the directory;
    # the monkeypatched read() fails the test if any member is actually inflated
    def _no_read(self, name, pwd=None):
        raise AssertionError("member was inflated before the archive limit fired")
    monkeypatch.setattr(zipfile.ZipFile, "read", _no_read)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("3D/3dmodel.model", b"<model/>" + b"x" * 900)
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue(), max_archive_bytes=500)
    assert e.value.reason == "archive_too_big"


def test_3mf_member_count_cap():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(uploadsafe.MAX_ARCHIVE_MEMBERS + 1):
            z.writestr(f"f{i}.txt", "x")
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(buf.getvalue())
    assert e.value.reason == "archive_too_many_members"


def test_broken_zip_is_rejected_cleanly():
    with pytest.raises(uploadsafe.Rejected):
        uploadsafe.check(b"PK\x03\x04" + b"\x00" * 40)


# ------------------------------------------------------------------ size cap
def test_size_cap():
    with pytest.raises(uploadsafe.Rejected) as e:
        uploadsafe.check(b"\x00" * (uploadsafe.MAX_BYTES + 1))
    assert e.value.reason == "too_big"
    assert uploadsafe.check(png())                          # small files pass


def test_rejected_message_is_user_safe():
    try:
        uploadsafe.check(b"\x00" * 10)
        assert False
    except uploadsafe.Rejected as e:
        assert e.reason == "unknown_type" and "STL" in str(e) and "stack" not in str(e)


def test_check_never_decodes_or_loads():
    # a PNG whose IDAT is empty/invalid still passes: only the header is read
    c = uploadsafe.check(png(w=10, h=10))
    assert c.image["pixels"] == 100
