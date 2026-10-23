"""Printer picker search + brand groups in Chromium at 1280/390/320.   python tests/ui_printer_picker.py URL"""
import sys
from playwright.sync_api import sync_playwright
URL = sys.argv[1].rstrip("/"); bad = []
def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)
MOUNT = """async () => { const m = await import('/static/printer.js'); await m.loadCatalog();
  const d = document.createElement('div'); d.id = 'pickTest'; d.style.cssText = 'padding:8px;background:var(--panel,#fff)';
  document.body.prepend(d); d.innerHTML = m.pickerHTML('pt'); m.wirePicker('pt', v => window.__picked = v); return true }"""
with sync_playwright() as pw:
    b = pw.chromium.launch(); errs = []
    for w in (1280, 390, 320):
        mob = w < 500
        pg = b.new_page(viewport={"width": w, "height": 844}, is_mobile=mob, has_touch=mob)
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(URL + "/"); pg.wait_for_timeout(600)
        pg.evaluate(MOUNT); pg.wait_for_timeout(200)
        groups = pg.eval_on_selector_all("#pt_pr optgroup", "g=>g.map(x=>x.label)")
        ok(f"{w}: printers grouped by brand, Longer included", len(groups) >= 20 and "Longer" in groups and groups == sorted(groups, key=str.lower), groups)
        for sel in ("#pt_q", "#pt_pr", "#pt_nz"):
            bb = pg.locator(sel).bounding_box()
            ok(f"{w}: {sel} is a 44px tap target inside the viewport", bb and bb["height"] >= 44 and bb["x"] >= 0 and bb["x"] + bb["width"] <= w + 1, bb)
        ok(f"{w}: no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"))
        pg.fill("#pt_q", "longer"); pg.wait_for_timeout(150)
        names = pg.eval_on_selector_all("#pt_pr option", "o=>o.map(x=>x.textContent)")
        ok(f"{w}: 'longer' leaves Longer printers (plus the current pick)", any("LK5 Pro" in n for n in names) and any("Orange 4K" in n for n in names) and len(names) <= 3, names)
        pg.fill("#pt_q", "lk5"); pg.wait_for_timeout(150)
        ok(f"{w}: a single match is selected straight away", pg.input_value("#pt_pr") == "longer_lk5_pro" and (pg.evaluate("window.__picked") or {}).get("printer_id") == "longer_lk5_pro")
        ok(f"{w}: info shows the sourced build volume", "300 × 300 × 400" in pg.inner_text("#pt_info"), pg.inner_text("#pt_info"))
        pg.fill("#pt_q", "orange"); pg.wait_for_timeout(150)
        ok(f"{w}: resin pick hides the nozzle field", pg.input_value("#pt_pr") == "longer_orange_4k" and not pg.is_visible("#pt_nzf"))
        pg.fill("#pt_q", "zzzz"); pg.wait_for_timeout(100)
        ok(f"{w}: no-match message, selection kept", "No printer matches" in pg.inner_text("#pt_qn") and pg.input_value("#pt_pr") == "longer_orange_4k")
        pg.fill("#pt_q", ""); pg.wait_for_timeout(100)
        ok(f"{w}: clearing shows every printer", pg.locator("#pt_pr option").count() == pg.evaluate("(async()=>(await (await fetch('/api/printers/catalog')).json()).printers.length)()"))
        pg.close()
    ok("no page errors", not errs, errs)
    b.close()
print("PASS chrome" if not bad else f"FAILED {len(bad)}")
sys.exit(1 if bad else 0)
