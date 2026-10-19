"""ZEIM sketch engine: 2D entities on a plane, profile regions, offset/trim and a constraint solver.

Original code written from first principles for ZEIM (see ROADMAP.md: no code from any GPL CAD
project is read or re-expressed here). The solver is plain nonlinear least squares: every
constraint and locked dimension is a residual function of the sketch's numbers; we minimise the
sum of squares (scipy.optimize.least_squares, BSD) plus a tiny pull toward the current values so
under-constrained sketches move as little as possible.

Entity schema (all numbers in sketch-plane millimetres):
  line    {id, type:"line",    p0:[x,y], p1:[x,y]}
  arc     {id, type:"arc",     c:[x,y], r, a0, a1}          (degrees, counter-clockwise a0 -> a1)
  circle  {id, type:"circle",  c:[x,y], r}
  ellipse {id, type:"ellipse", c:[x,y], rx, ry, rot}
  polygon {id, type:"polygon", c:[x,y], r, n, rot}           (regular, r = circumradius)
  spline  {id, type:"spline",  pts:[[x,y],...], closed}       (Catmull-Rom through the points)
  poly    {id, type:"poly",    pts:[[x,y],...], closed}       (polyline, e.g. from Offset)
Point references: "<id>.p0", "<id>.p1", "<id>.c", "<id>.s" / "<id>.e" (arc start/end), "<id>.pts.<k>".
Constraints {type, a, b?, value?}: coincident, horizontal, vertical, parallel, perpendicular, equal,
tangent, concentric, lock, length, radius, distance, angle, midpoint.
"""
from __future__ import annotations

import math

import numpy as np

MAX_ENTITIES = 400
MAX_CONSTRAINTS = 800
MAX_PTS = 400
SEG_PER_CIRCLE = 96
LIM = 5000.0
TYPES = ("line", "arc", "circle", "ellipse", "polygon", "spline", "poly")
CTYPES = ("coincident", "horizontal", "vertical", "parallel", "perpendicular", "equal", "tangent",
          "concentric", "lock", "length", "radius", "distance", "angle", "midpoint")


class SketchError(ValueError):
    pass


def _f(v, name, lo=-LIM, hi=LIM):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise SketchError(f"{name} must be a number.")
    if not math.isfinite(v) or not lo <= v <= hi:
        raise SketchError(f"{name} must be {lo:g}..{hi:g}.")
    return v


def _pt(v, name):
    if not isinstance(v, (list, tuple)) or len(v) != 2:
        raise SketchError(f"{name} must be [x, y].")
    return [_f(v[0], name), _f(v[1], name)]


def check(sk: dict) -> dict:
    """Validate + normalise a sketch {entities, constraints}. Raises SketchError."""
    if not isinstance(sk, dict):
        raise SketchError("sketch must be an object.")
    ents = sk.get("entities") or []
    cons = sk.get("constraints") or []
    if not isinstance(ents, list) or not isinstance(cons, list):
        raise SketchError("entities/constraints must be lists.")
    if len(ents) > MAX_ENTITIES or len(cons) > MAX_CONSTRAINTS:
        raise SketchError("Sketch is too big.")
    out, ids = [], set()
    for i, e in enumerate(ents):
        if not isinstance(e, dict) or e.get("type") not in TYPES:
            raise SketchError(f"Entity {i + 1}: unknown type.")
        t = e["type"]
        eid = str(e.get("id") or f"e{i + 1}")[:24]
        if eid in ids:
            raise SketchError(f"Duplicate entity id {eid}.")
        ids.add(eid)
        n = {"id": eid, "type": t, "construction": bool(e.get("construction"))}
        if t == "line":
            n["p0"], n["p1"] = _pt(e.get("p0"), "p0"), _pt(e.get("p1"), "p1")
        elif t in ("arc", "circle", "ellipse", "polygon"):
            n["c"] = _pt(e.get("c"), "centre")
            if t in ("arc", "circle", "polygon"):
                n["r"] = _f(e.get("r"), "radius", 1e-4, LIM)
            if t == "arc":
                n["a0"], n["a1"] = _f(e.get("a0"), "a0", -1e4, 1e4), _f(e.get("a1"), "a1", -1e4, 1e4)
            if t == "ellipse":
                n["rx"], n["ry"] = _f(e.get("rx"), "rx", 1e-4, LIM), _f(e.get("ry"), "ry", 1e-4, LIM)
                n["rot"] = _f(e.get("rot", 0), "rot", -1e4, 1e4)
            if t == "polygon":
                n["n"] = int(_f(e.get("n", 6), "sides", 3, 64))
                n["rot"] = _f(e.get("rot", 0), "rot", -1e4, 1e4)
        else:
            pts = e.get("pts") or []
            if not isinstance(pts, list) or not 2 <= len(pts) <= MAX_PTS:
                raise SketchError(f"{t} needs 2..{MAX_PTS} points.")
            n["pts"] = [_pt(p, "point") for p in pts]
            n["closed"] = bool(e.get("closed"))
        out.append(n)
    cout = []
    for i, c in enumerate(cons):
        if not isinstance(c, dict) or c.get("type") not in CTYPES:
            raise SketchError(f"Constraint {i + 1}: unknown type.")
        n = {"type": c["type"], "a": str(c.get("a", ""))[:40]}
        if c.get("b") is not None:
            n["b"] = str(c["b"])[:40]
        if c.get("value") is not None:
            n["value"] = _f(c["value"], "value", -1e4, 1e4)
        if c.get("id") is not None:
            n["id"] = str(c["id"])[:24]
        cout.append(n)
    return {"entities": out, "constraints": cout}


# ------------------------------------------------------------------ tessellation
def _arc_pts(c, r, a0, a1):
    while a1 <= a0:
        a1 += 360.0
    n = max(4, int(SEG_PER_CIRCLE * (a1 - a0) / 360.0))
    t = np.radians(np.linspace(a0, a1, n + 1))
    return np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]


def _catmull(pts, closed, k=12):
    P = np.asarray(pts, float)
    if closed:
        P = np.vstack([P[-1], P, P[0], P[1]])
    else:
        P = np.vstack([P[0], P, P[-1]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0, 1, k, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return np.asarray(out)


def tessellate(e: dict) -> tuple[np.ndarray, bool]:
    """Polyline for an entity and whether it is a closed loop by itself."""
    t = e["type"]
    if t == "line":
        return np.array([e["p0"], e["p1"]], float), False
    if t == "arc":
        return _arc_pts(e["c"], e["r"], e["a0"], e["a1"]), False
    if t == "circle":
        return _arc_pts(e["c"], e["r"], 0, 360)[:-1], True
    if t == "ellipse":
        tt = np.linspace(0, 2 * math.pi, SEG_PER_CIRCLE, endpoint=False)
        ro = math.radians(e["rot"])
        x, y = e["rx"] * np.cos(tt), e["ry"] * np.sin(tt)
        return np.c_[e["c"][0] + x * math.cos(ro) - y * math.sin(ro), e["c"][1] + x * math.sin(ro) + y * math.cos(ro)], True
    if t == "polygon":
        tt = np.radians(e["rot"]) + np.arange(e["n"]) * 2 * math.pi / e["n"]
        return np.c_[e["c"][0] + e["r"] * np.cos(tt), e["c"][1] + e["r"] * np.sin(tt)], True
    if t == "spline":
        return _catmull(e["pts"], e["closed"]), e["closed"]
    return np.asarray(e["pts"], float), e["closed"]


def regions(sk: dict, picks: list | None = None):
    """Closed profile regions as a shapely (Multi)Polygon.
    Default: even-odd (a loop inside a loop is a hole). `picks` = list of [x,y] points: only the
    elementary faces containing those points (click a region to extrude just that one)."""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    lines, loops = [], []
    for e in sk["entities"]:
        if e.get("construction"):
            continue
        P, closed = tessellate(e)
        if closed and len(P) >= 3:
            loops.append(Polygon(P).buffer(0))
            lines.append(LineString(np.vstack([P, P[:1]])))
        elif len(P) >= 2:
            lines.append(LineString(P))
    if not lines:
        return None
    # snap tiny gaps (typed coordinates seldom meet exactly) by rounding to 1 µm
    noded = unary_union([_round(l) for l in lines])
    faces = [f for f in polygonize(noded) if f.area > 1e-6]
    if not faces:
        return None
    if picks:
        chosen = [f for f in faces if any(f.buffer(1e-6).contains(Point(p)) for p in picks)]
    else:
        # even-odd: depth = how many elementary faces' loops contain this face's interior point
        filled = [Polygon(f.exterior) for f in faces]
        chosen = []
        for f in faces:
            ip = f.representative_point()
            depth = sum(1 for g, fl in zip(faces, filled) if g is not f and fl.contains(ip))
            if depth % 2 == 0:
                chosen.append(f)
    if not chosen:
        return None
    u = unary_union(chosen)
    return u if not u.is_empty else None


def _round(ls):
    from shapely.geometry import LineString
    return LineString(np.round(np.asarray(ls.coords), 4))


def region_rings(sk: dict, picks=None) -> list[dict]:
    """JSON-friendly profile preview: [{outer:[[x,y]..], holes:[[[x,y]..]..], area}]"""
    g = regions(sk, picks)
    if g is None:
        return []
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    return [{"outer": np.round(np.asarray(p.exterior.coords), 4).tolist(),
             "holes": [np.round(np.asarray(h.coords), 4).tolist() for h in p.interiors],
             "area": round(p.area, 4)} for p in polys if p.geom_type == "Polygon"]


def faces(sk: dict) -> list[dict]:
    """Every elementary closed face (for click-to-pick regions)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize, unary_union
    lines = []
    for e in sk["entities"]:
        if e.get("construction"):
            continue
        P, closed = tessellate(e)
        lines.append(_round(LineString(np.vstack([P, P[:1]]) if closed else P)))
    if not lines:
        return []
    out = []
    for f in polygonize(unary_union(lines)):
        if f.area > 1e-6:
            rp = f.representative_point()
            out.append({"outer": np.round(np.asarray(f.exterior.coords), 4).tolist(), "inside": [rp.x, rp.y], "area": round(f.area, 4)})
    return out


# ------------------------------------------------------------------ offset / trim
def offset(sk: dict, eid: str, d: float) -> dict:
    """New entity offset from `eid` by d mm (+ = outward/left). Circles/arcs/polygons stay exact; others become polylines."""
    e = _ent(sk, eid)
    d = _f(d, "offset", -1000, 1000)
    t = e["type"]
    import itertools
    nid = _new_id(sk)
    if t in ("circle", "arc", "polygon"):
        r = e["r"] + d
        if r <= 1e-4:
            raise SketchError("Offset makes the radius zero or negative.")
        return {**e, "id": nid, "r": r}
    if t == "line":
        p0, p1 = np.array(e["p0"]), np.array(e["p1"])
        v = p1 - p0
        nrm = np.array([-v[1], v[0]]) / (np.linalg.norm(v) or 1)
        return {"id": nid, "type": "line", "p0": (p0 + nrm * d).tolist(), "p1": (p1 + nrm * d).tolist()}
    from shapely.geometry import LineString, Polygon
    P, closed = tessellate(e)
    if closed:
        g = Polygon(P).buffer(d, join_style=2)
        if g.is_empty or g.geom_type != "Polygon":
            raise SketchError("Offset collapses the shape.")
        pts = np.asarray(g.exterior.coords)[:-1]
    else:
        g = LineString(P).offset_curve(d, join_style=2)
        if g.is_empty or g.geom_type != "LineString":
            raise SketchError("Offset collapses the curve.")
        pts = np.asarray(g.coords)
    del itertools
    return {"id": nid, "type": "poly", "pts": np.round(pts, 5).tolist()[:MAX_PTS], "closed": closed}


def trim(sk: dict, eid: str, at: list) -> list[dict]:
    """Remove the piece of `eid` between its neighbouring intersections that is nearest the point `at`.
    Lines split into lines; circles/arcs become arcs. Returns the replacement entities (may be [])."""
    e = _ent(sk, eid)
    at = np.array(_pt(at, "at"))
    if e["type"] not in ("line", "circle", "arc"):
        raise SketchError("Trim works on lines, arcs and circles.")
    from shapely.geometry import LineString
    others = []
    for o in sk["entities"]:
        if o["id"] != eid and not o.get("construction"):
            P, closed = tessellate(o)
            others.append(LineString(np.vstack([P, P[:1]]) if closed else P))
    if e["type"] == "line":
        p0, p1 = np.array(e["p0"]), np.array(e["p1"])
        L = LineString([p0, p1]); ln = L.length
        ts = sorted({0.0, 1.0, *[L.project(q) / ln for q in _ipoints(L, others)]})
        ta = L.project(_P(at)) / ln
        k = max(i for i in range(len(ts) - 1) if ts[i] <= ta + 1e-12) if ta > 0 else 0
        k = min(k, len(ts) - 2)
        out = []
        for a, b in ((0.0, ts[k]), (ts[k + 1], 1.0)):
            if b - a > 1e-6:
                out.append({"id": _new_id(sk, len(out)), "type": "line", "p0": (p0 + (p1 - p0) * a).tolist(), "p1": (p0 + (p1 - p0) * b).tolist()})
        return out
    c, r = np.array(e["c"]), e["r"]
    a0, a1 = (0.0, 360.0) if e["type"] == "circle" else (e["a0"], e["a1"])
    while a1 <= a0:
        a1 += 360
    P = _arc_pts(c, r, a0, a1)
    L = LineString(P)
    angs = sorted({(math.degrees(math.atan2(q.y - c[1], q.x - c[0])) - a0) % 360 + a0 for q in _ipoints(L, others)})
    aa = (math.degrees(math.atan2(at[1] - c[1], at[0] - c[0])) - a0) % 360 + a0
    cuts = angs if e["type"] == "circle" else [a for a in angs if a0 + 1e-6 < a < a1 - 1e-6]
    if e["type"] == "circle":
        if len(cuts) < 2:
            return []           # a circle crossed fewer than twice: trimming removes it all
        lo = max([a for a in cuts if a <= aa], default=cuts[-1] - 360)
        hi = min([a for a in cuts if a > aa], default=cuts[0] + 360)
        return [{"id": _new_id(sk), "type": "arc", "c": c.tolist(), "r": r, "a0": hi % 360, "a1": (lo % 360) if lo % 360 > hi % 360 else lo % 360 + 360}]
    bounds = [a0, *cuts, a1]
    k = max(i for i in range(len(bounds) - 1) if bounds[i] <= aa + 1e-9) if aa >= a0 else 0
    k = min(k, len(bounds) - 2)
    out = []
    for s, t in ((a0, bounds[k]), (bounds[k + 1], a1)):
        if t - s > 1e-4:
            out.append({"id": _new_id(sk, len(out)), "type": "arc", "c": c.tolist(), "r": r, "a0": s, "a1": t})
    return out


def _P(p):
    from shapely.geometry import Point
    return Point(float(p[0]), float(p[1]))


def _ipoints(L, others):
    pts = []
    for o in others:
        x = L.intersection(o)
        if x.is_empty:
            continue
        for g in getattr(x, "geoms", [x]):
            if g.geom_type == "Point":
                pts.append(g)
            elif hasattr(g, "coords"):
                from shapely.geometry import Point
                pts += [Point(q) for q in g.coords]
    return pts


def _ent(sk, eid):
    for e in sk["entities"]:
        if e["id"] == eid:
            return e
    raise SketchError(f"No entity {eid}.")


def _new_id(sk, k=0):
    used = {e["id"] for e in sk["entities"]}
    i = len(used) + 1 + k
    while f"e{i}" in used:
        i += 1
    return f"e{i}"


# ------------------------------------------------------------------ solver
class _Vars:
    """Flattens the sketch's numbers into one vector x and maps names <-> indices."""

    def __init__(self, ents):
        self.idx, self.x0 = {}, []
        self.ents = {e["id"]: e for e in ents}
        for e in ents:
            t, i = e["type"], e["id"]
            if t == "line":
                self._add(i + ".p0", e["p0"]); self._add(i + ".p1", e["p1"])
            elif t in ("arc", "circle", "ellipse", "polygon"):
                self._add(i + ".c", e["c"])
                if t in ("arc", "circle", "polygon"):
                    self._add(i + ".r", [e["r"]])
                if t == "arc":
                    self._add(i + ".a", [math.radians(e["a0"]), math.radians(e["a1"])])
                if t == "ellipse":
                    self._add(i + ".rx", [e["rx"]]); self._add(i + ".ry", [e["ry"]])
            else:
                for k, p in enumerate(e["pts"]):
                    self._add(f"{i}.pts.{k}", p)
        self.x0 = np.array(self.x0, float)

    def _add(self, name, vals):
        self.idx[name] = list(range(len(self.x0), len(self.x0) + len(vals)))
        self.x0.extend(float(v) for v in vals)

    def point(self, x, ref):
        """[x, y] of a point reference as a function of x."""
        if ref in self.idx and len(self.idx[ref]) == 2:
            a, b = self.idx[ref]
            return np.array([x[a], x[b]])
        eid, _, part = ref.partition(".")
        if part in ("s", "e") and eid + ".a" in self.idx:
            c = self.point(x, eid + ".c"); r = x[self.idx[eid + ".r"][0]]
            ang = x[self.idx[eid + ".a"][0 if part == "s" else 1]]
            return c + r * np.array([math.cos(ang), math.sin(ang)])
        raise SketchError(f"Unknown point {ref}.")

    def is_point(self, ref):
        try:
            self.point(self.x0, ref)
            return True
        except SketchError:
            return False

    def line(self, x, eid):
        e = self.ents.get(eid)
        if not e or e["type"] != "line":
            raise SketchError(f"{eid} is not a line.")
        return self.point(x, eid + ".p0"), self.point(x, eid + ".p1")

    def radius(self, x, eid):
        if eid + ".r" not in self.idx:
            raise SketchError(f"{eid} has no radius.")
        return x[self.idx[eid + ".r"][0]]


def _unit(v):
    n = math.hypot(v[0], v[1])
    return v / n if n > 1e-12 else v


def _residuals(V: _Vars, cons, x):
    r = []
    for c in cons:
        t, a, b = c["type"], c.get("a", ""), c.get("b")
        val = c.get("value")
        if t == "coincident":
            r += list(V.point(x, a) - V.point(x, b))
        elif t in ("horizontal", "vertical"):
            if V.is_point(a) and b:                         # two points level / plumb
                p, q = V.point(x, a), V.point(x, b)
            else:
                p, q = V.line(x, a)
            r.append((q[1] - p[1]) if t == "horizontal" else (q[0] - p[0]))
        elif t in ("parallel", "perpendicular"):
            p0, p1 = V.line(x, a); q0, q1 = V.line(x, b)
            u, v = _unit(p1 - p0), _unit(q1 - q0)
            r.append((u[0] * v[1] - u[1] * v[0]) if t == "parallel" else (u @ v))
        elif t == "equal":
            ea, eb = V.ents.get(a.split(".")[0]), V.ents.get((b or "").split(".")[0])
            if not ea or not eb:
                raise SketchError("equal needs two entities.")
            def size(e):
                if e["type"] == "line":
                    p, q = V.line(x, e["id"]); return np.linalg.norm(q - p)
                return V.radius(x, e["id"])
            r.append(size(ea) - size(eb))
        elif t == "concentric":
            r += list(V.point(x, a + ".c") - V.point(x, b + ".c"))
        elif t == "tangent":
            ea, eb = V.ents.get(a), V.ents.get(b)
            if not ea or not eb:
                raise SketchError("tangent needs two entities.")
            if ea["type"] != "line" and eb["type"] == "line":
                ea, eb = eb, ea
            if ea["type"] == "line":                        # line-circle: distance centre->line == r
                p, q = V.line(x, ea["id"]); cc = V.point(x, eb["id"] + ".c")
                u = _unit(q - p)
                r.append(abs(u[0] * (cc[1] - p[1]) - u[1] * (cc[0] - p[0])) - V.radius(x, eb["id"]))
            else:                                           # circle-circle: external (or internal if closer)
                c1, c2 = V.point(x, ea["id"] + ".c"), V.point(x, eb["id"] + ".c")
                r1, r2 = V.radius(x, ea["id"]), V.radius(x, eb["id"])
                d = np.linalg.norm(c2 - c1)
                r.append(min(abs(d - (r1 + r2)), abs(d - abs(r1 - r2))) * (1 if d >= abs(r1 - r2) else -1))
        elif t == "lock":
            p = V.point(x, a)
            r += list((p - np.array(c["at"])) * 10.0) if "at" in c else []
        elif t == "length":
            p, q = V.line(x, a)
            r.append(np.linalg.norm(q - p) - val)
        elif t == "radius":
            r.append(V.radius(x, a) - val)
        elif t == "distance":
            r.append(np.linalg.norm(V.point(x, b) - V.point(x, a)) - val)
        elif t == "angle":
            p0, p1 = V.line(x, a); q0, q1 = V.line(x, b)
            u, v = _unit(p1 - p0), _unit(q1 - q0)
            ang = math.atan2(u[0] * v[1] - u[1] * v[0], u @ v)
            r.append(math.sin((abs(ang) - math.radians(val))) * 10)
        elif t == "midpoint":
            p, q = V.line(x, b)
            r += list(V.point(x, a) - (p + q) / 2)
    return np.array(r, float)


def solve(sk: dict) -> dict:
    """Solve the sketch's constraints. Returns {sketch, ok, residual, dof_estimate, message}."""
    from scipy.optimize import least_squares
    sk = check(sk)
    V = _Vars(sk["entities"])
    cons = []
    for c in sk["constraints"]:
        c = dict(c)
        if c["type"] == "lock":                    # lock pins the point where it is NOW
            c["at"] = V.point(V.x0, c["a"]).tolist()
        cons.append(c)
    for c in cons:                                  # surface bad references as a clear error
        if c["type"] in ("length", "radius", "distance", "angle") and c.get("value") is None:
            raise SketchError(f"{c['type']} needs a value.")
    if not cons:
        return {"sketch": sk, "ok": True, "residual": 0.0, "dof_estimate": len(V.x0), "message": "Nothing to solve."}
    _residuals(V, cons, V.x0)
    w = 1e-3                                        # pull toward the drawn values: smallest change wins
    f = lambda x: np.concatenate([_residuals(V, cons, x), w * (x - V.x0)])
    res = least_squares(f, V.x0, method="lm" if len(f(V.x0)) >= len(V.x0) else "trf", xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=4000)
    x = res.x
    for _ in range(3):                              # polish without the pull so constraints are exact
        g = lambda y: _residuals(V, cons, y)
        try:
            r2 = least_squares(g, x, method="trf", xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=2000)
            x = r2.x
        except ValueError:
            break
    resid = float(np.abs(_residuals(V, cons, x)).max(initial=0.0))
    J = _jac(lambda y: _residuals(V, cons, y), x)
    rank = int(np.linalg.matrix_rank(J, tol=1e-7)) if J.size else 0
    out = _write(sk, V, x)
    ok = resid < 1e-5
    return {"sketch": out, "ok": ok, "residual": resid, "dof_estimate": max(0, len(x) - rank),
            "message": "Solved." if ok else "Some constraints conflict; showing the closest fit."}


def _jac(fn, x, h=1e-7):
    f0 = fn(x)
    J = np.zeros((len(f0), len(x)))
    for i in range(len(x)):
        y = x.copy(); y[i] += h
        J[:, i] = (fn(y) - f0) / h
    return J


def _write(sk, V, x):
    ents = []
    for e in sk["entities"]:
        e = dict(e); i = e["id"]; t = e["type"]
        g = lambda n: [float(x[k]) for k in V.idx[n]]
        if t == "line":
            e["p0"], e["p1"] = g(i + ".p0"), g(i + ".p1")
        elif t in ("arc", "circle", "ellipse", "polygon"):
            e["c"] = g(i + ".c")
            if t in ("arc", "circle", "polygon"):
                e["r"] = abs(g(i + ".r")[0])
            if t == "arc":
                a0, a1 = g(i + ".a"); e["a0"], e["a1"] = math.degrees(a0), math.degrees(a1)
            if t == "ellipse":
                e["rx"], e["ry"] = abs(g(i + ".rx")[0]), abs(g(i + ".ry")[0])
        else:
            e["pts"] = [g(f"{i}.pts.{k}") for k in range(len(e["pts"]))]
        ents.append(e)
    return {"entities": ents, "constraints": sk["constraints"]}


# ------------------------------------------------------------------ plane
NAMED_PLANES = {"XY": ([0, 0, 0], [0, 0, 1], [1, 0, 0]), "XZ": ([0, 0, 0], [0, -1, 0], [1, 0, 0]),
                "YZ": ([0, 0, 0], [1, 0, 0], [0, 1, 0])}


def plane(p, _depth: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(origin, xdir, ydir, normal) from "XY"/"XZ"/"YZ", {origin, normal, xdir?}, or a construction plane:
    {"offset": {"base": <plane>, "distance": d}} or {"mid": [<plane>, <plane>]} (the two must be parallel)."""
    if isinstance(p, dict) and ("offset" in p or "mid" in p):
        if _depth >= 3:
            raise SketchError("Construction planes nest too deep.")
        if "offset" in p:
            spec = p["offset"]
            if not isinstance(spec, dict):
                raise SketchError("offset plane needs {base, distance}.")
            return offset_plane(spec.get("base", "XY"), spec.get("distance", 0), _depth + 1)
        pair = p["mid"]
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise SketchError("midplane needs two planes.")
        return mid_plane(pair[0], pair[1], _depth + 1)
    if isinstance(p, str):
        if p not in NAMED_PLANES:
            raise SketchError("plane must be XY, XZ, YZ or {origin, normal}.")
        o, n, xd = NAMED_PLANES[p]
    elif isinstance(p, dict):
        o = [_f(v, "plane origin") for v in (p.get("origin") or [0, 0, 0])[:3]]
        n = [_f(v, "plane normal", -1e3, 1e3) for v in (p.get("normal") or [0, 0, 1])[:3]]
        xd = p.get("xdir")
        if xd is not None:
            xd = [_f(v, "plane xdir", -1e3, 1e3) for v in xd[:3]]
    else:
        raise SketchError("plane must be XY, XZ, YZ or {origin, normal}.")
    o, n = np.array(o, float), np.array(n, float)
    if len(o) != 3 or len(n) != 3 or np.linalg.norm(n) < 1e-9:
        raise SketchError("Bad plane.")
    n = n / np.linalg.norm(n)
    if xd is None or abs(np.dot(xd, n)) > 0.99 * np.linalg.norm(xd) or np.linalg.norm(xd) < 1e-9:
        ref = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
        xd = ref - n * (ref @ n)
    xd = np.array(xd, float); xd = xd - n * (xd @ n); xd /= np.linalg.norm(xd)
    yd = np.cross(n, xd)
    return o, xd, yd, n


def offset_plane(base, distance, _depth: int = 0):
    """The base plane moved `distance` mm along its normal (same in-plane axes)."""
    d = _f(distance, "offset distance")
    o, xd, yd, n = plane(base, _depth)
    return o + n * d, xd, yd, n


def mid_plane(a, b, _depth: int = 0):
    """The plane halfway between two parallel planes; keeps a's normal and axes."""
    oa, xa, ya, na = plane(a, _depth)
    ob, _, _, nb = plane(b, _depth)
    if abs(float(na @ nb)) < 0.999:
        raise SketchError("Midplane needs two parallel planes or faces.")
    gap = float((ob - oa) @ na)
    return oa + na * (gap / 2), xa, ya, na
