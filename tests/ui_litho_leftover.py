"""Browser check for leftover litho extras. Run: python tests/ui_litho_leftover.py [URL]. Exit 1 on failure."""
import os
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8823"
OUT = "/workspace/qa/leftover-litho/shots/"
os.makedirs(OUT, exist_ok=True)
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def run(p, w, h, tag):
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": w, "height": h})
    pg.add_init_script("localStorage.level='expert'; localStorage.setItem('zeim.adult','yes')")
    pg.goto(URL + "/#studio")
    pg.wait_for_timeout(1500)
    pg.click("#sSample")
    pg.wait_for_timeout(800)
    # new shapes visible
    for sh in ("oval", "triangle", "scallop"):
        check(pg.locator(f"[data-shape='{sh}']").count() == 1, f"{tag}: shape card {sh}")
    pg.evaluate("document.querySelector(\"[data-shape='scallop']\").click()")
    pg.wait_for_timeout(400)
    check(pg.evaluate("!document.querySelector('#frameStyleBox').hidden"), f"{tag}: frame style shown for flat")
    check(pg.evaluate("!document.querySelector('#collageBox').hidden"), f"{tag}: collage box shown for flat")
    pg.select_option("#frame_style", "double")
    pg.screenshot(path=OUT + f"{tag}_scallop_frame.png")
    # stand + end caps
    pg.evaluate("document.querySelector(\"[data-shape='rect']\").click()")
    pg.wait_for_timeout(300)
    check(pg.evaluate("!document.querySelector('#hangOpts').hidden"), f"{tag}: hang/stand opts for rect")
    pg.check("#stand")
    pg.wait_for_timeout(200)
    check(pg.evaluate("!document.querySelector('#standCapsRow').hidden"), f"{tag}: stand caps row after stand on")
    pg.check("#stand_caps")
    pg.screenshot(path=OUT + f"{tag}_stand_caps.png")
    # collage chrome
    pg.check("#collageOn")
    pg.wait_for_timeout(200)
    check(pg.evaluate("!document.querySelector('#collageOpts').hidden"), f"{tag}: collage opts after enable")
    pg.screenshot(path=OUT + f"{tag}_collage.png")
    # oval shape chrome
    pg.evaluate("document.querySelector(\"[data-shape='oval']\").click()")
    pg.wait_for_timeout(300)
    pg.screenshot(path=OUT + f"{tag}_oval.png")
    b.close()


with sync_playwright() as p:
    run(p, 1280, 800, "w1280")
    run(p, 390, 844, "w390")
print("DONE", "FAILS=" + str(len(fails)))
sys.exit(1 if fails else 0)
