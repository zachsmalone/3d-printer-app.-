"""App factory. Run: uvicorn app.main:app --port 8765"""
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import branding
from .api import builds, community, edit, learn, printing
from .api import settings as settings_api
from . import config
from .config import STATIC

import logging as _logging

_log = _logging.getLogger("uvicorn.error")
if config.HOST not in config.LOOPBACK_HOSTS:
    _log.warning("ZEIM is set to listen on %s (not just this computer). There is NO real authentication yet: "
                 "anyone who can reach this address can use it. Use only on a trusted network.", config.HOST)
if config.MODE == "local" and config.HOST not in config.LOOPBACK_HOSTS:
    _log.warning("PHOTO3D_MODE=local while listening beyond this computer: printer/settings changes are open to everyone who can connect.")

import re as _re


class RedactTokens(_logging.Filter):
    """Signed /f/<token>/... links must not be readable in server.log (anyone with log access could replay them while live)."""
    _PAT = _re.compile(r"(/f/)[^/\s?\"]+")

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(self._PAT.sub(r"\1[redacted]", a) if isinstance(a, str) else a for a in record.args)
        if isinstance(record.msg, str):
            record.msg = self._PAT.sub(r"\1[redacted]", record.msg)
        return True


for _n in ("uvicorn.access", "uvicorn.error", "uvicorn"):
    _lg = _logging.getLogger(_n)
    if not any(isinstance(f, RedactTokens) for f in _lg.filters):
        _lg.addFilter(RedactTokens())

_aud = _logging.getLogger("zeim.audit")      # settings changes that matter for safety (class code + time, never names)
if not _aud.handlers:
    _h = _logging.StreamHandler(); _h.setFormatter(_logging.Formatter("%(asctime)s AUDIT %(message)s"))
    _aud.addHandler(_h); _aud.setLevel(_logging.INFO); _aud.propagate = False

_docs = {} if config.API_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title=f"{branding.PRODUCT_NAME} (photo3d)", version="0.3", **_docs)
for r in (builds.router, edit.router, printing.router, printing.files_router, settings_api.router,
          community.router, learn.router, learn.pages):
    app.include_router(r)
try:
    from .community import privacy as _privacy
    _privacy.migrate_minors()          # existing 13-17 data -> current teen posture (idempotent)
except Exception:                      # never block start-up on a migration problem
    import logging
    logging.getLogger("zeim").exception("minor data migration failed")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def limit_json_body(request: Request, call_next):
    """JSON endpoints never need big bodies; refuse them before they are parsed (uploads use multipart and have their own caps)."""
    from fastapi.responses import JSONResponse
    from .api.textcap import MAX_JSON_BODY
    ct = request.headers.get("content-type", "")
    if ct.startswith("application/json"):
        try:
            n = int(request.headers.get("content-length", "0") or 0)
        except ValueError:
            n = 0
        if n > MAX_JSON_BODY:
            return JSONResponse(status_code=413, content={"detail": "Request too large."})
    return await call_next(request)


def _inline_script_hashes() -> str:
    """CSP hashes of the few inline <script> blocks our own pages have (the importmap, the share-test page) so no 'unsafe-inline' is needed for scripts."""
    import base64, hashlib, re
    out = []
    for f in ("index.html", "sharetest.html"):
        try:
            html = (STATIC / f).read_text(encoding="utf-8")
        except OSError:
            continue
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
            out.append("'sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode() + "'")
    return " ".join(out)


CSP = ("default-src 'self'; script-src 'self' " + _inline_script_hashes() + "; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    h = resp.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=()")
    h.setdefault("Content-Security-Policy", CSP)
    if request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=15552000")
    return resp


@app.middleware("http")
async def ensure_session_cookie(request: Request, call_next):
    """Give every visitor a session id on their FIRST request (even if that request fails), so rate limits and
    ownership checks always see a stable identity."""
    from .community.identity import COOKIE
    import secrets
    if request.url.path == "/healthz":          # health probes must not mint sessions
        return await call_next(request)
    sid = request.cookies.get(COOKIE)
    new = None
    if not sid or len(sid) < 16:
        new = secrets.token_urlsafe(24)
        raw = request.scope["headers"]
        existing = [v for k, v in raw if k == b"cookie"]
        raw[:] = [(k, v) for k, v in raw if k != b"cookie"]
        raw.append((b"cookie", ((existing[0].decode() + "; ") if existing else "").encode() + f"{COOKIE}={new}".encode()))
    resp = await call_next(request)
    if new:
        from .community.identity import cookie_args
        resp.set_cookie(COOKIE, new, max_age=3600 * 24 * 365, **cookie_args(request))
    return resp


from .community.safety import ChatBlocked as _ChatBlocked


@app.exception_handler(_ChatBlocked)
async def _chat_blocked(request: Request, exc: _ChatBlocked):
    """ONE error shape for every refused text: HTTP 422 (413 too long, 503 filter unavailable) with code, message, context and detail."""
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status, content={**exc.payload, "detail": exc.payload.get("message", "")})


@app.get("/sharetest", include_in_schema=False)
def sharetest():
    """SEND-0: hidden, unlinked page for finding out what the iOS share sheet accepts. Adults only (the page checks /api/me; the file endpoint enforces it)."""
    return FileResponse(STATIC / "sharetest.html", headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"})


@app.get("/healthz", include_in_schema=False)
def healthz():
    """Liveness probe for containers / uptime monitors: no auth, no cookies, no user data."""
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC / "favicon.ico")
