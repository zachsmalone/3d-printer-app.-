"""Showcase filters: printer, material, supports, licence, mature (default hide)."""
import pytest

from app.community import catalog
from app.community.store import ENGAGEMENT, LISTINGS, MODERATION, PREFS, PRINTS
from tests.b1 import client, photo_build


@pytest.fixture(autouse=True)
def _fresh():
    snap = {s: s.read() for s in (LISTINGS, ENGAGEMENT, PREFS, PRINTS, MODERATION)}
    yield
    for s, was in snap.items():
        s.write(was)


def U(n):
    return client({"display_name": n, "dob": "1990-01-01"})


def publish(c, title, **extra):
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d", "tags": ["lamp"],
                                      "accept_guidelines": True, "nsfw": False, "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def patch(iid, **kv):
    def f(l):
        for i in l:
            if i["id"] == iid:
                i.update(kv)
    LISTINGS.update(f)


def ids(c, qs=""):
    r = c.get("/api/showcase?tab=free" + qs)
    assert r.status_code == 200, r.text
    return {i["id"] for i in r.json()["items"]}


def test_facets_from_metadata():
    f = catalog.facets({"printer": "FDM, 0.4 mm nozzle", "material": "PLA, 0.2 mm", "supports_level": "None", "license_id": "cc-by-4.0"})
    assert f == {"printer": "fdm", "material": "pla", "supports": "no", "licence": "cc-by-4.0"}
    assert catalog.facets({"printer": "MSLA resin", "material": "Standard resin", "needs_supports": True})["supports"] == "yes"
    assert catalog.facets({}) == {"printer": "unknown", "material": "unknown", "supports": "unknown", "licence": "unknown"}
    assert catalog.facets({"supports_level": "Light, under the hook"})["supports"] == "yes"


def test_filters_unknown_stays_unless_specific():
    c = U("Filt")
    a = publish(c, "Known")
    b = publish(c, "Bare")
    patch(a["id"], printer="FDM", material="PETG", supports_level="none", license_id="cc0-1.0")
    patch(b["id"], license_id="")
    assert {a["id"], b["id"]} <= ids(c)
    assert a["id"] in ids(c, "&printer=fdm") and b["id"] not in ids(c, "&printer=fdm")
    assert b["id"] in ids(c, "&printer=unknown") and a["id"] not in ids(c, "&printer=unknown")
    assert a["id"] in ids(c, "&material=petg") and a["id"] not in ids(c, "&material=pla")
    assert a["id"] in ids(c, "&supports=no") and a["id"] not in ids(c, "&supports=yes")
    assert a["id"] in ids(c, "&licence=cc0-1.0") and b["id"] not in ids(c, "&licence=cc0-1.0")
    assert b["id"] in ids(c, "&licence=unknown")
    combo = ids(c, "&printer=fdm&material=petg&supports=no&licence=cc0-1.0")
    assert a["id"] in combo and b["id"] not in combo
    item = next(i for i in c.get("/api/showcase?tab=free").json()["items"] if i["id"] == a["id"])
    assert item["facets"]["material"] == "petg"


def test_mature_default_hide_and_show():
    c = U("Mat")
    m = publish(c, "Mature", nsfw=True)
    v = U("MatView")
    r = v.get("/api/showcase?tab=free").json()
    assert r["filters"]["mature"] == "hide" and m["id"] not in {i["id"] for i in r["items"]}
    assert m["id"] in ids(v, "&mature=show")
    assert m["id"] in ids(c)                          # owner always sees their own, even with mature=hide


@pytest.mark.parametrize("qs", ["&printer=laser", "&material=wood", "&supports=maybe", "&licence=gpl", "&mature=blur", "&licence=CC0"])
def test_bad_values_400(qs):
    assert U("Bad").get("/api/showcase?tab=free" + qs).status_code == 400


def test_sorts_still_work_with_filters():
    c = U("Srt")
    publish(c, "S1")
    for s in ("likes", "printed"):
        assert c.get(f"/api/showcase?tab=free&sort={s}&supports=unknown").status_code == 200


def test_ui_has_filters_and_honest_wording():
    html = open("static/index.html").read()
    for i in ("shPrinter", "shMaterial", "shSupports", "shLicence", "shMature", "shFiltReset"):
        assert f'id="{i}"' in html
    seg = html[html.index('id="shFilters"'):html.index('id="shGrid"')]
    assert '<option value="hide">Hide</option><option value="show">Show</option>' in seg
    low = seg.lower()
    for w in ("kid", "child", "family", "school", "best", "guarantee"):
        assert w not in low
    js = open("static/community.js").read()
    assert "shFilterQS()" in js


def test_mature_default_follows_opt_in_setting():
    c = U("OptIn")
    m = publish(c, "Mature2", nsfw=True)
    v = U("Viewer")
    assert m["id"] not in ids(v)                                     # default: hidden
    assert v.put("/api/me/mature", json={"hide_mature": False}).status_code == 200
    r = v.get("/api/showcase?tab=free").json()
    assert r["filters"]["mature"] == "show" and m["id"] in {i["id"] for i in r["items"]}
    assert m["id"] not in ids(v, "&mature=hide")                     # the filter can still hide it
