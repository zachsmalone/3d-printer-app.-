"""Thank-you / credits page data. The WORDS live in app/credits.json (so design and wording can change without touching code).
Facts are read, not typed: Python package versions and licences from the installed package metadata, PrusaSlicer's version/licence from
the system package, three.js from the licence header in the vendored file, makers from the library manifests when they exist.
Anything that cannot be read says so instead of guessing."""
from __future__ import annotations

import json
import re
import subprocess
from functools import lru_cache
from importlib import metadata as md
from pathlib import Path

from ..config import ROOT, STATIC

FILE = Path(__file__).resolve().parent.parent / "credits.json"
UNKNOWN_LICENCE = "see the project page"


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def _licence(m) -> str:
    """Licence from package metadata: SPDX expression, else the trove licence classifiers, else a SHORT License field. Never a guess."""
    expr = (m.get("License-Expression") or "").strip()
    if expr:
        return expr
    cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]]
    if cls:
        return " / ".join(cls)
    lic = (m.get("License") or "").strip()
    return lic if lic and "\n" not in lic and len(lic) <= 40 else UNKNOWN_LICENCE


def _url(m) -> str:
    urls = {}
    for u in m.get_all("Project-URL") or []:
        k, _, v = u.partition(",")
        urls[k.strip().lower()] = v.strip()
    for k in ("homepage", "home", "repository", "source", "documentation"):
        if urls.get(k):
            return urls[k]
    return (m.get("Home-page") or "").strip()


def direct_requirements() -> list[str]:
    """Names in requirements.txt (the packages ZEIM itself asks for)."""
    out = []
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("-"):
            out.append(re.split(r"[=<>~!\[; ]", line, maxsplit=1)[0].strip())
    return out


def python_packages() -> list[dict]:
    out = []
    for name, what in data()["tools"]["python"].items():
        try:
            m = md.metadata(name)
            out.append({"name": name, "version": md.version(name), "licence": _licence(m), "url": _url(m), "what": what})
        except md.PackageNotFoundError:
            out.append({"name": name, "version": "", "licence": UNKNOWN_LICENCE, "url": "", "what": what, "missing": True})
    return sorted(out, key=lambda p: p["name"].lower())


@lru_cache(maxsize=8)
def _dpkg_version(pkg: str) -> str:
    try:
        return subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True, timeout=5).stdout.strip().split("-")[0].split("+")[0]
    except Exception:
        return ""


@lru_cache(maxsize=8)
def _debian_licence(pkg: str) -> str:
    """The licence of the package's main stanza ('Files: *') from /usr/share/doc/<pkg>/copyright."""
    try:
        txt = Path(f"/usr/share/doc/{pkg}/copyright").read_text(errors="replace")
    except OSError:
        return ""
    m = re.search(r"^Files:\s*\*\s*\n(?:[^\n]*\n)*?License:\s*([^\n]+)", txt, re.M)
    return m.group(1).strip() if m else ""


def system_tools() -> list[dict]:
    import shutil
    out = []
    for t in data()["tools"]["system"]:
        found = bool(shutil.which(t["command"]))
        ver = _dpkg_version(t["dpkg"]) if found else ""
        lic = _debian_licence(t["dpkg"]) if found else ""
        out.append({"name": t["name"], "version": ver, "licence": lic or UNKNOWN_LICENCE, "url": t["url"], "what": t["what"], "installed": found})
    return out


def bundled() -> list[dict]:
    out = []
    for b in data()["tools"]["bundled"]:
        try:
            head = (STATIC / b["file"]).read_text(encoding="utf-8")[:600]
        except OSError:
            head = ""
        spdx = re.search(r"SPDX-License-Identifier:\s*([\w.\-+ ]+)", head)
        rev = re.search(r'const t="(\d{2,3})"', head)
        out.append({"name": b["name"], "version": ("r" + rev.group(1)) if rev and "module" in b["file"] else "", "licence": spdx.group(1).strip() if spdx else UNKNOWN_LICENCE,
                    "url": b["url"], "what": b["what"]})
    return out


def is_held(m: dict) -> bool:
    """The one switch (app/credits.json -> hold): NASA and share-alike items stay off public display until cleared."""
    h = data().get("hold", {})
    if not h.get("enabled"):
        return False
    lid = m.get("license_id") or (m.get("license") or {}).get("spdx", "").lower().replace("_", "-")
    if lid in h.get("license_ids", []):
        return True
    if any(x.lower() in (m.get("creator") or "").lower() for x in h.get("creator_contains", [])):
        return True
    src = f"{m.get('source_url', '')} {m.get('source_page_url', '')}".lower()
    return any(x.lower() in src for x in h.get("source_contains", []))


def listable(m: dict) -> bool:
    """A library model may be shown publicly only if it has a manifest entry that is verified, is not in the quarantine, and is not held."""
    if not m.get("id") or not m.get("creator") or m.get("verified") is False:
        return False
    if any("_quarantine" in str(f.get("path", "")) for f in m.get("files", [])) or m.get("status") in ("hold", "removed", "paused", "not_ready"):
        return False
    return not is_held(m)


def makers() -> list[dict]:
    """Creators of library models, from the manifest file(s) when they exist: [{creator, models: [{title, licence, licence_url, url}]}].
    Only manifest entries that pass listable(): nothing quarantined, unverified or held is ever named here."""
    by: dict = {}
    for rel in data()["creators"].get("manifests", []):
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for m in doc.get("models", []):
            if not listable(m):
                continue
            lic = m.get("license") or {}
            by.setdefault(m.get("creator") or "Unknown", []).append({"title": m.get("title", ""), "licence": lic.get("name", ""), "licence_url": lic.get("url", ""),
                                                                      "url": m.get("source_page_url", "")})
    return [{"creator": c, "models": sorted(ms, key=lambda x: x["title"])} for c, ms in sorted(by.items(), key=lambda kv: kv[0].lower())]


def licences() -> dict:
    return {k: v for k, v in data().get("licences", {}).items() if not k.startswith("_")}


def _clean(x, n: int = 200) -> str:
    """Single-line, control-free text (credit strings go into HTML, 3MF XML and STL headers; no newline injection)."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(x or "")).strip()[:n]


def _https(u) -> str:
    u = str(u or "").strip()
    return u if re.match(r"^https://[^\s<>\"']+$", u) else ""


def credit_line(item: dict) -> dict | None:
    """The credit shown on a shared model / Original card and its download page. Keeps the short keys
    {'creator', 'licence', 'licence_url'} and adds the data-file fields of the attribution standard (section 7.1)
    that can be derived. Uses the item's own record (item['credit'] / item['license_id'] / item['license']); a project made on
    ZEIM shows its maker only - no licence is invented."""
    c = item.get("credit") or {}
    lid = c.get("license_id") or item.get("license_id") or ""
    row = licences().get(lid, {}) if lid else {}
    lic = c.get("licence") or c.get("license") or item.get("license") or {}
    if isinstance(lic, str):
        lic = {"name": lic}
    name = row.get("name") or lic.get("name", "")
    url = row.get("url") if row else lic.get("url", "")
    creator = _clean(c.get("creator") or item.get("creator"), 120)
    if not creator:
        return None
    title = _clean(item.get("title"), 120)
    short = f'"{title}" by {creator}' if title else f"by {creator}"
    if name:
        short += f" · {name}"
    if row.get("share_alike"):
        short += " · share-alike"
    full = [short]
    if _https(item.get("source_url")):
        full.append("Source: " + _https(item["source_url"]))
    if name:
        full.append(f"Licence: {name}" + (f" ({url})" if url else ""))
    full.append("Provided as-is, with no warranty (see licence).")
    return {"creator": creator, "licence": name, "licence_url": _https(url), "license_id": lid, "license_name": name,
            "license_url": _https(url), "share_alike": bool(row.get("share_alike")), "creator_url": _https(item.get("creator_url")),
            "creator_verified": bool(item.get("creator_verified", False)), "source_url": _https(item.get("source_url")),
            "credit_line": short[:240], "credit_full": "\n".join(full)}


REQUIRED = ("id", "title", "creator", "license_id", "provenance", "printer", "status")


def validate_record(rec: dict) -> list[str]:
    """Attribution standard 7.1 validator: [] when the record may be shown publicly, else the names of the failing fields."""
    bad = [f for f in REQUIRED if not str(rec.get(f) or "").strip()]
    row = licences().get(rec.get("license_id", ""))
    if rec.get("license_id") and not row:
        bad.append("license_id (not in the fixed table)")
    if row and rec.get("license_id") not in ("private", "class-only") and (rec.get("license_url") or "") != (row.get("url") or ""):
        bad.append("license_url (must match the table)")
    if rec.get("status") != "ready":
        bad.append("status (not ready)")
    if rec.get("printer") and rec["printer"] not in ("fdm", "resin", "both"):
        bad.append("printer")
    if not rec.get("example") and rec.get("third_party") and not _https(rec.get("source_url")):
        bad.append("source_url")
    return bad


def launch_problems() -> list[str]:
    """Things that must be filled in before a public launch (attribution standard D4)."""
    p = []
    if not (data().get("takedown", {}).get("contact") or "").strip():
        p.append("credits takedown contact is still empty (app/credits.json)")
    return p


def assert_launch_ready() -> None:
    import os
    if os.environ.get("PHOTO3D_PUBLIC_LAUNCH") == "1" and launch_problems():
        raise RuntimeError("PHOTO3D_PUBLIC_LAUNCH=1 but: " + "; ".join(launch_problems()))
