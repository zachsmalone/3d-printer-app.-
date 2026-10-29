"""Printer-address safety: stop the server being used to reach addresses it must never dial.

A printer saved in Settings is dialed BY THE SERVER (connection test, G-code upload). On a shared
server that turns any saved address into a server-side request, so shared mode refuses addresses
that point back at the server itself or at private/internal networks (loopback, link-local cloud
metadata, RFC1918 LAN ranges). Local mode keeps everything: ZEIM runs on the user's own computer,
next to the printer, and loopback/LAN addresses are the normal case there.

Self-hosters who deliberately run shared mode on a machine inside the printer's LAN can set
PHOTO3D_LAN_PRINTERS=1 to allow private LAN ranges (loopback and link-local stay blocked).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

MAX_URL_LEN = 300

# Always blocked in shared mode: the server's own loopback, link-local (incl. cloud metadata
# endpoints like 169.254.169.254), multicast and reserved space. Never a printer.
_ALWAYS_BLOCKED = [
    ipaddress.ip_network("0.0.0.0/8"), ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"), ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"), ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"), ipaddress.ip_network("ff00::/8"),
]
# Private LAN ranges: blocked in shared mode unless the operator opted in (self-hosted on the
# printer's LAN). Never a printer on a hosted server.
_LAN_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]


class PrinterURLProblem(ValueError):
    """A printer address that must not be saved or dialed."""


def parse_printer_url(url: object) -> str:
    """Structural validation for every printer address, in every mode: http(s) only, a host,
    no credentials, a parseable port, a sane length. Returns the cleaned URL string."""
    v = (url or "").strip() if isinstance(url, str) else ""
    if not v:
        return ""
    if len(v) > MAX_URL_LEN:
        raise PrinterURLProblem("Printer address is too long.")
    u = urlsplit(v)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise PrinterURLProblem("Printer address must start with http:// or https://")
    if u.username or u.password:
        raise PrinterURLProblem("Printer address cannot contain a username or password.")
    try:
        u.port
    except ValueError:
        raise PrinterURLProblem("Printer address has an invalid port.") from None
    return v


def _denied(ip: str, *, lan_ok: bool) -> bool:
    a = ipaddress.ip_address(ip)
    if any(a in net for net in _ALWAYS_BLOCKED):
        return True
    return not lan_ok and any(a in net for net in _LAN_RANGES)


def shared_mode_denial(url: str, *, lan_ok: bool) -> str | None:
    """The reason this address may not be dialed on a shared server, or None if it is fine.

    Resolves the host and checks every address it maps to; a hostname that does not resolve is
    left to the connection test to report (it is not a security problem)."""
    try:
        u = urlsplit(url)
        host = u.hostname or ""
        if not host:
            return "Printer address has no host."
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, ValueError):
        return None
    for info in infos:
        ip = info[4][0]
        try:
            if _denied(ip, lan_ok=lan_ok):
                if lan_ok:
                    return ("On a shared server the printer address cannot point at the server's own machine "
                            "(loopback or link-local). Give the printer's LAN address, or run ZEIM in local mode.")
                return ("On a shared server the printer address cannot point at the server's own machine or a private "
                        "network address: the server must never be used to reach internal addresses. Use the printer's "
                        "public address, or run ZEIM on a computer on the same network as the printer.")
        except ValueError:
            continue
    return None
