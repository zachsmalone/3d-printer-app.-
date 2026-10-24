"""Browser check for litho-up2. Run: python tests/ui_litho_up2.py [URL]. Exit 1 on failure."""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8822"
OUT = "/workspace/qa/litho-up2/shots/"
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    ok or fails.append(msg)


def build(pg):
    pg.evaluate("document.querySelector('#btnBuild').click()")
    pg.wait_for_timeout(500)
    if pg.is_visible("#btnAutoDel"):
        pg.click("#btnAutoDel")
    for _ in range(240):
        if not pg.is_visible("#busy"):
            break
        pg.wait_for_timeout(250)
    pg.wait_for_timeout(1200)


def open_settings(pg):
    if pg.is_visible("#xo_tile") or pg.is_visible("#expertOpts"):
        return
    chip = pg.locator(".zws-p:has(#expertOpts) .zws-chip, .zws-p:has(#backing) .zws-chip")
    if chip.count():
        chip.first.click()
        pg.wait_for_timeout(600)


def run(p, w, h, tag):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": w, "height": h})
    pg.add_init_script("localStorage.level='expert'; localStorage.setItem('zeim.adult','yes')")
    pg.goto(URL + "/#studio")
    pg.wait_for_timeout(1500)
    pg.click("#sSample")
    pg.wait_for_timeout(800)
    open_settings(pg)
    pg.evaluate("document.getElementById('expertOpts').hidden = false")
    pg.evaluate("document.querySelector('#tileBox')?.scrollIntoView({block:'center'})")
    check(pg.is_visible("#xo_tile"), f"{tag}: seamless tile checkbox shown")
    check(pg.locator("select[name=grey_method]").count() == 1, f"{tag}: grey method select shown")
    check(pg.locator("input[name=brightness]").count() == 1, f"{tag}: brightness slider shown")
    pg.check("#xo_tile")
    pg.wait_for_timeout(200)
    check(pg.is_enabled("#xo_mmrep"), f"{tag}: mm_per_repeat enabled when tile on")
    pg.screenshot(path=OUT + f"{tag}_tone_tile.png")
    # night-light fit
    pg.evaluate("document.querySelector(\"[data-shape='nightlight']\").click()")
    pg.wait_for_timeout(500)
    check(pg.evaluate("!document.querySelector('#lightFitBox').hidden"), f"{tag}: light fit shown for night-light")
    pg.select_option("#lightFit", "tealight")
    check(pg.input_value("#diameter_mm") == "38", f"{tag}: tea-light fit sets diameter 38")
    help_t = (pg.text_content("#lightFitHelp") or "").lower()
    check("led" in help_t and "flame" in help_t, f"{tag}: honest LED / flame caution")
    pg.screenshot(path=OUT + f"{tag}_nightlight_fit.png")
    # plate size on rect
    pg.evaluate("document.querySelector(\"[data-shape='rect']\").click()")
    pg.wait_for_timeout(400)
    check(pg.evaluate("!document.querySelector('#frameSizeBox').hidden"), f"{tag}: plate size shown for flat shapes")
    pg.select_option("#frameSize", "4x6")
    check(pg.input_value("#width_mm") == "152", f"{tag}: 4×6 sets width 152")
    pg.screenshot(path=OUT + f"{tag}_frame_size.png")
    # build with stand + tile off, then export parts
    pg.uncheck("#xo_tile")
    if pg.locator("#stand").count():
        pg.check("#stand")
    build(pg)
    bid = pg.evaluate("window.__photo3d?.current?.id")
    bodies = pg.evaluate("(window.__photo3d?.current?.stats?.bodies || []).map(b => b.name)")
    check(bid and "stand" in bodies, f"{tag}: build with stand has two bodies ({bodies})")
    pg.evaluate(f"window.zeimExport.open({{ws:'studio', bid:{bid!r}}})")
    pg.wait_for_timeout(1200)
    check(pg.is_visible("#expParts"), f"{tag}: export parts fieldset shown")
    pg.check("input[name=expPart][value=stand]")
    href = pg.get_attribute("#expGo", "href") or ""
    check("part=stand" in href, f"{tag}: download link carries part=stand ({href})")
    pg.screenshot(path=OUT + f"{tag}_export_parts.png")
    pg.keyboard.press("Escape")
    # tiled sleeve build
    pg.evaluate("document.querySelector(\"[data-shape='nightlight']\").click()")
    pg.wait_for_timeout(400)
    open_settings(pg)
    pg.evaluate("document.getElementById('expertOpts').hidden = false")
    pg.check("#xo_tile")
    pg.fill("#xo_mmrep", "30") if False else pg.evaluate("(()=>{const e=document.querySelector('#xo_mmrep');e.value=30;e.dispatchEvent(new Event('input'))})()")
    build(pg)
    params = pg.evaluate("window.__photo3d?.current?.params")
    check(params and params.get("tile") is True and params.get("mm_per_repeat") == 30,
          f"{tag}: tiled sleeve saved ({params and {k: params.get(k) for k in ('tile','mm_per_repeat','shape')}})")
    pg.screenshot(path=OUT + f"{tag}_tiled_sleeve.png")
    b.close()


with sync_playwright() as p:
    run(p, 1280, 900, "w1280")
    run(p, 390, 844, "w390")
print("PASS chrome" if not fails else "FAILS: " + str(fails))
sys.exit(1 if fails else 0)
