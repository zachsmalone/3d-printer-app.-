"""K1: printer preset (NOT a new printer type), read-only connection test, one bed for Slice and Send."""
import json, socket, threading, time
import pytest, uvicorn
from fastapi import FastAPI
from app import config
from app.services import printers, settings, slicer
from tests.b1 import client, photo_build, ADULT, SUSPENDED, UNDER18


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _mock(port, state="ready", status=200):
    m = FastAPI(); seen = []
    @m.middleware("http")
    async def log(request, call_next):
        seen.append((request.method, request.url.path)); return await call_next(request)
    @m.get("/server/info")
    async def si():
        from fastapi.responses import JSONResponse
        return JSONResponse({"result": {"klippy_state": state, "moonraker_version": "v0.9"}}, status_code=status)
    @m.get("/printer/info")
    async def pi(): return {"result": {"state": state}}
    srv = uvicorn.Server(uvicorn.Config(m, port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started: break
        time.sleep(0.1)
    return seen, srv


def _save(c, url, **kw):
    r = c.put("/api/settings", json={"printers": [{"name": "K1", "type": "moonraker", "url": url, "profile": "creality_k1", **kw}]}); assert r.status_code == 200, r.text
    return settings.load()["printers"][0]["id"]


def test_k1_is_a_preset_on_moonraker_not_a_new_printer_type(local):
    assert "creality" not in {t["type"] for t in printers.TYPES} and printers.IMPLEMENTED == {"octoprint", "moonraker"}
    c = client(ADULT); pid = _save(c, "http://127.0.0.1:1")
    p = c.get("/api/settings").json()["printers"][0]
    assert p["profile"] == "creality_k1" and p["experimental"] is True and p["profile_label"] == "Creality K1 (Experimental)"
    assert (p["bed_x"], p["bed_y"]) == (220.0, 220.0)                                   # blank bed -> the K1's own, not 250x210
    assert c.get("/api/settings").json()["printer_presets"][0]["id"] == "creality_k1"
    bad = c.put("/api/settings", json={"printers": [{"name": "x", "type": "octoprint", "url": "http://x", "profile": "creality_k1"}]})
    assert bad.status_code == 400 and "moonraker" in bad.text
    assert c.put("/api/settings", json={"printers": [{"name": "x", "type": "moonraker", "url": "http://x", "profile": "nope"}]}).status_code == 400


def test_test_route_is_read_only_and_reports_ready(local):
    port = _port(); seen, srv = _mock(port)
    c = client(ADULT); pid = _save(c, f"http://127.0.0.1:{port}")
    r = c.post(f"/api/printers/{pid}/test").json()
    assert r["ok"] is True and "ready" in r["message"] and "Experimental" in r["message"] and r["detail"]["klippy_state"] == "ready"
    assert seen and all(m == "GET" for m, _ in seen) and {p for _, p in seen} <= {"/server/info", "/printer/info"}      # no print, no upload, no command
    srv.should_exit = True


def test_test_route_friendly_failures(local):
    port = _port(); seen, srv = _mock(port, state="error")
    c = client(ADULT); pid = _save(c, f"http://127.0.0.1:{port}")
    r = c.post(f"/api/printers/{pid}/test").json()
    assert r["ok"] is False and "not ready" in r["message"] and "state=error" in r["message"]
    srv.should_exit = True
    pid2 = _save(c, "http://127.0.0.1:%d" % _port())                                     # nothing listening
    r2 = c.post(f"/api/printers/{pid2}/test").json()
    assert r2["ok"] is False and "Nothing answers" in r2["message"] or "Could not reach" in r2["message"]
    assert "Traceback" not in json.dumps(r2) and "127.0.0.1" not in r2["message"]
    stub = c.put("/api/settings", json={"printers": [{"name": "b", "type": "bambu", "url": "x"}]}); assert stub.status_code == 200
    r3 = c.post(f"/api/printers/{settings.load()['printers'][0]['id']}/test").json()
    assert r3["ok"] is False and "not implemented" in r3["message"]


def test_test_route_refuses_suspended_visitors_and_unknown_ids(local):
    c = client(ADULT); pid = _save(c, "http://127.0.0.1:1")
    assert c.post("/api/printers/nope/test").status_code == 404
    for who in (client(SUSPENDED),):
        assert who.post(f"/api/printers/{pid}/test").status_code == 403


def test_shared_server_only_admin_can_test(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    a = client(ADULT)
    # 127.0.0.1 is now refused in shared mode (SSRF guard); a public-looking address stands in, and the
    # connection test is stubbed so this stays a permissions test, not a network test.
    assert a.put("/api/settings", json={"printers": [{"name": "K1", "type": "moonraker", "url": "http://127.0.0.1:1"}]}, headers={"X-Admin-Token": "t0k"}).status_code == 400
    assert a.put("/api/settings", json={"printers": [{"name": "K1", "type": "moonraker", "url": "http://203.0.113.5:1"}]}, headers={"X-Admin-Token": "t0k"}).status_code == 200
    pid = settings.load()["printers"][0]["id"]
    monkeypatch.setattr(printers, "test", lambda pr: {"ok": False, "message": "stubbed", "detail": {}})
    assert a.post(f"/api/printers/{pid}/test").status_code == 403                       # an ordinary adult on a shared server may not make the server dial out
    assert a.post(f"/api/printers/{pid}/test", headers={"X-Admin-Token": "t0k"}).status_code == 200
    a.put("/api/settings", json={"printers": []}, headers={"X-Admin-Token": "t0k"})


def test_slice_and_send_use_the_same_bed_and_profile(local, monkeypatch):
    if not slicer.find_slicer():
        pytest.skip("no slicer")
    c = client(ADULT); pid = _save(c, "http://127.0.0.1:1"); bid = photo_build(c)
    calls = []
    real = slicer.slice_model
    def spy(model, outdir, *a, **k):
        calls.append((a, k)); return real(model, outdir, *a, **k)
    monkeypatch.setattr(slicer, "slice_model", spy)
    r1 = c.post(f"/api/slice/{bid}", data={"printer_id": pid}).json()
    g = (config.OUT / bid / "model.gcode").read_text()                                    # G-code of the K1 slice (before the generic one overwrites it)
    c.post(f"/api/send/{bid}", data={"printer_id": pid})                                  # upload fails (nothing listening) - slicing already happened
    r0 = c.post(f"/api/slice/{bid}").json()
    assert r1["bed"] == [220.0, 220.0] and r0["bed"] == [250.0, 210.0]                   # no printer -> the documented generic bed
    (a1, k1), (a2, k2), _ = calls[0], calls[1], calls[2]
    assert tuple(a1[5]) == tuple(a2[5]) == (220.0, 220.0) and str(a1[6]) == str(a2[6]) and str(a1[6]).endswith("creality_k1.ini")
    assert "START_PRINT" in g and "END_PRINT" in g


def test_k1_profile_keeps_the_values_from_the_research_file():
    ini = printers.PROFILES["creality_k1"]["ini"].read_text()
    assert "bed_shape = 0x0,220x0,220x220,0x220" in ini and "gcode_flavor = klipper" in ini and "START_PRINT" in ini


# ---- Settings polish: default slicer + stub labels ----------------------------------------------------------------------------------
def test_default_slicer_auto_means_creality_with_a_k1_preset_and_old_values_still_work():
    from app.services import settings
    assert settings.DEFAULTS["default_slicer"] == "auto"
    assert settings.effective_slicer({"default_slicer": "auto", "printers": []}) == "prusaslicer"
    assert settings.effective_slicer({"default_slicer": "auto", "printers": []}, phone=True) == "creality"
    assert settings.effective_slicer({"default_slicer": "auto", "printers": [{"profile": "creality_k1"}]}) == "creality"
    assert settings.effective_slicer({"default_slicer": "cura", "printers": [{"profile": "creality_k1"}]}) == "cura"       # a deliberate choice wins


def test_settings_accept_creality_and_ignore_unknown_slicers_and_stubs_say_coming_soon():
    assert all("Coming soon" in t["label"] and "stub" not in t["label"].lower() for t in printers.TYPES if not t["implemented"])
    assert all("not implemented" not in t["hint"].lower() for t in printers.TYPES)
    assert settings.save_from_client({"default_slicer": "creality", "printers": []})["default_slicer"] == "creality"
    assert settings.save_from_client({"default_slicer": "evil://x", "printers": []})["default_slicer"] == "auto"
    assert settings.save_from_client({"printers": []})["default_slicer"] == "auto"
