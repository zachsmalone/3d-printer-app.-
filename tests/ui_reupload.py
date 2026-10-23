"""Re-upload protection UI at 1280px and 390px (Chrome + WebKit): sharing a copy of another maker's model shows the
credited-remix offer (remixes on) or a friendly refusal (remixes off) inside the Share dialog, with line icons; the
owner's project shows 'Report a copy'.  python tests/ui_reupload.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/")
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)
SIGN = "async n => (await fetch('/api/me/signup', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({display_name: n, dob: '1990-01-01'})})).status"
GEN = """async () => { const sb = await (await fetch('/static/sample.jpg')).blob(); const fd = new FormData(); fd.append('file', new File([sb], 'a.jpg', {type:'image/jpeg'}));
  fd.append('mode','relief'); fd.append('resolution','40'); fd.append('width_mm','40'); fd.append('photo_ack','true');
  return (await (await fetch('/api/generate', {method:'POST', body: fd})).json()).id; }"""
PUB = """async ([bid, allow]) => (await (await fetch('/api/showcase', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({build_id: bid, title: 'Original ' + allow, description: 'd', tags: ['x'],
    accept_guidelines: true, nsfw: false, visibility: 'public', license_id: 'cc-by-4.0', allow_remixes: allow})})).json())"""
OPENPUB = """async bid => { const m = await import('/static/app.js'); m.S.current = {id: bid, title: 'My upload'}; document.querySelector('#btnPublish').click(); }"""
OPEN = "id => { const a = document.createElement('a'); a.dataset.openItem = id; a.href = '#'; document.body.append(a); a.click(); a.remove(); }"
EMOJI = "() => /[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u.test(document.querySelector('#pubConflict').innerText)"
PRIV = """async () => { for (const i of (await (await fetch('/api/me/projects')).json()).projects)
  await fetch('/api/showcase/' + i.id + '/visibility', {method:'PUT', headers:{'content-type':'application/json'}, body: JSON.stringify({visibility: 'private'})}); }"""
def share(pg):
    pg.check("[name=pub_nsfw][value=no]"); pg.check("#pub_ok"); pg.select_option("#pub_vis", "public")
    pg.click("#btnDoPublish"); pg.wait_for_selector("#pubConflict:not([hidden])", timeout=20000); pg.wait_for_timeout(300)
def fits(pg, sel):
    return pg.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect(); return r.width > 0 && r.right <= innerWidth + 1 && r.left >= -1; }", sel)
def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    for w, h in ((1280, 900), (390, 844)):
        tag = f"{name} {w}px"; errs = []
        own, oth = b.new_context(viewport={"width": w, "height": h}), b.new_context(viewport={"width": w, "height": h})
        po, pt = own.new_page(), oth.new_page()
        for pg in (po, pt): pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL + "/"); pg.wait_for_timeout(400)
        po.evaluate(SIGN, f"Maker{w}{name}"); pt.evaluate(SIGN, f"Second{w}{name}")
        for pg in (po, pt): pg.reload(); pg.wait_for_timeout(600)
        off = po.evaluate(PUB, [po.evaluate(GEN), False])
        ok(f"{tag}: remix-off original posted", off.get("allow_remixes") is False, off)
        # 1) remixes off -> refused, keep private offered
        bid = pt.evaluate(GEN); pt.evaluate(OPENPUB, bid); pt.wait_for_selector("#dlgPublish[open]", timeout=10000)
        share(pt)
        txt = pt.inner_text("#pubConflict")
        ok(f"{tag}: refusal shown", "can't be shared" in txt and "Private" in txt, txt)
        ok(f"{tag}: no credited-remix button when remixes are off", pt.locator("#pubAsRemix").count() == 0)
        ok(f"{tag}: line icon, no emoji", pt.locator("#pubConflict svg use").count() >= 1 and not pt.evaluate(EMOJI))
        ok(f"{tag}: panel fits the width", fits(pt, "#pubConflict"))
        pt.screenshot(path=f"previews/ui_reup_refused_{name}_{w}.png")
        pt.click("#pubKeepPrivate"); pt.wait_for_timeout(1500)
        ok(f"{tag}: Keep it Private closes the dialog", not pt.evaluate("document.querySelector('#dlgPublish').open"))
        # 2) remixes on -> credited remix offer
        po.evaluate("async id => fetch('/api/showcase/' + id + '/remixes', {method:'PUT', headers:{'content-type':'application/json'}, body: JSON.stringify({allow_remixes: true})})", off["id"])
        bid = pt.evaluate(GEN); pt.evaluate(OPENPUB, bid); pt.wait_for_selector("#dlgPublish[open]", timeout=10000)
        share(pt)
        ok(f"{tag}: credited-remix offer shown", pt.locator("#pubAsRemix").is_visible() and "credited remix" in pt.inner_text("#pubConflict"))
        ok(f"{tag}: offer fits the width", fits(pt, "#pubConflict") and fits(pt, "#pubAsRemix"))
        pt.screenshot(path=f"previews/ui_reup_offer_{name}_{w}.png")
        pt.click("#pubAsRemix"); pt.wait_for_timeout(2000)
        ok(f"{tag}: posted as credited remix", not pt.evaluate("document.querySelector('#dlgPublish').open"))
        # 3) owner: Report a copy
        po.goto(URL + "/#showcase"); po.wait_for_timeout(600); po.evaluate(OPEN, off["id"]); po.wait_for_selector("#itCopyBtn", timeout=15000)
        po.click("#itCopyBtn"); po.wait_for_timeout(1200)
        ok(f"{tag}: Report a copy panel opens", po.locator("#itCopyBox").is_visible() and po.locator("#itCopyUrl").is_visible())
        ok(f"{tag}: copy panel fits", fits(po, "#itCopyBox"))
        po.locator("#itCopyBox").scroll_into_view_if_needed()
        po.screenshot(path=f"previews/ui_reup_report_copy_{name}_{w}.png")
        for pg in (po, pt):            # tidy up so the next width starts from a clean Showcase
            pg.evaluate(PRIV)
        ok(f"{tag}: no page errors", not errs, errs)
        own.close(); oth.close()
    b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
