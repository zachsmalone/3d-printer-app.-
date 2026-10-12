"""Lay a multi-part Original out as separate plate STLs that each fit the bed (default Creality K1: 220 x 220 mm).
    python tools/originals_plates.py library/originals/rain-guard-bird-feeder.stl [--bed 220 220] [--gap 6]
Writes <slug>_plate1.stl, _plate2.stl ... next to the input (the original file is left untouched)."""
import argparse, sys
from pathlib import Path
import trimesh


def pack(parts, bed=(220.0, 220.0), gap=6.0, margin=5.0):
    """Shelf packing (largest first, each part may turn 90 degrees). Returns a list of plates, each a list of placed meshes."""
    W, H = bed[0] - 2 * margin, bed[1] - 2 * margin
    items = []
    for p in parts:
        p = p.copy(); p.apply_translation(-p.bounds[0])
        if p.extents[0] > W or p.extents[1] > H:            # try a quarter turn
            p.apply_transform(trimesh.transformations.rotation_matrix(1.5707963, (0, 0, 1))); p.apply_translation(-p.bounds[0])
        if p.extents[0] > W or p.extents[1] > H:
            raise ValueError(f"a part is {p.extents[0]:.0f} x {p.extents[1]:.0f} mm: larger than the bed on its own")
        items.append(p)
    items.sort(key=lambda p: -p.extents[1])
    plates, cur, x, y, row = [], [], 0.0, 0.0, 0.0
    for p in items:
        w, h = p.extents[0], p.extents[1]
        if x + w > W:
            x, y, row = 0.0, y + row + gap, 0.0
        if y + h > H:
            plates.append(cur); cur, x, y, row = [], 0.0, 0.0, 0.0
        q = p.copy(); q.apply_translation((margin + x, margin + y, 0)); cur.append(q)
        x += w + gap; row = max(row, h)
    if cur:
        plates.append(cur)
    return plates


def plate_fits(m, bed=(220.0, 220.0)) -> bool:
    """The WHOLE plate must fit, not just its largest part."""
    e = m.extents
    return bool((e[0] <= bed[0] and e[1] <= bed[1]) or (e[1] <= bed[0] and e[0] <= bed[1]))


def main(argv=None):
    a = argparse.ArgumentParser(); a.add_argument("stl"); a.add_argument("--bed", nargs=2, type=float, default=(220, 220)); a.add_argument("--gap", type=float, default=6)
    o = a.parse_args(argv)
    src = Path(o.stl); m = trimesh.load(src, force="mesh")
    plates = pack(m.split(only_watertight=False), tuple(o.bed), o.gap)
    for n, pl in enumerate(plates, 1):
        out = trimesh.util.concatenate(pl)
        assert plate_fits(out, tuple(o.bed)), out.extents
        dst = src.with_name(f"{src.stem}_plate{n}.stl"); out.export(dst)
        print(dst.name, "x".join(f"{v:.1f}" for v in out.extents), f"{len(pl)} part(s)")


if __name__ == "__main__":
    sys.exit(main())
