"""Per-deploy version query on static JS/CSS, so a phone does not keep an old module after a release.

Safari has been seen to reuse JS modules even when the server sends Cache-Control: no-cache
and an ETag. HTML stays no-cache and points at /static/file.js?v=<deploy>, and an import map
sends every module import (including relative ones that resolve to /static/...) to that same
version. Unversioned /static/*.js requests stay no-cache so existing revalidation tests hold.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from .config import ROOT, STATIC

_ATTR = re.compile(
    r'(?P<pre>\b(?:src|href)\s*=\s*(?P<q>["\']))'
    r'(?P<url>/static/[^"\']+?\.(?:js|css))'
    r'(?P<qs>\?[^"\']*)?'
    r'(?P=q)',
    re.I,
)
_IMPORTMAP = re.compile(
    r'(<script\s+type=["\']importmap["\']\s*>)(.*?)(</script>)',
    re.I | re.S,
)
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def _deploy_sha() -> str:
    for name in (".deploy-sha", "DEPLOYED_COMMIT.txt"):
        path = ROOT / name
        try:
            token = path.read_text(encoding="utf-8").strip().split()[0]
        except OSError:
            continue
        if re.fullmatch(r"[0-9A-Fa-f]{7,40}", token):
            return token.lower()[:12]
    return ""


def _content_version() -> str:
    h = hashlib.sha256()
    for f in sorted(STATIC.rglob("*")):
        if f.is_file() and f.suffix.lower() in {".js", ".css"}:
            h.update(f.relative_to(STATIC).as_posix().encode())
            h.update(b"\0")
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def asset_version() -> str:
    return _deploy_sha() or _content_version()


ASSET_VERSION = asset_version()


def _with_v(url: str, qs: str | None, ver: str) -> str:
    items: list[str] = []
    found = False
    if qs:
        for part in qs[1:].split("&"):
            if part.startswith("v="):
                items.append(f"v={ver}")
                found = True
            elif part:
                items.append(part)
    if not found:
        items.append(f"v={ver}")
    return url + "?" + "&".join(items)


def _js_map(ver: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in sorted(STATIC.rglob("*.js")):
        if not f.is_file():
            continue
        rel = f.relative_to(STATIC).as_posix()
        if rel == "sw.template.js":
            continue
        url = "/static/" + rel
        out[url] = f"{url}?v={ver}"
    return out


def _merge_imports(existing: dict, ver: str) -> dict:
    imports = dict(existing.get("imports") or {})
    for key, val in list(imports.items()):
        if isinstance(val, str) and val.startswith("/static/") and re.search(r"\.(js|css)$", val.split("?", 1)[0]):
            path, qs = (val.split("?", 1) + [""])[:2]
            imports[key] = _with_v(path, ("?" + qs) if qs else None, ver)
    imports.update(_js_map(ver))
    existing = dict(existing)
    existing["imports"] = imports
    return existing


def _ensure_importmap(html: str, ver: str) -> str:
    # Only pages that already have a map, or load ES modules, need one.
    # A classic <script src> (the workbench) is stamped via ?v= on the tag alone.
    low = html.lower()
    has_module = 'type="module"' in low or "type='module'" in low
    has_dynamic = 'import("/static/' in html or "import('/static/" in html
    if not _IMPORTMAP.search(html) and not has_module and not has_dynamic:
        return html
    payload = _merge_imports({}, ver)
    body = json.dumps(payload, separators=(",", ":"), sort_keys=False)
    m = _IMPORTMAP.search(html)
    if m:
        try:
            current = json.loads(m.group(2))
            if not isinstance(current, dict):
                current = {}
        except json.JSONDecodeError:
            current = {}
        body = json.dumps(_merge_imports(current, ver), separators=(",", ":"), sort_keys=False)
        return html[: m.start()] + m.group(1) + body + m.group(3) + html[m.end() :]
    tag = f'<script type="importmap">{body}</script>'
    lower = html.lower()
    idx = lower.find("<head>")
    if idx >= 0:
        at = idx + len("<head>")
        return html[:at] + tag + html[at:]
    idx = lower.find("<script")
    if idx >= 0:
        return html[:idx] + tag + html[idx:]
    return html


def stamp_html(html: str, ver: str | None = None) -> str:
    ver = ver or ASSET_VERSION

    def repl(m: re.Match) -> str:
        return f"{m.group('pre')}{_with_v(m.group('url'), m.group('qs'), ver)}{m.group('q')}"

    return _ensure_importmap(_ATTR.sub(repl, html), ver)


def csp_for_html(html: str) -> str:
    """Same policy as app.main.CSP, with hashes taken from the stamped page (the import map changes)."""
    hashes = []
    for m in _INLINE_SCRIPT.finditer(html):
        digest = hashlib.sha256(m.group(1).encode()).digest()
        hashes.append("'sha256-" + base64.b64encode(digest).decode() + "'")
    script = " ".join(["'self'", *hashes])
    return (
        "default-src 'self'; script-src " + script + "; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    )


def cache_control_for(path: str, query_v: str | None) -> str:
    path = path.lower()
    if path.endswith((".webp", ".png", ".jpg", ".jpeg", ".svg", ".ico")):
        return "public, max-age=86400"
    if path.endswith((".js", ".css")) and query_v == ASSET_VERSION:
        return "public, max-age=31536000, immutable"
    return "no-cache"




def _without_headers(headers, *names) -> dict[str, str]:
    drop = {n.lower() for n in names}
    return {k: v for k, v in headers.items() if k.lower() not in drop}


def _set_header(headers: dict[str, str], name: str, value: str) -> None:
    for k in list(headers):
        if k.lower() == name.lower():
            del headers[k]
    headers[name] = value


async def stamp_html_responses(request: Request, call_next):
    """Rewrite every HTML response so script and stylesheet URLs carry the deploy version."""
    resp = await call_next(request)
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype != "text/html":
        return resp
    chunks: list[bytes] = []
    async for chunk in resp.body_iterator:
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return Response(content=raw, status_code=resp.status_code, headers=dict(resp.headers), media_type=ctype)
    stamped = stamp_html(text)
    if stamped == text:
        # Body already consumed; replay the original bytes and headers unchanged
        # (coming-soon keeps its tighter CSP and no-store).
        headers = _without_headers(resp.headers, "content-length")
        return Response(content=raw, status_code=resp.status_code, headers=headers, media_type=ctype)
    headers = _without_headers(resp.headers, "content-length", "content-type")
    cc = ""
    for k, v in list(headers.items()):
        if k.lower() == "cache-control":
            cc = v
            break
    if "no-store" not in cc.lower():
        _set_header(headers, "Cache-Control", "no-cache")
    # Only recompute CSP when inline script bodies changed (the import map).
    # Otherwise keep the global policy, which also covers sharetest/builder hashes.
    if _INLINE_SCRIPT.findall(text) != _INLINE_SCRIPT.findall(stamped):
        _set_header(headers, "Content-Security-Policy", csp_for_html(stamped))
    return HTMLResponse(stamped, status_code=resp.status_code, headers=headers)
