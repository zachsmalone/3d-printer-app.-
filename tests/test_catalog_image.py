"""Repo catalogs must be in the image at /app/data.

Clicking Resin or My Printer calls print_setup.public() -> printer_public() -> nozzle_options() -> specs().
specs() reads Path(__file__).parents[2] / "data" / "nozzles" / "nozzle-specs.json", which is /app/data/...
in the container. PHOTO3D_DATA (/data) is runtime user state and does not carry these files.

The image only receives files that survive .dockerignore. `data/**` drops runtime files at any depth;
`!data/<catalog>` puts the tracked JSON back. Uploads, accounts, and keys stay out.
"""
import json
import posixpath
import re
import subprocess
from pathlib import Path

from app.services import print_setup as ps

ROOT = Path(__file__).resolve().parents[1]

# Paths production reads next to the app package (parents[2] of the module file).
CATALOG_SOURCES = {
    "app/services/print_setup.py": (
        'parents[2] / "data" / "nozzles" / "nozzle-specs.json"',
        'parents[2] / "data" / "materials" / "filaments.json"',
    ),
    "app/core/resin.py": ('parents[2] / "data" / "resin" / "resin.json"',),
    "app/services/calibration.py": ('parents[2] / "data" / "smartfix" / "smartfix-map.json"',),
    "app/core/smartsplit.py": ('parents[2] / "data" / "split" / "split-specs.json"',),
    "app/services/doctor.py": ('parents[2] / "data" / "troubleshooting" / "problems.json"',),
}

# User state that must never be sent as build context, even if it sits in the checkout's data/.
RUNTIME_EXCLUDED = (
    "data/settings.json",
    "data/users.json",
    "data/projects.json",
    "data/link.key",
    "data/auth.sqlite3",
    "data/projects/abc/model.stl",
    "data/fonts/Upload.ttf",
    "data/classrooms.json",
)


def test_resin_and_my_printer_load_catalogs_beside_the_app_package():
    """The Resin 500 was FileNotFoundError on this nozzle-specs path. Load it the way production does."""
    root = Path(ps.__file__).resolve().parents[2]
    assert ps.SPECS_PATH == root / "data" / "nozzles" / "nozzle-specs.json"
    assert ps.FILAMENTS_PATH == root / "data" / "materials" / "filaments.json"
    assert ps.SPECS_PATH.is_file() and ps.FILAMENTS_PATH.is_file()
    body = ps.public()
    resin = [p for p in body["printers"] if p["technology"] == "Resin"]
    assert resin and all(p["nozzles"] == [] and p["nozzle_options"] == [] for p in resin)
    assert "0.4" in ps.specs()["nozzles"]
    for rel, snippets in CATALOG_SOURCES.items():
        text = (root / rel).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in text, rel
    for rel in (
        "data/nozzles/nozzle-specs.json",
        "data/materials/filaments.json",
        "data/resin/resin.json",
        "data/smartfix/smartfix-map.json",
        "data/split/split-specs.json",
        "data/troubleshooting/problems.json",
    ):
        path = root / rel
        assert path.is_file(), rel
        json.loads(path.read_text(encoding="utf-8"))


def test_image_build_copies_catalogs_and_not_runtime_data():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY data ./data" in dockerfile
    assert "PHOTO3D_DATA=/data" in dockerfile
    compose = (ROOT / "reports/deploy/docker-compose.yml").read_text(encoding="utf-8")
    assert "${ZEIM_HOST_DIR:-/srv/zeim}/data:/data" in compose
    assert "../../data:/app/data:ro" in compose
    assert "../../data:/data" not in compose
    patterns = _dockerignore_patterns(ROOT / ".dockerignore")
    assert "data" not in patterns
    tracked = subprocess.check_output(["git", "ls-files", "data"], cwd=ROOT, text=True).splitlines()
    catalogs = [p for p in tracked if p.endswith((".json", ".md"))]
    assert any(p.endswith("nozzle-specs.json") for p in catalogs)
    assert any(p.endswith("resin.json") for p in catalogs)
    for rel in catalogs:
        assert _in_build_context(rel, patterns), rel
    for rel in RUNTIME_EXCLUDED:
        assert not _in_build_context(rel, patterns), rel
    assert _in_build_context(".env.example", patterns)
    assert not _in_build_context(".env", patterns)
    assert not _in_build_context("tests/test_app.py", patterns)
    assert _in_build_context("app/services/print_setup.py", patterns)


class _Pattern:
    def __init__(self, kind, pattern, prefix, suffix, regex, exception):
        self.kind = kind
        self.pattern = pattern
        self.prefix = prefix
        self.suffix = suffix
        self.regex = regex
        self.exception = exception

    def matches(self, path):
        if self.kind == "exact":
            return path == self.pattern
        if self.kind == "prefix":
            return path.startswith(self.prefix)
        if self.kind == "suffix":
            if path.endswith(self.suffix):
                return True
            return bool(self.suffix) and self.suffix[0] == "/" and path == self.suffix[1:]
        return self.regex.search(path) is not None


def _dockerignore_patterns(path):
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        patterns.append(line.strip())
    return patterns


def _compile(pattern):
    """moby/patternmatcher compile: `**` at the end is a prefix, leading `**` is a suffix, `*` does not cross `/`."""
    reg = "^"
    detected = "exact"
    pos = 0
    token = 0
    n = len(pattern)
    while pos < n:
        ch = pattern[pos]
        pos += 1
        if ch == "*":
            if pos < n and pattern[pos] == "*":
                pos += 1
                if pos < n and pattern[pos] == "/":
                    pos += 1
                if pos >= n:
                    if detected == "exact":
                        detected = "prefix"
                    else:
                        reg += ".*"
                        detected = "regexp"
                else:
                    reg += "(?:.*" + re.escape("/") + ")?"
                    detected = "regexp"
                if token == 0:
                    detected = "suffix"
            else:
                reg += "[^/]*"
                detected = "regexp"
        elif ch == "?":
            reg += "[^/]"
            detected = "regexp"
        elif ch in ".+()|{}$":
            reg += "\\" + ch
        elif ch == "\\":
            if pos < n:
                reg += "\\" + pattern[pos]
                pos += 1
            detected = "regexp"
        elif ch in "[]":
            reg += ch
            detected = "regexp"
        else:
            reg += ch
        token += 1
    if detected == "regexp":
        return detected, None, None, re.compile(reg + "$")
    if detected == "prefix":
        return detected, pattern[:-2], None, None
    if detected == "suffix":
        return detected, None, pattern[2:], None
    return detected, None, None, None


def _parsed(raw_patterns):
    parsed = []
    for raw in raw_patterns:
        cleaned = posixpath.normpath(raw.strip())
        exception = cleaned.startswith("!")
        pattern = cleaned[1:] if exception else cleaned
        if exception:
            pattern = posixpath.normpath(pattern)
        if pattern in ("", "."):
            continue
        kind, prefix, suffix, regex = _compile(pattern)
        parsed.append(_Pattern(kind, pattern, prefix, suffix, regex, exception))
    return parsed


def _excludes(path, raw_patterns):
    """True when moby MatchesOrParentMatches would ignore this path (last matching rule wins)."""
    path = posixpath.normpath(path)
    matched = False
    parent = posixpath.dirname(path)
    parents = []
    if parent not in ("", "."):
        acc = []
        for part in parent.split("/"):
            acc.append(part)
            parents.append("/".join(acc))
    for pat in _parsed(raw_patterns):
        if pat.exception != matched:
            continue
        match = pat.matches(path)
        if not match:
            for candidate in parents:
                if pat.matches(candidate):
                    match = True
                    break
        if match:
            matched = not pat.exception
    return matched


def _in_build_context(rel, raw_patterns):
    """A file is sent only when the walk can enter every parent. An excluded directory hides its children."""
    rel = posixpath.normpath(rel.strip("/"))
    acc = []
    for part in rel.split("/"):
        acc.append(part)
        if _excludes("/".join(acc), raw_patterns):
            return False
    return True
