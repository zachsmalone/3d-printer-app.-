"""Theft protection for Showcase uploads: duplicate hold, owner tag in 3MF downloads, 'Report as stolen'.

Nothing here deletes anything. A near-duplicate of ANOTHER maker's model is held (hidden) for a moderator, who
restores it (moderation 'restore') or acts on it. Owners re-uploading their own model, and credited remixes of a
project that allows remixes, pass. See app/community/fingerprint.py for what the fingerprint can and can't catch.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

from .. import config
from . import fingerprint
from .store import JsonFile, MODERATION

FINGERPRINTS = JsonFile("fingerprints", {})      # item id -> {"fp": {...}, "key": cache key for Originals}
DMCA_URL = "/legal/takedown"
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


def share_conflict(match: dict) -> dict:
    """The 409 body for a share that matches another maker's model: a credited-remix offer, or a refusal."""
    from .catalog import remix_status
    m = match["item"]
    orig = {"id": m["id"], "title": m.get("title", ""), "creator": m.get("creator", ""), "share_url": f"/p/{m['id']}"}
    fill = {"title": orig["title"][:60] or "a project", "creator": orig["creator"] or "another maker"}
    if remix_status(m)["can_remix"]:
        return {"code": "remix_offer", "message": REMIX_OFFER_MESSAGE.format(**fill), "original": orig,
                "exact": bool(match["exact"]), "can_keep_private": True}
    return {"code": "copy_refused", "message": REFUSED_MESSAGE.format(**fill), "original": orig,
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
    import json
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
        head = mo.group(0)
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
