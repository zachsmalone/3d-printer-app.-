"""Static files must always revalidate (the phone test broke when Safari mixed cached old modules with new ones)."""
from tests.b1 import client


def test_static_files_always_revalidate_so_a_phone_never_mixes_old_and_new_modules():
    c = client()
    for u in ("/static/app.js", "/static/edit.js", "/static/boot.js", "/static/style.css", "/static/vendor/three.module.min.js"):
        r = c.get(u); assert r.status_code == 200, u
        assert r.headers.get("cache-control") == "no-cache" and r.headers.get("etag"), (u, dict(r.headers))
    assert c.get("/static/app.js", headers={"If-None-Match": c.get("/static/app.js").headers["etag"]}).status_code == 304      # revalidation stays cheap
    assert '<script src="/static/boot.js"></script>' in c.get("/").text
