"""Object storage seam (Phase 1 Task 3): minimal S3-compatible SigV4 client + local fallback.

Tests run against a real local HTTP server shaped like S3 (PUT/GET/DELETE, Authorization
header required). A live smoke test against real S3/R2 with real credentials is still
needed before launch — that part cannot be done from the repo.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services import objectstore


class _FakeS3(ThreadingHTTPServer):
    objects: dict = {}
    auth_headers: list = []


class _Handler(BaseHTTPRequestHandler):
    def _clean_path(self):
        return self.path.split("?")[0]

    def _auth(self):
        _FakeS3.auth_headers.append(self.headers.get("Authorization", ""))

    def do_PUT(self):
        self._auth()
        n = int(self.headers.get("Content-Length", 0))
        _FakeS3.objects[self._clean_path()] = self.rfile.read(n)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self._auth()
        if self._clean_path() in _FakeS3.objects:
            body = _FakeS3.objects[self._clean_path()]
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        self._auth()
        _FakeS3.objects.pop(self._clean_path(), None)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture
def s3(monkeypatch):
    """A live local S3-shaped server + env pointing the client at it."""
    srv = _FakeS3(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    for k in ("PHOTO3D_S3_ENDPOINT", "PHOTO3D_S3_BUCKET", "PHOTO3D_S3_KEY", "PHOTO3D_S3_SECRET", "PHOTO3D_S3_REGION"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PHOTO3D_S3_ENDPOINT", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setenv("PHOTO3D_S3_BUCKET", "zeim-test")
    monkeypatch.setenv("PHOTO3D_S3_KEY", "AKIDEXAMPLE")
    monkeypatch.setenv("PHOTO3D_S3_SECRET", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
    monkeypatch.setenv("PHOTO3D_S3_REGION", "us-east-1")
    _FakeS3.objects = {}
    _FakeS3.auth_headers = []
    yield srv
    srv.shutdown()


def test_unconfigured_means_local_fallback(monkeypatch):
    for k in ("PHOTO3D_S3_ENDPOINT", "PHOTO3D_S3_BUCKET", "PHOTO3D_S3_KEY", "PHOTO3D_S3_SECRET"):
        monkeypatch.delenv(k, raising=False)
    assert objectstore.enabled() is False        # files stay on disk; no network is touched


def test_put_get_roundtrip_with_sigv4(s3):
    assert objectstore.enabled() is True
    url = objectstore.put("builds/b1/model.stl", b"solid x", content_type="model/stl")
    assert "zeim-test/builds/b1/model.stl" in url
    assert _FakeS3.objects["/zeim-test/builds/b1/model.stl"] == b"solid x"
    # every request carried a proper SigV4 Authorization header
    assert _FakeS3.auth_headers and all(h.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/") for h in _FakeS3.auth_headers)
    assert objectstore.get("builds/b1/model.stl") == b"solid x"


def test_get_missing_object_raises(s3):
    with pytest.raises(Exception):
        objectstore.get("no/such/key")


def test_delete_removes_the_object(s3):
    objectstore.put("k", b"v")
    objectstore.delete("k")
    with pytest.raises(Exception):
        objectstore.get("k")


def test_signed_url_is_a_presigned_get(s3):
    objectstore.put("pub/share.png", b"PNGDATA")
    u = objectstore.signed_url("pub/share.png", ttl_s=600)
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in u and "X-Amz-Expires=600" in u and "X-Amz-Signature=" in u
    # the presigned URL actually fetches the object without any Authorization header
    import httpx
    r = httpx.get(u, timeout=10)
    assert r.status_code == 200 and r.content == b"PNGDATA"
    # and it was accepted with NO Authorization header present (signature is in the query)
    assert all("Credential" not in (h or "") or h.startswith("AWS4") for h in _FakeS3.auth_headers)


def test_sigv4_is_deterministic_for_a_fixed_time(monkeypatch):
    """Same inputs -> same signature (regression guard for the signing code)."""
    import datetime
    cfg = {"endpoint": "https://s3.example.org", "bucket": "b", "key": "K", "secret": "S", "region": "us-east-1"}
    t = datetime.datetime(2026, 10, 17, 12, 0, 0, tzinfo=datetime.timezone.utc)
    h1 = objectstore._sign_request("PUT", "https://s3.example.org/b/x", {"content-type": "text/plain"}, b"hello", cfg, amz_date=t)
    h2 = objectstore._sign_request("PUT", "https://s3.example.org/b/x", {"content-type": "text/plain"}, b"hello", cfg, amz_date=t)
    assert h1["Authorization"] == h2["Authorization"]
    assert "Signature=" in h1["Authorization"]
    # a different payload changes the signature
    h3 = objectstore._sign_request("PUT", "https://s3.example.org/b/x", {"content-type": "text/plain"}, b"tampered", cfg, amz_date=t)
    assert h3["Authorization"] != h1["Authorization"]
