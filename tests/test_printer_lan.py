"""An adult on a self-host can save and see a LAN printer when both flags are on. The public URL stays put."""
from app import config
from tests.b1 import client, ADULT


def test_adult_saves_lan_printer_without_touching_the_public_url(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    monkeypatch.setattr(config, "LAN_PRINTERS", True)
    monkeypatch.setenv("ZEIM_PRINTER_DIRECT", "1")
    a = client(ADULT)
    assert a.put("/api/settings", json={"public_base_url": "https://evil.example", "printers": []}).status_code == 403
    r = a.put("/api/settings/printers", json={
        "public_base_url": "https://evil.example",
        "printers": [{"name": "K1", "type": "moonraker", "url": "http://10.1.2.3:7125", "profile": "creality_k1"}],
    })
    assert r.status_code == 200, r.text
    body = a.get("/api/settings").json()
    assert body["printer_manage"] is True
    assert body["printers"][0]["url"] == "http://10.1.2.3:7125"
    assert body.get("public_base_url") != "https://evil.example"
    blocked = a.put("/api/settings/printers", json={"printers": [{"name": "meta", "type": "moonraker", "url": "http://169.254.169.254/"}]})
    assert blocked.status_code == 400
    monkeypatch.setattr(config, "LAN_PRINTERS", False)
    assert a.put("/api/settings/printers", json={"printers": []}).status_code == 403
    assert a.get("/api/settings").json()["printers"][0].get("url") in (None, "")
