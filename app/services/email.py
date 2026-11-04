"""Shared email module (RET7 digest, ONB9 setup help, expiry warning). SWITCHED OFF by default.

Sends only when ZEIM_EMAIL_ENABLED=1 AND CLOUDFLARE_EMAIL_TOKEN is set; otherwise every send is a
logged no-op. Provider: Cloudflare Email Service REST API, from noreply@zeimapp.com ("ZEIM").

Opt-in only. ZEIM's auth store keeps only a keyed hash of each email address, so nobody can be mailed
unless they explicitly opt in here, which stores the address in DATA/email_optin.json (chmod 600).
That is a change to the privacy page's "sign-in codes only" promise: update it BEFORE turning this on.
Every message carries an unsubscribe link (+ List-Unsubscribe header) that removes the address.

RET7 (weekly digest) is NOT transactional; Cloudflare Email Service is for transactional mail only.
It is built default-off and refuses to send unless ZEIM_EMAIL_DIGEST_ALLOWED=1 (another provider)."""
from __future__ import annotations

import hashlib, hmac, html, json, logging, os, secrets, threading
from pathlib import Path
from urllib.parse import quote

from .. import config

log = logging.getLogger("zeim.email")
ACCOUNT = "589efa2a3041d62f3b04dd398bcce6b7"
ENDPOINT = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/email/sending/send"
FROM = {"address": "noreply@zeimapp.com", "name": "ZEIM"}
SITE = os.environ.get("ZEIM_PUBLIC_URL", "https://zeimapp.com").rstrip("/")
KINDS = ("setup", "expiry", "digest")        # what a person can opt in to, separately
_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("ZEIM_EMAIL_ENABLED", "0") == "1" and bool(os.environ.get("CLOUDFLARE_EMAIL_TOKEN"))


# ---------- opt-in store ----------
def _store() -> Path:
    return Path(config.DATA) / "email_optin.json"


def _load() -> dict:
    try: return json.loads(_store().read_text())
    except Exception: return {}


def _save(d: dict):
    p = _store(); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(d)); os.chmod(tmp, 0o600); tmp.replace(p)


def opt_in(user_id: str, address: str, kinds) -> dict:
    kinds = [k for k in kinds if k in KINDS]
    if "@" not in address or not kinds:
        raise ValueError("an address and at least one kind are required")
    with _lock:
        d = _load(); d[user_id] = {"address": address.strip(), "kinds": sorted(set(kinds))}; _save(d)
    return d[user_id]


def opt_out(user_id: str, kind: str | None = None):
    with _lock:
        d = _load(); row = d.get(user_id)
        if not row: return
        row["kinds"] = [k for k in row["kinds"] if kind and k != kind]
        if not row["kinds"]: d.pop(user_id)        # last kind gone: the address is deleted too
        _save(d)


def subscribed(user_id: str, kind: str) -> str | None:
    row = _load().get(user_id)
    return row["address"] if row and kind in row["kinds"] else None


# ---------- unsubscribe tokens ----------
def _secret() -> bytes:
    p = Path(config.DATA) / "email_secret"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(secrets.token_hex(32)); os.chmod(p, 0o600)
    return p.read_text().strip().encode()


def unsub_token(user_id: str) -> str:
    return hmac.new(_secret(), b"unsub\0" + user_id.encode(), hashlib.sha256).hexdigest()[:32]


def unsub_url(user_id: str) -> str:
    return f"{SITE}/api/email/unsubscribe?u={quote(user_id)}&t={unsub_token(user_id)}"


def check_unsub(user_id: str, token: str) -> bool:
    return hmac.compare_digest(unsub_token(user_id), token or "")


# ---------- templates (plain, humble; html + text) ----------
def _wrap(title: str, paras: list[str], link: tuple[str, str] | None, uid: str) -> tuple[str, str]:
    u = unsub_url(uid)
    text = "\n\n".join([title, *paras] + ([f"{link[0]}: {link[1]}"] if link else []) +
                       [f"You get this because you asked for it. Stop these emails: {u}"])
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paras)
    btn = f'<p><a href="{html.escape(link[1])}">{html.escape(link[0])}</a></p>' if link else ""
    h = (f'<div style="font-family:system-ui,sans-serif;max-width:520px;color:#222"><h2 style="font-size:18px">{html.escape(title)}</h2>'
         f'{body}{btn}<hr style="border:0;border-top:1px solid #ddd"><p style="font-size:12px;color:#666">You get this because you asked for it. '
         f'<a href="{html.escape(u)}">Stop these emails</a>.</p></div>')
    return h, text


SETUP = {
    1: ("Welcome to ZEIM", ["Thanks for making an account. If you'd like a first step, the Learn tab has a short lesson called \"Your first print\"."], ("Open the lesson", f"{SITE}/#learn/first-print")),
    3: ("Setting up your printer in ZEIM", ["You can tell ZEIM which printer you have, so sizes and settings match it. It's under the printer switch at the top of the app."], ("Open ZEIM", f"{SITE}/")),
    7: ("Keeping your builds", ["Builds are removed after a while unless you star them. Starred builds stay until you delete them."], ("See my builds", f"{SITE}/#account")),
}


def render(kind: str, uid: str, **kw) -> tuple[str, str, str]:
    """-> (subject, html, text)"""
    if kind == "setup":
        title, paras, link = SETUP[int(kw.get("day", 1))]
    elif kind == "expiry":
        n, days = int(kw.get("count", 1)), int(kw.get("days", 3))
        title = "Some builds will be removed soon"
        paras = [f"{n} of your builds {'is' if n == 1 else 'are'} due to be removed in about {days} day{'s' if days != 1 else ''}. Star a build to keep it."]
        link = ("See my builds", f"{SITE}/#account")
    elif kind == "digest":
        items = [str(t) for t in kw.get("titles", [])][:5]
        title = "Projects you haven't opened in a while"
        paras = ["These are waiting where you left them: " + ", ".join(items) + "." if items else "Your projects are waiting where you left them."]
        link = ("Open my projects", f"{SITE}/#account")
    else:
        raise ValueError(kind)
    h, t = _wrap(title, paras, link, uid)
    return title, h, t


# ---------- send ----------
def send(user_id: str, kind: str, **kw) -> dict:
    """Send one message if (and only if) the person opted in to this kind and email is switched on."""
    to = subscribed(user_id, kind)
    if not to:
        return {"sent": False, "reason": "not opted in"}
    if kind == "digest" and os.environ.get("ZEIM_EMAIL_DIGEST_ALLOWED", "0") != "1":
        log.info("email: digest skipped (not transactional; not allowed on Cloudflare Email Service)")
        return {"sent": False, "reason": "digest not allowed on this provider"}
    subject, h, t = render(kind, user_id, **kw)
    payload = {"from": FROM, "to": [to], "subject": subject, "html": h, "text": t,
               "headers": {"List-Unsubscribe": f"<{unsub_url(user_id)}>"}}
    if not enabled():
        log.info("email (off, not sent): kind=%s user=%s subject=%r", kind, user_id, subject)
        return {"sent": False, "reason": "email switched off", "payload": payload}
    import httpx
    r = httpx.post(ENDPOINT, json=payload, timeout=15,
                   headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_EMAIL_TOKEN']}"})
    ok = r.status_code < 300
    log.info("email: kind=%s user=%s status=%s", kind, user_id, r.status_code)
    return {"sent": ok, "status": r.status_code}
