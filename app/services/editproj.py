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
import threading
import uuid
from collections import OrderedDict

import numpy as np
import trimesh
from PIL import Image

from ..core import exporters, geometry, meshedit, meshthumb
from ..core.geometry import Body, Model
from .history import store

_lock = threading.RLock()
_BASES: dict[str, trimesh.Trimesh] = {}
_STATES: dict[str, OrderedDict] = {}
MAX_PREVIEW_FACES = 150_000
MAX_UPLOAD_EDIT = 50 * 1024 * 1024


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


def mesh_at(bid: str, meta: dict | None = None, head: int | None = None) -> trimesh.Trimesh:
    meta = meta or store.get(bid)
    head = meta["head"] if head is None else head
    with _lock:
        cache = _STATES.setdefault(bid, OrderedDict())
        if head in cache:
            cache.move_to_end(head)
            return cache[head]
        # resume from the nearest cached earlier state
        start = max([h for h in cache if h <= head], default=None)
        m = cache[start] if start is not None else _base(bid, meta)
        for k in range(start or 0, head):
            o = meta["ops"][k]
            m, _ = meshedit.apply(m, o["op"], o["params"])
        cache[head] = m
        while len(cache) > 6:
            cache.popitem(last=False)
        return m


def _stats(m: trimesh.Trimesh, title: str) -> dict:
    a = meshedit.analyze(m)
    return {"bodies": [{"name": title, "triangles": a["triangles"], "watertight": a["watertight"], "volume_mm3": a["volume_mm3"]}],
            "watertight": a["watertight"], "size_mm": a["size_mm"], "triangles": a["triangles"]}


def as_model(m: trimesh.Trimesh, title: str) -> Model:
    return Model(bodies=[Body(title[:40] or "model", m.vertices.copy(), m.faces.copy())], mode="edit")


def model(bid: str) -> Model:
    meta = store.get(bid)
    return as_model(mesh_at(bid, meta), meta["title"])


def ensure_exports(bid: str):
    """(Re)write model.stl/obj/3mf + thumb.png when they are stale. No-op for photo builds."""
    try:
        meta = store.get(bid)
    except KeyError:
        return
    if meta.get("kind") != "edit":
        return
    d = store.dir(bid)
    if meta.get("exports_head") == meta["head"] and all((d / f"model.{e}").exists() for e in exporters.WRITERS):
        return
    with _lock:
        meta = store.get(bid)
        m = mesh_at(bid, meta)
        mdl = as_model(m, meta["title"])
        for ext, fn in exporters.WRITERS.items():
            (d / f"model.{ext}").write_bytes(fn(mdl))
        (d / "model.gcode").unlink(missing_ok=True)       # stale slice
        Image.fromarray(meshthumb.render(m.vertices, m.faces)).save(d / "thumb.png")
        meta["exports_head"] = meta["head"]
        store.save(meta)


# ---------------------------------------------------------------- creation
def create(owner_sid: str, visibility: str, *, title: str, base: dict, original: bytes, original_ext: str,
           mesh: trimesh.Trimesh, beginner: bool, warnings: list[str], import_scale: float = 1.0,
           import_units: str = "mm", source_image: tuple[bytes, str] | None = None) -> dict:
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


# ---------------------------------------------------------------- editing
def _commit(bid: str, meta: dict, head: int):
    meta["head"] = head
    m = mesh_at(bid, meta)
    meta["stats"] = _stats(m, meta["title"])
    store.save(meta)
    store.cache.pop(bid, None)


def add_op(bid: str, op: str, params: dict) -> dict:
    with _lock:
        meta = store.get(bid)
        cur = mesh_at(bid, meta)
        new, rep = meshedit.apply(cur, op, params)       # raises OpError → nothing is stored
        ops = meta["ops"][:meta["head"]]                  # drop the redo tail
        ops.append({"op": op, "params": params, "label": meshedit.label(op, params)})
        meta["ops"] = ops
        meta["head"] = len(ops)
        for h in [h for h in _STATES.get(bid, {}) if h > meta["head"] - 1]:
            _STATES[bid].pop(h, None)
        _STATES.setdefault(bid, OrderedDict())[meta["head"]] = new
        meta["stats"] = _stats(new, meta["title"])
        meta["last_report"] = rep
        store.save(meta)
        store.cache.pop(bid, None)
    return rep


def goto(bid: str, head: int):
    with _lock:
        meta = store.get(bid)
        if not 0 <= head <= len(meta["ops"]):
            raise meshedit.OpError("no such step")
        meta["last_report"] = None
        _commit(bid, meta, head)


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
            "text": True, "fonts": list(meshedit.FONTS), "max_upload_mb": MAX_UPLOAD_EDIT // 2**20,
            "formats": sorted(meshedit.ALLOWED), "image_formats": sorted(meshedit.IMAGE_EXT), "units": list(meshedit.UNIT_MM)}


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


def payload(bid: str, report=None) -> dict:
    from ..api.builds import summary
    meta = store.get(bid)
    m = mesh_at(bid, meta)
    ensure_exports(bid)
    meta = store.get(bid)
    ops = [{"i": i + 1, "op": o["op"], "label": o["label"]} for i, o in enumerate(meta["ops"])]
    return {**summary(meta), "params": {}, "auto_notes": [], "info": {}, "preview": preview(m),
            "ops": ops, "head": meta["head"], "can_undo": meta["head"] > 0, "can_redo": meta["head"] < len(meta["ops"]),
            "analysis": meshedit.analyze(m), "base": meta["base"], "warnings": meta.get("warnings", []),
            "report": report if report is not None else meta.get("last_report"),
            "original": f"/api/edit/{bid}/original", "capabilities": capabilities()}
