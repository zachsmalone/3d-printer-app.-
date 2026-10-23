"""ZEIM is 18+ only: no kid / family / school framing anywhere a visitor can read it.
Scans user-facing text (HTML, Markdown, JS and Python string literals, API JSON). The only allowed mentions are the
safety prohibitions (child-safety reports, CSAM rules, 'especially children' in the photo rule) and code identifiers."""
import os, re
from tests.b1 import client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDS = re.compile(r"\b(kids?|kid's|child|children|family|families|family-friendly|school|schools|classroom|classrooms|teacher|teachers|students?|ages \d|ages \$)\b", re.I)
ALLOW = re.compile(r"minor_safety|minors?\b|unsafe or sexual situation|especially children|child-safety|child safety|csam|not_family_friendly|"
                   r"\.children|children\.|child process|memory-capped child|guarded children|direct children|child dialog|a child:|not a child|"
                   r"firmware family|font|FontProperties|family=|_family|family key|nozzle-specs|Families in nozzle|K1 family|"
                   r"School STEM|school features were removed|school features removed|after\\s\+school|which\)\\s\+school|_PARENTS|parentNode|parentElement|"
                   r"\bkids\b\)|\.\.\.kids|kids\.forEach|kids \|\||\(kids|, kids\)|RESERVED", re.I)
# Detection lists, not shown to anyone: the grooming-phrase detector, reserved usernames and the memory-capped worker.
SKIP_FILES = {os.path.join("app", "community", "safety.py"), os.path.join("app", "community", "usernames.py"), os.path.join("app", "core", "guard.py")}
SKIP_DIRS = {"vendor", "perplexity-workbench", "wordlists", "__pycache__"}
STRING = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`[^`]*`")


def _files():
    for base in ("static", "app"):
        for d, ds, fs in os.walk(os.path.join(ROOT, base)):
            ds[:] = [x for x in ds if x not in SKIP_DIRS]
            for f in fs:
                if f.endswith((".html", ".md", ".js", ".py")) and os.path.relpath(os.path.join(d, f), ROOT) not in SKIP_FILES:
                    yield os.path.join(d, f)


def _hits(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    out = []
    for n, line in enumerate(txt.splitlines(), 1):
        if path.endswith(".py"):
            parts = [m.group(0) for m in STRING.finditer(line)]
        else:
            parts = [line]
        for p in parts:
            for m in WORDS.finditer(p):
                ctx = p[max(0, m.start() - 60): m.end() + 60]
                if not ALLOW.search(ctx):
                    out.append(f"{os.path.relpath(path, ROOT)}:{n}: ...{ctx}...")
    return out


def test_no_kid_family_or_school_wording_in_user_facing_text():
    bad = [h for f in _files() for h in _hits(f)]
    assert not bad, "child/family/school wording found:\n" + "\n".join(bad[:40])


def test_served_pages_and_lessons_have_no_child_framing():
    c = client()
    texts = {u: c.get(u).text for u in ("/", "/static/terms.html", "/legal/community-guidelines", "/static/cad.html")}
    r = c.get("/api/learn/lessons")
    if r.status_code == 200:
        texts["/api/learn/lessons"] = r.text
    for u, t in texts.items():
        for m in WORDS.finditer(t):
            ctx = t[max(0, m.start() - 60): m.end() + 60]
            assert ALLOW.search(ctx), f"{u}: ...{ctx}..."


def test_the_safety_prohibitions_are_still_there():
    g = open(os.path.join(ROOT, "static", "COMMUNITY_GUIDELINES.html"), encoding="utf-8").read()
    assert "Anything that puts a child in an unsafe or sexual situation" in g     # removing wording must never remove a safety rule
    assert 'value="minor_safety"' in open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
