"""PERF8 benchmark: p95 wall time of a small real slice, cold vs warm page cache.

cold = before each run, the PrusaSlicer binary and its shared libraries are dropped from the page cache
       (posix_fadvise DONTNEED, no root needed), which is the state after a deploy or a long quiet spell.
warm = the state the warm-up keeps (services/slicer_warm.py).
Usage: python tools/perf8_bench.py [runs] [model.stl]   (default 15 runs, a 20 mm cube with a hole)"""
import os, statistics, subprocess, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(globals().get("__file__", "/app/x/y")).resolve().parents[1]))
from app.services import slice_engine as se


def files_to_drop(engine):
    out = [engine]
    try:
        for line in subprocess.run(["ldd", engine], capture_output=True, text=True).stdout.splitlines():
            parts = line.split("=>")
            p = (parts[1] if len(parts) > 1 else parts[0]).strip().split(" ")[0]
            if p.startswith("/"):
                out.append(p)
    except OSError:
        pass
    return out


def drop(paths):
    for p in paths:
        try:
            fd = os.open(os.path.realpath(p), os.O_RDONLY)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED); os.close(fd)
        except OSError:
            pass


def p95(xs):
    xs = sorted(xs); k = max(0, int(round(0.95 * len(xs) + 0.5)) - 1)
    return xs[min(k, len(xs) - 1)]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    engine = se.find_engine(); assert engine, "PrusaSlicer not found"
    libs = files_to_drop(engine)
    prof, _ = se.profile_for()
    with tempfile.TemporaryDirectory() as td:
        if len(sys.argv) > 2:
            model = Path(sys.argv[2])
        else:
            import trimesh
            m = trimesh.creation.box(extents=(20, 20, 20)).difference(trimesh.creation.cylinder(radius=5, height=30))
            model = Path(td) / "bench.stl"; m.export(model)
        def one():
            t = time.monotonic(); se.slice_model_path(model, prof, Path(td) / "o.gcode"); return time.monotonic() - t
        cold, warm = [], []
        for _ in range(n):
            drop(libs); cold.append(one())
        one()
        for _ in range(n):
            warm.append(one())
    print(f"engine={engine} files_dropped={len(libs)} runs={n}")
    for k, v in (("cold", cold), ("warm", warm)):
        print(f"{k}: p50={statistics.median(v):.2f}s p95={p95(v):.2f}s min={min(v):.2f}s max={max(v):.2f}s")


if __name__ == "__main__":
    main()
