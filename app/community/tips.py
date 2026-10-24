"""Optional tip link a creator may add to their own project (one link, https only).

Shown as a quiet link on the model page. Never prompted, never counted, never ranked.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit

MAX_LEN = 300
_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
# private / special-use name suffixes that never point at a public tip page
_PRIVATE_SUFFIXES = (".localhost", ".internal", ".local", ".lan", ".home", ".arpa")
# a dotted/dashed IPv4 inside a name (127.0.0.1.nip.io, 10-0-0-1.sslip.io): DNS-rebinding style hosts
_EMBEDDED_IPV4 = re.compile(r"(?:^|[.-])\d{1,3}(?:[.-]\d{1,3}){3}(?:$|[.-])")


# shorteners / open redirectors hide the real destination
_REDIRECTORS = {"bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly", "rebrand.ly", "t.ly",
                "tiny.cc", "rb.gy", "shorturl.at", "s.id", "v.gd", "bl.ink", "lnkd.in", "trib.al", "dlvr.it", "short.io",
                "l.facebook.com", "lm.facebook.com", "out.reddit.com", "href.li", "urlz.fr", "qrco.de"}
_REDIRECT_PATHS = {("google.com", "/url"), ("www.google.com", "/url"), ("youtube.com", "/redirect"), ("www.youtube.com", "/redirect")}


def _has_format_or_control(text: str) -> bool:
    """Unicode format (Cf: zero-width, bidi overrides) or control (Cc: incl. DEL U+007F, U+0085) characters."""
    return any(unicodedata.category(ch) in ("Cf", "Cc") for ch in text)


def domain(url: str) -> str:
    """The host a tip link goes to, for the visible link text."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def check(url) -> str:
    """'' clears the link. Anything else must be a plain https:// URL to a public host name."""
    if url is None:
        return ""
    if not isinstance(url, str):
        raise ValueError("The tip link must be text.")
    if _has_format_or_control(url):          # before strip(): strip() would silently drop U+0085 etc.
        raise ValueError("The tip link can't contain hidden or control characters.")
    url = url.strip()
    if not url:
        return ""
    if len(url) > MAX_LEN:
        raise ValueError(f"The tip link can be at most {MAX_LEN} characters.")
    if _has_format_or_control(url) or _has_format_or_control(unquote(url)):
        raise ValueError("The tip link can't contain hidden or control characters.")
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
    if (not _HOST.match(host) or host == "localhost" or host.endswith(_PRIVATE_SUFFIXES)
            or _EMBEDDED_IPV4.search(host)):
        raise ValueError("That doesn't look like a public web address.")
    if any(lbl.startswith("xn--") for lbl in host.split(".")):
        raise ValueError("Please use the plain web address (no look-alike international characters).")
    bare = host[4:] if host.startswith("www.") else host
    if host in _REDIRECTORS or bare in _REDIRECTORS or (host, (p.path or "/").rstrip("/").lower()) in _REDIRECT_PATHS:
        raise ValueError("Please link straight to your tip page, not a link shortener or redirect.")
    from . import safety
    rest = re.sub(r"[/?&=#+;,]+", " ", unquote(f"{p.path} {p.query} {p.fragment}"))
    if safety.scan_contact(f" {rest} "):
        raise ValueError("The tip link can't include an email address or phone number.")
    try:
        p.port
    except ValueError:
        raise ValueError("That doesn't look like a web link.")
    # scheme and host are case-insensitive: store them lowercase so every client renders the link
    return urlunsplit(("https", p.netloc.lower(), p.path, p.query, p.fragment))
