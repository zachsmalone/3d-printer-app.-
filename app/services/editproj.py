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
            if not _replay_safe(o):
                continue
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
    # the object name inside exported OBJ/3MF is deliberately generic: the project title (user text) is never written into files
    return Model(bodies=[Body("model", m.vertices.copy(), m.faces.copy())], mode="edit")


def model(bid: str) -> Model:
    meta = store.get(bid)
    return as_model(printable_at(bid, meta), meta["title"])


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
        m = printable_at(bid, meta)
        quality = export_quality(m)
        meta["quality_gate"] = quality
        if not quality["ok"]:
            meta["warnings"] = list(dict.fromkeys((meta.get("warnings") or []) + [quality["message"]]))
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


TEXT_MAX = 60       # characters for the emboss/deboss text (same as meshedit.op_text)


def check_op_text(op: str, params: dict) -> dict:
    """Free text that ends up in a model is gated like any other text others can read: length cap first, then the
    language + personal-info filter. Raises safety.ChatBlocked (nothing is stored). Returns the params with text trimmed."""
    from ..community import safety
    out = dict(params)
    for k, v in params.items():
        if isinstance(v, str) and len(v) > 200:
            raise ValueError(f"'{k}' is too long.")
        if op == "text" and isinstance(v, (dict, list)):
            raise ValueError(f"'{k}' must be a simple value.")
    if op == "plate" and params.get("action") == "text":     # plate editor text on one object: same cap + filter
        for k in ("text", "font", "mode", "face"):
            if isinstance(params.get(k), (dict, list)):
                raise ValueError(f"'{k}' must be a simple value.")
    if op == "text" or (op == "plate" and params.get("action") == "text"):
        txt = params.get("text", "")
        if not isinstance(txt, str):
            raise ValueError("Text must be text.")
        if len(txt) > TEXT_MAX:
            raise ValueError(f"Text must be 1-{TEXT_MAX} characters.")
        out["text"] = safety.check(txt, "edit:text")
    return out


def _replay_safe(o: dict) -> bool:
    """Ops stored before the filter existed (or by an older word list) are re-checked when a project is replayed:
    a text step that no longer passes is skipped instead of being rendered into the mesh and its exports."""
    if o.get("op") != "text" and not (o.get("op") == "plate" and (o.get("params") or {}).get("action") == "text"):
        return True
    from ..community import safety
    t = o.get("params", {}).get("text", "")
    return isinstance(t, str) and len(t) <= TEXT_MAX and not safety.scan(t)


def bed_of(meta: dict) -> list:
    b = ((meta.get("base") or {}).get("plate") or {}).get("bed_mm") or []
    return [float(x) for x in b[:3]] + [220.0, 220.0, 250.0][len(b[:3]):] if b else [220.0, 220.0, 250.0]


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
    with _lock:
        meta = store.get(bid)
        cur = mesh_at(bid, meta)
        if op == "plate":                                 # the server's own layout + bed, never the client's
            params = {**params, "layout": layout_at(meta, cur)}
            params.setdefault("bed", bed_of(meta))
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
        pl = {k: v for k, v in (meta.get("plate_layouts") or {}).items() if int(k) < meta["head"]}
        if op == "plate" and isinstance(rep, dict) and rep.get("layout"):
            pl[str(meta["head"])] = rep["layout"]
        elif pl.get(str(meta["head"] - 1)) and len(new.faces) == len(cur.faces):   # move/rotate/scale keep the objects
            pl[str(meta["head"])] = pl[str(meta["head"] - 1)]
        meta["plate_layouts"] = pl
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


def preview_objects(m: trimesh.Trimesh, layout: dict) -> dict:
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
        bodies.append({"name": f"Object {i + 1}", "color": None, "object": i,
                       "positions": base64.b64encode(np.asarray(o.vertices).astype("<f4").tobytes()).decode(),
                       "indices": base64.b64encode(np.asarray(f).astype("<u4").tobytes()).decode()})
    return {"decimated": dec, "bodies": bodies}


def export_quality(m: trimesh.Trimesh) -> dict:
    """Fast print-ready gate before export: refuse silent bad geometry and explain the fix."""
    a = meshedit.analyze(m)
    issues = []
    if not a["watertight"]:
        issues.append("not watertight")
    if a["boundary_edges"] > 0:
        issues.append(f"{a['boundary_edges']} open boundary edge(s)")
    if a["nonmanifold_edges"] > 0:
        issues.append(f"{a['nonmanifold_edges']} non-manifold edge(s)")
    if a["triangles"] < 4:
        issues.append("too few triangles")
    max_dim = max(a["size_mm"], default=0.0)
    if max_dim <= 0 or not np.isfinite(max_dim):
        issues.append("invalid geometry")
    elif max_dim > 1000:
        issues.append("model is too large for a practical print")
    if a["volume_mm3"] <= 0 and a["watertight"]:
        issues.append("zero or negative volume")
    return {
        "ok": not issues,
        "issues": issues,
        "message": "Model is print-safe to export." if not issues else "Fix the model before export: " + "; ".join(issues) + ". Run Repair or simplify the mesh, then validate again.",
        "watertight": a["watertight"],
        "size_mm": a["size_mm"],
        "triangles": a["triangles"],
    }


def payload(bid: str, report=None) -> dict:
    from ..api.builds import summary
    meta = store.get(bid)
    m = mesh_at(bid, meta)
    ensure_exports(bid)
    meta = store.get(bid)
    ops = [{"i": i + 1, "op": o["op"], "label": o["label"]} for i, o in enumerate(meta["ops"])]
    from ..core import plate as _plate
    L = layout_at(meta, m)
    pinfo = _plate.describe(m, L, tuple(bed_of(meta)))
    prev = preview_objects(m, pinfo["layout"]) if len(pinfo["objects"]) > 1 else preview(m)
    analysis = meshedit.analyze(m)
    quality = export_quality(m)
    return {**summary(meta), "params": {}, "auto_notes": [], "info": {}, "preview": prev, "plate": pinfo,
            "ops": ops, "head": meta["head"], "can_undo": meta["head"] > 0, "can_redo": meta["head"] < len(meta["ops"]),
            "analysis": analysis, "quality_gate": quality, "base": meta["base"], "warnings": meta.get("warnings", []),
            "report": report if report is not None else meta.get("last_report"),
            "original": f"/api/edit/{bid}/original", "capabilities": capabilities()}
