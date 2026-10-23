"""Send must-dos (send-privacy.md section 8) + SEND-2..9 server side. Browser parts: tests/ui_sendsheet.py via test_b1_ui.py."""
import io, json, os, re, stat, zipfile
import pytest
from app import config
from app.services import settings
from tests import b1
from tests.b1 import client, photo_build, ADULT, SUSPENDED, UNDER18, ADMIN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(config, "MODE", "local")


def _printer(key="SECRET-API-KEY-123"):
    return {"printers": [{"name": "Shed", "type": "octoprint", "url": "http://10.0.0.5", "api_key": key}]}


# ---------------------------------------------------------------- encrypt printer API keys
def test_printer_api_key_is_encrypted_at_rest_and_still_usable(local):
    c = client(ADULT)
    assert c.put("/api/settings", json=_printer()).status_code == 200
    raw = settings.FILE.read_text()
    assert "SECRET-API-KEY-123" not in raw and "enc:v1:" in raw
    assert settings.load()["printers"][0]["api_key"] == "SECRET-API-KEY-123"          # the app can still use it
    assert settings.get_printer(settings.load()["printers"][0]["id"])["api_key"] == "SECRET-API-KEY-123"
    assert "api_key" not in json.dumps(c.get("/api/settings").json())                 # and the browser never gets it
    assert stat.S_IMODE(os.stat(settings.KEYFILE).st_mode) == 0o600 and stat.S_IMODE(os.stat(settings.FILE).st_mode) == 0o600


def test_blank_key_on_save_keeps_the_stored_encrypted_key(local):
    c = client(ADULT); c.put("/api/settings", json=_printer())
    pid = settings.load()["printers"][0]["id"]
    c.put("/api/settings", json={"printers": [{"id": pid, "name": "Shed 2", "type": "octoprint", "url": "http://10.0.0.5", "api_key": ""}]})
    assert settings.load()["printers"][0]["api_key"] == "SECRET-API-KEY-123" and "SECRET-API-KEY-123" not in settings.FILE.read_text()


def test_legacy_plain_text_keys_are_migrated_and_a_lost_key_means_no_key(local):
    settings.FILE.write_text(json.dumps({"public_base_url": "", "default_slicer": "prusaslicer", "printers": [
        {"id": "old1", "name": "Old", "type": "octoprint", "url": "http://10.0.0.6", "api_key": "LEGACY-PLAIN", "bed_x": 250, "bed_y": 210}]}))
    assert settings.load()["printers"][0]["api_key"] == "LEGACY-PLAIN"
    assert "LEGACY-PLAIN" not in settings.FILE.read_text()                            # re-written encrypted on first read
    settings.KEYFILE.write_text(__import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())   # key lost/replaced
    assert settings.load()["printers"][0]["api_key"] == ""                            # no crash, no ciphertext leaked into a request header


def test_secret_key_from_environment_wins(local, monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("PHOTO3D_SECRET_KEY", Fernet.generate_key().decode())
    tok = settings.encrypt_secret("abc"); assert tok.startswith("enc:v1:") and settings.decrypt_secret(tok) == "abc"
    assert settings.encrypt_secret(tok) == tok                                         # never double-encrypts


# ---------------------------------------------------------------- never bundle the source; headers; generic names
def test_uploaded_source_and_meta_are_never_downloadable_or_in_exports():
    c = client(ADULT); bid = photo_build(c)
    for name in ("source.png", "source.jpg", "meta.json", "../meta.json", "original.stl"):
        assert c.get(f"/files/{bid}/{name}").status_code in (404, 422)
    for ext in ("zip", "png", "jpg", "json", "source"):
        assert c.get(f"/api/download/{bid}/{ext}").status_code == 404
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/files/{bid}/model.3mf").content))
    assert sorted(z.namelist()) == sorted(["[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model",
                                           "Metadata/model_settings.config", "Metadata/zeim_slots.json"])   # slot mapping only
    assert set(__import__("json").loads(z.read("Metadata/zeim_slots.json"))) == {"slots", "filament_to_slot", "colours", "notes"}
    stl = c.get(f"/files/{bid}/model.stl").content
    assert stl[:80].startswith(b"photo3d") and b"Ada" not in stl and b"s.png" not in stl


def test_downloads_are_no_store_with_generic_file_names():
    c = client(ADULT); bid = photo_build(c)
    for u in (f"/files/{bid}/model.stl", f"/files/{bid}/model.3mf", f"/files/{bid}/model.obj", f"/api/download/{bid}/stl", f"/files/{bid}/thumb.png"):
        r = c.get(u); assert r.status_code == 200 and r.headers["cache-control"] == "no-store", u
    assert re.search(r'filename="photo3d_[0-9a-f]+\.stl"', c.get(f"/files/{bid}/model.stl").headers["content-disposition"])
    assert c.get(f"/files/{bid}/model.stl").headers["referrer-policy"] == "no-referrer"


def test_build_summary_lists_file_sizes_for_the_sheet():
    c = client(ADULT); photo_build(c)
    b = c.get("/api/builds").json()["builds"][0]
    assert set(b["sizes"]) == {"stl", "obj", "3mf"} and all(v > 100 for v in b["sizes"].values())


def test_edit_project_exports_carry_no_title_in_object_names():
    c = client(ADULT)
    r = c.post("/api/edit/new", files={"file": ("Emma_birthday.stl", __import__("trimesh").creation.box(extents=(20, 20, 20)).export(file_type="stl"), "application/octet-stream")},
               data={"title": "Emma_birthday"})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/files/{bid}/model.3mf").content)); xml = z.read("3D/3dmodel.model").decode()
    assert "Emma" not in xml and "Emma" not in c.get(f"/files/{bid}/model.obj").text


# ---------------------------------------------------------------- capabilities the sheet draws from
def test_share_rows_ship_off_until_the_device_spike_passed(monkeypatch):
    a = client(ADULT)
    assert a.get("/api/me").json()["send"]["share_ui"] is False and a.get("/api/me").json()["send"]["share"] is True
    monkeypatch.setattr(config, "SEND_SHARE_UI", True)
    assert a.get("/api/me").json()["send"]["share_ui"] is True
    assert client(SUSPENDED).get("/api/me").json()["send"]["share_ui"] is False                 # never for a suspended account, flag or not


def test_printer_ui_only_in_local_mode_for_adults(monkeypatch):
    monkeypatch.setattr(config, "MODE", "shared")
    a = client(ADULT); assert a.get("/api/me").json()["send"]["printer_ui"] is False
    monkeypatch.setattr(config, "MODE", "local")
    assert a.get("/api/me").json()["send"]["printer_ui"] is True
    assert client(SUSPENDED).get("/api/me").json()["send"]["printer_ui"] is False



# ---------------------------------------------------------------- static guards on the sheet's code
def test_send_sheet_code_never_builds_a_link_or_calls_the_token_route():
    js = open(os.path.join(ROOT, "static", "send.js"), encoding="utf-8").read()
    assert "/f/" not in js and "url:" not in js and "mailto" not in js
    assert "navigator.share({ files: [file], title:" in js
    assert 'rel="noopener noreferrer"' in js and 'target="_blank"' in js
    assert js.count("crealitycloud.com") == 1 and "api.creality" not in js


def test_no_loose_format_buttons_left_in_result_bars():
    html = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
    assert 'id="downloads"' not in html and 'id="editDownloads"' not in html and 'id="btnSendSheet"' in html and 'id="editSend"' in html
