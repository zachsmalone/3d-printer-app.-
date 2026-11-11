"""Slice and Open in CAD on a Showcase item, plus the publish licence picker.

Button visibility is decided in static/showcase-open.js (no permission is inferred there).
The licence change route is owner-only and does not rewrite remix credit.
"""
import re
import subprocess
from pathlib import Path

import pytest

from app.community import licensing
from app.community.store import LISTINGS
from app.services import credits
from tests.b1 import client, photo_build

ROOT = Path(__file__).resolve().parents[1]
COMM = (ROOT / "static" / "community.js").read_text(encoding="utf-8")
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")


def U(n="Maker", dob="1990-01-01"):
    return client({"display_name": n, "dob": dob})


@pytest.fixture(autouse=True)
def _fresh_listings():
    snap = LISTINGS.read()
    yield
    LISTINGS.write(snap)


def publish(c, title="Pub", **extra):
    r = c.post("/api/showcase", json={"build_id": photo_build(c), "title": title, "description": "d",
                                      "tags": ["lamp"], "accept_guidelines": True, "nsfw": False,
                                      "visibility": "public", **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _fn(src, name):
    m = re.search(rf"\n(?:async )?function {name}\(", src)
    assert m, name
    rest = src[m.end():]
    nxt = re.search(r"\n(?:async )?function |\n\$\(\"#", rest)
    return src[m.start():m.end() + (nxt.start() if nxt else len(rest))]


def test_open_rules_match_the_showcase_cases():
    r = subprocess.run(["node", str(ROOT / "tests" / "showcase_open_check.mjs")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    sa = sorted(k for k, v in licensing.LICENSES.items() if v.get("share_alike") is True)
    assert sa == ["cc-by-nc-sa-4.0", "cc-by-sa-4.0"]


def test_dialog_wiring_keeps_remix_and_the_test_slice_check():
    assert "Remix this" in COMM
    assert "Test-slice it for my printer" in COMM
    assert 'id="itSlice"' in COMM and 'id="itCad"' in COMM
    assert "> Slice</button>" in COMM and "> Open in CAD</button>" in COMM
    slice_fn = _fn(COMM, "startSlice")
    cad_fn = _fn(COMM, "openInCad")
    remix_fn = _fn(COMM, "startRemix")
    printer = _fn(COMM, "openPrinter")
    assert "rememberRemixIntent" not in slice_fn
    assert 'rememberRemixFor("cad", item)' in cad_fn
    assert "rememberRemixIntent(item)" in remix_fn
    assert "sliceDestination" in printer
    assert 'location.hash = "torchc0"' in printer
    assert 'location.hash = "slicer"' in printer
    assert "zeim:torchc0-file" in printer and "zeim:open-edit" in printer
    assert "Your recent builds are full" in COMM
    assert "Slice it or download the file instead." in cad_fn
    assert "cadPageHref" in cad_fn
    mesh = _fn(COMM, "showcaseMesh")
    assert "showcaseFile" in mesh and "fetchBytes" in mesh and "new File" in mesh
    payload = _fn(COMM, "publishPayload")
    assert 'license_id: $("#pub_license")?.value || "private-use"' in payload
    assert 'id="pub_license"' in HTML
    assert "/api/showcase/licenses" in COMM
    assert "/license" in COMM


def test_private_use_credit_line_names_the_licence():
    cl = credits.credit_line({"title": "Cup", "creator": "@ada", "license_id": "private-use"})
    assert cl["licence"] == "Private use"
    assert "Private use" in cl["credit_line"]
    assert cl["licence_url"] == ""
    # a maker with no licence id still gets no invented licence
    plain = credits.credit_line({"title": "Cup", "creator": "@ada"})
    assert plain["licence"] == ""
    page = publish(U("Credit"), "Personal cup")
    assert page["license_id"] == "private-use"
    assert page["credit"]["licence"] == "Private use"
    html = client().get("/p/" + page["id"]).text
    assert "Private use" in html and "Licence:" in html


def test_owner_can_change_licence_and_remix_credit_stays():
    maker, remixer, other = U("OwnerLic"), U("RemixLic"), U("StrangerLic")
    src = publish(maker, "Source cup", license_id="cc-by-4.0")
    rem = publish(remixer, "Remixed cup", remix_of=src["id"], license_id="cc-by-4.0")
    r = maker.put(f"/api/showcase/{src['id']}/license", json={"license_id": "cc-by-nd-4.0"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["license_id"] == "cc-by-nd-4.0"
    assert body["can_remix"] is False
    assert "CC BY-ND 4.0" in body["credit"]["credit_line"]
    stored = next(i for i in LISTINGS.read() if i["id"] == rem["id"])
    assert stored["remix_of"] == src["id"]
    assert stored["license_id"] == "cc-by-4.0"
    chain = remixer.get(f"/api/showcase/{rem['id']}").json()["remix_chain"]
    assert src["id"] in [x.get("id") for x in chain]
    assert maker.put(f"/api/showcase/{src['id']}/license", json={"license_id": "private-use"}).json()["license_id"] == "private-use"
    assert next(i for i in LISTINGS.read() if i["id"] == rem["id"])["remix_of"] == src["id"]


def test_licence_change_rejects_unknown_and_non_owners():
    maker, other = U("OwnerGate"), U("OtherGate")
    item = publish(maker, "Gated", license_id="cc-by-4.0")
    url = f"/api/showcase/{item['id']}/license"
    for bad in ({}, {"license_id": ""}, {"license_id": "gpl-3.0"}, {"license_id": 3}):
        r = maker.put(url, json=bad)
        assert r.status_code == 400, r.text
        assert "unknown licence" in r.json()["detail"]
    assert other.put(url, json={"license_id": "cc0-1.0"}).status_code == 404
    assert client().put(url, json={"license_id": "cc0-1.0"}).status_code == 404
    assert maker.put("/api/showcase/zo-pencil-cup/license", json={"license_id": "cc0-1.0"}).status_code == 404
    assert licensing.require("cc-by-4.0") == "cc-by-4.0"
    with pytest.raises(ValueError):
        licensing.require("")
    with pytest.raises(ValueError):
        licensing.require(None)


def test_publish_still_rejects_nd_and_private_use_sources():
    maker, remixer = U("NdSrc"), U("NdRem")
    nd = publish(maker, "No derivatives", license_id="cc-by-nd-4.0")
    prv = publish(maker, "Personal only")
    assert prv["license_id"] == "private-use"
    for src in (nd, prv):
        r = remixer.post("/api/showcase", json={"build_id": photo_build(remixer), "title": "Not allowed",
                                                "description": "d", "tags": ["lamp"], "accept_guidelines": True,
                                                "nsfw": False, "visibility": "public", "remix_of": src["id"],
                                                "license_id": "cc-by-4.0"})
        assert r.status_code == 422, r.text
        assert "doesn't allow publishing remixes" in r.json()["detail"]
