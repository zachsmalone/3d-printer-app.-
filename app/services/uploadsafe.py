"""Upload checks: content-sniffed file types with size, mesh-complexity and image-bomb limits.

Standalone module (launch-safety groundwork). The existing upload flows do NOT call it yet —
app/api/builds.py handles photos via app/core/imagesafe.py and app/api/edit.py handles
meshes — wiring it in touches files owned by others; docs/uploadsafe.md describes the
adoption path. Everything here is pure input -> verdict, no global state, no I/O beyond
the bytes it is handed.

What it checks, in order:
1. size: the raw upload is capped (default 25 MB, matching config.MAX_UPLOAD).
2. type by CONTENT, never by file name: PNG/JPEG/GIF/WEBP/BMP images, binary+ASCII STL,
   OBJ, 3MF (ZIP container). Unknown content is refused.
3. image decompression bombs: width*height parsed from the image HEADER (no decode) is
   capped (default 100 MP, matching imagesafe.MAX_PIXELS) — a 20-byte PNG header can claim
   a gigapixel canvas; refusing it before PIL ever decodes is the point.
4. mesh complexity: triangle/vertex counts are capped (faces default 3,000,000 to match
   meshedit.MAX_FACES) — read from the STL header / counted cheaply, not by loading a mesh.
5. 3MF archives: member count, per-member and total UNCOMPRESSED sizes are capped before
   any member is read (a small zip can expand to gigabytes).

Every refusal is a Rejected exception with a stable reason code and a message that is safe
to show to a user as-is.
"""
from __future__ import annotations

import io
import struct
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

try:
    from ..core import meshedit
    _MAX_FACES_DEFAULT = meshedit.MAX_FACES          # stay in sync with the editor's cap
except Exception:                                     # pragma: no cover - import isolation
    _MAX_FACES_DEFAULT = 3_000_000

MAX_BYTES = 25 * 1024 * 1024          # one upload (matches config.MAX_UPLOAD)
MAX_IMAGE_PIXELS = 100_000_000        # width*height from the header, before any decode (matches imagesafe.MAX_PIXELS)
MAX_FACES = _MAX_FACES_DEFAULT        # mesh triangles (matches meshedit.MAX_FACES)
MAX_VERTICES = 3_000_000              # mesh vertices (a watertight mesh has ~2 per face)
MAX_ARCHIVE_MEMBERS = 200             # 3MF: files inside the zip
MAX_MEMBER_BYTES = 64 * 1024 * 1024    # 3MF: one member, UNCOMPRESSED
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024  # 3MF: whole archive, UNCOMPRESSED
MAX_MODEL_XML_BYTES = 32 * 1024 * 1024  # the 3D model XML member specifically
MAX_COMPONENT_DEPTH = 64               # 3MF: <components> nesting we will resolve before refusing

MESSAGES = {
    "too_big": "That file is too large. Keep uploads under {mb} MB.",
    "unknown_type": "That file type isn't supported. Use a JPG/PNG photo or an STL/OBJ/3MF model.",
    "image_too_many_pixels": "That image is too big (too many megapixels). Use a smaller one.",
    "image_bad_header": "That image file is damaged. Try re-saving it.",
    "too_many_faces": "That model has too many triangles (limit {n:,}). Simplify it first.",
    "too_many_vertices": "That model has too many vertices (limit {n:,}). Simplify it first.",
    "archive_too_many_members": "That 3MF file contains too many files.",
    "archive_too_big": "That 3MF file expands too large. Re-export it with fewer or smaller parts.",
    "archive_bad": "That 3MF file is damaged or isn't a 3MF. Re-export it.",
}


class Rejected(ValueError):
    """Message is safe to show to the user as-is; .reason is a stable code; .detail is for logs."""

    def __init__(self, reason: str, **detail):
        self.reason = reason
        self.detail = detail
        super().__init__(MESSAGES[reason].format(mb=MAX_BYTES // (1024 * 1024),
                                                n=detail.get("limit", MAX_FACES)))


@dataclass
class Checked:
    """Verdict for one upload. kind: 'image' | 'mesh'; format: 'png' | 'stl' | 'obj' | '3mf' ..."""
    kind: str
    format: str
    size_bytes: int
    image: dict | None = None            # {"width", "height", "pixels"}
    mesh: dict | None = None             # {"vertices", "faces"}
    archive: dict | None = None          # {"members", "total_uncompressed_bytes"}

    def to_dict(self) -> dict:
        return {"kind": self.kind, "format": self.format, "size_bytes": self.size_bytes,
                "image": self.image, "mesh": self.mesh, "archive": self.archive}


# ------------------------------------------------------------------ sniffing (content, never the file name)
def _sniff_image(data: bytes) -> tuple[str, int, int] | None:
    """(format, width, height) from the header, or None when not a known image."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":                       # PNG: IHDR is the first chunk
        if len(data) < 24:
            raise Rejected("image_bad_header")
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:3] == b"\xff\xd8\xff":                           # JPEG: walk the segments to a SOF
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            m, ln = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", w, h
            if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD9:
                i += 2
                continue
            i += 2 + ln
        raise Rejected("image_bad_header")
    if data[:6] in (b"GIF87a", b"GIF89a"):                    # GIF: walk blocks, bound every frame
        if len(data) < 11:
            raise Rejected("image_bad_header")
        w, h = struct.unpack("<HH", data[6:10])
        mw, mh = w, h
        j = 13
        if data[10] & 0x80:                                    # skip the global color table if present
            j += 3 << ((data[10] & 7) + 1)

        def skip_subblocks(j: int) -> int:                     # data sub-blocks end at a zero length
            while j < len(data):
                ln = data[j]
                j += 1 + ln
                if ln == 0:
                    break
            return j

        while j < len(data):
            b = data[j]
            if b == 0x3B:                                      # trailer: done
                break
            if b == 0x2C:                                      # image descriptor: bound this frame
                if j + 10 > len(data):
                    break
                fw, fh = struct.unpack("<HH", data[j + 5:j + 9])
                mw, mh = max(mw, fw), max(mh, fh)
                lflags = data[j + 9]
                j += 10
                if lflags & 0x80:                               # local color table
                    j += 3 << ((lflags & 7) + 1)
                j = skip_subblocks(j + 1)                       # +1: the LZW min-code-size byte
            elif b == 0x21:                                    # extension: skip its sub-blocks
                j = skip_subblocks(j + 2)
            else:                                              # not a GIF block: refuse, don't guess
                raise Rejected("image_bad_header")
        return "gif", mw, mh
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":          # WEBP: VP8X canvas / VP8 / VP8L
        i = 12
        while i + 8 <= len(data):
            fourcc, ln = data[i:i + 4], struct.unpack("<I", data[i + 4:i + 8])[0]
            body = data[i + 8:i + 8 + ln]
            if fourcc == b"VP8X" and len(body) >= 10:
                w = int.from_bytes(body[4:7], "little") + 1
                h = int.from_bytes(body[7:10], "little") + 1
                return "webp", w, h
            if fourcc == b"VP8 " and len(body) >= 10:          # lossy: 6-byte tag+sync, then 14-bit w/h
                w = int.from_bytes(body[6:8], "little") & 0x3FFF
                h = int.from_bytes(body[8:10], "little") & 0x3FFF
                return "webp", w, h
            if fourcc == b"VP8L" and len(body) >= 5:           # lossless: 14 bits w, 14 bits h
                bits = int.from_bytes(body[1:5], "little")
                return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            i += 8 + ln + (ln & 1)
        raise Rejected("image_bad_header")
    if data[:2] == b"BM" and len(data) >= 26:                 # BMP: BITMAPINFOHEADER
        w, h = struct.unpack("<ii", data[18:26])
        return "bmp", abs(w), abs(h)
    return None


def _sniff_stl(data: bytes) -> tuple[str, int, int] | None:
    """(format, faces, vertices_estimate) for STL, or None when not STL.

    ASCII counting is case-insensitive (the loader accepts any case) and
    whitespace-tolerant, so an uppercase or tab-separated file can't report
    zero complexity and slip past the caps."""
    if len(data) >= 84:                                       # binary STL: count must match exactly
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + n * 50 == len(data):
            return "stl", n, n * 3
    head = data[:1024].lstrip()
    if head[:5].lower() == b"solid" and b"facet normal" in head.lower():
        f = v = 0
        for line in data.upper().splitlines():               # bounded by the size cap above
            s = line.lstrip()
            if s.startswith(b"FACET"):
                f += 1
            elif s.startswith(b"VERTEX"):
                v += 1
        return "stl", f, v
    return None


def _sniff_obj(data: bytes) -> tuple[str, int, int] | None:
    """(format, triangles, vertices) for OBJ, or None when not OBJ.

    A face record with n corners becomes n-2 triangles — the count a downstream
    triangulating loader would actually produce, not the record count."""
    if not data or any(b > 0x7F or (b < 0x09 and b not in (0x0A, 0x0D)) for b in data[:512]):
        return None                                           # OBJ is text; binary content isn't one
    v = f = 0
    for line in data.splitlines():                            # bounded by the size cap above
        s = line.strip()
        if s[:2] in (b"v ", b"v\t"):
            v += 1
        elif s[:2] in (b"f ", b"f\t"):
            corners = sum(1 for c in s[2:].split() if c.split(b"/")[0])   # strip v/vt/vn suffixes
            f += max(1, corners - 2) if corners else 1
    if v == 0 and f == 0:
        return None
    return "obj", f, v


def _sniff_3mf(data: bytes, *, max_archive_members: int = MAX_ARCHIVE_MEMBERS,
               max_member_bytes: int = MAX_MEMBER_BYTES, max_archive_bytes: int = MAX_ARCHIVE_BYTES,
               max_model_xml_bytes: int = MAX_MODEL_XML_BYTES) -> tuple[str, dict, dict | None, dict | None]:
    """3MF: (format, archive stats, mesh counts or None). Raises Rejected on bad/oversized archives.

    Face/vertex counts resolve <components> objects and <build> items, so an archive
    that multiplies a small mesh through instances cannot understate its complexity;
    a component graph we can't resolve (missing object, cycle) is refused outright."""
    if data[:4] != b"PK\x03\x04":
        raise ValueError("not a zip")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise Rejected("archive_bad")
    infos = zf.infolist()
    if len(infos) > max_archive_members:
        raise Rejected("archive_too_many_members", members=len(infos))
    total = sum(i.file_size for i in infos)
    if total > max_archive_bytes or any(i.file_size > max_member_bytes for i in infos):
        raise Rejected("archive_too_big", total=total)      # from the directory: nothing is inflated yet
    arch = {"members": len(infos), "total_uncompressed_bytes": total}
    mesh: dict | None = None
    for i in infos:                                           # EVERY .model part is inspected — a
        if not i.filename.lower().endswith(".model"):         # small first part can't hide a big second one
            continue
        if i.file_size > max_model_xml_bytes:
            raise Rejected("archive_too_big", member=i.filename)
        try:
            root = ET.fromstring(zf.read(i))                  # expat's entity-amplification limit bounds
        except (ET.ParseError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
            raise Rejected("archive_bad")                    # XML expansion bombs inside this
        part = _count_3mf_model(root)
        mesh = part if mesh is None else {"vertices": mesh["vertices"] + part["vertices"],
                                          "faces": mesh["faces"] + part["faces"]}
    if mesh is None:                                          # a 3MF without a model part is broken
        raise Rejected("archive_bad")
    return "3mf", arch, mesh


def _count_3mf_model(root) -> dict:
    """Effective vertex/triangle counts for a 3MF model, components and build items resolved.

    Resolution is memoized, so work is linear in objects regardless of how often a
    subgraph is referenced. An unresolvable graph (missing object, cycle, malformed
    component) is refused outright."""
    def tag(e) -> str:
        return e.tag.rsplit("}", 1)[-1]
    objects: dict[str, dict] = {}                              # id -> {mesh: (v,t)} | {components: [ids]}
    for e in root.iter():
        if tag(e) != "object" or "id" not in e.attrib:
            continue
        for c in e:
            if tag(c) == "mesh":
                v = sum(1 for x in c.iter() if tag(x) == "vertex")
                t = sum(1 for x in c.iter() if tag(x) == "triangle")
                objects[e.attrib["id"]] = {"mesh": (v, t)}
            elif tag(c) == "components":
                objects[e.attrib["id"]] = {"components": [x.attrib.get("objectid")
                                                            for x in c if tag(x) == "component"]}
    memo: dict[str, tuple[int, int]] = {}

    def resolve(oid: str, depth: int = 0) -> tuple[int, int]:  # (vertices, triangles) of one object
        if oid in memo:
            return memo[oid]
        if oid not in objects:
            raise Rejected("archive_bad", detail="component references a missing object")
        if depth > MAX_COMPONENT_DEPTH:
            raise Rejected("archive_bad", detail="component nesting too deep")
        o = objects[oid]
        if "mesh" in o:
            out = o["mesh"]
        elif o["components"]:
            out = tuple(sum(x) for x in zip(*(resolve(cid, depth + 1) for cid in o["components"])))
        else:                                                  # an object with neither mesh nor components
            out = (0, 0)
        memo[oid] = out
        return out

    v = t = 0
    for e in root.iter():                                      # build items place objects; each counts
        if tag(e) != "item":
            continue
        if e.attrib.get("objectid") not in objects:            # a build item pointing nowhere is broken
            raise Rejected("archive_bad", detail="build item references a missing object")
        dv, dt = resolve(e.attrib["objectid"])
        v += dv
        t += dt
    if v or t:
        return {"vertices": v, "faces": t}
    # no build section (or empty): fall back to the raw mesh totals across all objects
    v = t = 0
    for o in objects.values():
        if "mesh" in o:
            v += o["mesh"][0]
            t += o["mesh"][1]
    return {"vertices": v, "faces": t}


def sniff(data: bytes) -> tuple[str, str] | None:
    """(kind, format) from the content, or None when nothing matches. Cheap; no limits applied."""
    try:
        img = _sniff_image(data)
    except Rejected:
        img = None
    if img:
        return "image", img[0]
    if data[:4] == b"PK\x03\x04":
        try:
            return "mesh", _sniff_3mf(data)[0]
        except (Rejected, ValueError):
            return None
    stl = _sniff_stl(data)
    if stl:
        return "mesh", stl[0]
    obj = _sniff_obj(data)
    if obj:
        return "mesh", obj[0]
    return None


# ------------------------------------------------------------------ the verdict
def check(data: bytes, *, max_bytes: int = MAX_BYTES, max_pixels: int = MAX_IMAGE_PIXELS,
          max_faces: int = MAX_FACES, max_vertices: int = MAX_VERTICES,
          max_archive_members: int = MAX_ARCHIVE_MEMBERS, max_member_bytes: int = MAX_MEMBER_BYTES,
          max_archive_bytes: int = MAX_ARCHIVE_BYTES, max_model_xml_bytes: int = MAX_MODEL_XML_BYTES) -> Checked:
    """Full check of one upload. Raises Rejected; never decodes image pixels or builds a mesh."""
    if not data:
        raise Rejected("unknown_type")
    if len(data) > max_bytes:
        raise Rejected("too_big", size=len(data))
    try:
        img = _sniff_image(data)
    except Rejected as e:
        raise Rejected("image_bad_header") if e.reason == "image_bad_header" else e
    if img:
        fmt, w, h = img
        if w <= 0 or h <= 0:
            raise Rejected("image_bad_header")
        if w * h > max_pixels:
            raise Rejected("image_too_many_pixels", width=w, height=h)
        return Checked("image", fmt, len(data), image={"width": w, "height": h, "pixels": w * h})
    if data[:4] == b"PK\x03\x04":
        fmt, arch, mesh = _sniff_3mf(data, max_archive_members=max_archive_members,
                                    max_member_bytes=max_member_bytes, max_archive_bytes=max_archive_bytes,
                                    max_model_xml_bytes=max_model_xml_bytes)
        if mesh and mesh["faces"] > max_faces:
            raise Rejected("too_many_faces", faces=mesh["faces"], limit=max_faces)
        if mesh and mesh["vertices"] > max_vertices:
            raise Rejected("too_many_vertices", vertices=mesh["vertices"], limit=max_vertices)
        return Checked("mesh", fmt, len(data), mesh=mesh, archive=arch)
    stl = _sniff_stl(data)
    if stl:
        _, faces, verts = stl
        if faces > max_faces:
            raise Rejected("too_many_faces", faces=faces, limit=max_faces)
        if verts > max_vertices:
            raise Rejected("too_many_vertices", vertices=verts, limit=max_vertices)
        return Checked("mesh", "stl", len(data), mesh={"vertices": verts, "faces": faces})
    obj = _sniff_obj(data)
    if obj:
        _, faces, verts = obj
        if faces > max_faces:
            raise Rejected("too_many_faces", faces=faces, limit=max_faces)
        if verts > max_vertices:
            raise Rejected("too_many_vertices", vertices=verts, limit=max_vertices)
        return Checked("mesh", "obj", len(data), mesh={"vertices": verts, "faces": faces})
    raise Rejected("unknown_type")
