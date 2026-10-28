"""2D->3D tab in a real browser (Chrome): w1280 + w390, no overlaps, fake engine makes a model with the AI label and
opens the shared export picker, cooldown countdown shows; a second server without an engine shows 'not installed'.
python tests/ui_ai3d.py URL_FAKE_A URL_FAKE_B URL_MISSING [SHOTDIR]"""
import os, sys
from playwright.sync_api import sync_playwright
U1 = {1280: sys.argv[1].rstrip("/"), 390: sys.argv[2].rstrip("/")}; U2 = sys.argv[3].rstrip("/"); SHOT = sys.argv[4] if len(sys.argv) > 4 else ""
bad = []


def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n, "" if c else x)
    if not c: bad.append(n)


OVERLAP = """() => { const els=[...document.querySelectorAll('#viewAi3d .card, #viewAi3d .zt-band, #viewAi3d .pagehead, #viewAi3d button:not([hidden]), #viewAi3d label')]
 .filter(e=>e.offsetParent && e.getBoundingClientRect().width>0); const r=[]; const W=document.documentElement.clientWidth;
 for(const e of els){const b=e.getBoundingClientRect(); if(b.right>W+1) r.push('offscreen '+(e.id||e.className));}
 const cards=[...document.querySelectorAll('#viewAi3d .a3grid > .card')].map(e=>e.getBoundingClientRect());
 for(let i=0;i<cards.length;i++)for(let j=i+1;j<cards.length;j++){const a=cards[i],b=cards[j];
  if(a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1) r.push('cards '+i+','+j);}
 if(document.documentElement.scrollWidth>W+1) r.push('h-scroll '+document.documentElement.scrollWidth);
 return r; }"""


def shot(pg, n):
    if SHOT: pg.screenshot(path=os.path.join(SHOT, n), full_page=True)


with sync_playwright() as p:
    exe = os.environ.get("ZEIM_CHROME", "")
    b = p.chromium.launch(executable_path=exe, args=["--no-sandbox", "--disable-dev-shm-usage"]) if exe else p.chromium.launch()
    for w, h in ((1280, 900), (390, 844)):
        pg = b.new_page(viewport={"width": w, "height": h})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(U2 + "/#2d3d"); pg.wait_for_selector("#viewAi3d:not([hidden])"); pg.wait_for_timeout(800)
        eng = pg.inner_text("#a3Engine")
        ok(f"w{w}: engine missing state", "not installed" in eng.lower(), eng)
        ok(f"w{w}: Make disabled without engine", pg.is_disabled("#a3Go"))
        shot(pg, f"w{w}-engine-missing.png")
        pg.goto(U1[w] + "/#ai3d"); pg.wait_for_selector("#viewAi3d:not([hidden])"); pg.wait_for_timeout(800)
        ok(f"w{w}: nav tab present", pg.locator('[data-view="ai3d"]').first.is_visible() or w < 600)
        ok(f"w{w}: no overlaps (empty)", pg.evaluate(OVERLAP) == [], pg.evaluate(OVERLAP))
        ok(f"w{w}: photo prep is on the page", "Photo prep" in pg.inner_text("#viewAi3d") and "TripoSR" in pg.inner_text("#viewAi3d"))
        exit_hit = pg.evaluate("""() => {
          const exit = document.querySelector('#viewAi3d [data-ws-act="exit"]');
          const save = document.getElementById('saveInd');
          if (!exit) return 'no-exit';
          const b = exit.getBoundingClientRect();
          if (b.width < 40 || b.height < 40 || b.bottom < 0 || b.top > innerHeight) return 'off';
          if (!save || save.getBoundingClientRect().width < 1) return 'ok';
          const s = save.getBoundingClientRect();
          const overlap = b.left < s.right - 1 && s.left < b.right - 1 && b.top < s.bottom - 1 && s.top < b.bottom - 1;
          return overlap ? 'overlap' : 'ok';
        }""")
        ok(f"w{w}: Exit stays clear of the auto-save pill", exit_hit == "ok", exit_hit)
        shot(pg, f"w{w}-empty.png")
        pg.click("#a3Sample"); pg.check('input[name=a3Mode][value=bust]', force=True)
        pg.wait_for_selector("#a3Go:not([disabled])", timeout=10000)
        shot(pg, f"w{w}-ready.png")
        pg.click("#a3Go"); pg.wait_for_selector("#a3Res:not([hidden])", timeout=90000); pg.wait_for_timeout(1200)
        res = pg.inner_text("#a3Res")
        ok(f"w{w}: saved title is the Title field (Tango), not the sample name", "Tango" in res and "Sample photo" not in res, res)
        ok(f"w{w}: result carries AI label", "AI-made" in res, res)
        ok(f"w{w}: no overlaps (result)", pg.evaluate(OVERLAP) == [], pg.evaluate(OVERLAP))
        shot(pg, f"w{w}-result.png")
        plan = pg.inner_text("#a3Plan")
        tick = pg.inner_text("#a3Tick")
        ok(f"w{w}: cooldown is a status line", "photo to mesh" in plan.lower() and ":" in tick, plan + " | " + tick)
        ok(f"w{w}: no cooldown popup", pg.locator("#a3Cool").count() == 0)
        ok(f"w{w}: handoff stays in the page", "Send to CAD" in res and "Check" in res, res)
        pg.locator("#a3Res button", has_text="Export").first.click(); pg.wait_for_timeout(1500)
        dlg = pg.locator("dialog[open]")
        txt = dlg.first.inner_text() if dlg.count() else ""
        ok(f"w{w}: shared export picker opens with K1 0.2mm name", "K1" in txt and "0.2mm" in txt, txt[:300])
        shot(pg, f"w{w}-export.png")
        ok(f"w{w}: no page errors", not errs, errs)
        pg.close()
    b.close()
if not bad: print("PASS chrome")
