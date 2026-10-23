"""Likely trouble spots by height for the G-code preview's problem markers (written for ZEIM).
Cheap geometry on the sliced model (model.stl, already placed on the bed): steep overhang bands and parts that start
in mid-air (islands), plus Will-it-print notes that have no height. These are hints, never a diagnosis."""
from __future__ import annotations

import numpy as np

MAX_FACES = 400_000
OVERHANG_NZ = -0.707          # face points down more than 45 deg from vertical
MIN_AREA_MM2 = 4.0            # ignore specks


def markers(stl_path, supports: str = "off", will_print: dict | None = None, limit: int = 8) -> list[dict]:
    out: list[dict] = []
    try:
        import trimesh
        mesh = trimesh.load(str(stl_path), force="mesh", process=False)
        if 0 < len(mesh.faces) <= MAX_FACES:
            z0 = float(mesh.bounds[0][2])
            sup = supports not in ("off", "none", "", None)
            n, c, a = mesh.face_normals, mesh.triangles_center, mesh.area_faces
            down = (n[:, 2] < OVERHANG_NZ) & (c[:, 2] - z0 > 0.5)
            if down.any():
                zs = np.round((c[down, 2] - z0) / 0.5) * 0.5          # 0.5 mm bands
                bands: dict[float, float] = {}
                for z, ar in zip(zs, a[down]):
                    bands[z] = bands.get(z, 0.0) + float(ar)
                top = sorted((b for b in bands.items() if b[1] >= MIN_AREA_MM2), key=lambda b: -b[1])[:limit]
                for z, ar in sorted(top):
                    out.append({"z": round(float(z), 2), "kind": "overhang",
                                "text": f"Steep overhang (about {ar:.0f} mm² facing down)" + (". Supports are on, check they reach it." if sup else ". Supports are off: this may sag or fail.")})
            m = mesh.copy(); m.merge_vertices()
            comps = trimesh.graph.connected_components(m.face_adjacency, nodes=np.arange(len(m.faces)))
            if 1 < len(comps) <= 200:
                for comp in comps:
                    lo = float(m.vertices[m.faces[comp]].reshape(-1, 3)[:, 2].min()) - z0
                    if lo > 0.3 and len(out) < limit * 2:
                        out.append({"z": round(lo, 2), "kind": "island",
                                    "text": "A separate part starts here in mid-air" + (" (supports are on)." if sup else ": it has nothing under it.")})
    except Exception:
        pass
    wp = will_print or {}
    thin = (wp.get("checks") or {}).get("thin_wall") or {}
    if thin.get("ok") is False:
        out.append({"z": None, "kind": "thin", "text": "Will-it-print found walls thinner than one line (height not known): look for gaps in the walls."})
    return out
