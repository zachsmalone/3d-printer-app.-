"""The large-STL view is sent before the full check, and every slice path stays off until that check finishes."""
import gzip
import hashlib
import json
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import trimesh

from tests import b1  # noqa: F401
from tests.b1 import ADULT, client

pytestmark = pytest.mark.filterwarnings("ignore:Using `httpx` with `starlette.testclient`:DeprecationWarning")


@pytest.fixture
def c():
    return client(ADULT)


def _ball():
    return trimesh.creation.uv_sphere(radius=30, count=[40, 40])


def _open(c, monkeypatch, *, block_finish=False):
    from app.core import fdmlean
    from app.services import editproj
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 200)
    gate = threading.Event()
    entered = []

    def blocked(bid):
        entered.append(bid)
        if block_finish:
            gate.wait(5)

    if block_finish:
        monkeypatch.setattr(editproj, "finish_full_check", blocked)
    data = _ball().export(file_type="stl")
    faces = struct.unpack_from("<I", data, 80)[0]
    release = threading.Timer(2.0, gate.set)
    release.start()
    t0 = time.perf_counter()
    with c.stream("POST", "/api/edit/new", files={"file": ("big.stl", data, "model/stl")},
                  data={"fdm_big": "true", "progress": "1"}) as resp:
        assert resp.status_code == 200, resp.read()
        lines = [json.loads(x) for x in resp.iter_lines() if x.strip()]
    elapsed = time.perf_counter() - t0
    release.cancel()
    return data, faces, lines, elapsed, entered, gate


def test_view_arrives_while_the_check_is_blocked(c, monkeypatch):
    data, faces, lines, elapsed, entered, gate = _open(c, monkeypatch, block_finish=True)
    assert elapsed < 2, "the view waited on the full check"
    views = [e for e in lines if e["phase"] == "view"]
    assert views[-1]["done"] == views[-1]["total"] == faces
    assert all("percent" not in e for e in lines)
    last = lines[-1]
    assert last["phase"] == "interactive" and last["slice_ready"] is False
    assert last["project"]["analysis"]["triangles"] == faces
    pid = last["project"]["id"]
    from app.services import editproj
    from app.services.history import store
    original = store.dir(pid) / "original.stl"
    for _ in range(50):
        if original.is_file():
            break
        time.sleep(0.02)
    assert original.read_bytes() == data
    assert hashlib.sha256(original.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()
    assert not (store.dir(pid) / "model.stl").is_file()
    blocked = c.post("/api/slice", data={"model_id": pid, "printer_id": "creality_k1"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "model_pending"
    legacy = c.post(f"/api/slice/{pid}", data={"layer_height": "0.2"})
    assert legacy.status_code == 409 and legacy.json()["detail"]["code"] == "model_pending"
    send = c.post(f"/api/send/{pid}", data={"printer_id": "missing"})
    assert send.status_code == 409 and send.json()["detail"]["code"] == "model_pending"
    editproj.ensure_stl(pid)
    editproj.ensure_exports(pid)
    assert not (store.dir(pid) / "model.stl").is_file()
    gate.set()


def test_a_torn_model_record_does_not_slice(c, monkeypatch):
    _data, _faces, lines, _elapsed, _entered, gate = _open(c, monkeypatch, block_finish=True)
    pid = lines[-1]["project"]["id"]
    from app.services import slice_engine as eng
    from app.services.history import store
    called = []
    monkeypatch.setattr(eng, "slice_model_path", lambda *a, **k: called.append("engine") or (_ for _ in ()).throw(AssertionError("engine")))
    real = store.get

    def torn(bid):
        if bid == pid and not torn.used:
            torn.used = True
            raise RuntimeError("torn record")
        return real(bid)

    torn.used = False
    monkeypatch.setattr(store, "get", torn)
    r = c.post("/api/slice", data={"model_id": pid})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "model_unread"
    assert called == []
    gate.set()


def test_delete_during_the_check_is_not_rebuilt(c, monkeypatch):
    from app.core import fdmlean, meshedit
    from app.services import editproj
    from app.services.history import store
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 200)
    entered = threading.Event()
    proceed = threading.Event()
    real = meshedit.load_mesh

    def wait_load(data, ext, *a, **k):
        entered.set()
        assert proceed.wait(5)
        return real(data, ext, *a, **k)

    monkeypatch.setattr(meshedit, "load_mesh", wait_load)
    data = _ball().export(file_type="stl")
    r = c.post("/api/edit/new", files={"file": ("big.stl", data, "model/stl")}, data={"fdm_big": "true", "progress": "1"})
    assert r.status_code == 200, r.text
    last = [json.loads(x) for x in r.text.splitlines() if x.strip()][-1]
    pid = last["project"]["id"]
    d = store.dir(pid)
    for _ in range(50):
        if (d / "original.stl").is_file():
            break
        time.sleep(0.02)
    worker = threading.Thread(target=editproj.finish_full_check, args=(pid,), daemon=True)
    worker.start()
    assert entered.wait(5)
    store.delete(pid)
    proceed.set()
    worker.join(5)
    assert not d.exists()
    assert not (d / "meta.json").exists() and not (d / "model.stl").exists()


def _multipart(fields: dict, file_field):
    boundary = "----zeimpending"
    name, blob, ctype = file_field
    parts = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
        f"Content-Type: {ctype}\r\n\r\n".encode() + blob + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def test_stream_through_a_buffering_proxy_is_not_gated_on_the_check(monkeypatch):
    """A proxy that holds the whole response, then gzip-compresses it, the way Caddy encode does.
    The view still comes back while the full check is blocked."""
    import http.client
    import uvicorn
    from app.core import fdmlean
    from app.main import app
    from app.services import editproj
    monkeypatch.setattr(fdmlean, "FDM_MAX_FACES", 200)
    gate = threading.Event()

    def blocked(bid):
        gate.wait(5)

    monkeypatch.setattr(editproj, "finish_full_check", blocked)

    app_sock = socket.socket()
    app_sock.bind(("127.0.0.1", 0))
    app_port = app_sock.getsockname()[1]
    app_sock.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=app_port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started

    class Buffer(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            return

        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n)
            conn = http.client.HTTPConnection("127.0.0.1", app_port, timeout=8)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "accept-encoding")}
            headers["Connection"] = "close"
            conn.request("POST", self.path, body, headers)
            upstream = conn.getresponse()
            raw = upstream.read()
            conn.close()
            # Hold every byte until the app response has ended, then compress once.
            gz = gzip.compress(raw)
            self.send_response(upstream.status)
            self.send_header("Content-Type", upstream.getheader("Content-Type") or "application/octet-stream")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(gz)))
            if upstream.getheader("Set-Cookie"):
                self.send_header("Set-Cookie", upstream.getheader("Set-Cookie"))
            self.end_headers()
            self.wfile.write(gz)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Buffer)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_port
    data = _ball().export(file_type="stl")
    faces = struct.unpack_from("<I", data, 80)[0]

    def call(path, payload=None, form=None, cookie=""):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
        if form is None:
            blob = json.dumps(payload).encode()
            headers = {"Content-Type": "application/json", "Content-Length": str(len(blob)), "Connection": "close"}
        else:
            blob, ctype = _multipart(form, ("big.stl", data, "model/stl"))
            headers = {"Content-Type": ctype, "Content-Length": str(len(blob)), "Connection": "close"}
        if cookie:
            headers["Cookie"] = cookie
        conn.request("POST", path, blob, headers)
        resp = conn.getresponse()
        out = gzip.decompress(resp.read())
        got = resp.getheader("Set-Cookie") or cookie
        conn.close()
        return resp.status, out, got

    status, blob, cookie = call("/api/me/signup", {"display_name": "Ada Adult", "dob": "1985-05-05"})
    assert status == 200, blob
    cookie = cookie.split(";", 1)[0]
    t0 = time.perf_counter()
    status, blob, _cookie = call("/api/edit/new", form={"fdm_big": "true", "progress": "1"}, cookie=cookie)
    elapsed = time.perf_counter() - t0
    gate.set()
    httpd.shutdown()
    assert elapsed < 2, elapsed
    assert status == 200, blob[:300]
    lines = [json.loads(x) for x in blob.decode().splitlines() if x.strip()]
    last = lines[-1]
    assert last["phase"] == "interactive" and last["slice_ready"] is False
    assert last["project"]["analysis"]["triangles"] == faces
    assert all("percent" not in e for e in lines)
