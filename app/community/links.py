"""Public profile links. A person types a handle or a page link. ZEIM stores an https URL.

OAuth is separate and optional. These links do not need it, and they do not post anywhere.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from . import safety

# Order is the order in Settings and on a profile.
PLATFORMS = (
    {"id": "tiktok", "label": "TikTok", "hosts": frozenset({"tiktok.com"})},
    {"id": "instagram", "label": "Instagram", "hosts": frozenset({"instagram.com"})},
    {"id": "reddit", "label": "Reddit", "hosts": frozenset({"reddit.com", "old.reddit.com"})},
    {"id": "patreon", "label": "Patreon", "hosts": frozenset({"patreon.com"})},
    {"id": "youtube", "label": "YouTube", "hosts": frozenset({"youtube.com", "m.youtube.com"})},
    {"id": "x", "label": "X", "hosts": frozenset({"x.com", "twitter.com", "mobile.twitter.com"})},
    {"id": "website", "label": "Website", "hosts": frozenset()},
)
_BY_ID = {p["id"]: p for p in PLATFORMS}

_HANDLE = {
    "tiktok": re.compile(r"^[A-Za-z0-9._-]{2,24}$"),
    "instagram": re.compile(r"^[A-Za-z0-9._]{1,30}$"),
    "reddit": re.compile(r"^[A-Za-z0-9_-]{3,21}$"),
    "patreon": re.compile(r"^[A-Za-z0-9_-]{1,40}$"),
    "x": re.compile(r"^[A-Za-z0-9_]{1,15}$"),
}
_YT_AT = re.compile(r"^[A-Za-z0-9._-]{3,30}$")
_YT_ID = re.compile(r"^UC[A-Za-z0-9_-]{16,30}$")

_ICONS = {
    "tiktok": '<path d="M9 8v8a3 3 0 1 1-2-2.8M9 8c.6 2 2.2 3.2 4.2 3.4"/>',
    "instagram": '<rect x="5" y="5" width="14" height="14" rx="4"/><circle cx="12" cy="12" r="3.2"/><circle cx="16.5" cy="7.5" r=".8" fill="currentColor" stroke="none"/>',
    "reddit": '<circle cx="12" cy="13" r="6"/><circle cx="9.5" cy="12.5" r=".6" fill="currentColor" stroke="none"/><circle cx="14.5" cy="12.5" r=".6" fill="currentColor" stroke="none"/><path d="M9.5 15.2c.8.7 1.6 1 2.5 1s1.7-.3 2.5-1M14.5 8.5l2-2"/>',
    "patreon": '<circle cx="12" cy="12" r="6"/><path d="M12 8v8"/>',
    "youtube": '<rect x="4" y="7" width="16" height="10" rx="2"/><path d="M11 10l4 2-4 2z" fill="currentColor" stroke="none"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "website": '<circle cx="12" cy="12" r="7"/><path d="M5 12h14M12 5c2 2.2 2 9.6 0 14M12 5c-2 2.2-2 9.6 0 14"/>',
}


def clean(links: dict) -> dict:
    """Keep only known places. Empty text removes that place. Raises ValueError for a bad link."""
    if not isinstance(links, dict):
        raise ValueError("Send each place as text.")
    out = {}
    for key, value in links.items():
        spec = _BY_ID.get(key)
        if not spec:
            raise ValueError("That isn't one of the places you can link.")
        raw = _raw(value)
        if not raw:
            continue
        if len(raw) > 300:
            raise ValueError(f"{spec['label']} is too long.")
        url, handle = _normalize(key, raw)
        _words_ok(handle, spec["label"])
        out[key] = {"handle": handle, "url": url, "verified": False}
    return out


def for_display(stored: dict | None) -> list[dict]:
    """Https links safe to show. A stored row that no longer parses is left off."""
    if not isinstance(stored, dict):
        return []
    out = []
    for spec in PLATFORMS:
        row = stored.get(spec["id"])
        if not isinstance(row, dict):
            continue
        raw = str(row.get("url") or row.get("handle") or "").strip()
        if not raw:
            continue
        try:
            url, handle = _normalize(spec["id"], raw)
        except ValueError:
            continue
        if not url.startswith("https://"):
            continue
        out.append({"id": spec["id"], "label": spec["label"], "url": url, "handle": handle})
    return out


def anchors(rows: list[dict] | None) -> str:
    """Small icon links. Each one opens in a new tab and does not pass rank."""
    from html import escape
    bits = []
    for row in rows or []:
        url = str(row.get("url") or "")
        if not url.startswith("https://"):
            continue
        label = str(row.get("label") or row.get("id") or "Link")
        icon = _ICONS.get(row.get("id") or "", '<circle cx="12" cy="12" r="5"/>')
        bits.append(
            f'<a class="soc" href="{escape(url, quote=True)}" target="_blank" rel="noopener nofollow ugc" '
            f'aria-label="{escape(label)}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
            f'stroke="currentColor" stroke-width="1.7" aria-hidden="true" focusable="false">{icon}</svg></a>'
        )
    if not bits:
        return ""
    return '<p class="soclinks">' + "".join(bits) + "</p>"


def _raw(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("url") or value.get("handle") or "").strip()
    raise ValueError("Use a name or a link.")


def _words_ok(text: str, label: str) -> None:
    """Language filter on the name, not on the URL, so a real website is not refused for being a link."""
    flat = re.sub(r"[^A-Za-z0-9]+", " ", text or "").strip()
    if flat:
        safety.check(flat, f"{label} link")
    if text and re.fullmatch(r"[0-9 .+\-()]{7,}", text):
        safety.check(text, f"{label} link")


def _normalize(key: str, raw: str) -> tuple[str, str]:
    spec = _BY_ID[key]
    if key == "website":
        return _website(raw)
    parsed = _split_url(raw)
    if parsed is None:
        handle = raw.strip().lstrip("@").split("?")[0].strip().strip("/")
        return _from_handle(key, handle, "at"), handle
    host, segs = parsed
    if host not in spec["hosts"]:
        raise ValueError(f"That link isn't a {spec['label']} profile.")
    kind, handle = _from_path(key, segs)
    return _from_handle(key, handle, kind), handle


def _from_handle(key: str, handle: str, kind: str) -> str:
    if key == "youtube" and kind == "channel":
        if not _YT_ID.match(handle):
            raise ValueError("That YouTube channel link doesn't look right.")
        return f"https://www.youtube.com/channel/{handle}"
    if key == "youtube":
        if not _YT_AT.match(handle):
            raise ValueError("Use a YouTube name of 3 to 30 letters, numbers, . _ or -.")
        if kind == "c":
            return f"https://www.youtube.com/c/{handle}"
        if kind == "user":
            return f"https://www.youtube.com/user/{handle}"
        return f"https://www.youtube.com/@{handle}"
    rule = _HANDLE[key]
    label = _BY_ID[key]["label"]
    if not rule.match(handle):
        raise ValueError(f"Use a {label} name, or paste the profile link.")
    if key == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    if key == "instagram":
        return f"https://www.instagram.com/{handle}"
    if key == "reddit":
        return f"https://www.reddit.com/user/{handle}"
    if key == "patreon":
        return f"https://www.patreon.com/{handle}"
    if key == "x":
        return f"https://x.com/{handle}"
    raise ValueError(f"Use a {label} name, or paste the profile link.")


def _from_path(key: str, segs: list[str]) -> tuple[str, str]:
    if not segs:
        raise ValueError(f"Use your {_BY_ID[key]['label']} profile link.")
    low = [s.lower() for s in segs]
    if key == "tiktok":
        if low[0] in ("foryou", "explore", "discover", "live", "tag"):
            raise ValueError("Use your TikTok profile link.")
        if len(segs) > 1:
            raise ValueError("Use your TikTok profile, not a single video.")
        return "at", segs[0][1:] if segs[0].startswith("@") else segs[0]
    if key == "instagram":
        if low[0] in ("p", "reel", "reels", "stories", "explore", "accounts", "tv", "direct"):
            raise ValueError("Use your Instagram profile, not a single post.")
        if len(segs) > 1:
            raise ValueError("Use your Instagram profile, not a single post.")
        return "at", segs[0]
    if key == "reddit":
        if low[0] == "r":
            raise ValueError("Use your Reddit profile, not a community.")
        if low[0] in ("user", "u") and len(segs) >= 2:
            if len(segs) > 2:
                raise ValueError("Use your Reddit profile, not a single post.")
            return "at", segs[1]
        raise ValueError("Use your Reddit profile link.")
    if key == "patreon":
        if low[0] in ("posts", "login", "join", "oauth2"):
            raise ValueError("Use your Patreon page.")
        if low[0] in ("c", "cw") and len(segs) >= 2:
            if len(segs) > 2:
                raise ValueError("Use your Patreon page, not a single post.")
            return "at", segs[1]
        if len(segs) > 1:
            raise ValueError("Use your Patreon page, not a single post.")
        return "at", segs[0]
    if key == "youtube":
        if low[0] in ("watch", "shorts", "playlist", "live", "feed", "results", "clip"):
            raise ValueError("Use your YouTube page, not a video.")
        if segs[0].startswith("@"):
            if len(segs) > 1:
                raise ValueError("Use your YouTube page, not a video.")
            return "at", segs[0][1:]
        if low[0] == "channel" and len(segs) >= 2:
            return "channel", segs[1]
        if low[0] in ("c", "user") and len(segs) >= 2:
            return low[0], segs[1]
        if len(segs) == 1:
            return "at", segs[0]
        raise ValueError("Use your YouTube page, not a video.")
    if key == "x":
        if low[0] in ("home", "explore", "search", "i", "intent", "share", "settings", "messages", "compose", "tos", "privacy"):
            raise ValueError("Use your X profile link.")
        if len(segs) > 1:
            raise ValueError("Use your X profile, not a single post.")
        return "at", segs[0].lstrip("@")
    raise ValueError("Use a name or a profile link.")


def _split_url(raw: str):
    text = raw.strip()
    if text.startswith("@") and "://" not in text and "/" not in text:
        return None
    looks = "://" in text or text.startswith("www.") or ("/" in text and "." in text.split("/")[0])
    if not looks:
        return None
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Use an https profile link.")
    if parts.username or parts.password:
        raise ValueError("That link has a username in it. Use the public page.")
    host = (parts.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host in ("youtu.be",):
        raise ValueError("Use your YouTube page, not a video.")
    segs = [p for p in parts.path.split("/") if p]
    return host, segs


def _website(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if "@" in text and "://" not in text:
        raise ValueError("Use a website address, not an email.")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise ValueError("Use an https link for your website.")
    if parts.username or parts.password:
        raise ValueError("That link has a username in it. Use the public page.")
    host = (parts.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        shown = host[4:]
    else:
        shown = host
    if not shown or "." not in shown or shown in ("localhost",) or shown.endswith(".local") or shown.endswith(".localhost"):
        raise ValueError("Use a public website address.")
    try:
        ipaddress.ip_address(shown)
    except ValueError:
        pass
    else:
        raise ValueError("Use a public website address.")
    path = parts.path or ""
    if "\\" in path or ".." in path.split("/"):
        raise ValueError("That website link isn't usable.")
    if path == "/":
        path = ""
    query = ("?" + parts.query) if parts.query else ""
    url = "https://" + shown + path + query
    if len(url) > 300:
        raise ValueError("That website link is too long.")
    _words_ok(shown + " " + path.replace("/", " "), "Website")
    return url, shown
