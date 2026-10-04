#!/usr/bin/env python3
"""Red-team: which user-input paths run through the language/PII gate, and are they consistent?
Uses FastAPI TestClient against a THROWAWAY app state (PHOTO3D_OUT / PHOTO3D_DATA -> fresh /tmp dirs). Never touches live data or :8765.
Run: PYTHONPATH=/workspace/photo3d /workspace/photo3d/.venv/bin/python /workspace/photo3d/reports/filter_redteam_paths.py
Abusive test strings are generated from the app's own word lists at runtime and printed MASKED.
"""
import os, sys, tempfile, json, re, time
_tmp = tempfile.mkdtemp(prefix="rt_paths_")
os.environ["PHOTO3D_OUT"] = _tmp + "/out"; os.environ["PHOTO3D_DATA"] = _tmp + "/data"; os.environ["PHOTO3D_ADMIN_TOKEN"] = "rt-admin"
sys.path.insert(0, "/workspace/photo3d")
from fastapi.testclient import TestClient
from app.main import app
from app.community import safety as S
from tests.make_sample import make

L = S._L.load()
def mask(w): return w[0] + "*" * (len(w) - 1)
words = sorted(w for w in L.words if re.fullmatch(r"[a-z]{4,6}", w) and w not in L.allow_words and S.scan_language(w))
stem_w = next(w for w in words if any(s in w for s in L.stems))
non_stem = next(w for w in words if not any(s in w for s in L.stems) and not S.scan_language(w[:2] + "_" + w[2:]) is None is False)
# a non-stem word whose mid-split bypasses the filter (to test nickname regex)
non_stem = next(w for w in words if not any(s in w for s in L.stems) and S.scan_language(w[:2] + "-" + w[2:]) is None)
CYR = {"a": "а", "e": "е", "o": "о", "c": "с", "p": "р", "x": "х", "i": "і"}
cyr = lambda w: "".join(CYR.get(c, c) for c in w)
VARIANTS = {
    "plain": lambda w: w,
    "Cyrillic homoglyph": cyr,
    "ZWSP mid": lambda w: w[:2] + "\u200b" + w[2:],
    "mid-split with '-'": lambda w: w[:2] + "-" + w[2:],
    "plain email": None, "obfuscated email 'x at gmail dot com'": None, "10-digit phone": None, "URL no scheme .com": None,
    "URL no scheme .xyz": None, "bare @handle": None, "'snap me'": None,
}
PAYLOAD = {
    "plain email": "kid@example.com", "obfuscated email 'x at gmail dot com'": "kid at gmail dot com", "10-digit phone": "5551234567",
    "URL no scheme .com": "example.com", "URL no scheme .xyz": "example.xyz", "bare @handle": "@coolkid99", "'snap me'": "snap me",
}
rows = []
def rec(path, field, variant, status, extra=""):
    rows.append({"path": path, "field": field, "variant": variant, "http": status, "result": "BLOCKED" if status in (400, 413, 422) else ("accepted" if status in (200, 201) else f"other:{status}"), "note": extra})
    print(f"{path:44s} {field:14s} {variant:38s} -> {status} {extra}")

def txt(w, v):
    return PAYLOAD[v] if v in PAYLOAD else VARIANTS[v](w)

def client(): return TestClient(app)
adult = client(); assert adult.post("/api/me/signup", json={"display_name": "Ada Adult", "dob": "1985-05-05"}).status_code == 200
other = client(); assert other.post("/api/me/signup", json={"display_name": "Ola Other", "dob": "1990-01-01"}).status_code == 200

print("== signup display_name ==")
for v in VARIANTS:
    c = client(); r = c.post("/api/me/signup", json={"display_name": txt(stem_w if v != 'mid-split with \'-\'' else non_stem, v), "dob": "1990-01-01"})
    rec("POST /api/me/signup", "display_name", v, r.status_code, (r.json().get("detail") or r.json().get("message") or "")[:40] if r.status_code != 200 else "")

print("== profile links (/api/me/links) handle ==")
for v in ("plain", "Cyrillic homoglyph", "mid-split with '-'", "10-digit phone", "bare @handle"):
    w = non_stem if v.startswith("mid") else stem_w
    h = txt(w, v)
    r = adult.put("/api/me/links", json={"instagram": h})
    rec("PUT /api/me/links", "instagram", v, r.status_code, "(only a charset regex [A-Za-z0-9._-] is applied)" if r.status_code == 200 else (r.text[:50]))
r = adult.put("/api/me/links", json={"tiktok": "5551234567"}); rec("PUT /api/me/links", "tiktok", "10-digit phone as handle", r.status_code)
r = adult.put("/api/me/links", json={"reddit": "kid.gmail.com"}); rec("PUT /api/me/links", "reddit", "domain-like handle", r.status_code)

print("== classroom name / nickname ==")
room = None
for v in ("plain", "Cyrillic homoglyph", "ZWSP mid", "mid-split with '-'", "plain email", "10-digit phone"):
    w = non_stem if v.startswith("mid") else stem_w
    r = adult.post("/api/classrooms", json={"name": txt(w, v), "password": "plum-otter-42"})
    rec("POST /api/classrooms", "name", v, r.status_code)
    if r.status_code == 200 and room is None: room = r.json()["code"]
if room is None:
    room = adult.post("/api/classrooms", json={"name": "Maker Class", "password": "plum-otter-42"}).json()["code"]
for v in ("plain", "Cyrillic homoglyph", "ZWSP mid", "mid-split with '-'", "10-digit phone", "URL no scheme .com"):
    w = non_stem if v.startswith("mid") else stem_w
    c = client(); r = c.post("/api/classrooms/join", json={"code": room, "nickname": txt(w, v), "password": "plum-otter-42"})
    rec("POST /api/classrooms/join", "nickname", v, r.status_code, (str(r.json().get("detail") or r.json().get("message"))[:48] if r.status_code != 200 else ""))

print("== builds / titles / filenames ==")
img = make(_tmp + "/s.png")
def build(c, title="", filename="s.png"):
    r = c.post("/api/generate", files={"file": (filename, open(img, "rb"), "image/png")}, data={"mode": "relief", "width_mm": "40", "resolution": "30", "title": title})
    return r
r = build(adult, title=stem_w); rec("POST /api/generate", "title", "plain (private build)", r.status_code, "(accepted)" if r.status_code == 200 else r.text[:60])
bid_bad = r.json().get("id") if r.status_code == 200 else None
r = build(adult, filename=stem_w + ".png"); rec("POST /api/generate", "upload filename", "plain (becomes default title)", r.status_code, "(accepted)" if r.status_code == 200 else r.text[:60])
bid_fn = r.json().get("id") if r.status_code == 200 else None
if bid_fn:
    t = adult.get(f"/api/builds/{bid_fn}").json().get("title"); print("   stored build title from filename (masked):", mask(t) if t else t)
bid_ok = build(adult, title="My print").json()["id"]

print("== showcase publish ==")
def pub(c, bid, title="Cool print", desc="", tags=None):
    return c.post("/api/showcase", json={"title": title, "description": desc, "tags": tags or [], "build_id": bid, "accept_guidelines": True, "visibility": "private"})
for fld in ("title", "description", "tag"):
    for v in ("plain", "Cyrillic homoglyph", "ZWSP mid", "mid-split with '-'", "plain email", "obfuscated email 'x at gmail dot com'", "10-digit phone", "URL no scheme .com", "URL no scheme .xyz", "bare @handle", "'snap me'"):
        w = non_stem if v.startswith("mid") else stem_w
        t = txt(w, v)
        kw = {"title": dict(title=t), "description": dict(desc=t), "tag": dict(tags=[t])}[fld]
        r = pub(adult, bid_ok, **kw)
        rec("POST /api/showcase", fld, v, r.status_code, ("code=" + str(r.json().get("code"))) if r.status_code == 422 and isinstance(r.json(), dict) else "")
r = pub(adult, bid_ok, tags="abcdefghij"); rec("POST /api/showcase", "tags (string)", "tags given as a str", r.status_code)
r = pub(adult, bid_ok, tags=[1, None, {"a": 1}]); rec("POST /api/showcase", "tags (non-str)", "tags with non-str items", r.status_code)

print("== classroom submit + feedback ==")
stu = client(); assert stu.post("/api/classrooms/join", json={"code": room, "nickname": "student1", "password": "plum-otter-42"}).status_code == 200
bid_stu = build(stu, title="Student part").json()["id"]
for v in ("plain", "Cyrillic homoglyph", "mid-split with '-'", "plain email"):
    w = non_stem if v.startswith("mid") else stem_w
    r = stu.post(f"/api/classrooms/{room}/projects", json={"build_id": bid_stu, "title": txt(w, v)})
    rec("POST /api/classrooms/{c}/projects", "title", v, r.status_code)
r = stu.post(f"/api/classrooms/{room}/projects", json={"build_id": bid_stu, "title": ""}); pid = r.json().get("id"); rec("POST /api/classrooms/{c}/projects", "title", "empty -> falls back to build title", r.status_code)
if bid_fn:
    # student with a build whose default title came from an abusive filename
    stu2 = client(); stu2.post("/api/classrooms/join", json={"code": room, "nickname": "student2", "password": "plum-otter-42"})
    b2 = build(stu2, filename=stem_w + ".png").json()["id"]
    r = stu2.post(f"/api/classrooms/{room}/projects", json={"build_id": b2}); rec("POST /api/classrooms/{c}/projects", "title (from filename)", "plain via default title", r.status_code)
for v in ("plain", "Cyrillic homoglyph", "ZWSP mid", "mid-split with '-'", "plain email", "obfuscated email 'x at gmail dot com'", "10-digit phone", "URL no scheme .xyz", "'snap me'"):
    w = non_stem if v.startswith("mid") else stem_w
    r = adult.post(f"/api/classrooms/{room}/projects/{pid}/feedback", json={"comment": txt(w, v)})
    rec("POST /api/classrooms/{c}/projects/{p}/feedback", "comment", v, r.status_code)

print("== reports (moderation) free text ==")
r = other.get("/api/showcase"); 
r = adult.post("/api/showcase", json={"title": "Public one", "description": "", "tags": [], "build_id": bid_ok, "accept_guidelines": True, "visibility": "public"})
iid = r.json().get("id") if r.status_code == 200 else None
if iid:
    r = other.post(f"/api/showcase/{iid}/report", json={"reason": "other", "details": stem_w + " kid@example.com 5551234567"})
    rec("POST /api/showcase/{id}/report", "details", "plain (moderator-only)", r.status_code, "(stored unfiltered, max 1000 chars; reaches moderators only)")

print("== edit workspace ==")
import trimesh
stl = trimesh.creation.box([20, 20, 10]).export(file_type="stl")
r = adult.post("/api/edit/new", files={"file": ("part.stl", stl, "application/octet-stream")}, data={"title": stem_w}); rec("POST /api/edit/new", "title", "plain (private)", r.status_code, ("" if r.status_code == 200 else str(r.json().get("detail"))[:48]))
r = adult.post("/api/edit/new", files={"file": (stem_w + ".stl", stl, "application/octet-stream")}); rec("POST /api/edit/new", "upload filename", "plain (default title)", r.status_code, "")

print("== benign text through the real API (false positives users would actually hit) ==")
for fld, t in [("description", "Material: PLA, 0.2 mm layers. More information in the README. License: CC BY."), ("title", "Rabbit chair"), ("description", "A bit chunky but it prints fine"),
               ("title", "Mini game tokens"), ("tag", "hard"), ("description", "Print is hard but I've gotten better"), ("title", "Map of Niger and Nigeria"), ("description", "Snap fit lid, no supports")]:
    kw = {"title": dict(title=t), "description": dict(desc=t), "tag": dict(tags=[t])}[fld]
    r = pub(adult, bid_ok, **kw)
    rec("POST /api/showcase (benign)", fld, t[:36], r.status_code, ("code=" + str(r.json().get("code"))) if r.status_code == 422 and isinstance(r.json(), dict) else "")

print("== error shape consistency ==")
shapes = {}
c = client(); r = c.post("/api/me/signup", json={"display_name": stem_w, "dob": "1990-01-01"}); shapes["signup display_name"] = (r.status_code, sorted(r.json().keys()))
r = adult.post("/api/classrooms", json={"name": stem_w, "password": "plum-otter-42"}); shapes["classroom name"] = (r.status_code, sorted(r.json().keys()))
c = client(); r = c.post("/api/classrooms/join", json={"code": room, "nickname": stem_w, "password": "plum-otter-42"}); shapes["nickname"] = (r.status_code, sorted(r.json().keys()))
r = pub(adult, bid_ok, title=stem_w); shapes["showcase title"] = (r.status_code, sorted(r.json().keys()))
r = adult.post(f"/api/classrooms/{room}/projects/{pid}/feedback", json={"comment": stem_w}); shapes["feedback"] = (r.status_code, sorted(r.json().keys()))
r = stu.post(f"/api/classrooms/{room}/projects", json={"build_id": bid_stu, "title": stem_w}); shapes["student project title"] = (r.status_code, sorted(r.json().keys()))
for k, v in shapes.items(): print(f"{k:24s} {v}")

print("\n== stored data check: did anything unfiltered reach public listing? ==")
pubs = other.get("/api/showcase").json()
print("public listing items:", len(pubs) if isinstance(pubs, list) else list(pubs.keys()))
out = {"stem_word_masked": mask(stem_w), "nonstem_word_masked": mask(non_stem), "rows": rows, "error_shapes": {k: list(v[1]) + [v[0]] for k, v in shapes.items()}}
open("/workspace/photo3d/reports/filter-redteam-paths-results.json", "w").write(json.dumps(out, ensure_ascii=False, indent=1))
print("temp dir (disposable):", _tmp)
