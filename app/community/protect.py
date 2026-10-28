"""Theft protection for Showcase uploads.

Sharing a near-duplicate of another maker's public project is not published as-is. If that project allows
remixes, the maker gets a credited-remix offer. If remixes are off, the share is refused. Keeping it Private
is always allowed, and a later flip to public is checked again. Nothing is deleted.

Downloaded 3MF files carry a hidden owner tag (model id, maker, first-posted date). Importing that file and
sharing it again is treated like a shape match, including when the shape check misses. A tag for a project
this maker cannot already see is ignored, so a guessed id cannot reveal private work.

The maker's own re-upload, and a remix that credits the source, pass. 'Report as stolen' and 'Report a copy'
go to moderators and do not hide a project by themselves. See fingerprint.py for the shape check's limits.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

from .. import config
from ..services.history import store as _builds
from . import fingerprint
from .store import JsonFile, MODERATION

FINGERPRINTS = JsonFile("fingerprints", {})      # item id -> {"fp": {...}, "key": cache key for Originals}
DMCA_URL = "/legal/takedown"
_MODEL_ID = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
HOLD_MESSAGE = ("Thanks! This model looks very close to one another maker already posted on ZEIM, so a moderator will "
                "take a quick look before it goes live. Nothing has been deleted. If it is your own work or a credited "
                "remix, you don't need to do anything; you can also add a note with the Appeal button.")


def remember(item_id: str, fp: dict | None) -> None:
    if fp:
        FINGERPRINTS.update(lambda d: d.__setitem__(item_id, {"fp": fp}))


def _fp_for(i: dict, store: dict) -> dict | None:
    rec = store.get(i["id"])
    if not i.get("original"):
        return (rec or {}).get("fp")
    # ZEIM Originals: fingerprint the first model file once, cached by file size + mtime
    f = next((x["name"] for x in i.get("files", []) if x["name"].lower().endswith((".stl", ".3mf", ".obj"))), None)
    p = config.ORIGINALS / f if f else None
    if not p or not p.is_file():
        return None
    st = p.stat()
    key = f"{p.name}:{st.st_size}:{int(st.st_mtime)}"
    if rec and rec.get("key") == key:
        return rec.get("fp")
    fp = fingerprint.safe_compute(p)
    FINGERPRINTS.update(lambda d: d.__setitem__(i["id"], {"fp": fp, "key": key}))
    return fp


def _chain_ids(remix_of: str, items_by_id: dict) -> set:
    out, cur = set(), remix_of
    while cur and cur not in out:
        out.add(cur)
        cur = (items_by_id.get(cur) or {}).get("remix_of")
    return out


def find_match(fp: dict | None, creator_id: str, remix_of: str = "", exclude: str = "") -> dict | None:
    """Best match among OTHER makers' projects that are PUBLIC (live in the Showcase) or ZEIM Originals, ignoring the
    credited remix source chain. Private / followers-only work of others is never compared, so a refusal can't reveal
    it. None = passes."""
    if not fp:
        return None
    from .catalog import _all, is_public
    items = _all()
    by_id = {x["id"]: x for x in items}
    credited = _chain_ids(remix_of, by_id) if remix_of else set()
    store = FINGERPRINTS.read()
    best = None
    for i in items:
        if i["id"] == exclude or i["id"] in credited or i.get("example") or i.get("creator_id") == creator_id:
            continue
        if not i.get("original") and not is_public(i):
            continue
        s = fingerprint.similar(fp, _fp_for(i, store))
        if s and (best is None or s["score"] > best["score"]):
            best = {**s, "item": i}
    return best


def own_match(fp: dict | None, creator_id: str, exclude: str = "") -> dict | None:
    if not fp:
        return None
    from .catalog import _all
    store = FINGERPRINTS.read()
    for i in _all():
        if i["id"] != exclude and i.get("creator_id") == creator_id and fingerprint.similar(fp, _fp_for(i, store)):
            return i
    return None


REMIX_OFFER_MESSAGE = ("This looks very close to \u201c{title}\u201d by {creator}, which is already in the Showcase. "
                       "Its maker allows remixes, so you can share yours as a credited remix that links back to it. "
                       "You can also keep it Private in your library.")
REFUSED_MESSAGE = ("Sorry, this can't be shared to the Showcase: it looks very close to \u201c{title}\u201d by {creator}, "
                   "and its maker has turned remixes off. It is still saved in your library, and you can keep it Private. "
                   "This check compares shapes, so it can be wrong; if you think it is, please contact the ZEIM team.")
TAG_OFFER_MESSAGE = ("This file still carries \u201c{title}\u201d by {creator}, which is already in the Showcase. "
                     "Its maker allows remixes, so you can share yours as a credited remix that links back to it. "
                     "You can also keep it Private in your library.")
TAG_REFUSED_MESSAGE = ("Sorry, this can't be shared to the Showcase: this file still carries \u201c{title}\u201d by {creator}, "
                       "and its maker has turned remixes off. It is still saved in your library, and you can keep it Private. "
                       "If you made this yourself and the tag is leftover from an earlier download, please contact the ZEIM team.")


def read_owner_tag(source) -> dict | None:
    """Model id from a ZEIM-tagged 3MF (Metadata/zeim_owner.json or 3D/3dmodel.model). None if absent."""
    try:
        z = zipfile.ZipFile(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source)
    except (zipfile.BadZipFile, OSError, ValueError):
        return None
    meta: dict[str, str] = {}
    try:
        names = {n.lower(): n for n in z.namelist()}
        if "metadata/zeim_owner.json" in names:
            try:
                raw = json.loads(z.read(names["metadata/zeim_owner.json"])[:65536])
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, OSError, TypeError):
                raw = None
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(k, str) and isinstance(v, (str, int, float, bool)):
                        meta[k] = str(v)
        if "3d/3dmodel.model" in names:
            try:
                xml = z.read(names["3d/3dmodel.model"])[:4 * 2**20]
            except (KeyError, OSError):
                xml = b""
            for m in re.finditer(br'<metadata\s+name=(["\'])([^"\']+)\1[^>]*>([^<]*)</metadata>', xml):
                key = m.group(2).decode("utf-8", "replace")
                val = m.group(3).decode("utf-8", "replace").strip()
                meta.setdefault(key, val)
                if key.startswith("zeim:"):
                    meta.setdefault(key[5:], val)
    finally:
        z.close()
    mid = (meta.get("ModelId") or "").strip()
    if not _MODEL_ID.match(mid):
        return None
    return {"model_id": mid}


def build_owner_tag(build_id: str) -> dict | None:
    """The tag on the untouched import (original.3mf). Re-exported model.3mf files are not tagged."""
    if not build_id:
        return None
    try:
        p = _builds.dir(build_id) / "original.3mf"
    except KeyError:
        return None
    if not p.is_file():
        return None
    return read_owner_tag(p)


def _visible_item(model_id: str, actor):
    # catalog imports this module inside publish, so the lookup stays in the function.
    from .catalog import Denied, get
    try:
        return get(model_id, actor)
    except Denied:
        return None


def tag_match(model_id: str, actor, creator_id: str, remix_of: str = "", exclude: str = "") -> dict | None:
    """Another maker's project named by an owner tag, when this maker can already see it and it is not the credit chain."""
    if not model_id:
        return None
    from .catalog import _all
    by_id = {x["id"]: x for x in _all()}
    credited = _chain_ids(remix_of, by_id) if remix_of else set()
    if model_id == exclude or model_id in credited:
        return None
    i = _visible_item(model_id, actor)
    if not i or i.get("example") or i.get("creator_id") == creator_id:
        return None
    return {"exact": True, "score": 1.0, "item": i, "via": "owner_tag"}


def own_tagged(model_id: str, actor, creator_id: str) -> dict | None:
    i = _visible_item(model_id, actor) if model_id else None
    if i and i.get("creator_id") == creator_id and not i.get("example"):
        return i
    return None


def _remix_blocked(item: dict) -> bool:
    from .catalog import remix_status
    return not remix_status(item)["can_remix"]


def choose_match(shape: dict | None, tagged: dict | None) -> dict | None:
    """Prefer a remix-off project. When both sides agree, the file's owner tag names the download source."""
    if not tagged:
        return shape
    if not shape or shape["item"]["id"] == tagged["item"]["id"]:
        return tagged
    shape_off, tag_off = _remix_blocked(shape["item"]), _remix_blocked(tagged["item"])
    if tag_off and not shape_off:
        return tagged
    if shape_off and not tag_off:
        return shape
    return tagged


def review_upload(fp, *, actor, creator_id: str, remix_of: str = "", build_id: str = "",
                  source_model_id: str = "", exclude: str = "") -> dict:
    """Shape match plus the owner tag on an imported 3MF. `source_model_id` is remembered for a later public flip."""
    tag = build_owner_tag(build_id) if build_id else None
    mid = (tag or {}).get("model_id") or (source_model_id or "")
    if mid and not _MODEL_ID.match(mid):
        mid = ""
    shape = find_match(fp, creator_id, remix_of, exclude)
    tagged = tag_match(mid, actor, creator_id, remix_of, exclude) if mid else None
    return {"match": choose_match(shape, tagged), "source_model_id": mid,
            "own": own_tagged(mid, actor, creator_id) if mid else None}


def share_conflict(match: dict) -> dict:
    """The 409 body for a share that matches another maker's model: a credited-remix offer, or a refusal."""
    from .catalog import remix_status
    m = match["item"]
    orig = {"id": m["id"], "title": m.get("title", ""), "creator": m.get("creator", ""), "share_url": f"/p/{m['id']}"}
    fill = {"title": orig["title"][:60] or "a project", "creator": orig["creator"] or "another maker"}
    tagged = match.get("via") == "owner_tag"
    if remix_status(m)["can_remix"]:
        msg = TAG_OFFER_MESSAGE if tagged else REMIX_OFFER_MESSAGE
        return {"code": "remix_offer", "message": msg.format(**fill), "original": orig,
                "exact": bool(match["exact"]), "can_keep_private": True}
    msg = TAG_REFUSED_MESSAGE if tagged else REFUSED_MESSAGE
    return {"code": "copy_refused", "message": msg.format(**fill), "original": orig,
            "exact": bool(match["exact"]), "can_keep_private": True}


def likely_copies(i: dict) -> list[dict]:
    """For the owner's 'Report a copy': later, other-maker, live projects whose geometry matches, not credited remixes."""
    from .catalog import _all, is_public
    store = FINGERPRINTS.read()
    fp = _fp_for(i, store)
    if not fp:
        return []
    items = _all()
    by_id = {x["id"]: x for x in items}
    out = []
    for x in items:
        if x["id"] == i["id"] or x.get("creator_id") == i.get("creator_id") or x.get("example") or not is_public(x):
            continue
        if i["id"] in _chain_ids(x.get("remix_of", ""), by_id) or str(x.get("created", "")) < str(i.get("created", "")):
            continue
        s = fingerprint.similar(fp, _fp_for(x, store))
        if s:
            out.append({"id": x["id"], "title": x.get("title", ""), "creator": x.get("creator", ""),
                        "share_url": f"/p/{x['id']}", "created": x.get("created"), "exact": s["exact"]})
    return out


def hold(item: dict, match: dict, account_id: str | None) -> dict:
    """Hide the new upload and open a moderation report that links to the matched (likely original) project."""
    from . import moderation
    m = match["item"]
    details = (f"Automatic duplicate hold: geometry {'is identical to' if match['exact'] else 'closely matches'} "
               f"/p/{m['id']} \"{m.get('title', '')[:60]}\" by {m.get('creator', '?')} (first posted {str(m.get('created', ''))[:10]}). "
               "Restore to release the upload; it was not deleted.")
    rep = moderation.report(item["id"], "system:duplicate-check", "duplicate_hold", details, account_id)

    def f(md):
        if item["id"] not in md["hidden"]:
            md["hidden"].append(item["id"])
        r = next((x for x in md["reports"] if x["id"] == rep["id"]), None)
        if r is not None:
            r.update(original_id=m["id"], original_url=f"/p/{m['id']}", exact_match=bool(match["exact"]))
    MODERATION.update(f)
    return {"match": m["id"], "exact": bool(match["exact"]), "report_id": rep["id"], "at": datetime.now(timezone.utc).isoformat()}


def likely_original(i: dict) -> dict | None:
    """For 'Report as stolen': the earliest-posted other-maker project whose geometry matches this one."""
    from .catalog import _all
    store = FINGERPRINTS.read()
    fp = _fp_for(i, store)
    if not fp:
        return None
    hits = [x for x in _all() if x["id"] != i["id"] and x.get("creator_id") != i.get("creator_id") and not x.get("example")
            and str(x.get("created", "")) < str(i.get("created", "")) and fingerprint.similar(fp, _fp_for(x, store))]
    return min(hits, key=lambda x: str(x.get("created", ""))) if hits else None


# ---------------- owner tag in downloaded 3MF ----------------
def owner_meta(i: dict) -> dict:
    base = config.PUBLIC_BASE_URL or ""
    return {"Title": i.get("title", ""), "Designer": i.get("creator", ""),
            "CreationDate": str(i.get("created", ""))[:10],
            "zeim:ModelId": i["id"], "zeim:CreatorHandle": i.get("creator", ""),
            "zeim:FirstPosted": str(i.get("created", "")), "zeim:SourceURL": f"{base}/p/{i['id']}",
            **({"zeim:AIMade": "true"} if i.get("ai_made") else {})}


ZNS = "https://zeim.app/ns/owner-tag/2026"
_MODEL_RE = re.compile(rb"<model\b[^>]*>", re.S)


def tag_3mf(data: bytes, meta: dict) -> bytes:
    """Return the 3MF with ZEIM owner metadata in 3D/3dmodel.model (3MF core <metadata> elements; custom names
    use a declared 'zeim' namespace) plus a small Metadata/zeim_owner.json. Unparseable input is returned unchanged."""
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
        names = zin.namelist()
        model = next((n for n in names if n.lower() == "3d/3dmodel.model"), None)
        if not model:
            return data
        xml = zin.read(model)
        mo = _MODEL_RE.search(xml)
        if not mo:
            return data
        for k in meta:                                   # drop any earlier copy of the same metadata names
            xml = re.sub(rb"<metadata\s+name=" + re.escape(quoteattr(k).encode()) + rb"[^>]*?(/>|>.*?</metadata>)", b"", xml, flags=re.S)
        mo = _MODEL_RE.search(xml)
        head = mo.group(0)
        new_head = head
        if b"xmlns:zeim" not in head:
            new_head = head[:-1].rstrip(b"/") + f' xmlns:zeim="{ZNS}">'.encode()
        tags = "".join(f"\n <metadata name={quoteattr(k)}>{escape(str(v))}</metadata>" for k, v in meta.items()).encode()
        xml = xml[:mo.start()] + new_head + tags + xml[mo.end():]
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
            for n in names:
                if n == "Metadata/zeim_owner.json":
                    continue
                zo.writestr(zin.getinfo(n), xml if n == model else zin.read(n))
            zo.writestr("Metadata/zeim_owner.json", json.dumps({k.replace("zeim:", ""): v for k, v in meta.items()}, indent=1))
        return out.getvalue()
    except (zipfile.BadZipFile, KeyError, OSError):
        return data
