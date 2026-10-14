"""Home (Studio) redesign: hero + 3-step path, landmarks, radios, viewer buttons, Send or save, footer, themes, reduced motion, and axe-core (if installed at
/workspace/a11y-tools or $AXE_JS). Chrome + WebKit (axe in Chrome only).   python tests/ui_home.py URL   (TEMP-data server)"""
import json, os, re, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]
AXE = os.environ.get("AXE_JS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")
bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)

def axe(pg, label):
    if not os.path.exists(AXE): raise SystemExit("FAIL axe missing: " + AXE)
    pg.add_script_tag(path=AXE)
    r = pg.evaluate("axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','best-practice']}}).then(r=>r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,t:v.nodes.slice(0,3).map(n=>n.target.join(' '))})))")
    ok(f"axe: {label}: no violations", not r, json.dumps(r)[:900])

def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    def page(w=390, h=844, **kw):
        ctx = b.new_context(viewport={"width": w, "height": h}, bypass_csp=True, **kw)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(800); return ctx, pg
    ctx, pg = page()
    h1 = pg.locator("h1:visible"); 
    ok(f"{name}: exactly one visible h1 with the agreed words", h1.count() == 1 and h1.inner_text().strip() == "Turn a photo into something you can print.", h1.all_inner_texts())
    t = pg.inner_text("body")
    ok(f"{name}: says 'Free to use' and never 'free forever'", "Free to use" in t and not re.search(r"free forever", t, re.I))
    ok(f"{name}: landmarks: one banner, one main, one contentinfo, nav Main + Your progress",
       pg.evaluate("""() => [document.querySelectorAll('body > header').length, [...document.querySelectorAll('main')].filter(m=>!m.hidden).length, document.querySelectorAll('body > footer').length,
                      [...document.querySelectorAll('nav')].filter(n=>n.getClientRects().length>0).map(n=>n.getAttribute('aria-label')).join('|'), document.querySelectorAll('dialog header, dialog footer').length].join(',')""") == "1,1,1,Main|Your progress,0")
    ok(f"{name}: path starts on step 1 with a polite status", pg.get_attribute("#path li[data-step='1']", "aria-current") == "step" and pg.get_attribute("#pathSay", "aria-live") == "polite" and "Step 1 of 3" in pg.inner_text("#pathSay"))
    prim = pg.evaluate("[...document.querySelectorAll('main .btn.primary')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.top<844&&!e.disabled}).map(e=>e.id)")
    ok(f"{name}: one primary action above the fold", len(prim) == 1 and prim[0] in ("sTake", "sChoose"), prim)
    ok(f"{name}: Build button says Make my 3D model", "Make my 3D model" in pg.inner_text("#btnBuild"))
    ok(f"{name}: style and thickness are radio groups with legends", pg.locator("#modeCards legend").count() == 1 and pg.locator("#modeCards input[type=radio]").count() == 4
       and pg.locator("#presetSeg legend").inner_text() == "Thickness" and pg.locator("#presetSeg input[type=radio]").count() == 3)
    pg.click("#modeCards [data-mode=relief]")
    ok(f"{name}: choosing Relief checks the radio", pg.is_checked("#modeCards input[value=relief]"))
    pg.focus("#modeCards input[value=relief]"); pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(100)
    ok(f"{name}: arrow keys move through the styles", pg.is_checked("#modeCards input[value=popart]") and pg.inner_text("#presetHelp") != "")
    pg.click("#modeCards [data-mode=lithophane]"); pg.click("#presetSeg [data-preset=thick]")
    ok(f"{name}: thickness radio selected", pg.is_checked("#presetSeg input[value=thick]"))
    pg.click("#presetSeg [data-preset=standard]")
    # footer
    links = pg.eval_on_selector_all(".sitefoot a", "a=>a.map(x=>[x.textContent.trim(), x.getAttribute('href'), x.getBoundingClientRect().height])")
    ok(f"{name}: footer has Rules, Privacy, Terms, Credits, each >= 44px", [l[0] for l in links][:3] == ["Rules", "Privacy", "Terms"] and all(l[2] >= 43.5 for l in links), links)
    for l in links:
        if l[1].startswith("https://"): continue   # external (PrusaSlicer attribution)
        r = pg.request.get(URL + l[1]); ok(f"{name}: footer link {l[1]} exists (200)", r.status == 200, r.status)
    if with_axe: axe(pg, "Studio empty, 390 light")
    # build from the sample
    pg.click("#sSample"); pg.wait_for_selector("#result:not([hidden])", timeout=60000); pg.wait_for_timeout(600)
    ok(f"{name}: path reaches step 3 with ticks and a status", pg.get_attribute("#path li[data-step='3']", "aria-current") == "step" and "Model ready. Step 3 of 3" in pg.inner_text("#pathSay")
       and pg.inner_text("#path li[data-step='1'] .n") == "✓" and "done" in pg.get_attribute("#path li[data-step='2']", "class"))
    ok(f"{name}: focus moves to the result heading", pg.evaluate("document.activeElement.id") == "resultH")
    ok(f"{name}: viewer has a text alternative and Turn left / Turn right / Reset view buttons >= 44px",
       pg.get_attribute("#viewer", "role") == "img" and "3D preview" in pg.get_attribute("#viewer", "aria-label")
       and all(pg.locator(s).is_visible() and pg.locator(s).bounding_box()["height"] >= 43.5 for s in ("#vLeft", "#vRight", "#vReset")))
    pg.click("#vLeft"); pg.click("#vRight"); ok(f"{name}: turn buttons do not throw", True)
    bs = pg.locator("#btnSendSheet")
    ok(f"{name}: 'Send or save' opens a dialog", bs.inner_text().strip().endswith("Send or save") and bs.get_attribute("aria-haspopup") == "dialog")
    bs.click(); pg.wait_for_selector("#dlgSendSheet[open]")
    st = pg.inner_text("#dlgSendSheet")
    ok(f"{name}: sheet title and groups", "Send or save your model" in st and "SAVE IT" in st.upper(), st[:200])
    ok(f"{name}: sheet does not say anything works that is untested", not re.search(r"\\b(works|tested and|guaranteed)\\b", st, re.I) or "untested" in st.lower() or "Not tried" in st, st[:300])
    if with_axe: axe(pg, "Send sheet open, 390 light")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    ok(f"{name}: Esc returns focus to Send or save", pg.evaluate("document.activeElement.id") == "btnSendSheet")
    ok(f"{name}: history list is a real list under 'Pick up where you left off'", pg.locator("ul#histList > li.hcard").count() >= 1 and pg.locator("h2:has-text('Pick up where you left off')").count() == 1)
    ok(f"{name}: Keep exploring tiles are links", pg.locator(".tiles a.tile").count() == 3)
    if with_axe: axe(pg, "Studio built, 390 light")
    pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(300)
    ok(f"{name}: Experienced collapses the hero to 'Studio' and hides the tiles", pg.locator("h1:visible").inner_text().strip() == "Studio" and not pg.is_visible(".lede") and not pg.is_visible(".tiles"))
    if with_axe: axe(pg, "Experienced, 390 light")
    pg.select_option("#modeSel", "beginner")
    # themes
    ok(f"{name}: default look is the warm light theme", pg.evaluate("document.documentElement.dataset.theme || 'warm'") == "warm")
    pg.click("#themeToggle"); pg.wait_for_timeout(150)
    ok(f"{name}: Dark mode toggle switches to dark, remembered after reload", pg.evaluate("document.documentElement.dataset.theme") == "dark" and (pg.reload() or True) and (pg.wait_for_timeout(700) or True) and pg.evaluate("document.documentElement.dataset.theme") == "dark")
    if with_axe: axe(pg, "Studio, 390 dark")
    pg.click("#themeToggle")
    ctx.close()
    # first visit with no saved choice follows the OS preference
    ctx, pg = page(color_scheme="dark")
    ok(f"{name}: no saved choice + OS dark preference starts dark", pg.evaluate("document.documentElement.dataset.theme") == "dark"); ctx.close()
    # widths
    for w in (320, 360, 390, 768, 1280):
        ctx, pg = page(w, 800)
        sw = pg.evaluate("document.documentElement.scrollWidth"); tb = pg.evaluate("document.querySelector('.topbar').getBoundingClientRect().height")
        ok(f"{name}: {w}px: no sideways scroll", sw <= w, sw)
        if w <= 390: ok(f"{name}: {w}px: top bar <= 170px tall", tb <= 170, tb)
        if with_axe and w in (320, 1280): axe(pg, f"Studio empty, {w} light")
        ctx.close()
    # reduced motion
    ctx, pg = page(reduced_motion="reduce")
    anim = pg.evaluate("getComputedStyle(document.querySelector('.spin')).animationName"); ok(f"{name}: reduced motion stops the spinner", anim in ("none", ""), anim); ctx.close()
    # keyboard order of the first controls
    ctx, pg = page()
    order = []
    for _ in range(11):
        pg.keyboard.press("Tab"); order.append(pg.evaluate("document.activeElement.id || document.activeElement.textContent.trim().slice(0,12)"))
    ok(f"{name}: keyboard reaches the six tabs, Mode, then the Dark mode toggle", all(t in order for t in ("Showcase", "Slicer", "CAD", "Lithophane", "Smart Fix", "Account", "modeSel", "themeToggle")) and order.index("modeSel") < order.index("themeToggle"), order)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()

with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
