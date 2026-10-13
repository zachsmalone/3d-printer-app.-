"""Accessibility round 3 leftovers (verified on origin/zeim 077b2fa, 2026-10-13): every form control on the page has a name
(incl. Print / Publish / Settings dialogs, Edit tools, fields drawn later), Settings sections are real tabs with arrow keys,
Showcase list buttons say which one is on (aria-pressed), the 3D preview label describes the model after a build, and
the keyboard-only photo pick + Build path (re-checked) still opens the picker, announces and moves focus.
Chrome (+ axe label rules) and WebKit.  No screen reader or real phone here."""
import json, os, sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1]; bad = []
AXE = os.environ.get("AXE_JS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "axe.min.js")
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
UNNAMED = """() => [...document.querySelectorAll('input,select,textarea,button')].filter(e => e.type !== 'hidden' && e.getAttribute('aria-hidden') !== 'true').filter(e => {
  const lab = e.labels ? [...e.labels].map(l => l.textContent.trim()).join('') : '';
  const lb = (e.getAttribute('aria-labelledby') || '').split(' ').filter(Boolean).map(i => document.getElementById(i)?.textContent.trim() || '').join('');
  const txt = e.tagName === 'BUTTON' ? (e.textContent.trim() || [...e.querySelectorAll('img[alt]')].map(i => i.alt).join('')) : '';
  return !(lab || e.getAttribute('aria-label') || lb || txt || e.title || (['submit','button'].includes(e.type) && e.tagName === 'INPUT' ? e.value : ''));
}).map(e => e.id || e.name || e.outerHTML.slice(0, 80))"""
def axe_label(pg, root):
    pg.add_script_tag(path=AXE)
    return pg.evaluate(f"axe.run(document.querySelector('{root}'), {{runOnly:{{type:'rule',values:['label','select-name','button-name']}}}}).then(r=>r.violations.map(v=>({{id:v.id,t:v.nodes.slice(0,3).map(n=>n.target.join(' '))}})))")
def run(name, launch, with_axe):
    try: b = launch()
    except Exception as e: print(f"SKIP {name}: {str(e).splitlines()[0][:80]}"); return
    errs = []
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, bypass_csp=True)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(URL.rstrip("/") + "/#studio"); pg.wait_for_timeout(1000)
    # keyboard photo pick (round-1 blocker #1, re-checked)
    pg.wait_for_selector("#sChoose:visible"); chooser = False
    for _ in range(3):                                   # a cold browser can take a moment to wire the picker
        pg.focus("#sChoose")
        try:
            with pg.expect_file_chooser(timeout=3000): pg.keyboard.press("Enter")
            chooser = True; break
        except Exception:
            pg.wait_for_timeout(700)
    ok(f"{name}: Enter on 'Choose a photo' opens the photo picker", chooser)
    pg.keyboard.press("Escape")
    pg.focus("#sSample"); pg.keyboard.press("Enter")                 # the sample photo builds straight away
    pg.wait_for_selector("#resultH:visible", timeout=120000)
    for _ in range(240):
        if not pg.is_disabled("#btnBuild"): break
        pg.wait_for_timeout(250)
    pg.wait_for_timeout(300)
    ok(f"{name}: after Build, focus moves to the result heading", pg.evaluate("document.activeElement.id") == "resultH", pg.evaluate("document.activeElement.id"))
    ok(f"{name}: after Build, the polite status says it is ready", "ready" in pg.inner_text("#buildHint").lower() and pg.get_attribute("#buildHint", "aria-live") == "polite")
    lab = pg.get_attribute("#viewer", "aria-label") or ""
    ok(f"{name}: the 3D preview label describes the model (style, size in mm, pieces)", "millimetres" in lab and "piece" in lab and "Lithophane" in lab, lab)
    # every control on the page has a name (closed dialogs included)
    left = pg.evaluate(UNNAMED)
    ok(f"{name}: every input/select/button in Studio + dialogs has a name", not left, left)
    ok(f"{name}: the Width label still belongs to the number box (slider has its own name)",
       pg.evaluate("document.getElementById('width_mm').labels.length === 1 && !!document.getElementById('widthRange').getAttribute('aria-label')"))
    # Print dialog fields
    pg.click("#btnPrint"); pg.wait_for_selector("#dlgPrint[open]")
    ok(f"{name}: Print layer/infill/brim are labelled", pg.evaluate("['s_layer','s_fill','s_brim'].every(i => document.getElementById(i).labels.length === 1)"))
    if with_axe: v = axe_label(pg, "#dlgPrint"); ok(f"{name}: axe label rules clean in Print", not v, v)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    # Settings: real tabs
    pg.evaluate("location.hash='account'"); pg.click("#btnSettings"); pg.wait_for_selector("#dlgSettings[open]")
    ok(f"{name}: Settings sections are a tablist with 2 tabs", pg.locator("#dlgSettings [role=tablist] [role=tab]").count() == 2)
    pg.focus("#tabPrint"); pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(150)
    ok(f"{name}: ArrowRight moves to the next tab, selects it and shows its panel",
       pg.evaluate("document.activeElement.id") == "tabAcc" and pg.get_attribute("#tabAcc", "aria-selected") == "true"
       and pg.get_attribute("#tabPrint", "aria-selected") == "false" and pg.locator("#tAcc").is_visible() and not pg.locator("#tPrint").is_visible())
    ok(f"{name}: only the selected tab is a Tab stop", pg.evaluate("[...document.querySelectorAll('#dlgSettings [role=tab]')].map(t => t.tabIndex).join()") == "-1,0")
    pg.keyboard.press("Home"); pg.wait_for_timeout(100)
    ok(f"{name}: Home goes back to the first tab", pg.evaluate("document.activeElement.id") == "tabPrint" and pg.locator("#tPrint").is_visible())
    ok(f"{name}: Public base URL is labelled", pg.evaluate("document.getElementById('set_base').labels.length") == 1)
    if with_axe: v = axe_label(pg, "#dlgSettings"); ok(f"{name}: axe label rules clean in Settings", not v, v)
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    # Showcase list buttons
    pg.click("#mainNav [data-view=showcase]"); pg.wait_for_selector("#shTabs button")
    pressed = pg.evaluate("[...document.querySelectorAll('#shTabs button')].map(b => b.getAttribute('aria-pressed'))")
    ok(f"{name}: Showcase list buttons carry aria-pressed, exactly one on", pressed.count("true") == 1 and all(p in ("true", "false") for p in pressed), pressed)
    pg.click('#shTabs [data-tab=free]'); pg.wait_for_timeout(300)
    ok(f"{name}: picking a list moves aria-pressed", pg.get_attribute('#shTabs [data-tab=free]', "aria-pressed") == "true"
       and pg.evaluate("[...document.querySelectorAll('#shTabs [aria-pressed=true]')].length") == 1)
    ok(f"{name}: the Showcase list group is named", pg.get_attribute("#shTabs", "role") == "group" and bool(pg.get_attribute("#shTabs", "aria-label")))
    # Edit tools (drawn by edit.js after a model loads) + printer rows: labels linked automatically
    pg.click('#mainNav [data-view=slicer]'); pg.wait_for_timeout(300)
    pg.click("#editSample"); pg.wait_for_selector("#editOps button[data-goto]", timeout=60000); pg.wait_for_timeout(300)
    pg.select_option("#modeSel", "expert"); pg.wait_for_timeout(300)        # Experienced mode shows every Edit tool
    pg.evaluate("document.querySelectorAll('details.tool').forEach(d => d.open = true)"); pg.wait_for_timeout(200)
    left = pg.evaluate(UNNAMED)
    ok(f"{name}: every Edit tool field has a name", not left, left)
    fid = pg.evaluate("[...document.querySelectorAll('[data-form] .field input[type=number]')].find(x => x.offsetParent !== null && x.labels.length)?.id || ''")
    if fid:
        pg.locator(f"label[for='{fid}']").click(); pg.wait_for_timeout(100)
    ok(f"{name}: clicking an Edit field's label focuses its box", bool(fid) and pg.evaluate("document.activeElement.id") == fid, fid)
    if with_axe: v = axe_label(pg, "body"); ok(f"{name}: axe label rules clean with Edit tools open", not v, v)
    ok(f"{name}: no page errors", not errs, errs)
    ctx.close(); b.close()
with sync_playwright() as p:
    run("chrome", lambda: p.chromium.launch(channel="chrome"), True)
    run("webkit", lambda: p.webkit.launch(), False)
sys.exit(1 if bad else 0)
