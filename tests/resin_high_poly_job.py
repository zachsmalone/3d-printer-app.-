"""Worker for the high-poly TorchC0 prepare test.

Lives outside the test module so the memory-capped child can import it.
`procjob` re-imports `function.__module__`, and pytest loads the test file
under a name that is not importable in that child.
"""
import gc
import resource
import time

import numpy as np
import trimesh

from app.core import meshedit, resin

# uv_sphere(count=[250, 700]) is 694_400 triangles. Production failed on 694_838.
_COUNT = (250, 700)
_LIFT = resin.DEFAULT_BASE_LIFT_MM + resin.DEFAULT_RAFT_MM


def _relief_mask(nu=380, nv=460, base_mm=2.8, bosses=True):
    """Watertight relief shell, about 130 x 165 mm, one connected solid.

    The sheet is thinner than two hollow walls, so it stays solid. Bosses are
    thick enough to leave separate cavities. `bosses=False` is the thin mask
    that should be returned solid.
    """
    u = np.linspace(-1.0, 1.0, nu)
    v = np.linspace(-1.0, 1.0, nv)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    x = 65.0 * uu
    y = 82.5 * vv
    z = 18.0 * np.cos(uu * np.pi / 2.0) * np.cos(vv * np.pi / 2.0)
    # Low-frequency relief only. Tighter wrinkles sit inside one voxel and the
    # cavity then crosses the real surface.
    z = z + 0.40 * np.sin(x * 0.22) * np.cos(y * 0.18)
    thick = np.full(uu.shape, float(base_mm), dtype=np.float64)
    if bosses:
        for bx, by, bh, sx, sy in (
            (0.00, 0.12, 22.0, 0.16, 0.13),
            (-0.55, 0.50, 20.0, 0.15, 0.12),
            (0.55, 0.46, 20.0, 0.15, 0.12),
            (0.08, -0.50, 21.0, 0.16, 0.13),
            (-0.48, -0.18, 19.0, 0.14, 0.12),
        ):
            r2 = ((uu - bx) / sx) ** 2 + ((vv - by) / sy) ** 2
            thick = thick + bh * np.exp(-r2)
    points = np.stack([x, y, z], axis=-1)
    du = np.empty_like(points)
    dv = np.empty_like(points)
    du[1:-1] = points[2:] - points[:-2]
    du[0] = points[1] - points[0]
    du[-1] = points[-1] - points[-2]
    dv[:, 1:-1] = points[:, 2:] - points[:, :-2]
    dv[:, 0] = points[:, 1] - points[:, 0]
    dv[:, -1] = points[:, -1] - points[:, -2]
    normal = np.cross(du, dv)
    normal /= np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-12)
    if normal[nu // 2, nv // 2, 2] < 0.0:
        normal = -normal
    inner = points - normal * thick[..., None]

    def vid(i, j, side):
        return side * nu * nv + i * nv + j

    faces = []
    for i in range(nu - 1):
        i0 = i * nv
        i1 = (i + 1) * nv
        for j in range(nv - 1):
            a, b = i0 + j, i1 + j
            c, d = i1 + j + 1, i0 + j + 1
            faces.append((a, b, d))
            faces.append((b, c, d))
            shift = nu * nv
            faces.append((a + shift, d + shift, b + shift))
            faces.append((b + shift, d + shift, c + shift))
    # Stitch the rim so the sheet is one solid, not two nested shells.
    def rim(outer_loop, inner_loop):
        for k in range(len(outer_loop) - 1):
            a, b = outer_loop[k], outer_loop[k + 1]
            c, d = inner_loop[k + 1], inner_loop[k]
            faces.append((a, b, c))
            faces.append((a, c, d))
    rim([vid(0, j, 0) for j in range(nv)], [vid(0, j, 1) for j in range(nv)])
    rim([vid(nu - 1, j, 0) for j in range(nv - 1, -1, -1)], [vid(nu - 1, j, 1) for j in range(nv - 1, -1, -1)])
    rim([vid(i, 0, 0) for i in range(nu - 1, -1, -1)], [vid(i, 0, 1) for i in range(nu - 1, -1, -1)])
    rim([vid(i, nv - 1, 0) for i in range(nu)], [vid(i, nv - 1, 1) for i in range(nv)])
    mesh = trimesh.Trimesh(np.vstack([points.reshape(-1, 3), inner.reshape(-1, 3)]), np.asarray(faces, np.int64), process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _organic():
    mesh = trimesh.creation.uv_sphere(radius=1.0, count=list(_COUNT))
    mesh.apply_scale([65.0, 82.5, 36.5])
    verts = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    disp = 2.2 * np.sin(verts[:, 0] * 0.08) * np.cos(verts[:, 1] * 0.06) + 1.4 * np.sin(verts[:, 2] * 0.11)
    mesh.vertices = verts + normals * disp[:, None]
    return mesh


def _detailed():
    """Same size and triangle count as `_organic`, with sculpt-scale wrinkles.

    Full-resolution voxelization of this shell peaked near 3.7 GB. The smooth
    displacement above did not. The wrinkles are the stand-in for the Oni mask.
    """
    mesh = trimesh.creation.uv_sphere(radius=1.0, count=list(_COUNT))
    mesh.apply_scale([65.0, 82.5, 36.5])
    verts = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    disp = (
        1.6 * np.sin(x * 1.7) * np.cos(y * 1.3) * np.sin(z * 1.9)
        + 0.9 * np.sin(x * 4.2 + y * 3.1) * np.cos(z * 3.7)
        + 0.45 * np.sin(x * 8.5) * np.sin(y * 7.7 + z * 6.3)
        + 0.25 * np.cos(x * 14.0 + z * 11.0) * np.sin(y * 13.0)
    )
    mesh.vertices = verts + normals * disp[:, None]
    return mesh


def _pack(points):
    rounded = np.ascontiguousarray(np.round(np.asarray(points, dtype=np.float64), 3))
    return np.frombuffer(rounded.tobytes(), dtype=np.dtype((np.void, 24)))


def _kept_fraction(original, prepared):
    """Share of original vertices that still exist on the prepared mesh (0.001 mm)."""
    sample = _pack(original)
    have = np.sort(_pack(prepared))
    at = np.clip(np.searchsorted(have, sample), 0, len(have) - 1)
    return float(np.sum(have[at] == sample) / max(len(sample), 1))


def run_detail(kind):
    """Prepare the wrinkled shell. Hollow must keep the outer surface and a real drain."""
    if kind not in ("hollow", "both"):
        raise AssertionError(kind)
    opts = {
        "hollow": {"hollow": "true", "supports": "false", "tilt_deg": 0},
        "both": {"hollow": "true", "supports": "true", "tilt_deg": 0},
    }[kind]
    started = time.perf_counter()
    mesh = _detailed()
    faces_in = int(len(mesh.faces))
    if not mesh.is_watertight or len(mesh.split(only_watertight=False)) != 1:
        raise AssertionError(f"{kind}: mesh is not one watertight shell")
    if not 600_000 <= faces_in <= 800_000:
        raise AssertionError(f"{kind}: expected 600k-800k triangles, got {faces_in}")
    gc.collect()
    out, rep = resin.prepare(mesh, resin.settings(opts))
    seconds = time.perf_counter() - started
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    placed = resin.place_on_bed(mesh, 0.0, 0.0)
    supports_on = opts["supports"] == "true"
    shift = np.array([0.0, 0.0, _LIFT if supports_on else 0.0])
    kept = _kept_fraction(placed.vertices, out.vertices - shift)
    hol = rep.get("hollow") or {}
    sup = rep.get("support") or {}
    saved = float(hol.get("volume_saved_pct") or 0.0)
    wall = hol.get("thinnest_wall_mm")
    pitch = float(hol.get("resolution_mm") or 0.0)
    if saved <= 50.0 or hol.get("holes") != [2]:
        raise AssertionError(f"{kind}: hollow did not keep a drained cavity ({hol})")
    if wall is None or float(wall) < 2.0 - pitch:
        raise AssertionError(f"{kind}: wall {wall} mm is below 2 - {pitch}")
    if kept < 0.99:
        raise AssertionError(f"{kind}: outer surface was not kept ({kept:.4f})")
    if len(out.faces) < faces_in:
        raise AssertionError(f"{kind}: triangle count fell from {faces_in} to {len(out.faces)}")
    pillars = int(sup.get("supports") or 0)
    touch = None
    if supports_on:
        band = out.vertices[(out.vertices[:, 2] > 4.2) & (out.vertices[:, 2] < 5.95)]
        if len(band) < 30 or pillars < 80:
            raise AssertionError(f"{kind}: supports did not build ({pillars})")
        cell = 1.5
        model_cells = set(map(tuple, np.floor(placed.vertices[:, :2] / cell).astype(np.int32)))
        cols = np.unique(np.floor(band[:, :2] / cell).astype(np.int32), axis=0)
        step = max(1, len(cols) // 24)
        picked = cols[::step][:24]
        touch = sum(tuple(col) in model_cells for col in picked) / len(picked)
        if touch < 0.5:
            raise AssertionError(f"{kind}: pillars do not sit under the model ({touch:.2f})")
    else:
        # A sealed cavity is two shells. Each open drain is a line through the wall that
        # does not hit material on its way out or back into the void.
        axes = hol.get("drain_axes") or []
        if len(axes) < 2 or not out.is_watertight:
            raise AssertionError(f"{kind}: drain did not open the cavity (axes {len(axes)}, watertight {out.is_watertight})")
        for inner_pt, outer_pt in axes:
            if not meshedit._hole_is_open(np.asarray(out.vertices), np.asarray(out.faces), inner_pt, outer_pt):
                raise AssertionError(f"{kind}: drain axis is still blocked")
    # 180 s leaves margin under the 240 s prepare kill. The 2-core child is about a minute
    # on this mesh; a run near 240 s is the old single-core layer check coming back.
    if seconds > 180:
        raise AssertionError(f"{kind}: {seconds:.0f}s is not inside the 180s prepare budget")
    return {
        "seconds": round(seconds, 2),
        "rss_mb": round(rss_mb, 1),
        "faces_in": faces_in,
        "faces_out": int(len(out.faces)),
        "kept": round(kept, 4),
        "saved": round(saved, 1),
        "wall_mm": None if wall is None else round(float(wall), 2),
        "pitch_mm": round(pitch, 3),
        "holes": list(hol.get("holes") or []),
        "pillars": pillars,
        "touch": None if touch is None else round(touch, 3),
        "stages": hol.get("stages"),
    }


def run_case(kind):
    """One prepare. Returns timings and checks; not the mesh."""
    opts = {
        "supports": {"hollow": "false", "supports": "true", "tilt_deg": 0},
        "hollow": {"hollow": "true", "supports": "false", "tilt_deg": 0},
        "both": {"hollow": "true", "supports": "true", "tilt_deg": 0},
    }[kind]
    started = time.perf_counter()
    mesh = _organic()
    faces_in = int(len(mesh.faces))
    if not mesh.is_watertight or len(mesh.split(only_watertight=False)) != 1:
        raise AssertionError(f"{kind}: mesh is not one watertight shell")
    if not 600_000 <= faces_in <= 800_000:
        raise AssertionError(f"{kind}: expected 600k-800k triangles, got {faces_in}")
    # split() leaves a large graph on the mesh; free it before the capped prepare.
    gc.collect()
    out, rep = resin.prepare(mesh, resin.settings(opts))
    seconds = time.perf_counter() - started
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    placed = resin.place_on_bed(mesh, 0.0, 0.0)
    supports_on = opts["supports"] == "true"
    hollow_on = opts["hollow"] == "true"
    shift = np.array([0.0, 0.0, _LIFT if supports_on else 0.0])
    kept = _kept_fraction(placed.vertices[::12], out.vertices - shift)
    sup = rep.get("support") or {}
    hol = rep.get("hollow") or {}
    pillars = int(sup.get("supports") or 0)
    touch = None
    raft_span = None
    if supports_on:
        # Cylinder pillars only have vertices at their ends. The upper ring sits
        # tip_len (1.2 mm) under the contact, just below the lifted model (z >= 6).
        band = out.vertices[(out.vertices[:, 2] > 4.2) & (out.vertices[:, 2] < 5.95)]
        if len(band) < 30:
            raise AssertionError(f"{kind}: pillars did not reach up toward the model")
        # Same XY cell as a model vertex means the pillar stands under the surface.
        # A ray index of the full mesh is another rtree, which is what ran out of memory.
        cell = 1.5
        model_cells = set(map(tuple, np.floor(placed.vertices[:, :2] / cell).astype(np.int32)))
        cols = np.unique(np.floor(band[:, :2] / cell).astype(np.int32), axis=0)
        step = max(1, len(cols) // 24)
        picked = cols[::step][:24]
        touch = sum(tuple(col) in model_cells for col in picked) / len(picked)
        low = out.vertices[out.vertices[:, 2] < 0.35]
        raft_span = float(low[:, 0].max() - low[:, 0].min()) if len(low) else 0.0
        if pillars < 80:
            raise AssertionError(f"{kind}: expected real pillars, got {pillars}")
        if touch < 0.5:
            raise AssertionError(f"{kind}: pillars do not sit under the model ({touch:.2f})")
        if raft_span < 20.0 or abs(float(out.bounds[0][2])) > 1e-3:
            raise AssertionError(f"{kind}: raft missing (span {raft_span}, z0 {out.bounds[0][2]})")
        if not sup.get("overlapping"):
            raise AssertionError(f"{kind}: supports were fused, which rewrites the model")
    if hollow_on:
        saved = float(hol.get("volume_saved_pct") or 0.0)
        if saved < 40.0 or hol.get("holes") != [2]:
            raise AssertionError(f"{kind}: hollow did not keep a drained cavity ({hol})")
    if kept < 0.85:
        raise AssertionError(f"{kind}: outer surface was not kept ({kept:.2f} of sampled vertices)")
    if len(out.faces) < faces_in:
        raise AssertionError(f"{kind}: triangle count fell from {faces_in} to {len(out.faces)}")
    if seconds > 180:
        raise AssertionError(f"{kind}: {seconds:.0f}s is not inside the 180s prepare budget")
    return {
        "seconds": round(seconds, 2),
        "rss_mb": round(rss_mb, 1),
        "faces_in": faces_in,
        "faces_out": int(len(out.faces)),
        "pillars": pillars,
        "kept": round(kept, 3),
        "touch": None if touch is None else round(touch, 3),
        "raft_span": None if raft_span is None else round(raft_span, 1),
        "saved": None if not hollow_on else round(float(hol["volume_saved_pct"]), 1),
    }


def _stage_table(rep):
    rows = ((rep.get("hollow") or {}).get("stages")) or []
    return [{k: row.get(k) for k in ("name", "ms", "attempt", "offset_mm", "wall_mm", "save_pct", "kept", "holes")} for row in rows]


def run_relief(kind):
    """Hollow a detailed relief mask. Several cavities, each drained, outer surface kept."""
    if kind not in ("hollow", "both"):
        raise AssertionError(kind)
    opts = {
        "hollow": {"hollow": "true", "supports": "false", "tilt_deg": 0},
        "both": {"hollow": "true", "supports": "true", "tilt_deg": 0},
    }[kind]
    started = time.perf_counter()
    mesh = _relief_mask()
    faces_in = int(len(mesh.faces))
    if not mesh.is_watertight or len(mesh.split(only_watertight=False)) != 1:
        raise AssertionError(f"{kind}: relief is not one watertight shell")
    if not 600_000 <= faces_in <= 800_000:
        raise AssertionError(f"{kind}: expected 600k-800k triangles, got {faces_in}")
    gc.collect()
    out, rep = resin.prepare(mesh, resin.settings(opts))
    seconds = time.perf_counter() - started
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    placed = resin.place_on_bed(mesh, 0.0, 0.0)
    supports_on = kind == "both"
    shift = np.array([0.0, 0.0, _LIFT if supports_on else 0.0])
    kept = _kept_fraction(placed.vertices, out.vertices - shift)
    hol = rep.get("hollow") or {}
    holes = list(hol.get("holes") or [])
    saved = float(hol.get("volume_saved_pct") or 0.0)
    if hol.get("left_solid") or saved < 10.0 or len(holes) < 3 or any(n != 2 for n in holes):
        raise AssertionError(f"{kind}: expected several drained cavities ({hol})")
    suction = (rep.get("layer_check") or {}).get("suction") or []
    if suction:
        raise AssertionError(f"{kind}: sealed cavity still flagged ({suction[:2]})")
    if kept < 0.99:
        raise AssertionError(f"{kind}: outer surface was not kept ({kept:.4f})")
    axes = hol.get("drain_axes") or []
    if len(axes) != sum(holes):
        raise AssertionError(f"{kind}: drain axes missing ({len(axes)} for {holes})")
    if not supports_on:
        # Supports lift the mesh. The hollow-only result is still in the placed frame.
        for inner_pt, outer_pt in axes:
            if not meshedit._hole_is_open(np.asarray(out.vertices), np.asarray(out.faces), inner_pt, outer_pt):
                raise AssertionError(f"{kind}: drain axis is still blocked")
    if seconds > 120:
        raise AssertionError(f"{kind}: {seconds:.0f}s is over the 120s budget on 2 cores")
    return {
        "seconds": round(seconds, 2),
        "rss_mb": round(rss_mb, 1),
        "faces_in": faces_in,
        "faces_out": int(len(out.faces)),
        "kept": round(kept, 4),
        "saved": round(saved, 1),
        "holes": holes,
        "suction": len(suction),
        "stages": _stage_table(rep),
    }


def run_thin_mask(kind="hollow"):
    """A thin relief saves too little to hollow. It comes back solid, with the note."""
    opts = {"hollow": "true", "supports": "false" if kind == "hollow" else "true", "tilt_deg": 0}
    started = time.perf_counter()
    mesh = _relief_mask(bosses=False, base_mm=2.6)
    faces_in = int(len(mesh.faces))
    if not mesh.is_watertight:
        raise AssertionError("thin relief is not watertight")
    gc.collect()
    out, rep = resin.prepare(mesh, resin.settings(opts))
    seconds = time.perf_counter() - started
    placed = resin.place_on_bed(mesh, 0.0, 0.0)
    supports_on = opts["supports"] == "true"
    shift = np.array([0.0, 0.0, _LIFT if supports_on else 0.0])
    kept = _kept_fraction(placed.vertices, out.vertices - shift)
    hol = rep.get("hollow") or {}
    note = meshedit.LEFT_SOLID_NOTE
    if not hol.get("left_solid") or note not in rep.get("notes", []):
        raise AssertionError(f"thin mask was hollowed ({hol}, notes {rep.get('notes')})")
    suction = (rep.get("layer_check") or {}).get("suction") or []
    if suction:
        raise AssertionError(f"solid mask reported a sealed cavity ({suction[:2]})")
    if kept < 0.99:
        raise AssertionError(f"outer surface was not kept ({kept:.4f})")
    if abs(float(hol.get("volume_saved_pct") or 0.0)) > 0.1:
        raise AssertionError(f"solid result saved volume ({hol})")
    if seconds > 120:
        raise AssertionError(f"{seconds:.0f}s is over the 120s budget on 2 cores")
    return {
        "seconds": round(seconds, 2),
        "faces_in": faces_in,
        "kept": round(kept, 4),
        "saved": hol.get("volume_saved_pct"),
        "note": note,
        "stages": _stage_table(rep),
        "suction": len(suction),
    }
