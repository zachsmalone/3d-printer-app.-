"""PERF3: images and fonts may be cached a day; JS, CSS and HTML still revalidate every time."""
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def test_images_get_a_day():
    r = c.get("/static/zt/slicer.webp")
    assert r.status_code == 200 and r.headers["cache-control"] == "public, max-age=86400"


def test_code_still_revalidates():
    for path in ("/static/app.js", "/static/style.css", "/static/privacy.html"):
        r = c.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
