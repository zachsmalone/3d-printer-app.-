"""Edit projects: the non-destructive layer on top of the build history.

An edit project is a normal history entry (counts toward the 5-build cap) with `kind: "edit"`:
  outputs/<id>/original.<ext>   the uploaded file, byte-for-byte, NEVER modified
  outputs/<id>/source.<ext>     (photo-based projects) the uploaded photo
  outputs/<id>/meta.json        {ops: [{op, params, label}], head, ...}
  outputs/<id>/model.{stl,obj,3mf}, thumb.png   derived at the current head (regenerated lazily)
The current mesh = replay of ops[:head] on the original. Undo/redo move `head`; a new op discards the redo tail.
"""
from __future__ import annotations

import base64
import copy
import ctypes
import hashlib
import json
import logging
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from ..core import cadops
from ..core import dims as dimmod
from ..core import exporters, geometry, meshedit, meshparts, meshthumb, part3mf, partslots
from ..core.geometry import Body, Model
from .history import store

_lock = threading.RLock()
_BASES: dict[str, trimesh.Trimesh] = {}
_STATES: dict[str, OrderedDict] = {}
MAX_PREVIEW_FACES = 150_000
MAX_UPLOAD_EDIT = 500 * 1024 * 1024


def is_edit(bid: str) -> bool:
    try:
        return store.get(bid).get("kind") == "edit"
    except KeyError:
        return False


# ---------------------------------------------------------------- state
def _base(bid: str, meta: dict) -> trimesh.Trimesh:
    m = _BASES.get(bid)
    if m is None:
        d = store.dir(bid)
        f = next(d.glob("original.*"))
        m, _ = meshedit.load_mesh(f.read_bytes(), f.suffix[1:])
        if len(_BASES) > 6:
            _BASES.pop(next(iter(_BASES)))
        _BASES[bid] = m
    return m


def _apply(meta: dict, m, o: dict):
    """meshedit.apply with this project's named dimensions substituted ("$name" -> number)."""
    try:
        params = dimmod.resolve(o["op"], o["params"], meta.get("dims"))
    except dimmod.DimError as e:
        raise meshedit.OpError(str(e))
    return meshedit.apply(m, o["op"], params)


def geometry_revision(meta: dict, head: int | None = None) -> str:
    """Identity of the derived printable mesh.

    The step index is not enough: undo then a different edit can reuse the same head, and named
    dimensions change the mesh without moving head. Skipped text steps are part of the identity so
    a warm process cannot keep a mesh that a cold replay would leave out.
    """
    head = int(meta["head"] if head is None else head)
    ops = (meta.get("ops") or [])[:head]
    skipped = [i for i, o in enumerate(ops) if not _replay_safe(o)]
    plate = (meta.get("plate_layouts") or {}).get(str(head))
    blob = json.dumps(
        {"v": 1, "ops": ops, "dims": meta.get("dims") or {}, "plate": plate, "skipped": skipped},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def _cache_put(bid: str, head: int, mesh, meta: dict) -> None:
    slot = _STATES.setdefault(bid, OrderedDict())
    slot[head] = (geometry_revision(meta, head), mesh)
    slot.move_to_end(head)
    while len(slot) > 6:
        slot.popitem(last=False)


def _cache_hit(bid: str, head: int, meta: dict):
    slot = _STATES.get(bid)
    if not slot or head not in slot:
        return None
    entry = slot[head]
    if not (isinstance(entry, tuple) and len(entry) == 2):
        return None
    rev, mesh = entry
    if rev != geometry_revision(meta, head):
        return None
    slot.move_to_end(head)
    return mesh


def _migrate_body_refs(bid: str, meta: dict) -> dict:
    """Rewrite saved body indices to stable ids, using the geometry those indices named.

    Walks the stored steps in order, before any edit of an earlier step is applied. An index is
    the centre-sorted list position at that step. If that position is shared by two bodies, or a
    stored id is not on the mesh, this raises and does not save a guess. Caller holds `_lock`
    when the project is already on disk; a project that is not saved yet is left unchanged.
    """
    if not cadops.history_needs_body_migration(meta.get("ops") or []):
        return meta
    try:
        meta = store.get(bid)
    except KeyError:
        return meta
    if not cadops.history_needs_body_migration(meta.get("ops") or []):
        return meta
    m = cadops.ensure_body_ids(_base(bid, meta))
    new_ops = []
    changed = False
    for i, o in enumerate(meta.get("ops") or []):
        params = dict(o.get("params") or {})
        step_changed = False
        if _replay_safe(o):
            try:
                params, step_changed = cadops.bind_legacy_body_refs(m, o.get("op") or "", params)
                m, _ = _apply(meta, m, {"op": o.get("op"), "params": params})
            except meshedit.OpError as e:
                raise meshedit.OpError(f"Step {i + 1} ({o.get('label') or o.get('op')}): {e}")
        if step_changed:
            changed = True
            new_ops.append({**o, "params": params})
        else:
            new_ops.append(o)
    if changed:
        meta["ops"] = new_ops
        _STATES.pop(bid, None)
        store.save(meta)
        store.cache.pop(bid, None)
    return meta


def mesh_at(bid: str, meta: dict | None = None, head: int | None = None) -> trimesh.Trimesh:
    meta = meta or store.get(bid)
    head = meta["head"] if head is None else head
    with _lock:
        meta = _migrate_body_refs(bid, meta)
        hit = _cache_hit(bid, head, meta)
        if hit is not None:
            return hit
        rev = geometry_revision(meta, head)
        slot = _STATES.get(bid) or {}
        start = None
        for h in sorted((h for h in slot if isinstance(h, int) and h <= head), reverse=True):
            if _cache_hit(bid, h, meta) is not None:
                start = h
                break
        source = slot[start][1] if start is not None else _base(bid, meta)
        # Replay outside this lock. A CAD drag otherwise holds it across every heavy step,
        # and scene/slots/undo pile up behind one translate.
        m = source.copy()
        pending = []
        for k in range(start or 0, head):
            o = meta["ops"][k]
            if _replay_safe(o):
                pending.append(o)
        dims = copy.deepcopy(meta.get("dims"))
    replay_meta = {"dims": dims}
    for o in pending:
        m, _ = _apply(replay_meta, m, o)
    with _lock:
        try:
            fresh = store.get(bid)
        except KeyError:
            return m
        if geometry_revision(fresh, head) == rev:
            _cache_put(bid, head, m, fresh)
        return m


def _stats(m: trimesh.Trimesh, title: str) -> dict:
    a = meshedit.analyze(m)
    return {"bodies": [{"name": title, "triangles": a["triangles"], "watertight": a["watertight"], "volume_mm3": a["volume_mm3"]}],
            "watertight": a["watertight"], "size_mm": a["size_mm"], "triangles": a["triangles"]}


def as_model(m: trimesh.Trimesh, title: str) -> Model:
    # Export, slice, and handoff take one mesh. Parts stay on the project; this is their merge.
    # The object name inside exported OBJ/3MF is deliberately generic: the project title is never written into files.
    m = meshparts.merged_mesh(m)
    return Model(bodies=[Body("model", m.vertices.copy(), m.faces.copy())], mode="edit")


def model(bid: str) -> Model:
    meta = store.get(bid)
    return as_model(printable_at(bid, meta), meta["title"])


def _parts_stamp(meta: dict) -> str:
    """Identity of the part names and slots. Geometry can stay put while a slot changes."""
    parts = meta.get("parts") or []
    blob = json.dumps(
        [{"id": p.get("id"), "name": p.get("name"), "color": p.get("color"), "slot": p.get("slot")} for p in parts if isinstance(p, dict)],
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def _model_3mf_bytes(mesh: trimesh.Trimesh, meta: dict) -> bytes:
    """Cached 3MF. One slot, or every part on slot 1, stays the single-object file."""
    baked = part3mf.build(mesh, meta, part3mf.stored_slot_count(meta.get("parts")))
    if baked is not None:
        return baked[0]
    return exporters.to_3mf(as_model(mesh, meta.get("title") or "Model"))


def ensure_exports(bid: str):
    """(Re)write model.stl/obj/3mf + thumb.png when they are stale. No-op for photo builds."""
    try:
        meta = store.get(bid)
    except KeyError:
        return
    if meta.get("kind") != "edit" or not_ready(meta):
        return
    d = store.dir(bid)
    rev = geometry_revision(meta)
    stamp = _parts_stamp(meta)
    files_ready = all((d / f"model.{e}").exists() for e in exporters.WRITERS)
    if meta.get("exports_rev") == rev and meta.get("parts_export") == stamp and files_ready:
        return
    with _lock:
        meta = store.get(bid)
        if meta.get("kind") != "edit" or not_ready(meta):
            return
        d = store.dir(bid)
        rev = geometry_revision(meta)
        stamp = _parts_stamp(meta)
        files_ready = all((d / f"model.{e}").exists() for e in exporters.WRITERS)
        if meta.get("exports_rev") == rev and meta.get("parts_export") == stamp and files_ready:
            return
        if meta.get("exports_rev") == rev and files_ready:
            # The mesh is unchanged. Only the 3MF carries part slots.
            m = printable_at(bid, meta)
            (d / "model.3mf").write_bytes(_model_3mf_bytes(m, meta))
            meta["parts_export"] = stamp
            store.save(meta)
            return
        m = printable_at(bid, meta)
        quality = export_quality(m)
        meta["quality_gate"] = quality
        # N2: the export-gate warning describes the CURRENT mesh, so drop the old one (e.g. "not watertight" from import)
        # once Fix mesh makes it print-safe, and put the current one back if a later step / undo breaks it again.
        # Replay omissions are the same kind of derived note: they describe this mesh, not an older one.
        kept = [w for w in (meta.get("warnings") or []) if not w.startswith(_GATE_PREFIX) and not w.startswith(_REPLAY_PREFIX)]
        meta["warnings"] = list(dict.fromkeys(kept + replay_omissions(meta) + ([] if quality["ok"] else [quality["message"]])))
        mdl = as_model(m, meta["title"])
        for ext, fn in exporters.WRITERS.items():
            if ext == "3mf":
                (d / "model.3mf").write_bytes(_model_3mf_bytes(m, meta))
            else:
                (d / f"model.{ext}").write_bytes(fn(mdl))
        (d / "model.gcode").unlink(missing_ok=True)       # stale slice
        Image.fromarray(meshthumb.render(m.vertices, m.faces)).save(d / "thumb.png")
        meta["exports_rev"] = rev
        meta["stl_rev"] = rev
        meta["parts_export"] = stamp
        meta.pop("exports_head", None)
        store.save(meta)


def ensure_stl(bid: str):
    """Write model.stl for the current geometry. Slice uses this.

    OBJ, 3MF and the thumbnail stay on ensure_exports (import and download). Building them
    rewrites every triangle as text and is not part of producing G-code.
    """
    try:
        meta = store.get(bid)
    except KeyError:
        return
    if meta.get("kind") != "edit" or not_ready(meta):
        return
    d = store.dir(bid)
    rev = geometry_revision(meta)
    stl = d / "model.stl"
    if meta.get("stl_rev") == rev and stl.is_file():
        return
    with _lock:
        meta = store.get(bid)
        if meta.get("kind") != "edit" or not_ready(meta):
            return
        d = store.dir(bid)
        rev = geometry_revision(meta)
        stl = d / "model.stl"
        if meta.get("stl_rev") == rev and stl.is_file():
            return
        m = printable_at(bid, meta)
        stl.write_bytes(exporters.to_stl(as_model(m, meta["title"])))
        meta["stl_rev"] = rev
        store.save(meta)


# ---------------------------------------------------------------- AI-made provenance (T&S F1/F8)
AI_3MF_KEY = "zeim:AIMade"


def ai_lineage(meta: dict | None, _hops: int = 0) -> bool:
    """True if this build, or any build it was made from (parent_build / version_of / base.from_build), is AI-made."""
    if not meta or _hops > 32:
        return False
    if meta.get("ai") or meta.get("mode") == "ai3d":
        return True
    for pid in {meta.get("parent_build"), meta.get("version_of"), (meta.get("base") or {}).get("from_build")} - {None, ""}:
        try:
            if ai_lineage(store.get(pid), _hops + 1):
                return True
        except (KeyError, FileNotFoundError, OSError, ValueError):
            continue
    return False


def ai_in_3mf(data: bytes) -> bool:
    """A 3MF that ZEIM exported from an AI-made model carries zeim:AIMade=true (model metadata or Metadata/zeim_owner.json)."""
    import io
    import json
    import re
    import zipfile
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = {n.lower(): n for n in z.namelist()}
        if "3d/3dmodel.model" in names:
            xml = z.read(names["3d/3dmodel.model"])[:4 * 2**20]
            if re.search(rb'<metadata\s+name=["\']zeim:AIMade["\'][^>]*>\s*true\s*<', xml, re.I):
                return True
        if "metadata/zeim_owner.json" in names:
            return json.loads(z.read(names["metadata/zeim_owner.json"])[:65536]).get("AIMade") in (True, "true")
    except Exception:
        return False
    return False


# ---------------------------------------------------------------- creation
def create(owner_sid: str, visibility: str, *, title: str, base: dict, original: bytes, original_ext: str,
           mesh: trimesh.Trimesh, beginner: bool, warnings: list[str], import_scale: float = 1.0,
           import_units: str = "mm", source_image: tuple[bytes, str] | None = None,
           ai: bool = False, parent_build: str = "", parts: list | None = None) -> dict:
    """Caller must already hold `store.lock` and have reserved a history slot."""
    bid = uuid.uuid4().hex[:12]
    d = store.dir(bid)
    d.mkdir(parents=True)
    (d / f"original.{original_ext}").write_bytes(original)       # the untouched upload
    if source_image:
        (d / f"source.{source_image[1]}").write_bytes(source_image[0])
    ops = []
    if import_scale != 1.0:
        ops.append({"op": "scale", "params": {"factor": import_scale, "pivot": "origin"}, "label": f"Units: {import_units} → mm"})
    meta = {"id": bid, "kind": "edit", "mode": "edit", "beginner": beginner, "title": title[:60] or "Untitled",
            "base": base, "ops": ops, "head": len(ops), "warnings": warnings, "source": "",
            "params": {}, "auto_notes": [], "info": {}, "owner_sid": owner_sid, "visibility": visibility}
    if parent_build:
        meta["parent_build"] = parent_build
    if ai or (original_ext == "3mf" and ai_in_3mf(original)) or (parent_build and ai_lineage({"parent_build": parent_build})):
        meta["ai"] = True                                         # AI-made provenance survives the editor
    stored = meshparts.validate(parts, len(mesh.faces)) if parts else None
    if stored and meshparts.worth_storing(stored):
        meta["parts"] = stored
        layout = meshparts.plate_layout(stored, len(mesh.faces))
        if layout:
            meta["plate_layouts"] = {str(len(ops)): layout}
    _BASES[bid] = mesh
    try:
        m = mesh_at(bid, {**meta, "head": len(ops)})
        meta["stats"] = _stats(m, meta["title"])
    except meshedit.OpError:
        store.delete(bid)
        raise
    store.save(meta)
    ensure_exports(bid)
    return store.get(bid)


def _stats_from(a: dict, title: str) -> dict:
    return {"bodies": [{"name": title, "triangles": a["triangles"], "watertight": a["watertight"], "volume_mm3": a["volume_mm3"]}],
            "watertight": a["watertight"], "size_mm": a["size_mm"], "triangles": a["triangles"]}


_STL_REC = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
_PREVIEW_NOTE = "Preview only. The saved file keeps every triangle."


def _binary_stl_count(data: bytes) -> int:
    if len(data) < 84:
        raise meshedit.OpError("That file doesn't look like a binary STL.")
    n = int.from_bytes(data[80:84], "little")
    if len(data) != 84 + 50 * n or n <= 0:
        raise meshedit.OpError("That file doesn't look like a binary STL.")
    return n


def _bounds_from(lo, hi) -> dict:
    return {
        "size_mm": [round(float(x), 3) for x in (hi - lo)],
        "min_mm": [round(float(x), 3) for x in lo],
        "max_mm": [round(float(x), 3) for x in hi],
        "center_mm": [round(float(x), 3) for x in (lo + hi) / 2],
    }


def binary_stl_bounds(data: bytes) -> tuple[int, dict]:
    """Triangle count and axis-aligned bounds in mm. Does not copy or change `data`."""
    n = _binary_stl_count(data)
    tris = np.frombuffer(data, dtype=_STL_REC, count=n, offset=84)["v"]
    flat = tris.reshape(-1, 3)
    lo = np.min(flat, axis=0)
    hi = np.max(flat, axis=0)
    return n, _bounds_from(lo, hi)


def slim_preview(decimated: bool) -> dict:
    """View metadata with no triangle bytes. The browser already drew its own sample."""
    return {"decimated": bool(decimated), "authoritative": False, "note": _PREVIEW_NOTE, "bodies": []}


def iter_binary_stl_preview(data: bytes, max_faces: int = MAX_PREVIEW_FACES):
    """Walk a binary STL and yield view progress, then one preview_ready event.

    Progress counts source triangles visited. The preview keeps at most max_faces triangles.
    The bytes of `data` are not modified. This is not the mesh Slice or export will use.
    """
    n = _binary_stl_count(data)
    tris = np.frombuffer(data, dtype=_STL_REC, count=n, offset=84)["v"]
    flat = tris.reshape(-1, 3)
    lo = np.min(flat, axis=0)
    hi = np.max(flat, axis=0)
    bounds = _bounds_from(lo, hi)
    step = 1 if n <= max_faces else int(np.ceil(n / max_faces))
    picks = []
    chunk = max(step, n // 8)
    done = 0
    while done < n:
        nxt = min(n, done + chunk)
        sl = tris[done:nxt:step]
        if len(sl):
            picks.append(np.array(sl, copy=True))
        done = nxt
        yield {"phase": "view", "done": done, "total": n, "unit": "triangles"}
    chosen = np.concatenate(picks) if picks else np.zeros((0, 3, 3), np.float32)
    if len(chosen) > max_faces:
        chosen = chosen[:max_faces]
    pos = np.ascontiguousarray(chosen.reshape(-1, 3).astype("<f4"))
    idx = np.arange(len(pos), dtype="<u4")
    yield {"phase": "preview_ready", "triangles": int(n),
           "size_mm": bounds["size_mm"], "bounds": bounds,
           "preview": {"decimated": bool(step != 1), "authoritative": False, "note": _PREVIEW_NOTE,
                       "bodies": [{"name": "model", "color": None,
                                   "positions": base64.b64encode(pos.tobytes()).decode(),
                                   "indices": base64.b64encode(idx.tobytes()).decode()}]}}


PENDING_SLICE = ("The full model is still being checked. Slice stays off until that finishes. "
                 "The view is only a preview.")
CHECK_FAILED = "The full model could not be checked. Slice stays off. The view is only a preview."


def not_ready(meta: dict | None) -> str | None:
    """Why Slice must refuse this project, or None when it may run.

    A large STL stays blocked until `slice_ready` is true. A missing flag on that
    project is still pending: the editor reports it as not ready. Older projects
    have neither `header_triangles` nor `stats.pending`, so they still slice.
    """
    if not isinstance(meta, dict):
        return PENDING_SLICE
    if meta.get("slice_ready") is True:
        return None
    pending = meta.get("slice_ready") is False or (meta.get("stats") or {}).get("pending") is True or bool(meta.get("header_triangles"))
    if not pending:
        return None
    return str(meta.get("check_error") or PENDING_SLICE)


def create_pending_stl(owner_sid: str, visibility: str, *, title: str, base: dict, original: bytes | None,
                       beginner: bool, warnings: list[str], preview: dict | None, size_mm: list, triangles: int,
                       import_scale: float = 1.0, import_units: str = "mm", write_preview: bool = True,
                       bounds: dict | None = None) -> dict:
    """Save the pending record and mark Slice off. The original bytes are written when given.

    `write_preview` false keeps the large preview JSON off this call. The open path yields the
    in-memory preview first, then writes that file. A slow disk must not sit in front of the view.
    """
    bid = uuid.uuid4().hex[:12]
    d = store.dir(bid)
    d.mkdir(parents=True)
    if original is not None:
        (d / "original.stl").write_bytes(original)
    if write_preview and preview is not None:
        (d / "preview.json").write_text(json.dumps(preview))
    ops = []
    if import_scale != 1.0:
        ops.append({"op": "scale", "params": {"factor": import_scale, "pivot": "origin"},
                    "label": f"Units: {import_units} → mm"})
    note = (f"This view uses fewer triangles so it can open. The saved file keeps all {triangles:,} triangles. "
            "Slice stays off until the full check finishes.")
    meta = {"id": bid, "kind": "edit", "mode": "edit", "beginner": beginner, "title": title[:60] or "Untitled",
            "base": base, "ops": ops, "head": len(ops), "warnings": list(dict.fromkeys([*warnings, note])),
            "source": "", "params": {}, "auto_notes": [], "info": {}, "owner_sid": owner_sid, "visibility": visibility,
            "slice_ready": False, "header_triangles": triangles,
            "stats": {"triangles": triangles, "watertight": None, "size_mm": size_mm, "pending": True,
                      "min_mm": (bounds or {}).get("min_mm"), "max_mm": (bounds or {}).get("max_mm"),
                      "center_mm": (bounds or {}).get("center_mm"),
                      "bodies": [{"name": title[:60] or "Untitled", "triangles": triangles, "watertight": None, "volume_mm3": None}]}}
    store.save(meta)
    return store.get(bid)


def write_preview(bid: str, preview: dict) -> None:
    """Store the view mesh. Missing file stays a pending project; Slice does not run."""
    d = store.dir(bid)
    if not d.is_dir():
        return
    (d / "preview.json").write_text(json.dumps(preview))


def quick_payload(meta: dict, preview: dict | None = None, *, load_preview: bool = True) -> dict:
    """Project JSON for a large STL whose full check has not finished. Does not load the mesh.

    `load_preview` false skips the preview file. That file is the sampled view as base64 and
    is several megabytes; the status poll does not need it.
    """
    from ..api.builds import summary
    n = int(meta.get("header_triangles") or meta.get("stats", {}).get("triangles") or 0)
    if preview is None:
        if not load_preview:
            preview = slim_preview(n > MAX_PREVIEW_FACES)
        else:
            path = store.dir(meta["id"]) / "preview.json"
            preview = json.loads(path.read_text()) if path.is_file() else slim_preview(True)
    size = (meta.get("stats") or {}).get("size_mm") or [0, 0, 0]
    if meta.get("slice_ready") and meta.get("analysis"):
        analysis = meta["analysis"]
        quality = meta.get("quality_gate") or {"ok": None, "pending": True, "message": "Checking the full model."}
    else:
        st = meta.get("stats") or {}
        analysis = {"triangles": n, "vertices": None, "watertight": None, "size_mm": size, "volume_mm3": None,
                    "area_mm2": None, "pending": True, "boundary_edges": None, "components": None,
                    "min_mm": st.get("min_mm"), "max_mm": st.get("max_mm"), "center_mm": st.get("center_mm"),
                    "center_of_mass_mm": None}
        err = meta.get("check_error") or ""
        quality = {"ok": None, "pending": True,
                   "message": err or "Checking the full model. Slice stays off until this finishes. The view is a lighter preview."}
    ops = [{"i": i + 1, "op": o["op"], "label": o["label"], "name": o.get("name") or "",
            "params": {k: v for k, v in (o.get("params") or {}).items() if isinstance(v, (str, int, float, bool, dict, list, type(None)))},
            "editable": o["op"] not in ("plate", "import")} for i, o in enumerate(meta.get("ops") or [])]
    return {**summary(meta), "params": {}, "auto_notes": [], "info": {}, "preview": preview, "plate": None,
            "dims": meta.get("dims") or {}, "ops": ops, "head": meta.get("head") or 0,
            "can_undo": (meta.get("head") or 0) > 0, "can_redo": (meta.get("head") or 0) < len(meta.get("ops") or []),
            "analysis": analysis, "quality_gate": quality, "base": meta.get("base"), "warnings": meta.get("warnings", []),
            "slice_ready": bool(meta.get("slice_ready")), "report": meta.get("last_report"),
            "support_paint": support_paint_view(meta),
            "original": f"/api/edit/{meta['id']}/original", "capabilities": capabilities(),
            "parts": _parts_public(meta, int(meta.get("header_triangles") or n))}


def _mark_check_failed(bid: str) -> None:
    try:
        with store.lock:
            meta = store.get(bid)
            if meta.get("slice_ready") is True:
                return
            meta["check_error"] = CHECK_FAILED
            meta["slice_ready"] = False
            meta["quality_gate"] = {"ok": None, "pending": True, "message": CHECK_FAILED}
            store.save(meta)
    except KeyError:
        return


def _one_core():
    """Keep the full-mesh load from pinning every core the web worker needs.

    NumPy's OpenBLAS wheel exports a thread setter. Missing symbol or a different
    BLAS leaves the process alone. The previous count is restored afterwards.
    """
    libs = list(Path(np.__file__).resolve().parent.glob(".libs/libscipy_openblas*.so*"))
    libs += list(Path(np.__file__).resolve().parent.glob(".libs/libopenblas*.so*"))
    for lib_path in libs:
        try:
            lib = ctypes.CDLL(str(lib_path))
        except OSError:
            continue
        setter = None
        for name in ("openblas_set_num_threads", "scipy_openblas_set_num_threads64_", "openblas_set_num_threads64_"):
            if hasattr(lib, name):
                setter = getattr(lib, name)
                break
        getter = None
        for name in ("openblas_get_num_threads", "scipy_openblas_get_num_threads64_", "openblas_get_num_threads64_"):
            if hasattr(lib, name):
                getter = getattr(lib, name)
                break
        if setter is None:
            continue
        prev = int(getter()) if getter is not None else 0
        setter(1)
        return lib, setter, prev
    return None


def _restore_cores(token) -> None:
    if not token:
        return
    _lib, setter, prev = token
    setter(prev if prev > 0 else 0)


def store_original_and_check(bid: str, original: bytes) -> None:
    """Write the untouched STL, then start the check. Slice stays off if either step fails."""
    try:
        d = store.dir(bid)
        if not d.is_dir():
            return
        meta = store.get(bid)
        if meta.get("slice_ready") is not False:
            return
        partial = d / "original.stl.partial"
        partial.write_bytes(original)
        partial.replace(d / "original.stl")
    except Exception:
        _mark_check_failed(bid)
        return
    start_full_check(bid)


def start_full_check(bid: str) -> None:
    """Load, check, and write the slice STL off the view path. Failures leave Slice off."""
    def run():
        try:
            finish_full_check(bid)
        except Exception:
            logging.getLogger("zeim.import").exception("full model check failed")
            _mark_check_failed(bid)
    threading.Thread(target=run, name=f"zeim-stl-{bid}", daemon=True).start()


def finish_full_check(bid: str) -> None:
    """Authoritative mesh: every triangle from the original STL, then the quality check, then Slice may run.

    The mesh load does not hold the history lock. A project deleted or edited while that runs
    is not marked ready from the stale mesh.
    """
    for _attempt in range(3):
        with store.lock:
            try:
                meta = store.get(bid)
            except KeyError:
                return
            if meta.get("slice_ready") is not False:
                return
            d = store.dir(bid)
            original_path = d / "original.stl"
            if not original_path.is_file():
                meta["check_error"] = CHECK_FAILED
                meta["slice_ready"] = False
                meta["quality_gate"] = {"ok": None, "pending": True, "message": CHECK_FAILED}
                store.save(meta)
                return
            snapshot = {"created": meta.get("created"), "head": meta.get("head"),
                        "ops": copy.deepcopy(meta.get("ops")), "dims": copy.deepcopy(meta.get("dims")),
                        "title": meta.get("title") or "Untitled"}
        cores = _one_core()
        try:
            original = original_path.read_bytes()
            mesh, warns = meshedit.load_mesh(original, "stl")
            del original
            with _lock:
                try:
                    held = store.get(bid)
                except KeyError:
                    return
                _BASES[bid] = mesh
                m = mesh_at(bid, held)
                analysis = meshedit.analyze(m)
                quality = quality_from_analysis(analysis)
                stl_bytes = exporters.to_stl(as_model(m, snapshot["title"]))
                face_count = int(len(m.faces))
        except Exception:
            _restore_cores(cores)
            _mark_check_failed(bid)
            return
        _restore_cores(cores)
        with store.lock:
            try:
                meta = store.get(bid)
            except KeyError:
                return
            if meta.get("slice_ready") is True or meta.get("created") != snapshot["created"]:
                return
            if (meta.get("head"), meta.get("ops"), meta.get("dims")) != (snapshot["head"], snapshot["ops"], snapshot["dims"]):
                continue
            if not original_path.is_file() or not store.dir(bid).is_dir():
                return
            (d / "model.stl").write_bytes(stl_bytes)
            head = int(meta.get("head") or 0)
            layouts = dict(meta.get("plate_layouts") or {})
            layouts[str(head)] = {"counts": [face_count], "groups": [0], "hidden": [False]}
            meta["plate_layouts"] = layouts
            meta["analysis"] = analysis
            meta["analysis_rev"] = geometry_revision(meta)
            meta["quality_gate"] = quality
            meta["stats"] = _stats_from(analysis, meta["title"])
            meta["stl_rev"] = meta["analysis_rev"]
            meta["slice_ready"] = True
            meta.pop("check_error", None)
            if warns:
                meta["warnings"] = list(dict.fromkeys([*(meta.get("warnings") or []), *warns]))
            store.save(meta)
            return
    _mark_check_failed(bid)


def clone(owner_sid: str, visibility: str, src_bid: str, *, title: str, beginner: bool) -> dict:
    """'Save as a new version' of an edit project WITH its history (QA B12): the untouched original file, every step
    up to the current head (the redo tail is dropped, like a new step would), named dimensions, plate layouts and
    the display appearance are copied, so v2's earlier steps stay editable. The source project is not changed.
    Caller must already hold `store.lock`, have reserved a history slot and checked that the caller owns `src_bid`."""
    import shutil
    src = store.get(src_bid)
    sd = store.dir(src_bid)
    head = int(src.get("head", 0))
    bid = uuid.uuid4().hex[:12]
    d = store.dir(bid)
    d.mkdir(parents=True)
    try:
        for f in list(sd.glob("original.*")) + list(sd.glob("source.*")):
            shutil.copyfile(f, d / f.name)
        layouts = {k: v for k, v in (src.get("plate_layouts") or {}).items() if str(k).lstrip("-").isdigit() and int(k) <= head}
        meta = {"id": bid, "kind": "edit", "mode": "edit", "beginner": beginner, "title": title[:60] or "Untitled",
                "base": copy.deepcopy(src.get("base") or {}), "ops": copy.deepcopy(src.get("ops", [])[:head]), "head": head,
                "warnings": [], "source": "", "params": {}, "auto_notes": [], "info": {},
                "owner_sid": owner_sid, "visibility": visibility, "version_of": src_bid, "parent_build": src_bid}
        if ai_lineage(src):
            meta["ai"] = True
        for k in ("dims", "appearance", "photo_ack", "parts"):
            if src.get(k):
                meta[k] = copy.deepcopy(src[k])
        if layouts:
            meta["plate_layouts"] = copy.deepcopy(layouts)
        with _lock:                                          # reuse the source's parsed base + current state: no replay
            _BASES[bid] = _base(src_bid, src).copy()
            cur = mesh_at(src_bid, src).copy()
            _STATES[bid] = OrderedDict()
            _cache_put(bid, head, cur, meta)
        meta["stats"] = _stats(cur, meta["title"])
    except Exception:
        _BASES.pop(bid, None); _STATES.pop(bid, None)
        shutil.rmtree(d, ignore_errors=True)
        raise
    store.save(meta)
    ensure_exports(bid)
    return store.get(bid)


# ---------------------------------------------------------------- editing
def _commit(bid: str, meta: dict, head: int):
    meta["head"] = head
    m = mesh_at(bid, meta)
    meta["stats"] = _stats(m, meta["title"])
    store.save(meta)
    store.cache.pop(bid, None)


TEXT_MAX = 60       # characters for the emboss/deboss text (same as meshedit.op_text)


MAX_PARAM_STRINGS = 6000


def _scan_strings(v, safety, depth=0, seen=None):
    """Every free-text value anywhere in a step's params is plain text and passes the language /
    contact filter (stored params are shown in History and shared with public projects)."""
    seen = seen if seen is not None else [0]
    if depth > 8:
        raise ValueError("Step settings are nested too deeply.")
    if isinstance(v, str):
        seen[0] += 1
        if seen[0] > MAX_PARAM_STRINGS:
            raise ValueError("Too many text values in the step settings.")
        if "<" in v or ">" in v:
            raise ValueError("Step settings can't contain < or >.")
        if len(v) > 200:
            raise ValueError("A text value in the step settings is too long.")
        if v:
            safety.filter_only(v, "Text")
    elif isinstance(v, dict):
        for k, x in v.items():
            _scan_strings(str(k), safety, depth + 1, seen)
            _scan_strings(x, safety, depth + 1, seen)
    elif isinstance(v, list):
        for x in v:
            _scan_strings(x, safety, depth + 1, seen)


def check_op_text(op: str, params: dict) -> dict:
    """Free text that ends up in a model is gated like any other text others can read: length cap first, then the
    language + personal-info filter. Raises safety.ChatBlocked (nothing is stored). Returns the params with text trimmed."""
    from ..community import safety
    from ..core import cadops
    params = cadops.clean_params(op, params)
    _scan_strings(params, safety)
    out = dict(params)
    for k, v in params.items():
        if isinstance(v, str) and len(v) > 200:
            raise ValueError(f"'{k}' is too long.")
        if op == "text" and isinstance(v, (dict, list)):  # (cad_text: point/normal are lists, text checked below)
            raise ValueError(f"'{k}' must be a simple value.")
    if op == "plate" and params.get("action") == "text":     # plate editor text on one object: same cap + filter
        for k in ("text", "font", "mode", "face"):
            if isinstance(params.get(k), (dict, list)):
                raise ValueError(f"'{k}' must be a simple value.")
    if op in ("text", "cad_text") or (op == "plate" and params.get("action") == "text"):
        txt = params.get("text", "")
        if not isinstance(txt, str):
            raise ValueError("Text must be text.")
        if len(txt) > TEXT_MAX:
            raise ValueError(f"Text must be 1-{TEXT_MAX} characters.")
        out["text"] = safety.check(txt, "edit:text")
    return out


def _replay_safe(o: dict) -> bool:
    """Ops stored before the filter existed (or by an older word list) are re-checked when a project is replayed.
    A text step that no longer passes is left out of the mesh. mesh_at, the preview and ensure_exports all use
    this same check, and geometry_revision includes the skipped steps so a cached mesh cannot keep the text."""
    if o.get("op") not in ("text", "cad_text") and not (o.get("op") == "plate" and (o.get("params") or {}).get("action") == "text"):
        return True
    from ..community import safety
    t = o.get("params", {}).get("text", "")
    return isinstance(t, str) and len(t) <= TEXT_MAX and not safety.scan(t)


def replay_omissions(meta: dict, head: int | None = None) -> list[str]:
    """User-visible note when a stored text step is left out of the current mesh. Empty when every step replays."""
    head = int(meta["head"] if head is None else head)
    skipped = [i + 1 for i, o in enumerate((meta.get("ops") or [])[:head]) if not _replay_safe(o)]
    if not skipped:
        return []
    nums = ", ".join(str(i) for i in skipped)
    noun = "step" if len(skipped) == 1 else "steps"
    return [_REPLAY_PREFIX + f"text {noun} {nums} no longer passes the text check, so it is not in the preview or the export."]


def bed_of(meta: dict) -> list:
    b = ((meta.get("base") or {}).get("plate") or {}).get("bed_mm") or []
    return [float(x) for x in b[:3]] + [220.0, 220.0, 250.0][len(b[:3]):] if b else [220.0, 220.0, 250.0]


def _plate_bed(params: dict) -> dict:
    """A plate step may name the user's selected printer: its catalog bed is used (and saved with the step)."""
    pid = params.pop("printer_id", None)
    if pid:
        from . import print_setup as ps
        try:
            params = {**params, "bed": list(ps.bed_of(ps.resolve(str(pid))[0]))}
        except ps.SetupError as e:
            raise meshedit.OpError(str(e))
    return params


def split_plate(bid: str, owner_sid: str, visibility: str, params: dict, *, auto_delete_oldest: bool = False) -> dict:
    """Auto-arrange, then move every object that didn't fit onto a NEW plate project (arranged on its own).
    The current plate keeps the rest (one "delete" step, so Undo brings them back). Caller holds no locks."""
    from ..core import plate
    p = _plate_bed({k: v for k, v in params.items() if k in ("printer_id", "bed", "gap", "rotate")})
    rep = add_op(bid, "plate", {**p, "action": "arrange", "sel": []})
    over = (rep.get("arrange") or {}).get("overflow") or []
    if not over:
        return {"split": False, "message": "Everything already fits on this plate.", "new_project": None}
    meta = store.get(bid)
    m = mesh_at(bid, meta)
    objs, L = plate.normalise(m, layout_at(meta, m))
    if len(over) >= len(objs):
        return {"split": False, "message": "None of the objects fit this bed on their own; scale them down instead.", "new_project": None}
    moved = [objs[i] for i in over]
    combo, _ = plate.combine(moved, list(range(len(moved))), [False] * len(moved))
    bed = p.get("bed") or bed_of(meta)
    with store.lock:
        store.reserve(owner_sid, auto_delete_oldest)
        new = create(owner_sid, visibility, title=(meta.get("title") or "Plate")[:50] + " (plate 2)",
                     base={"type": "plate", "parts": len(moved), "units": "mm", "plate": {"bed_mm": list(bed)}},
                     original=combo.export(file_type="stl"), original_ext="stl", mesh=combo,
                     beginner=meta.get("beginner", True), warnings=[f"Split from another plate: {len(moved)} object(s) that didn't fit."])
    add_op(new["id"], "plate", {**p, "action": "arrange", "sel": []})
    add_op(bid, "plate", {"action": "delete", "sel": over, "bed": bed})
    add_op(bid, "plate", {**p, "action": "arrange", "sel": []})
    return {"split": True, "new_project": new["id"], "moved": len(moved),
            "message": f"Moved {len(moved)} object{'s' * (len(moved) > 1)} to a new plate. Open it from your history to slice it."}


def layout_at(meta: dict, m: trimesh.Trimesh, head: int | None = None) -> dict:
    """The plate layout (objects / groups / hidden) at a step; stale or missing -> connected components."""
    from ..core import plate
    head = meta["head"] if head is None else head
    L = (meta.get("plate_layouts") or {}).get(str(head))
    return L if plate.valid(L, m) else None


def printable_at(bid: str, meta: dict) -> trimesh.Trimesh:
    """What gets exported and sliced: the current mesh minus hidden plate objects."""
    from ..core import plate
    m = mesh_at(bid, meta)
    L = (meta.get("plate_layouts") or {}).get(str(meta["head"]))
    return plate.printable(m, L) if L else m


def add_op(bid: str, op: str, params: dict) -> dict:
    params = check_op_text(op, params)
    for _attempt in range(2):
        prepared = copy.deepcopy(params)
        with _lock:
            meta = _migrate_body_refs(bid, store.get(bid))
            head = int(meta["head"])
            rev = geometry_revision(meta, head)
        cur = mesh_at(bid, store.get(bid))
        with _lock:
            meta = store.get(bid)
            if int(meta["head"]) != head or geometry_revision(meta, head) != rev:
                continue
            title = meta.get("title") or "Model"
            if meta.get("appearance"):
                bound_appearance = cadops.bind_appearance(meta["appearance"], cur)
            else:
                bound_appearance = None
            prepared, _bound = cadops.bind_legacy_body_refs(cur, op, prepared)
            if op == "plate":                                 # the server's own layout + bed, never the client's
                prepared = {**prepared, "layout": layout_at(meta, cur)}
                prepared = _plate_bed(prepared)
                prepared.setdefault("bed", bed_of(meta))
            dims = copy.deepcopy(meta.get("dims"))
            before_faces = len(cur.faces)
            work = cur.copy()
        # The heavy step (and its memory-capped process) stays outside the project lock.
        new, rep = _apply({"dims": dims}, work, {"op": op, "params": prepared})
        persist = rep.pop("_persist", None) if isinstance(rep, dict) else None
        if persist:
            prepared = {**prepared, **persist}
        stats = _stats(new, title)
        with _lock:
            meta = store.get(bid)
            if int(meta["head"]) != head or geometry_revision(meta, head) != rev:
                continue
            if bound_appearance is not None:
                meta["appearance"] = bound_appearance
            ops = meta["ops"][:meta["head"]]                  # drop the redo tail
            ops.append({"op": op, "params": prepared, "label": meshedit.label(op, prepared)})
            meta["ops"] = ops
            meta["head"] = len(ops)
            for h in [h for h in list(_STATES.get(bid, {})) if h >= meta["head"]]:
                _STATES[bid].pop(h, None)
            meta["stats"] = stats
            meta["last_report"] = rep
            pl = {k: v for k, v in (meta.get("plate_layouts") or {}).items() if int(k) < meta["head"]}
            if op == "plate" and isinstance(rep, dict) and rep.get("layout"):
                pl[str(meta["head"])] = rep["layout"]
            elif pl.get(str(meta["head"] - 1)) and len(new.faces) == before_faces:   # move/rotate/scale keep the objects
                pl[str(meta["head"])] = pl[str(meta["head"] - 1)]
            meta["plate_layouts"] = pl
            _cache_put(bid, meta["head"], new, meta)
            store.save(meta)
            store.cache.pop(bid, None)
        return rep
    raise meshedit.OpError("That step was not applied because the model changed. Try it again.")


def _rewrite(bid: str, i: int, new_op: dict | None) -> dict:
    """Edit (new_op) or delete (None) step i (1-based), then replay every later step on top. All-or-nothing: if any step
    fails on the new result, nothing is stored. The history ends at the last step afterwards (the redo tail is dropped)."""
    with _lock:
        # Migrate index references against the saved history before this edit changes an earlier step.
        meta = _migrate_body_refs(bid, store.get(bid))
        ops = meta["ops"][:meta["head"]]
        if not 1 <= i <= len(ops):
            raise meshedit.OpError("no such step")
        if any(o["op"] == "plate" for o in ops[i - 1:]):
            raise meshedit.OpError("Steps from the plate editor (arrange/merge/etc.) and the steps before them can't be edited or deleted; undo to before them first.")
        if meta.get("appearance"):
            meta["appearance"] = cadops.bind_appearance(meta["appearance"], mesh_at(bid, meta))
        new_ops = ops[:i - 1] + ([new_op] if new_op else []) + ops[i:]
        m = mesh_at(bid, meta, head=i - 1)
        for k, o in enumerate(new_ops[i - 1:], start=i):
            if not _replay_safe(o):
                raise meshedit.OpError(f"Step {k} contains text that is not allowed.")
            try:
                m, _ = _apply(meta, m, o)
            except meshedit.OpError as e:
                raise meshedit.OpError(f"Step {k} ({o['label']}) would fail after this change: {e}")
        meta["ops"] = new_ops
        meta["head"] = len(new_ops)
        meta["plate_layouts"] = {k: v for k, v in (meta.get("plate_layouts") or {}).items() if int(k) < i}
        _STATES[bid] = OrderedDict()
        _cache_put(bid, meta["head"], m, meta)
        meta["stats"] = _stats(m, meta["title"])
        meta["last_report"] = None
        # Freshness is geometry_revision() (the steps, dimensions, plate and skipped text),
        # not the step index. A rewritten step changes that identity even when head stays put.
        store.save(meta)
        store.cache.pop(bid, None)
    return {"rewritten": i, "steps": len(new_ops)}


def edit_step(bid: str, i: int, params: dict) -> dict:
    meta = store.get(bid)
    if not 1 <= i <= meta["head"]:
        raise meshedit.OpError("no such step")
    o = meta["ops"][i - 1]
    params = check_op_text(o["op"], params)
    # a step may carry values resolved once and persisted with it (sculpt's flatten
    # plane). If the caller edits the step WITHOUT re-supplying them, the STORED ones
    # survive — re-deriving them after an earlier step changed would silently move the
    # target. (The _rewrite below replays with the merged params, so validation holds.)
    stored = o.get("params") or {}
    if o["op"] == "sculpt" and "plane" in stored and "plane" not in params:
        params = {**params, "plane": stored["plane"]}
    _, rep = _apply(meta, mesh_at(bid, meta, head=i - 1), {"op": o["op"], "params": params})   # validate this step alone first (clear error)
    # merge any once-resolved values the op asks to persist (sculpt's derived flatten
    # plane) — same pattern as add_op, so the SAVED step carries them and replays
    # reuse them instead of re-deriving (e.g. zero-strength -> positive-strength edit).
    persist = rep.pop("_persist", None) if isinstance(rep, dict) else None
    if persist:
        params = {**params, **persist}
    new = {"op": o["op"], "params": params, "label": meshedit.label(o["op"], params)}
    if o.get("name"):
        new["name"] = o["name"]                       # a user-renamed step keeps its name
    return _rewrite(bid, i, new)


def rename_step(bid: str, i: int, name: str) -> dict:
    """Give step i (1-based) a user name shown in the History panel ('' restores the automatic label)."""
    with _lock:
        meta = store.get(bid)
        if not 1 <= i <= len(meta["ops"]):
            raise meshedit.OpError("no such step")
        if name:
            meta["ops"][i - 1]["name"] = name
        else:
            meta["ops"][i - 1].pop("name", None)
        store.save(meta)
        store.cache.pop(bid, None)
    return {"renamed": i}


def set_dims(bid: str, dims: dict) -> dict:
    """Replace the project's named dimensions and replay every step with them. All-or-nothing; keeps the undo/redo position."""
    dims = dimmod.check_dims(dims)
    with _lock:
        meta = store.get(bid)
        old = meta.get("dims") or {}
        ops = meta["ops"]
        needed = set()
        for o in ops:
            if o["op"] not in dimmod.SKIP_OPS:
                needed |= dimmod.used_names(o["params"])
        missing = sorted(needed - set(dims))
        if missing:
            raise meshedit.OpError("Still used by a step: " + ", ".join("$" + n for n in missing))
        trial = {**meta, "dims": dims}
        m = _base(bid, trial)
        for k, o in enumerate(ops, start=1):
            if not _replay_safe(o):
                continue
            try:
                m, _ = _apply(trial, m, o)
            except meshedit.OpError as e:
                raise meshedit.OpError(f"Step {k} ({o['label']}) would fail with these values: {e}")
        meta["dims"] = dims
        _STATES[bid] = OrderedDict()
        meta["stats"] = _stats(mesh_at(bid, meta), meta["title"])
        meta["last_report"] = None
        store.save(meta)
        store.cache.pop(bid, None)
    return {"dims": dims, "changed": dims != old}


def delete_step(bid: str, i: int) -> dict:
    return _rewrite(bid, i, None)


def goto(bid: str, head: int):
    with _lock:
        meta = store.get(bid)
        if not 0 <= head <= len(meta["ops"]):
            raise meshedit.OpError("no such step")
        rev = geometry_revision(meta, head)
        title = meta.get("title") or "Model"
    m = mesh_at(bid, store.get(bid), head)
    stats = _stats(m, title)
    with _lock:
        meta = store.get(bid)
        if not 0 <= head <= len(meta["ops"]) or geometry_revision(meta, head) != rev:
            raise meshedit.OpError("That step was not applied because the model changed. Try it again.")
        meta["last_report"] = None
        meta["head"] = head
        meta["stats"] = stats
        store.save(meta)
        store.cache.pop(bid, None)


def undo(bid):
    meta = store.get(bid)
    if meta["head"] <= 0:
        raise meshedit.OpError("nothing to undo")
    goto(bid, meta["head"] - 1)


def redo(bid):
    meta = store.get(bid)
    if meta["head"] >= len(meta["ops"]):
        raise meshedit.OpError("nothing to redo")
    goto(bid, meta["head"] + 1)


def capabilities() -> dict:
    return {"boolean": meshedit.have_boolean(), "simplify": meshedit.have_simplify(), "hollow": meshedit.have_hollow(),
            "text": True, "fonts": meshedit.list_fonts(), "max_upload_mb": MAX_UPLOAD_EDIT // 2**20,
            "formats": sorted(meshedit.ALLOWED), "image_formats": sorted(meshedit.IMAGE_EXT), "units": list(meshedit.UNIT_MM)}


def _parts_public(meta: dict, n_faces: int) -> list[dict]:
    title = meta.get("title") or "Model"
    return meshparts.public(meshparts.resolve(meta.get("parts"), n_faces, title))


def save_parts(bid: str, parts: list[dict]) -> list[dict]:
    """Replace the part list for the current mesh. The mesh itself is unchanged.

    A list built against an older mesh (a step changed the triangles, or the ids are from
    before that step) is not an error. The parts that still match this mesh stay.
    """
    with _lock:
        meta = store.get(bid)
        m = mesh_at(bid, meta)
        title = meta.get("title") or "Model"
        stored = meshparts.validate(parts, len(m.faces))
        if not stored:
            return meshparts.resolve(meta.get("parts"), len(m.faces), title)
        meta = store.get(bid)
        meta["parts"] = stored
        layout = meshparts.plate_layout(stored, len(m.faces))
        if layout:
            layouts = dict(meta.get("plate_layouts") or {})
            layouts[str(meta.get("head") or 0)] = layout
            meta["plate_layouts"] = layouts
        store.save(meta)
        store.cache.pop(bid, None)
    return stored


def update_part_slots(bid: str, body: dict) -> tuple[list[dict], list[dict]]:
    """Apply a slot action to the parts on the mesh as it is right now.

    The whole read-modify-write holds the project lock. A step that lands between
    reading the parts and saving them used to fail with "Those parts don't match this model."
    Ids the client still has from before that step are ignored.
    """
    action = body.get("action") or "prepare"
    with _lock:
        meta = store.get(bid)
        m = mesh_at(bid, meta)
        title = meta.get("title") or "Model"
        n_faces = len(m.faces)
        stored_ok = meshparts.validate(meta.get("parts"), n_faces)
        current = stored_ok or meshparts.resolve(meta.get("parts"), n_faces, title)
        raw_ids = body.get("ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        known = {p.get("id") for p in current}
        ids = [i for i in raw_ids if i in known]
        if action in ("assign", "reset") and raw_ids and not ids:
            updated, flags = current, []
        else:
            count = partslots.clamp_count(body.get("slot_count", 1))
            updated, flags = partslots.apply(
                current, action, ids=ids, slot=body.get("slot"), slot_count=count,
                colours=partslots.parse_colours(body.get("colours")),
            )
        healed = meshparts.validate(updated, n_faces) or current
        if stored_ok and partslots.same(current, healed):
            return current, flags
        meta = store.get(bid)
        meta["parts"] = healed
        layout = meshparts.plate_layout(healed, n_faces)
        if layout:
            layouts = dict(meta.get("plate_layouts") or {})
            layouts[str(meta.get("head") or 0)] = layout
            meta["plate_layouts"] = layouts
        store.save(meta)
        store.cache.pop(bid, None)
    return healed, flags


def step_view(meta: dict, mesh: trimesh.Trimesh) -> dict:
    """History fields for the CAD scene. Does not rebuild export files or the editor preview."""
    ops = [{"i": i + 1, "op": o["op"], "label": o["label"], "name": o.get("name") or "",
            "params": {k: v for k, v in (o.get("params") or {}).items() if k != "layout" and isinstance(v, (str, int, float, bool, dict, list, type(None)))},
            "editable": o["op"] not in ("plate", "import")} for i, o in enumerate(meta.get("ops") or [])]
    rev = geometry_revision(meta)
    stored = meta.get("analysis") if meta.get("analysis_rev") == rev else None
    analysis = stored if isinstance(stored, dict) else meshedit.analyze(mesh)
    head = int(meta.get("head") or 0)
    return {"ops": ops, "head": head, "can_undo": head > 0,
            "can_redo": head < len(meta.get("ops") or []), "analysis": analysis}


def preview(m: trimesh.Trimesh) -> dict:
    v, f, dec = m.vertices, m.faces, False
    if len(f) > MAX_PREVIEW_FACES:
        dec = True
        try:
            import fast_simplification
            v, f = fast_simplification.simplify(m.vertices.astype(np.float32), m.faces.astype(np.int32),
                                                target_count=MAX_PREVIEW_FACES)
        except Exception:
            f = f[np.linspace(0, len(f) - 1, MAX_PREVIEW_FACES).astype(int)]
    return {"decimated": dec, "bodies": [{"name": "model", "color": None,
            "positions": base64.b64encode(np.asarray(v).astype("<f4").tobytes()).decode(),
            "indices": base64.b64encode(np.asarray(f).astype("<u4").tobytes()).decode()}]}


def preview_objects(m: trimesh.Trimesh, layout: dict, colors=None, names=None, part_ids=None) -> dict:
    """One preview body per plate object (so the viewer can select / highlight each)."""
    from ..core import plate as _plate
    objs = _plate.objects(m, layout)
    total = max(1, len(m.faces))
    bodies, dec = [], False
    for i, o in enumerate(objs):
        f = o.faces
        cap = max(200, int(MAX_PREVIEW_FACES * len(f) / total))
        if len(f) > cap:
            dec = True
            f = f[np.linspace(0, len(f) - 1, cap).astype(int)]
        color = colors[i] if colors and i < len(colors) else None
        name = names[i] if names and i < len(names) and names[i] else f"Object {i + 1}"
        part_id = part_ids[i] if part_ids and i < len(part_ids) else None
        bodies.append({"name": name, "color": color, "object": i, "part": part_id,
                       "positions": base64.b64encode(np.asarray(o.vertices).astype("<f4").tobytes()).decode(),
                       "indices": base64.b64encode(np.asarray(f).astype("<u4").tobytes()).decode()})
    return {"decimated": dec, "bodies": bodies}


def preview_parts(m: trimesh.Trimesh, parts: list[dict]) -> dict:
    """One coloured body per part when the plate is still a single object."""
    bodies = []
    for part in parts:
        sub = meshparts.submesh(m, part)
        bodies.append({
            "name": part["name"], "color": partslots.display_color(part), "object": 0,
            "part": part["id"],
            "positions": base64.b64encode(np.asarray(sub.vertices).astype("<f4").tobytes()).decode(),
            "indices": base64.b64encode(np.asarray(sub.faces).astype("<u4").tobytes()).decode(),
        })
    return {"decimated": False, "bodies": bodies}


_GATE_PREFIX = "Fix the model before export: "
_REPLAY_PREFIX = "Left out of the model: "


def quality_from_analysis(a: dict) -> dict:
    """Print-ready gate from an analysis dict. Does not scan the mesh again."""
    issues = []
    if not a.get("watertight"):
        issues.append("not watertight")
    if a.get("boundary_edges"):
        issues.append(f"{a['boundary_edges']} open boundary edge(s)")
    if a.get("nonmanifold_edges"):
        issues.append(f"{a['nonmanifold_edges']} non-manifold edge(s)")
    if (a.get("triangles") or 0) < 4:
        issues.append("too few triangles")
    size = a.get("size_mm") or [0, 0, 0]
    max_dim = max(size, default=0.0)
    if max_dim <= 0 or not np.isfinite(max_dim):
        issues.append("invalid geometry")
    elif max_dim > 1000:
        issues.append("model is too large for a practical print")
    if a.get("watertight") and (a.get("volume_mm3") or 0) <= 0:
        issues.append("zero or negative volume")
    return {
        "ok": not issues,
        "issues": issues,
        "message": "Closed mesh. You can export the geometry. Slice it before printing." if not issues else _GATE_PREFIX + "; ".join(issues) + ". Run Repair or simplify the mesh, then validate again.",
        "watertight": a.get("watertight"),
        "size_mm": size,
        "triangles": a.get("triangles"),
    }


def export_quality(m: trimesh.Trimesh) -> dict:
    """Fast print-ready gate before export: refuse silent bad geometry and explain the fix."""
    return quality_from_analysis(meshedit.analyze(m))


def support_paint_view(meta: dict) -> dict:
    """Strokes for this exact shape. A move, scale, or other step hides them until undo returns that shape."""
    rec = meta.get("support_paint") if isinstance(meta.get("support_paint"), dict) else {}
    strokes = rec.get("strokes") if isinstance(rec.get("strokes"), list) else []
    fresh = rec.get("rev") == geometry_revision(meta) and bool(strokes)
    return {"strokes": strokes if fresh else [], "stale": bool(strokes) and not fresh}


def save_support_paint(bid: str, strokes: list[dict]) -> dict:
    """Store paint against the current geometry. Does not change the mesh."""
    with store.lock:
        meta = store.get(bid)
        if strokes:
            meta["support_paint"] = {"rev": geometry_revision(meta), "strokes": strokes}
        else:
            meta.pop("support_paint", None)
        store.save(meta)
    return support_paint_view(meta)


def payload(bid: str, report=None, *, include_preview: bool = True) -> dict:
    from ..api.builds import summary
    meta = store.get(bid)
    if meta.get("header_triangles"):
        body = quick_payload(meta, load_preview=include_preview)
        if report is not None:
            body["report"] = report
        return body
    m = mesh_at(bid, meta)
    ensure_exports(bid)
    meta = store.get(bid)
    ops = [{"i": i + 1, "op": o["op"], "label": o["label"], "name": o.get("name") or "",
             "params": {k: v for k, v in (o.get("params") or {}).items() if k != "layout" and isinstance(v, (str, int, float, bool, dict, list, type(None)))},
             "editable": o["op"] not in ("plate", "import")} for i, o in enumerate(meta["ops"])]
    from ..core import plate as _plate
    L = layout_at(meta, m)
    pinfo = _plate.describe(m, L, tuple(bed_of(meta)))
    parts = meshparts.resolve(meta.get("parts"), len(m.faces), meta.get("title") or "Model")
    if len(pinfo["objects"]) > 1:
        matched = meshparts.labels_for_counts(parts, pinfo["layout"]["counts"], len(m.faces))
        if matched:
            prev = preview_objects(
                m, pinfo["layout"], colors=[partslots.display_color(p) for p in matched],
                names=[p["name"] for p in matched], part_ids=[p["id"] for p in matched])
        else:
            prev = preview_objects(m, pinfo["layout"])
    elif len(parts) > 1 and len(m.faces) <= MAX_PREVIEW_FACES:
        prev = preview_parts(m, parts)
    else:
        prev = preview(m)
        if len(parts) == 1 and prev.get("bodies"):
            prev["bodies"][0]["color"] = partslots.display_color(parts[0])
            prev["bodies"][0]["part"] = parts[0]["id"]
            prev["bodies"][0]["name"] = parts[0]["name"]
    analysis = meshedit.analyze(m)
    quality = export_quality(m)
    return {**summary(meta), "params": {}, "auto_notes": [], "info": {}, "preview": prev, "plate": pinfo,
            "dims": meta.get("dims") or {}, "ops": ops, "head": meta["head"], "can_undo": meta["head"] > 0, "can_redo": meta["head"] < len(meta["ops"]),
            "analysis": analysis, "quality_gate": quality, "base": meta["base"], "warnings": meta.get("warnings", []),
            "report": report if report is not None else meta.get("last_report"),
            "support_paint": support_paint_view(meta),
            "original": f"/api/edit/{bid}/original", "capabilities": capabilities(),
            "parts": meshparts.public(parts)}
