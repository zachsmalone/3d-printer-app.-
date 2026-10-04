"""Linked accounts (TikTok, Instagram, Reddit, Patreon) - "promote your other accounts" SCAFFOLDING.

Product intent: creators show link-outs to the channels they already use (we sell nothing here).
Handles typed in Settings are displayed as UNVERIFIED link-outs (see community/links.py); OAuth
below is the future path to *verify* a handle. Today OAuth only completes the token handshake -
it does not yet fetch/confirm the handle.

What exists: a provider interface, env-var based OAuth client config, the OAuth2
authorization-code redirect/callback plumbing with `state` checking, and
encrypted-at-rest token storage. What does NOT exist: any posting/sharing call.
`Provider.share()` raises NotImplementedError for every provider, and the OAuth
endpoints/scopes below are unverified against live provider apps.

Config (env vars; a provider is "not configured" until both are set):
    PHOTO3D_<PROVIDER>_CLIENT_ID, PHOTO3D_<PROVIDER>_CLIENT_SECRET
    e.g. PHOTO3D_REDDIT_CLIENT_ID. Redirect URI to register with each provider:
    <public base url>/api/accounts/<provider>/callback
Tokens: Fernet-encrypted in data/accounts.json.enc. Key from PHOTO3D_SECRET_KEY
(a Fernet key) or auto-generated into data/secret.key (chmod 600).

Add a provider = subclass OAuthProvider, fill the class attributes, add to REGISTRY.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from ..config import DATA

_lock = threading.Lock()
_pending: dict[str, dict] = {}  # state -> {provider, created}
TOKENS = DATA / "accounts.json.enc"


def _fernet() -> Fernet:
    env = os.environ.get("PHOTO3D_SECRET_KEY")
    if env:
        return Fernet(env.encode())
    kf = DATA / "secret.key"
    if not kf.exists():
        kf.write_bytes(Fernet.generate_key())
        kf.chmod(0o600)
    return Fernet(kf.read_bytes())


def _load_tokens() -> dict:
    if not TOKENS.exists():
        return {}
    try:
        return json.loads(_fernet().decrypt(TOKENS.read_bytes()))
    except (InvalidToken, ValueError):
        return {}


def _save_tokens(d: dict):
    TOKENS.write_bytes(_fernet().encrypt(json.dumps(d).encode()))
    TOKENS.chmod(0o600)


class OAuthProvider:
    id = ""
    label = ""
    authorize_url = ""
    token_url = ""
    scopes: list[str] = []
    client_id_param = "client_id"       # TikTok uses client_key
    token_auth = "body"                 # "basic" for Reddit
    extra_authorize: dict = {}
    docs = ""
    purpose = ""

    def env(self, what: str) -> str:
        return os.environ.get(f"PHOTO3D_{self.id.upper()}_{what}", "")

    def configured(self) -> bool:
        return bool(self.env("CLIENT_ID") and self.env("CLIENT_SECRET"))

    def authorize_redirect(self, state: str, redirect_uri: str) -> str:
        q = {self.client_id_param: self.env("CLIENT_ID"), "response_type": "code",
             "redirect_uri": redirect_uri, "scope": " ".join(self.scopes), "state": state,
             **self.extra_authorize}
        return f"{self.authorize_url}?{urlencode(q)}"

    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
        auth = None
        if self.token_auth == "basic":
            auth = (self.env("CLIENT_ID"), self.env("CLIENT_SECRET"))
        else:
            data.update({self.client_id_param: self.env("CLIENT_ID"),
                         "client_secret": self.env("CLIENT_SECRET")})
        r = httpx.post(self.token_url, data=data, auth=auth, timeout=30,
                       headers={"User-Agent": "photo3d/0.1"})
        r.raise_for_status()
        tok = r.json()
        tok["obtained_at"] = int(time.time())
        return tok

    def share(self, build: dict, token: dict) -> dict:
        raise NotImplementedError(f"Sharing to {self.label} is not implemented yet (see ROADMAP.md)")


class TikTok(OAuthProvider):
    id, label = "tiktok", "TikTok"
    authorize_url = "https://www.tiktok.com/v2/auth/authorize/"
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    scopes = ["user.info.basic", "video.upload"]
    client_id_param = "client_key"
    docs = "https://developers.tiktok.com/"
    purpose = "Link your channel; later: post build videos"


class Instagram(OAuthProvider):
    id, label = "instagram", "Instagram"
    authorize_url = "https://www.facebook.com/v19.0/dialog/oauth"
    token_url = "https://graph.facebook.com/v19.0/oauth/access_token"
    scopes = ["instagram_basic", "instagram_content_publish"]
    docs = "https://developers.facebook.com/docs/instagram-api/"
    purpose = "Link your profile; later: post build photos"


class Reddit(OAuthProvider):
    id, label = "reddit", "Reddit"
    authorize_url = "https://www.reddit.com/api/v1/authorize"
    token_url = "https://www.reddit.com/api/v1/access_token"
    scopes = ["identity", "submit"]
    token_auth = "basic"
    extra_authorize = {"duration": "permanent"}
    docs = "https://www.reddit.com/dev/api/"
    purpose = "Link your profile; later: post builds to maker subreddits"


class Patreon(OAuthProvider):
    id, label = "patreon", "Patreon"
    authorize_url = "https://www.patreon.com/oauth2/authorize"
    token_url = "https://www.patreon.com/api/oauth2/token"
    scopes = ["identity", "campaigns"]
    docs = "https://docs.patreon.com/"
    purpose = "Link out to your own Patreon page (nothing is sold inside this app)"


REGISTRY: dict[str, OAuthProvider] = {p.id: p for p in (TikTok(), Instagram(), Reddit(), Patreon())}


def status() -> list[dict]:
    toks = _load_tokens()
    out = []
    for p in REGISTRY.values():
        st = "connected" if p.id in toks else ("disconnected" if p.configured() else "not_configured")
        out.append({"id": p.id, "label": p.label, "state": st, "purpose": p.purpose, "docs": p.docs,
                    "env_vars": [f"PHOTO3D_{p.id.upper()}_CLIENT_ID", f"PHOTO3D_{p.id.upper()}_CLIENT_SECRET"],
                    "sharing_implemented": False,
                    "connected_at": toks.get(p.id, {}).get("obtained_at")})
    return out


def begin(provider: str, base_url: str) -> str:
    p = REGISTRY[provider]
    if not p.configured():
        raise RuntimeError("not configured")
    state = secrets.token_urlsafe(24)
    with _lock:
        for s in [s for s, v in _pending.items() if time.time() - v["created"] > 600]:
            _pending.pop(s, None)
        _pending[state] = {"provider": provider, "created": time.time()}
    return p.authorize_redirect(state, f"{base_url.rstrip('/')}/api/accounts/{provider}/callback")


def finish(provider: str, code: str, state: str, base_url: str):
    with _lock:
        pend = _pending.pop(state, None)
    if not pend or pend["provider"] != provider:
        raise ValueError("invalid or expired OAuth state")
    tok = REGISTRY[provider].exchange_code(code, f"{base_url.rstrip('/')}/api/accounts/{provider}/callback")
    with _lock:
        d = _load_tokens()
        d[provider] = tok
        _save_tokens(d)


def disconnect(provider: str):
    with _lock:
        d = _load_tokens()
        d.pop(provider, None)
        _save_tokens(d)
