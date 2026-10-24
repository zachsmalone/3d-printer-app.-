"""Printer addresses must never turn the server into a request-forger (SSRF).

Shared mode: saving or dialing a printer address that points at the server's own machine, cloud
metadata, or a private LAN range is refused. Local mode: ZEIM runs on the user's computer next to
the printer, so loopback/LAN addresses stay allowed there (existing behavior, existing tests).
"""
import pytest
from app import config
from app.services import printers, settings
from app.services import netguard
from tests.b1 import ADMIN, ADULT, client


@pytest.fixture
def shared(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")


@pytest.fixture
def lan_on(monkeypatch):
    monkeypatch.setattr(config, "LAN_PRINTERS", True)


def _save(c, url, headers=None, **kw):
    return c.put("/api/settings", json={"printers": [{"name": "P", "type": "moonraker", "url": url, **kw}]}, headers=headers)


# ---- structural validation (every mode) ----------------------------------------------------------------

@pytest.mark.parametrize("url", ["ftp://x", "gopher://x", "http://", "https://", "http://user:pw@printer.local",
                                "http://printer.local:99999", "x" * 500])
def test_malformed_addresses_are_refused_everywhere(url):
    assert _save(client(ADULT), url).status_code == 400


def test_stub_printer_types_keep_loose_addresses():
    # Coming-soon types still allow a placeholder address; implemented types (incl. bambu) do not.
    assert client(ADULT).put("/api/settings", json={"printers": [{"name": "b", "type": "prusalink", "url": "x"}]}).status_code == 200
    assert client(ADULT).put("/api/settings", json={"printers": [{"name": "b", "type": "bambu", "url": "x"}]}).status_code == 400


# ---- local mode stays open (the server sits next to the printer) ------------------------------------------------------

def test_local_mode_allows_loopback_and_lan_addresses():
    c = client(ADULT)
    assert _save(c, "http://127.0.0.1:7125").status_code == 200
    assert _save(c, "http://192.168.1.50/").status_code == 200


# ---- shared mode blocks internal destinations -------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:7125", "http://localhost/", "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",          # cloud metadata endpoint
    "http://10.0.0.5/", "http://172.16.1.5/", "http://192.168.1.5/", "http://100.64.0.7/",
    "http://[::1]/", "http://[fe80::1]/", "http://[fc00::5]/",
])
def test_shared_mode_refuses_internal_addresses(shared, url):
    r = _save(client(ADULT), url, headers=ADMIN)
    assert r.status_code == 400 and ("private" in r.text or "internal addresses" in r.text)


def test_shared_mode_accepts_public_addresses(shared):
    assert _save(client(ADULT), "http://203.0.113.5:7125", headers=ADMIN).status_code == 200


def test_lan_opt_in_allows_private_but_never_loopback_or_metadata(shared, lan_on):
    c = client(ADULT)
    assert _save(c, "http://10.0.0.5/", headers=ADMIN).status_code == 200      # deliberate self-hosted LAN setup
    assert _save(c, "http://192.168.1.50/", headers=ADMIN).status_code == 200
    assert _save(c, "http://127.0.0.1:7125", headers=ADMIN).status_code == 400
    assert _save(c, "http://169.254.169.254/", headers=ADMIN).status_code == 400


def test_shared_mode_denial_message_names_the_reason(shared):
    r = _save(client(ADULT), "http://127.0.0.1:7125", headers=ADMIN)
    assert r.status_code == 400 and "never be used to reach internal addresses" in r.text


# ---- connect-time enforcement (defence in depth: a printer crafted straight into settings.json) ------------------------

def _no_httpx(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the server must not connect to a blocked address")
    monkeypatch.setattr(printers.httpx, "Client", boom)


def test_test_route_refuses_blocked_addresses_without_connecting(shared, monkeypatch):
    _no_httpx(monkeypatch)
    r = printers.test({"name": "x", "type": "moonraker", "url": "http://169.254.169.254/"})
    assert r["ok"] is False and "internal addresses" in r["message"]


def test_send_refuses_blocked_addresses_without_connecting(shared, monkeypatch):
    _no_httpx(monkeypatch)
    r = printers.send({"name": "x", "type": "octoprint", "url": "http://127.0.0.1:8080/"}, None, "n.gcode", False)
    assert r["ok"] is False and "internal addresses" in r["message"]


def test_local_mode_still_connects(monkeypatch):
    """Local mode must keep working exactly as before: the guard only reacts to shared mode."""
    called = []
    class FakeResp:
        status_code = 200; text = "{}"
        def __init__(self, body=None):
            self._body = body
        def json(self):
            return self._body if self._body is not None else {"result": {"klippy_state": "ready", "moonraker_version": "v0.9"}}
    class FakeClient:
        def __init__(self, *a, **k): called.append(a)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, p):
            return FakeResp({"result": {"state": "ready"}} if p == "/printer/info" else None)
    monkeypatch.setattr(printers.httpx, "Client", FakeClient)
    r = printers.test({"name": "x", "type": "moonraker", "url": "http://127.0.0.1:7125"})
    assert r["ok"] is True and called          # the connection was attempted, as it should be


def test_netguard_denial_is_none_for_unresolvable_hosts(shared):
    """A hostname that does not resolve is not a security problem; the connection test reports it."""
    assert netguard.shared_mode_denial("http://no-such-host.invalid/", lan_ok=False) is None
