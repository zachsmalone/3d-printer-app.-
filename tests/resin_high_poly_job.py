"""Worker for the high-poly TorchC0 prepare test.

Lives outside the test module so the memory-capped child can import it.
`procjob` re-imports `function.__module__`, and pytest loads the test file
under a name that is not importable in that child.
"""
import resource
import time

import numpy as np
import trimesh

from app.core import resin

# uv_sphere(count=[250, 700]) is 694_400 triangles. Production failed on 694_838.
_COUNT = (250, 700)
_LIFT = resin.DEFAULT_BASE_LIFT_MM + resin.DEFAULT_RAFT_MM


def _organic():
    mesh = trimesh.creation.uv_sphere(radius=1.0, count=list(_COUNT))
    mesh.apply_scale([65.0, 82.5, 36.5])
    verts = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    disp = 2.2 * np.sin(verts[:, 0] * 0.08) * np.cos(verts[:, 1] * 0.06) + 1.4 * np.sin(verts[:, 2] * 0.11)
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
        pick = band[np.linspace(0, len(band) - 1, num=min(24, len(band)), dtype=int)]
        origins = pick + np.array([0.0, 0.0, 0.05])
        dirs = np.tile([0.0, 0.0, 1.0], (len(pick), 1))
        lifted = placed.copy()
        lifted.apply_translation([0.0, 0.0, _LIFT])
        loc, index_ray, _faces = lifted.ray.intersects_location(origins, dirs)
        if len(loc) == 0:
            touch = 0.0
        else:
            dist = loc[:, 2] - origins[np.asarray(index_ray), 2]
            close = dist < 3.0
            hit_rays = set(np.asarray(index_ray)[close].tolist())
            touch = len(hit_rays) / len(pick)
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
    if seconds > 230:
        raise AssertionError(f"{kind}: {seconds:.0f}s is not inside the 240s prepare limit")
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
