"""QA driver: runs sample meshes through the live Edit API (port 8766, temp dirs) and writes qa_results.json."""
import requests, time, json, io, sys, numpy as np, trimesh
from pathlib import Path
B = "http://127.0.0.1:8766"
S = Path(__file__).parent
OPS = {  # per-file op plans (each applied independently from the imported state, then undone)
 "default": [("repair", {}), ("scale", {"factor": 1.5}), ("rotate", {"rx": 90}), ("mirror", {"axis": "x"}), ("place", {"center_xy": True}),
             ("base", {"style": "outline", "thickness": 2, "margin": 3}), ("cut", {"axis": "z", "position": None, "keep": "above"}),
             ("hollow", {"wall": 2, "drain_diameter": 3}), ("simplify", {"keep_ratio": 0.5}),
             ("boolean", {"kind": "difference", "primitive": {"type": "cylinder"}}), ("text", {"text": "ZEIM", "mode": "emboss"})],
}
FILES = [("a_gear_bracket_binary.stl","mm"),("a2_gear_ascii.stl","mm"),("ギア_部品_é.stl","mm"),("b_multigroup_uv_normals.obj","mm"),
         ("b2_quads_box.obj","mm"),("c_multiobj_components_colors.3mf","mm"),("d_bad_open_flipped.stl","mm"),
         ("e_organic_330k_inches_offset.stl","in")]
res = {}
def t(): return time.time()
def wt(data, ext):
    m = trimesh.load(io.BytesIO(data), file_type=ext, process=False, force="mesh")
    m.merge_vertices()
    return {"tris": len(m.faces), "watertight": bool(m.is_watertight), "winding": bool(m.is_winding_consistent),
            "size": np.round(m.extents, 2).tolist()}
only = sys.argv[1:]
for fn, units in FILES:
    if only and not any(o in fn for o in only): continue
    r = {"ops": {}, "exports": {}, "slice": {}}
    res[fn] = r
    s = requests.Session()
    p = S / fn
    t0 = t()
    try:
        rp = s.post(B + "/api/edit/new", files={"file": (fn, open(p, "rb"))}, data={"units": units, "auto_delete_oldest": "true"}, timeout=600)
    except Exception as e:
        r["open"] = {"ok": False, "err": repr(e)}; continue
    r["open"] = {"ok": rp.status_code == 200, "status": rp.status_code, "sec": round(t() - t0, 2)}
    if rp.status_code != 200:
        r["open"]["err"] = rp.text[:300]; print(fn, r["open"]); continue
    j = rp.json(); bid = j["id"]
    r["open"]["warnings"] = j.get("warnings"); r["open"]["analysis"] = {k: j["analysis"][k] for k in ("triangles","watertight","winding_consistent","boundary_edges","nonmanifold_edges","inverted","size_mm","min_mm","components")}
    r["open"]["preview_decimated"] = j["preview"]["decimated"]
    r["open"]["payload_kb"] = len(rp.content)//1024
    base_an = j["analysis"]
    def apply(op, params):
        t1 = t()
        rr = s.post(f"{B}/api/edit/{bid}/op", json={"op": op, "params": params}, timeout=900)
        d = {"status": rr.status_code, "sec": round(t() - t1, 2)}
        if rr.status_code == 200:
            jj = rr.json(); a = jj["analysis"]
            d.update(ok=True, tris=a["triangles"], watertight=a["watertight"], size=a["size_mm"], msg=(jj.get("report") or {}).get("message"))
        else:
            d.update(ok=False, err=rr.text[:300])
        return d
    zmid = (base_an["min_mm"][2] + base_an["size_mm"][2] / 2)
    for op, params in OPS["default"]:
        params = dict(params)
        if op == "cut": params["position"] = round(zmid, 3)
        if op == "boolean":
            params["primitive"] = {"type": "cylinder", "diameter": max(1, min(base_an["size_mm"][:2]) / 5), "height": base_an["size_mm"][2] * 2,
                                   "position": [(base_an["min_mm"][0] + base_an["size_mm"][0]/2), (base_an["min_mm"][1] + base_an["size_mm"][1]/2), zmid]}
        if op == "text": params.update({"face": "top", "height": 1.0, "size": max(3, min(base_an["size_mm"][:2]) / 5)})
        r["ops"][op] = apply(op, params)
        if r["ops"][op]["ok"]: s.post(f"{B}/api/edit/{bid}/undo")
        else: pass
    # exports + slice of unmodified import
    def exp_slice(tag):
        out = {}
        for ext in ("stl", "obj", "3mf"):
            t1 = t(); dr = s.get(f"{B}/api/download/{bid}/{ext}", timeout=600)
            e = {"status": dr.status_code, "sec": round(t() - t1, 2), "kb": len(dr.content)//1024}
            if dr.status_code == 200:
                try: e.update(wt(dr.content, ext))
                except Exception as ex: e["parse_err"] = repr(ex)[:200]
            out[ext] = e
        t1 = t(); sr = s.post(f"{B}/api/slice/{bid}", data={"layer_height": 0.2, "fill_density": 15}, timeout=900)
        sj = sr.json() if sr.headers.get("content-type","").startswith("application/json") else {"raw": sr.text[:200]}
        sl = {"status": sr.status_code, "sec": round(t() - t1, 2), "ok": sj.get("ok"), "msg": sj.get("message"), "stats": sj.get("stats") or {k: sj.get(k) for k in ("print_time","filament_g") if sj.get(k)}}
        if sj.get("log"): sl["log_tail"] = sj["log"][-400:]
        if sj.get("download"):
            g = s.get(B + sj["download"]); sl["gcode_kb"] = len(g.content)//1024
            sl["gcode_layers"] = g.content.count(b";LAYER_CHANGE")
        sl["raw_keys"] = list(sj.keys())
        return out, sl
    r["exports"]["imported"], r["slice"]["imported"] = exp_slice("imported")
    # chain: repair -> scale to ~80mm max (if sane) -> place -> base
    chain = [("repair", {}), ("place", {"center_xy": True})]
    mx = max(base_an["size_mm"])
    if mx > 150 or mx < 20: chain.append(("scale", {"factor": round(80 / mx, 5), "pivot": "center"}))
    chain.append(("base", {"style": "outline", "thickness": 2, "margin": 3}))
    r["chain"] = [(o, apply(o, pp)) for o, pp in chain]
    r["exports"]["chain"], r["slice"]["chain"] = exp_slice("chain")
    s.delete(f"{B}/api/builds/{bid}")
    print(fn, "done", flush=True)
    json.dump(res, open(S / "qa_results.json", "w"), indent=1, ensure_ascii=False)
json.dump(res, open(S / "qa_results.json", "w"), indent=1, ensure_ascii=False)
