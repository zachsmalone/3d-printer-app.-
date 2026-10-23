"""UI6: 75/25 split, settings search, floating toolbar, no emoji, contrast, one-line consent. Chromium at 1280/390/320.   python tests/ui_ui6.py URL"""
import re, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
EMOJI = r"[\u{1F000}-\u{1FAFF}\u{2600}-\u{26FF}\u{2B06}\u{2B07}\u{2B50}\u{FE0F}\u{2702}\u{2705}\u{2708}-\u{270F}\u{2728}\u{23F0}-\u{23FA}]"
LUM = """c=>{const m=c.match(/[\\d.]+/g).map(Number);const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};return .2126*f(m[0])+.7152*f(m[1])+.0722*f(m[2])}"""
CR = f"""sel=>{{const L={LUM};const e=document.querySelector(sel);let b=e,bg;while(b){{bg=getComputedStyle(b).backgroundColor;if(!/rgba\\(.*, 0\\)|transparent/.test(bg))break;b=b.parentElement}}
 const a=L(getComputedStyle(e).color),c=L(bg||'rgb(255,255,255)');return (Math.max(a,c)+.05)/(Math.min(a,c)+.05)}}"""
with sync_playwright() as pw:
    b = pw.chromium.launch(); errs = []
    for w in (1280, 390, 320):
        mob = w < 500
        pg = b.new_page(viewport={"width": w, "height": 900 if not mob else 844}, is_mobile=mob, has_touch=mob)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "/#studio"); pg.wait_for_timeout(900)
        v = pg.locator("#viewer").bounding_box(); a = pg.locator("#viewCreate aside.controls").bounding_box()
        if w == 1280:
            r = v["width"] / (v["width"] + a["width"])
            ok(f"{w}: view/sidebar split is about 75/25 with the sidebar beside the view", 0.68 <= r <= 0.8 and a["x"] > v["x"] and abs(a["y"] - v["y"]) < 40, (r, v, a))
            ok(f"{w}: the 3D view fills the viewport height", v["height"] >= 900 - 160, v)
        else:
            mw = pg.locator("#viewCreate").bounding_box()["width"]
            ok(f"{w}: the view stays full width, sidebar stacked", v["width"] >= mw - 40 and (a["y"] + a["height"] <= v["y"] + 1 or a["y"] >= v["y"] + v["height"] - 1), (v, a, mw))
        ok(f"{w}: no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
        # toolbar
        ok(f"{w}: floating toolbar shows on the 3D view with 44px taps", pg.is_visible("#viewerCtx") and all(bb["height"] >= 44 and bb["width"] >= 44 for bb in [x.bounding_box() for x in pg.locator("#viewerCtx button").all()]) and pg.locator("#viewerCtx button").count() >= 1)
        tb = pg.locator("#viewerCtx").bounding_box()
        ok(f"{w}: toolbar sits inside the view", tb["x"] >= v["x"] and tb["x"] + tb["width"] <= v["x"] + v["width"] + 1, (tb, v))
        # no emoji in key UI (visible text, option labels, button labels)
        txt = pg.evaluate("document.body.innerText + [...document.querySelectorAll('option,button,summary,h3,label')].map(e=>e.textContent).join(' ')")
        found = pg.evaluate(f"t => t.match(/{EMOJI}/gu)", txt)
        ok(f"{w}: no emoji in the key UI", not found, found)
        # contrast
        for sel in ("body", "#viewCreate .help", "#viewCreate aside.controls h2"):
            c = pg.evaluate(CR, sel); ok(f"{w}: contrast of {sel} >= 4.5:1 (WCAG AA)", c >= 4.5, c)
        fs = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#viewCreate .help')).fontSize)")
        ok(f"{w}: helper text is at least 14px", fs >= 14, fs)
        # settings search (Advanced)
        pg.click("#toAdvanced"); pg.wait_for_timeout(300)
        ok(f"{w}: Advanced settings opened from the Recommended view", pg.is_visible("#expertOpts") and pg.input_value("#modeSel") == "expert")
        q = pg.locator("#expertOpts input[type=search]"); qb = q.bounding_box()
        ok(f"{w}: settings search box is visible and 44px tall", q.is_visible() and qb["height"] >= 44, qb)
        q.fill("gamma"); pg.wait_for_timeout(150)
        shown = pg.eval_on_selector_all("#expertOpts .field", "fs=>fs.filter(f=>f.offsetParent).map(f=>f.textContent.trim())")
        ok(f"{w}: typing 'gamma' leaves only the Gamma setting", len(shown) == 1 and "Gamma" in shown[0], shown)
        q.fill("zzzz"); pg.wait_for_timeout(100)
        ok(f"{w}: no-match message shows", pg.is_visible("#expertOpts ~ .setnone, .setnone:not([hidden])"))
        q.fill(""); pg.wait_for_timeout(100)
        ok(f"{w}: clearing the search shows every setting again", pg.eval_on_selector_all("#expertOpts .field.ui6-hide", "x=>x.length") == 0)
        pg.click("#toRecommended"); pg.wait_for_timeout(200)
        ok(f"{w}: back to Recommended", pg.is_visible("#beginnerOpts"))
        # consent
        pg.evaluate("document.getElementById('dlgPublish')?.showModal ? document.getElementById('dlgPublish').showModal() : 0"); pg.wait_for_timeout(200)
        sl = pg.locator("#pubConsent .consent1"); h = sl.bounding_box(); lh = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#pubConsent .consent1 span')).lineHeight)||22")
        full = pg.inner_text("#pubConsentFull") if pg.locator("#pubConsentFull").count() else ""
        ok(f"{w}: consent is a short line with the full text one tap away and as its description",
           sl.is_visible() and pg.get_attribute("#pub_ok", "aria-describedby") == "pubConsentFull" and not pg.evaluate("document.querySelector('#pubConsent details').open")
           and "minors" in pg.text_content("#pubConsentFull") and "permission" in pg.inner_text("#pubConsent .consent1"), (h,))
        pg.click("#pubConsent summary"); pg.wait_for_timeout(150)
        ok(f"{w}: expanding shows the full agreement", pg.is_visible("#pubConsentFull") and "license plates" in pg.inner_text("#pubConsentFull"))
        if w == 390: pg.evaluate("document.getElementById('dlgPublish').close()"); pg.screenshot(path="/workspace/qa/ui6/after-390-studio.png", full_page=True) if len(sys.argv) > 2 else None
        pg.close()
    ok("no page errors", not errs, errs)
    b.close()
print("PASS chrome" if not bad else "FAIL chrome"); sys.exit(1 if bad else 0)
