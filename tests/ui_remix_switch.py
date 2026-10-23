"""'Allow remixes: Yes/No': owner sees the switch, others see no Remix button and a 'Remixes off' note when it's No;
downloads stay. 1280px and 390px, Chrome + WebKit.  python tests/ui_remix_switch.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/")
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, x)
    if not c: bad.append(n)
SIGN = "async n => (await fetch('/api/me/signup', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({display_name: n, dob: '1990-01-01'})})).status"
PUB = """async allow => { const sb = await (await fetch('/static/sample.jpg')).blob(); const fd = new FormData(); fd.append('file', new File([sb], 'a.png', {type:'image/png'}));
  fd.append('mode','relief'); fd.append('resolution','40'); fd.append('width_mm','40'); fd.append('photo_ack','true');
  const g = await (await fetch('/api/generate', {method:'POST', body: fd})).json();
  const r = await fetch('/api/showcase', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({build_id: g.id, title: 'Remix test', description: 'd', tags: ['x'],
    accept_guidelines: true, nsfw: false, visibility: 'public', license_id: 'cc-by-4.0', allow_remixes: allow})}); return await r.json(); }"""
OPEN = "id => { const a = document.createElement('a'); a.dataset.openItem = id; a.href = '#'; document.body.append(a); a.click(); a.remove(); }"
def run(name, launch):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    for w, h in ((1280, 900), (390, 844)):
        tag = f"{name} {w}px"; errs = []
        own, oth = b.new_context(viewport={"width": w, "height": h}), b.new_context(viewport={"width": w, "height": h})
        po, pt = own.new_page(), oth.new_page()
        for pg in (po, pt): pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL + "/"); pg.wait_for_timeout(400)
        po.evaluate(SIGN, f"Own{w}{name}"); pt.evaluate(SIGN, f"Oth{w}{name}")
        item = po.evaluate(PUB, False)
        ok(f"{tag}: published with remixes off", item.get("allow_remixes") is False, item)
        pt.goto(URL + "/#showcase"); pt.wait_for_timeout(600); pt.evaluate(OPEN, item["id"]); pt.wait_for_selector("#itBody > *", timeout=15000); pt.wait_for_timeout(500)
        ok(f"{tag}: other user sees no Remix button", pt.locator("#itRemix").count() == 0)
        ok(f"{tag}: other user sees the 'Remixes off' note", pt.locator("#itRemixOff").is_visible() and "Remixes off" in pt.inner_text("#itRemixOff"))
        ok(f"{tag}: download link still shown", pt.locator("#itBody a[download]").count() >= 1)
        pt.screenshot(path=f"previews/ui_remix_off_{name}_{w}.png")
        po.goto(URL + "/#showcase"); po.wait_for_timeout(600); po.evaluate(OPEN, item["id"]); po.wait_for_selector("#itRemixSw", timeout=15000)
        ok(f"{tag}: owner sees the switch set to No", po.input_value("#itRemixSw") == "no")
        po.screenshot(path=f"previews/ui_remix_owner_{name}_{w}.png")
        po.select_option("#itRemixSw", "yes"); po.wait_for_timeout(1000)
        ok(f"{tag}: owner turning it on hides the note", po.locator("#itRemixOff").count() == 0)
        pt.evaluate(OPEN, item["id"]); pt.wait_for_timeout(800)
        ok(f"{tag}: other user now sees Remix", pt.locator("#itRemix").count() == 1)
        ok(f"{tag}: no page errors", not errs, errs)
        own.close(); oth.close()
    b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"))
    run("webkit", lambda: p.webkit.launch())
sys.exit(1 if bad else 0)
