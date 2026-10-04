"""Profile link-outs to a creator's other accounts (unverified until OAuth verification exists)."""
from __future__ import annotations

import re

TEMPLATES = {
    "tiktok": ("TikTok", "https://www.tiktok.com/@{h}"),
    "instagram": ("Instagram", "https://www.instagram.com/{h}"),
    "reddit": ("Reddit", "https://www.reddit.com/user/{h}"),
    "patreon": ("Patreon", "https://www.patreon.com/{h}"),
}
HANDLE = re.compile(r"^[A-Za-z0-9._-]{2,30}$")


def clean(links: dict) -> dict:
    out = {}
    for k, v in (links or {}).items():
        if k not in TEMPLATES:
            raise ValueError(f"unknown platform {k}")
        if not isinstance(v, str) and v is not None:
            raise ValueError(f"{TEMPLATES[k][0]} handle must be text")
        if v and len(v) > 100:
            raise ValueError(f"{TEMPLATES[k][0]} handle is too long (2-30 chars)")
        h = (v or "").strip().lstrip("@")
        if not h:
            continue
        if not HANDLE.match(h):
            raise ValueError(f"{TEMPLATES[k][0]} handle may only contain letters, digits . _ - (2-30 chars)")
        from . import safety
        safety.check(h, f"{TEMPLATES[k][0]} handle")        # same language + personal-info filter as every other text (raises ChatBlocked)
        out[k] = {"handle": h, "url": TEMPLATES[k][1].format(h=h), "verified": False}
    return out
