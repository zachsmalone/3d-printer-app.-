"""IOS-2 headless check (Chrome + playwright): at 390x844 and 820x1180 every visible interactive element is >= 44x44 CSS px,
every visible text input/select/textarea computes to font-size >= 16px (iOS Safari zooms into smaller ones), the viewport
meta has viewport-fit=cover, and a touch swipe that starts on the viewer's edge strip scrolls the PAGE while a swipe in the
middle does not. Emulated touch in desktop Chrome - NOT a real iPhone. python tests/ui_touch.py [url]"""
import sys, json
from playwright.sync_api import sync_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"
AUDIT = """() => {
  const out = {small: [], font: []};
  const vis = e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
    if (r.width < 1 || r.height < 1 || cs.visibility === 'hidden' || cs.display === 'none') return null;
    if (e.closest('[hidden],.sr-only,dialog:not([open])')) return null; return r; };
  const sel = 'button,a[href],input:not([type=hidden]):not([type=file]),select,textarea,summary,[role=button],[role=tab]';
  for (const e of document.querySelectorAll(sel)) {
    let r = vis(e); if (!r) continue;
    if (e.matches('input[type=checkbox],input[type=radio]')) { const l = e.closest('label'); if (l && vis(l)) r = l.getBoundingClientRect(); }
    if (e.tagName === 'A' && getComputedStyle(e).display === 'inline' && !e.matches('.btn,[role=button]')) continue; // inline text links in prose: WCAG exempts
    if (r.width < 43.5 || r.height < 43.5) out.small.push((e.id || e.className || e.tagName) + ' ' + (e.textContent || e.placeholder || '').trim().slice(0, 24) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
    if (e.matches('input:not([type=checkbox]):not([type=radio]):not([type=range]),select,textarea') && parseFloat(getComputedStyle(e).fontSize) < 15.99)
      out.font.push((e.id || e.name || e.tagName) + ' ' + getComputedStyle(e).fontSize);
  }
  return out; }"""
bad = []


def audit(pg, label):
    r = pg.evaluate(AUDIT)
    for k in ("small", "font"):
        for item in r[k]: bad.append((label, k, item))


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    for (w, h) in ((390, 844), (820, 1180)):
        ctx = b.new_context(viewport={"width": w, "height": h}, has_touch=True, is_mobile=True, device_scale_factor=2)
        pg = ctx.new_page(); pg.goto(URL); pg.wait_for_timeout(700)
        meta = pg.evaluate("document.querySelector('meta[name=viewport]').content")
        if "viewport-fit=cover" not in meta: bad.append((w, "viewport", meta))
        tag = f"{w}"
        audit(pg, tag + " studio-empty")
        pg.click("#levelSwitch [data-level=expert]"); pg.wait_for_timeout(300); audit(pg, tag + " studio-expert-empty")
        pg.click("#levelSwitch [data-level=beginner]"); pg.wait_for_timeout(200)
        # build a sample so the result bar, history card and viewer tools exist
        pg.click("#sSample"); pg.wait_for_timeout(400)
        if pg.locator("#btnBuild").is_enabled(): pg.click("#btnBuild")
        pg.wait_for_selector("#result:not([hidden])", timeout=120000); pg.wait_for_timeout(800)
        audit(pg, tag + " studio-built")
        # viewer scroll behaviour: edge strip scrolls the page, middle does not
        cdp = ctx.new_cdp_session(pg)
        def swipe(xf, label):
            pg.evaluate("document.querySelector('#viewer').scrollIntoView({block:'start'}); window.scrollBy(0,-140)"); pg.wait_for_timeout(300)
            vb = pg.locator("#viewer").bounding_box(); x = vb["x"] + xf(vb); y = max(vb["y"], 0) + 200
            before = pg.evaluate("window.scrollY")
            cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
            for i in range(1, 13):
                cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - i * 15}]}); pg.wait_for_timeout(16)
            cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []}); pg.wait_for_timeout(600)
            return pg.evaluate("window.scrollY") - before
        room = pg.evaluate("document.documentElement.scrollHeight - innerHeight")
        if room < 300: bad.append((w, "page not scrollable enough to test", room))
        edge = swipe(lambda vb: 8, "edge")
        mid = swipe(lambda vb: vb["width"] / 2, "mid")
        if edge < 50: bad.append((w, "edge-swipe did not scroll page", edge))
        if mid > 5: bad.append((w, "middle-swipe scrolled page (viewer should capture it)", mid))
        pg.evaluate("window.scrollTo(0,0)")
        # print dialog (local mode)
        if pg.locator("#btnPrint").is_visible():
            pg.click("#btnPrint"); pg.wait_for_timeout(500); audit(pg, tag + " print-dialog")
            pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        for view in ("edit", "showcase"):
            pg.click(f"#mainNav [data-view={view}]"); pg.wait_for_timeout(600); audit(pg, f"{tag} {view}")
        pg.screenshot(path=f"previews/ui_touch_{w}.png")
        ctx.close()
    b.close()
print(json.dumps(bad, indent=1) if bad else "OK"); sys.exit(1 if bad else 0)
