"""Parts of one project mesh.

The editor, the plate, slicing, supports, export, Smart Split, and the lithophane and
TorchC0 handoffs still share one triangle mesh. A part is a reference into that mesh
(runs of faces) plus a name, an optional detected colour, the source material id, and
a filament slot. The slot stays null until a later step assigns one.

A saved project that has no parts list is one part covering every face.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter

import numpy as np
import trimesh
from trimesh.util import unique_name

# Same budget as the plate editor: above this, walking shells costs more than opening the file.
AUTO_MAX_FACES = 400_000
AUTO_MIN_SHELLS = 2
AUTO_MAX_SHELLS = 16
MANUAL_MAX_SHELLS = 256
_NAME_MAX = 60
_ID = re.compile(r"^p[1-9][0-9]*$")


class PartsError(ValueError):
    pass


def merged_mesh(mesh: trimesh.Trimesh, parts=None) -> trimesh.Trimesh:
    """The single mesh every current consumer uses. Parts are face runs of this mesh."""
    del parts
    return mesh


def _clean_name(value, fallback: str) -> str:
    text = "".join(ch for ch in str(value or "") if ch >= " " and ch not in "<>").strip()
    text = re.sub(r"\s+", " ", text)[:_NAME_MAX]
    return text or fallback


def _norm_color(value) -> str | None:
    if not isinstance(value, str):
        return None
    h = value.strip()
    if not h.startswith("#"):
        return None
    hexes = h[1:]
    if len(hexes) == 8:
        hexes = hexes[:6]
    if len(hexes) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hexes):
        return None
    return "#" + hexes.upper()


def _kd_hex(parts: list[str]) -> str | None:
    try:
        rgb = [float(x) for x in parts[:3]]
    except (TypeError, ValueError):
        return None
    if len(rgb) < 3 or not all(np.isfinite(rgb)):
        return None
    if max(rgb) > 1:
        rgb = [c / 255.0 for c in rgb]
    rgb = [min(1.0, max(0.0, c)) for c in rgb]
    return "#" + "".join(f"{int(round(c * 255)):02X}" for c in rgb)


def _material_id(pid, index) -> str | None:
    if pid is None:
        return None
    text = str(pid).strip()
    if not text or len(text) > 40 or any(ch in text for ch in "<>"):
        return None
    if index is None or index == "":
        return text
    try:
        n = int(index)
    except (TypeError, ValueError):
        return text
    if n < 0 or n > 10_000:
        return text
    return f"{text}:{n}"


def _record(pid: str, name: str, color, material, runs, slot=None) -> dict:
    if not isinstance(slot, int):
        slot = None
    if not isinstance(material, str) or not material:
        material = None
    return {
        "id": pid,
        "name": _clean_name(name, pid),
        "color": _norm_color(color),
        "material": material,
        "slot": slot,
        "mesh": {"runs": [[int(s), int(c)] for s, c in runs]},
    }


def single(n_faces: int, name: str = "Model") -> list[dict]:
    if n_faces <= 0:
        return []
    return [_record("p1", name, None, None, [(0, int(n_faces))])]


def _runs_of(indices: np.ndarray) -> list[list[int]]:
    idx = np.asarray(indices, np.int64)
    if len(idx) == 0:
        return []
    idx = np.unique(idx)
    breaks = np.flatnonzero(np.diff(idx) != 1)
    starts = np.concatenate([[idx[0]], idx[breaks + 1]])
    ends = np.concatenate([idx[breaks], [idx[-1]]])
    return [[int(s), int(e - s + 1)] for s, e in zip(starts, ends)]


def face_indices(part: dict) -> np.ndarray:
    chunks = []
    for start, count in part["mesh"]["runs"]:
        chunks.append(np.arange(int(start), int(start) + int(count), dtype=np.int64))
    if not chunks:
        return np.zeros(0, np.int64)
    return np.concatenate(chunks)


def submesh(mesh: trimesh.Trimesh, part: dict) -> trimesh.Trimesh:
    runs = part["mesh"]["runs"]
    if len(runs) == 1:
        start, count = int(runs[0][0]), int(runs[0][1])
        faces = mesh.faces[start:start + count]
    else:
        faces = np.concatenate([mesh.faces[int(s):int(s) + int(c)] for s, c in runs])
    used, inv = np.unique(faces.ravel(), return_inverse=True)
    return trimesh.Trimesh(np.asarray(mesh.vertices)[used], inv.reshape(-1, 3), process=False)


def validate(raw, n_faces: int) -> list[dict] | None:
    """Stored parts that cover `n_faces` exactly once, or None."""
    if not isinstance(raw, list) or not raw or n_faces <= 0:
        return None
    seen = np.zeros(int(n_faces), np.uint8)
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return None
        mesh = item.get("mesh")
        runs = mesh.get("runs") if isinstance(mesh, dict) else None
        if not isinstance(runs, list) or not runs:
            return None
        clean_runs = []
        for run in runs:
            if not isinstance(run, (list, tuple)) or len(run) != 2:
                return None
            try:
                start, count = int(run[0]), int(run[1])
            except (TypeError, ValueError):
                return None
            if count <= 0 or start < 0 or start + count > n_faces:
                return None
            seen[start:start + count] += 1
            clean_runs.append((start, count))
        pid = item.get("id")
        if not isinstance(pid, str) or not _ID.match(pid):
            pid = f"p{i + 1}"
        slot = item.get("slot", None)
        if slot is not None and not isinstance(slot, int):
            return None
        material = item.get("material")
        if material is not None and not isinstance(material, str):
            return None
        out.append(_record(
            pid, item.get("name") or f"Part {i + 1}", item.get("color"),
            material, clean_runs, slot,
        ))
    if not np.all(seen == 1):
        return None
    return out


def resolve(stored, n_faces: int, title: str = "Model") -> list[dict]:
    """Saved parts when they still match this mesh, otherwise one part."""
    got = validate(stored, n_faces)
    if got:
        return got
    return single(n_faces, title or "Model")


def worth_storing(parts: list[dict] | None) -> bool:
    """A lone unnamed part is the old single-mesh project. Leave the key off."""
    if not parts:
        return False
    if len(parts) > 1:
        return True
    part = parts[0]
    if part.get("color") or part.get("material"):
        return True
    return part.get("name") not in (None, "", "Model", "Part 1")


def public(parts: list[dict]) -> list[dict]:
    out = []
    for part in parts:
        runs = part["mesh"]["runs"]
        out.append({
            "id": part["id"],
            "name": part["name"],
            "color": part.get("color"),
            "material": part.get("material"),
            "slot": part.get("slot"),
            "mesh": {"runs": [list(run) for run in runs]},
            "triangles": int(sum(int(c) for _, c in runs)),
        })
    return out


def plate_layout(parts: list[dict], n_faces: int) -> dict | None:
    """Contiguous parts in file order, as a plate layout. Otherwise None."""
    if len(parts) < 2:
        return None
    counts = []
    cursor = 0
    for part in parts:
        runs = part["mesh"]["runs"]
        if len(runs) != 1 or int(runs[0][0]) != cursor:
            return None
        count = int(runs[0][1])
        counts.append(count)
        cursor += count
    if cursor != n_faces:
        return None
    n = len(counts)
    return {"counts": counts, "groups": list(range(n)), "hidden": [False] * n}


def colors_for_bodies(mesh: trimesh.Trimesh, parts: list[dict], body_meshes) -> list:
    """Display colour for each CAD body when the part list is the same set of shells."""
    n = len(body_meshes)
    if n == 0 or len(parts) != n or len(mesh.faces) > 200_000 or not any(p.get("color") for p in parts):
        return [None] * n

    def part_centre(part):
        idx = face_indices(part)
        if len(idx) == 0:
            return (0.0, 0.0, 0.0)
        return tuple(np.round(mesh.triangles_center[idx].mean(axis=0), 3))

    order_p = sorted(range(n), key=lambda i: part_centre(parts[i]))
    order_b = sorted(range(n), key=lambda i: tuple(np.round(np.asarray(body_meshes[i].bounds.mean(axis=0), float), 3)))
    cols: list = [None] * n
    for pi, bi in zip(order_p, order_b):
        cols[bi] = parts[pi].get("color")
    return cols


def labels_for_counts(parts: list[dict], counts, n_faces: int) -> list[dict] | None:
    """Parts in the same order and sizes as plate object face counts."""
    try:
        counts = [int(c) for c in counts]
    except (TypeError, ValueError):
        return None
    if len(parts) != len(counts):
        return None
    cursor = 0
    for part, count in zip(parts, counts):
        runs = part["mesh"]["runs"]
        if len(runs) != 1 or int(runs[0][0]) != cursor or int(runs[0][1]) != count:
            return None
        cursor += count
    if cursor != n_faces:
        return None
    return parts


def from_bodies(bodies, n_faces: int) -> list[dict] | None:
    """One part per model body, in merge order. None when that is not this mesh."""
    cursor = 0
    built = []
    for i, body in enumerate(bodies or []):
        faces = getattr(body, "faces", None)
        count = 0 if faces is None else int(len(faces))
        if count <= 0:
            continue
        built.append(_record(
            f"p{len(built) + 1}",
            getattr(body, "name", None) or f"Part {i + 1}",
            getattr(body, "color", None),
            None,
            [(cursor, count)],
        ))
        cursor += count
    if cursor != int(n_faces) or len(built) <= 1:
        return None
    return built


# ---------------------------------------------------------------- shells

def _linear_shells(mesh: trimesh.Trimesh) -> list[np.ndarray]:
    """Disconnected face groups. One pass over the face adjacency, no mesh copy."""
    from trimesh.graph import connected_components
    n = len(mesh.faces)
    if n == 0:
        return []
    comps = connected_components(edges=mesh.face_adjacency, nodes=np.arange(n), min_len=1)
    groups = [np.asarray(sorted(int(i) for i in comp), np.int64) for comp in comps if len(comp)]
    if len(groups) > 1 and n <= AUTO_MAX_FACES:
        centers = mesh.triangles_center

        def key(faces):
            return tuple(np.round(centers[faces].mean(axis=0), 3))

        groups.sort(key=key)
    return groups


def _cad_shells(mesh: trimesh.Trimesh) -> list[np.ndarray] | None:
    """The CAD workspace's shell split. Imported here because cadops imports meshedit."""
    from . import cadops
    return cadops.shell_face_groups(mesh)


def shell_groups(mesh: trimesh.Trimesh) -> list[np.ndarray]:
    """Shells as face indices. CAD's split under the face cap, a linear walk above it."""
    if len(mesh.faces) <= AUTO_MAX_FACES:
        grouped = _cad_shells(mesh)
        if grouped is not None:
            return grouped
    return _linear_shells(mesh)


def _parts_from_groups(mesh: trimesh.Trimesh, groups: list[np.ndarray], previous=None) -> list[dict]:
    previous = previous or []
    by_runs = {}
    for part in previous:
        by_runs[tuple(tuple(run) for run in part["mesh"]["runs"])] = part
    used = set()
    built = []
    nxt = 1
    for faces in groups:
        runs = _runs_of(faces)
        key = tuple(tuple(run) for run in runs)
        prev = by_runs.get(key)
        if prev and prev["id"] not in used:
            used.add(prev["id"])
            built.append(_record(
                prev["id"], prev["name"], prev.get("color"), prev.get("material"), runs, prev.get("slot"),
            ))
            continue
        while f"p{nxt}" in used:
            nxt += 1
        pid = f"p{nxt}"
        used.add(pid)
        nxt += 1
        built.append(_record(pid, f"Part {len(built) + 1}", None, None, runs))
    return built


def detect(mesh: trimesh.Trimesh, previous=None) -> list[dict]:
    """Split disconnected shells into parts. Raises PartsError when that list would be huge."""
    if mesh is None or len(getattr(mesh, "faces", [])) == 0:
        raise PartsError("This model has no triangles to split.")
    groups = shell_groups(mesh)
    if len(groups) > MANUAL_MAX_SHELLS:
        raise PartsError(
            f"This mesh has {len(groups):,} separate pieces. Detect parts stops at {MANUAL_MAX_SHELLS} "
            "so a broken file is not split into thousands of parts."
        )
    if len(groups) <= 1:
        name = (previous or [{}])[0].get("name") if previous else "Model"
        return single(len(mesh.faces), name or "Model")
    return _parts_from_groups(mesh, groups, previous)


def _maybe_auto(mesh: trimesh.Trimesh, parts: list[dict], explicit: bool) -> list[dict]:
    """3MF/OBJ that named only one piece: split when the shell count is small."""
    if explicit or len(parts) != 1 or len(mesh.faces) > AUTO_MAX_FACES or len(mesh.faces) == 0:
        return parts
    groups = shell_groups(mesh)
    if groups is None or not AUTO_MIN_SHELLS <= len(groups) <= AUTO_MAX_SHELLS:
        return parts
    return _parts_from_groups(mesh, groups, parts)


# ---------------------------------------------------------------- 3MF colours

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else ""


def _parse_color_resources(root) -> dict[str, list[tuple[str | None, str | None]]]:
    found = {}
    for el in root.iter():
        kind = _local(el.tag)
        if kind not in ("basematerials", "colorgroup"):
            continue
        pid = el.get("id")
        if not pid:
            continue
        rows = []
        for child in el:
            ck = _local(child.tag)
            if kind == "basematerials" and ck == "base":
                rows.append((_norm_color(child.get("displaycolor")), child.get("name")))
            elif kind == "colorgroup" and ck == "color":
                rows.append((_norm_color(child.get("color")), None))
        found[pid] = rows
    return found


def _lookup(resources, pid, index) -> tuple[str | None, str | None]:
    rows = resources.get(str(pid)) if pid is not None else None
    if not rows:
        return None, _material_id(pid, index)
    try:
        n = int(index or 0)
    except (TypeError, ValueError):
        n = 0
    if not 0 <= n < len(rows):
        return None, _material_id(pid, index)
    color, _base_name = rows[n]
    return color, _material_id(pid, n)


def _triangle_vote(mesh_el, resources, limit: int) -> tuple[str | None, str | None, bool]:
    tris = None
    for child in mesh_el:
        if _local(child.tag) == "triangles":
            tris = child
            break
    if tris is None:
        return None, None, False
    votes: Counter = Counter()
    seen = 0
    varied = False
    for tri in tris:
        if _local(tri.tag) != "triangle":
            continue
        pid = tri.get("pid")
        index = tri.get("pindex", tri.get("p1"))
        if pid is None and index is None:
            continue
        varied = True
        if seen < limit:
            votes[(pid, index)] += 1
        seen += 1
        if seen >= limit and votes:
            break
    if not votes:
        return None, None, varied
    (pid, index), _n = votes.most_common(1)[0]
    color, material = _lookup(resources, pid, index)
    return color, material, varied


def _3mf_has_colour(archive: zipfile.ZipFile) -> bool:
    """Materials sit at the start of a model, before the vertex block. A compressed package hides that text."""
    for name in archive.namelist():
        if not name.lower().endswith(".model"):
            continue
        with archive.open(name) as handle:
            head = handle.read(4_000_000).lower()
        if b"displaycolor" in head or b"colorgroup" in head:
            return True
    return False


def _3mf_color_table(data: bytes) -> dict[str, dict]:
    """Geometry name -> display name, colour, source material id. Empty when the file has no colours."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return {}
    if not _3mf_has_colour(archive):
        return {}
    names = {n.lower(): n for n in archive.namelist()}
    root_name = names.get("3d/3dmodel.model")
    if not root_name:
        return {}
    try:
        from lxml import etree
    except ImportError:
        return {}
    try:
        root = etree.fromstring(archive.read(root_name))
    except etree.XMLSyntaxError:
        return {}
    resources = _parse_color_resources(root)
    # Production packages keep the mesh in another model file. Read those resources too.
    for el in root.iter():
        if _local(el.tag) != "component":
            continue
        path = next((v.strip("/") for k, v in el.attrib.items() if k.endswith("path")), None)
        if not path:
            continue
        alt = names.get(path.lower())
        if not alt:
            continue
        try:
            extra = etree.fromstring(archive.read(alt))
        except etree.XMLSyntaxError:
            continue
        resources.update(_parse_color_resources(extra))
    scan_tris = len(data) <= 8_000_000
    consumed: set[str] = set()
    counts: dict[str, int] = {}
    table = {}
    for el in root.iter():
        if _local(el.tag) != "object":
            continue
        oid = el.get("id")
        if not oid:
            continue
        raw_name = el.get("name") or oid
        geom = unique_name(raw_name, consumed, counts)
        consumed.add(geom)
        mesh_el = next((c for c in el if _local(c.tag) == "mesh"), None)
        if mesh_el is None:
            continue
        color, material = _lookup(resources, el.get("pid"), el.get("pindex", el.get("p1")))
        if scan_tris and el.get("pid") is None:
            voted, voted_mat, varied = _triangle_vote(mesh_el, resources, 50_000)
            if varied and voted:
                color, material = voted, voted_mat
        table[geom] = {"name": _clean_name(el.get("name") or f"Object {oid}", f"Object {oid}"),
                       "color": color, "material": material}
    return table


# ---------------------------------------------------------------- OBJ groups

def _obj_explicit(data: bytes) -> bool:
    head = data[:3].lower()
    if head.startswith(b"o ") or head.startswith(b"g ") or head.startswith(b"u"):
        if head.startswith(b"usemtl") or data.lower().startswith(b"usemtl "):
            return True
        if head.startswith(b"o ") or head.startswith(b"g "):
            return True
    low = data.lower()
    return b"\no " in low or b"\ng " in low or b"\nusemtl " in low or b"\ro " in low or b"\rg " in low or b"\rusemtl " in low


def _obj_face_lines(data: bytes) -> int:
    return data.count(b"\nf ") + data.count(b"\rf ") + (1 if data[:2].lower() == b"f " else 0)


def _mtl_colors(mtl: bytes | str | None) -> dict[str, str]:
    if not mtl:
        return {}
    text = mtl.decode("utf-8", "replace") if isinstance(mtl, (bytes, bytearray)) else str(mtl)
    name = None
    out = {}
    for line in text.splitlines():
        bits = line.split()
        if len(bits) < 2:
            continue
        key = bits[0].lower()
        if key == "newmtl":
            name = " ".join(bits[1:])
        elif key == "kd" and name and len(bits) >= 4:
            color = _kd_hex(bits[1:4])
            if color:
                out[name] = color
    return out


def _obj_labels(text: str) -> list[dict]:
    obj = group = mtl = None
    buckets: dict[tuple, dict] = {}
    order = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("o "):
            obj = stripped[2:].strip()
            continue
        if stripped.startswith("g "):
            group = stripped[2:].strip()
            continue
        if stripped.lower().startswith("usemtl ") or stripped.lower().startswith("usemtl\t"):
            mtl = stripped.split(None, 1)[1].strip()
            continue
        if not stripped.startswith("f "):
            continue
        nvert = len(stripped.split()) - 1
        if nvert < 3:
            continue
        key = (mtl, obj, group)
        if key not in buckets:
            buckets[key] = {"mtl": mtl, "obj": obj, "group": group, "triangles": 0}
            order.append(key)
        buckets[key]["triangles"] += nvert - 2
    return [buckets[k] for k in order]


def _obj_name(lab: dict, index: int, groups_for_object: dict) -> str:
    obj, group, mtl = lab.get("obj"), lab.get("group"), lab.get("mtl")
    if obj and groups_for_object.get(obj, 0) > 1 and group and group != obj:
        base = f"{obj} {group}"
    else:
        base = obj or group or mtl
    return _clean_name(base, f"Part {index + 1}")


def _obj_geometries(data: bytes, has_o: bool, has_g: bool, has_mtl: bool) -> list[trimesh.Trimesh] | None:
    from trimesh.exchange.obj import load_obj
    try:
        loaded = load_obj(
            io.BytesIO(data),
            split_objects=has_o,
            split_groups=has_g,
            group_material=has_mtl or has_o or has_g,
            skip_materials=True,
        )
    except Exception:
        return None
    geometry = loaded.get("geometry") if isinstance(loaded, dict) else None
    if not geometry:
        return None
    meshes = []
    for spec in reversed(list(geometry.values())):
        faces = np.asarray(spec.get("faces"))
        verts = np.asarray(spec.get("vertices"), float)
        if faces.ndim != 2 or faces.shape[1] != 3 or len(faces) == 0:
            return None
        meshes.append(trimesh.Trimesh(verts, faces, process=False))
    return meshes


def _obj_parts(data: bytes, mtl: bytes | None) -> list[tuple] | None:
    low = data.lower()
    has_o = b"\no " in low or b"\ro " in low or low.startswith(b"o ")
    has_g = b"\ng " in low or b"\rg " in low or low.startswith(b"g ")
    has_mtl = b"usemtl " in low
    meshes = _obj_geometries(data, has_o, has_g, has_mtl)
    if not meshes:
        return None
    text = data.decode("utf-8", "replace")
    labels = _obj_labels(text)
    colors = _mtl_colors(mtl)
    if len(labels) == len(meshes) and all(lab["triangles"] == len(m.faces) for lab, m in zip(labels, meshes)):
        per_obj: dict[str, int] = {}
        for lab in labels:
            if lab.get("obj"):
                per_obj[lab["obj"]] = per_obj.get(lab["obj"], 0) + 1
        out = []
        for i, (lab, mesh) in enumerate(zip(labels, meshes)):
            mtl_name = lab.get("mtl")
            out.append((mesh, _obj_name(lab, i, per_obj), colors.get(mtl_name or ""), _material_id(mtl_name, None) if mtl_name else None))
        return out
    out = []
    for i, mesh in enumerate(meshes):
        out.append((mesh, f"Part {i + 1}", None, None))
    return out


# ---------------------------------------------------------------- load

def _parts_from_geoms(geoms: list[tuple], *, concatenate: bool) -> tuple[trimesh.Trimesh, list[dict]]:
    from . import meshedit
    if concatenate or len(geoms) != 1:
        mesh = trimesh.util.concatenate([g[0] for g in geoms])
    else:
        mesh = geoms[0][0]
    mesh = meshedit._new(mesh.vertices, mesh.faces)
    before = len(mesh.faces)
    mesh.merge_vertices()
    if len(mesh.faces) == 0:
        raise meshedit.OpError("The file contains no triangles (maybe it is a curve/point file).")
    if len(mesh.faces) != before:
        return mesh, single(len(mesh.faces))
    parts = []
    cursor = 0
    for i, (_mesh, name, color, material) in enumerate(geoms):
        count = int(len(_mesh.faces))
        if count <= 0:
            continue
        parts.append(_record(f"p{len(parts) + 1}", name or f"Part {i + 1}", color, material, [(cursor, count)]))
        cursor += count
    if cursor != len(mesh.faces) or not parts:
        return mesh, single(len(mesh.faces))
    return mesh, parts


def _load_trimesh(data: bytes, ft: str):
    if ft == "3mf":
        return trimesh.load(io.BytesIO(data), file_type=ft, process=False)
    return trimesh.load(io.BytesIO(data), file_type=ft, process=False, force="mesh", skip_materials=True)


def load_document(data: bytes, ext: str, units_scale: float = 1.0, mtl: bytes | None = None, *,
                  split_shells: bool = False) -> tuple[trimesh.Trimesh, list[dict], list[str]]:
    """STL, OBJ, or 3MF as one mesh plus parts.

    The mesh matches the historical single-mesh loader (objects concatenated, then welded).
    `split_shells` is the editor import: a 3MF or OBJ that did not name several pieces is
    split when that yields 2–16 shells and the file is under the triangle cap. STL is never
    split here. Callers that only want the mesh pass `split_shells=False` and pay nothing extra.
    """
    from . import meshedit
    warnings: list[str] = []
    ft = (ext or "").lower().lstrip(".")
    if ft not in ("stl", "obj", "3mf"):
        raise meshedit.OpError(f"Could not read the {ft.upper()} file.")
    explicit = False
    geoms = None
    concatenate = False
    if ft == "obj" and _obj_explicit(data) and _obj_face_lines(data) <= AUTO_MAX_FACES:
        grouped = _obj_parts(data, mtl)
        if grouped:
            geoms = grouped
            explicit = True
            concatenate = len(grouped) > 1
    if geoms is None:
        try:
            loaded = _load_trimesh(data, ft)
        except meshedit.OpError:
            raise
        except Exception as exc:
            raise meshedit.OpError(f"Could not read the {ft.upper()} file: {exc}")
        if isinstance(loaded, trimesh.Scene):
            dumped = [g for g in loaded.dump() if isinstance(g, trimesh.Trimesh)]
            if not dumped:
                raise meshedit.OpError("The file contains no triangle meshes.")
            table = _3mf_color_table(data) if ft == "3mf" else {}
            nodes = list(loaded.graph.nodes_geometry)
            geoms = []
            for i, geom in enumerate(dumped):
                name, color, material = f"Part {i + 1}", None, None
                if i < len(nodes):
                    _transform, geom_name = loaded.graph[nodes[i]]
                    info = table.get(str(geom_name), {})
                    name = info.get("name") or str(geom_name or nodes[i])
                    color = info.get("color")
                    material = info.get("material")
                geoms.append((geom, name, color, material))
            explicit = len(geoms) > 1
            concatenate = True
        else:
            if not isinstance(loaded, trimesh.Trimesh):
                raise meshedit.OpError("The file contains no triangle meshes.")
            geoms = [(loaded, "Model", None, None)]
            explicit = False
    mesh, parts = _parts_from_geoms(geoms, concatenate=concatenate)
    if len(mesh.faces) > meshedit.MAX_FACES:
        raise meshedit.OpError(f"{len(mesh.faces):,} triangles is above the {meshedit.MAX_FACES:,} limit.")
    if not np.isfinite(mesh.vertices).all():
        raise meshedit.OpError("File contains invalid coordinates.")
    scale = 1.0
    if ft == "3mf":
        scale = meshedit._3mf_unit_scale(data)
        if scale != 1.0:
            mesh = meshedit._new(mesh.vertices * scale, mesh.faces)
            warnings.append(f"3MF declared units; converted to mm (×{scale:g}).")
    size = float(mesh.extents.max()) * (1.0 if ft == "3mf" else float(units_scale or 1.0))
    warnings += meshedit.size_warnings(size)
    if split_shells and ft in ("3mf", "obj"):
        parts = _maybe_auto(mesh, parts, explicit)
    return mesh, parts, warnings
