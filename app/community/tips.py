"""Optional tip link a creator may add to their own project (one link, https only).

Shown as a quiet link on the model page. Never prompted, never counted, never ranked.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

MAX_LEN = 300
_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def check(url) -> str:
    """'' clears the link. Anything else must be a plain https:// URL to a public host name."""
    if url is None:
        return ""
    if not isinstance(url, str):
        raise ValueError("The tip link must be text.")
    url = url.strip()
    if not url:
        return ""
    if len(url) > MAX_LEN:
        raise ValueError(f"The tip link can be at most {MAX_LEN} characters.")
    if any(ord(ch) < 33 or ch in '"<>\\`' for ch in url):
        raise ValueError("The tip link can't contain spaces or special characters.")
    try:
        p = urlsplit(url)
    except ValueError:
        raise ValueError("That doesn't look like a web link.")
    if p.scheme.lower() != "https":
        raise ValueError("The tip link must start with https://")
    if p.username or p.password or "@" in p.netloc:
        raise ValueError("The tip link can't include a login.")
    host = (p.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        raise ValueError("Use a web address with a name, not a number address.")
    except ValueError as e:
        if "number address" in str(e):
            raise
    if not _HOST.match(host) or host.endswith(".local") or host == "localhost":
        raise ValueError("That doesn't look like a public web address.")
    try:
        p.port
    except ValueError:
        raise ValueError("That doesn't look like a web link.")
    return url
