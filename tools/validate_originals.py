"""Check every ZEIM Original file against the printer bed as a WHOLE PLATE (not just its largest part).
    python tools/validate_originals.py [library/originals] [--bed 220 220 250]
A multi-part model whose layout plate is bigger than the bed only passes when every one of its _plateN.stl files fits.
Exit code 1 if anything fails. Geometry only: this is not a test print."""
import argparse, json, sys
from pathlib import Path
import trimesh
sys.path.insert(0, str(Path(__file__).resolve().parent))
from originals_plates import plate_fits


def check(lib: Path, bed=(220.0, 220.0, 250.0)) -> list[dict]:
    man = json.loads((lib / "originals_manifest.json").read_text())
    rows = []
    for x in man["models"]:
        main = lib / x["file"]
        plates = sorted(lib.glob(f"{main.stem}_plate*.stl"))
        files = plates or [main]
        res = []
        for f in files:
            m = trimesh.load(f, force="mesh")
            res.append({"file": f.name, "plate_mm": [round(float(v), 1) for v in m.extents],
                        "fits": plate_fits(m, bed[:2]) and m.extents[2] <= bed[2]})
        rows.append({"slug": x["slug"], "files": res, "pass": all(r["fits"] for r in res)})
    return rows


def main(argv=None):
    a = argparse.ArgumentParser(); a.add_argument("lib", nargs="?", default=str(Path(__file__).resolve().parent.parent / "library" / "originals"))
    a.add_argument("--bed", nargs=3, type=float, default=(220, 220, 250)); o = a.parse_args(argv)
    rows = check(Path(o.lib), tuple(o.bed))
    bad = [r for r in rows if not r["pass"]]
    for r in bad:
        print("FAIL", r["slug"], r["files"])
    print(f"{len(rows) - len(bad)}/{len(rows)} fit a {o.bed[0]:g}x{o.bed[1]:g}x{o.bed[2]:g} mm bed as whole plates")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
