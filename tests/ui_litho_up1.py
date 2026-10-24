"""Browser check for litho-up1. Run against a server: python tests/ui_litho_up1.py [URL]. Exit 1 on failure."""
import sys
from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8818"
OUT = "/workspace/qa/litho-up1/shots/"
fails = []
def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg); ok or fails.append(msg)

PANELS = """()=>[...document.querySelectorAll('.zws-p')].filter(w=>!w.hidden).map(w=>({id:w.id,
  off:w.classList.contains('auto-off'), r:(r=>[r.x,r.y,r.right,r.bottom])(w.getBoundingClientRect())}))"""
OVER = """()=>{const ps=[...document.querySelectorAll('.zws-p')].filter(w=>!w.hidden&&!w.classList.contains('auto-off')&&w.offsetWidth)
 .map(w=>[w.id,w.getBoundingClientRect()]);const o=[];for(let i=0;i<ps.length;i++)for(let j=i+1;j<ps.length;j++){const a=ps[i][1],b=ps[j][1];
 if(a.x+2<b.right&&b.x+2<a.right&&a.y+2<b.bottom&&b.y+2<a.bottom)o.push(ps[i][0]+'/'+ps[j][0])}
 return {o, sx: document.documentElement.scrollWidth>innerWidth+1}}"""
TINT = "()=>{const c=document.querySelector('#viewer canvas, canvas');return c?c.toDataURL().length:0}"

def build(pg):
    pg.evaluate("document.querySelector('#btnBuild').click()"); pg.wait_for_timeout(500)
    if pg.is_visible("#btnAutoDel"): pg.click("#btnAutoDel")
    for _ in range(240):
        if not pg.is_visible("#busy"): break
        pg.wait_for_timeout(250)
    pg.wait_for_timeout(1500)

def run(p, w, h, tag):
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": w, "height": h})
    pg.add_init_script("localStorage.level='expert'; localStorage.setItem('zeim.adult','yes')")
    pg.goto(URL + "/#studio"); pg.wait_for_timeout(1500); pg.click("#sSample"); pg.wait_for_timeout(800)
    pg.click("[data-shape='rect']") if pg.is_visible("[data-shape='rect']") else None
    first = None
    for i in range(4):
        build(pg); st = pg.evaluate(PANELS)
        first = first or st
        res = [x for x in st if x["id"].endswith("result") or "result" in x["id"]]
        check(all(not x["off"] for x in res), f"{tag}: result panel shown after build {i+1}")
        if w >= 1000: check(all(not x["off"] for x in st), f"{tag}: no panel tucked away after build {i+1}")
    ov = pg.evaluate(OVER); check(not ov["o"] and not ov["sx"], f"{tag}: no overlaps / sideways scroll {ov}")
    pg.screenshot(path=OUT + f"{tag}_after4builds.png")
    # backing colour
    if not pg.is_visible("#backing"):                                  # phone: Settings starts as a chip, open it
        chip = pg.locator(".zws-p:has(#backing) .zws-chip")
        if chip.count(): chip.first.click(); pg.wait_for_timeout(600)
    pg.evaluate("document.querySelector('#backingBox').scrollIntoView({block:'center'})")
    pg.select_option("#backing", "warm"); pg.wait_for_timeout(600)
    check(pg.get_attribute("#vLight", "aria-pressed") == "true", f"{tag}: choosing a backing turns Light on")
    pg.evaluate("document.querySelector('#backingBox').scrollIntoView({block:'center'})")
    pg.screenshot(path=OUT + f"{tag}_backing_warm.png")
    pg.select_option("#backing", "custom"); pg.fill("#backingHex", "#3366ff"); pg.dispatch_event("#backingHex", "input")
    pg.wait_for_timeout(600); pg.screenshot(path=OUT + f"{tag}_backing_custom_blue.png")
    pg.fill("#backingHex", "#33"); pg.dispatch_event("#backingHex", "input")
    check(pg.get_attribute("#backingHex", "aria-invalid") == "true", f"{tag}: bad hex flagged, not blocked")
    pg.fill("#backingHex", "#3366ff"); pg.dispatch_event("#backingHex", "input")
    build(pg)
    bid = pg.evaluate("window.__photo3d?.current?.id")
    saved = pg.evaluate("window.__photo3d?.current?.params?.backing")
    check(saved == "#3366ff", f"{tag}: backing saved with build ({saved})")
    pg.select_option("#backing", ""); pg.wait_for_timeout(300)
    ov = pg.evaluate(OVER); check(not ov["o"] and not ov["sx"], f"{tag}: no overlaps with Settings open {ov}")
    pg.screenshot(path=OUT + f"{tag}_settings_open.png")
    rc = pg.locator("#zws-result.min .zws-chip")
    if rc.count():                                                      # phone: result became a chip; tap brings it back
        rc.first.click(); pg.wait_for_timeout(700)
        ov = pg.evaluate(OVER)
        check(not pg.evaluate("document.querySelector('#zws-result').classList.contains('min')") and not ov["o"],
              f"{tag}: tapping the result chip brings it back, no overlap {ov}")
        pg.screenshot(path=OUT + f"{tag}_result_back.png")
    # export picker
    pg.evaluate(f"window.zeimExport.open({{ws:'studio', bid:{bid!r}}})"); pg.wait_for_timeout(1200)
    check(pg.is_visible("#expPreset"), f"{tag}: Bambu print settings option shown for 3MF")
    note = pg.text_content("#expPresetN") or ""
    check("Not tested on a real Bambu" in note, f"{tag}: honest note shown")
    pg.check("#expPresetOn"); pg.wait_for_timeout(200)
    check("preset=bambu_litho" in (pg.get_attribute("#expGo", "href") or ""), f"{tag}: download link carries preset")
    pg.screenshot(path=OUT + f"{tag}_export_bambu.png")
    dov = pg.evaluate("()=>{const d=document.querySelector('#dlgExport');return d.scrollWidth>d.clientWidth+1}")
    check(not dov, f"{tag}: export dialog has no sideways scroll")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
    pg.evaluate("document.querySelector(\"[data-shape='nightlight']\").click()"); pg.wait_for_timeout(500)
    check(pg.evaluate("!document.querySelector('#lipBox').hidden"), f"{tag}: lip controls shown for the night-light sleeve")
    pg.evaluate("(()=>{const e=document.querySelector('#lip_taper');e.value='none';e.dispatchEvent(new Event('input'))})()")
    check(pg.evaluate("!document.querySelector('#lipWarn').hidden"), f"{tag}: flat ledge shows a warning (not a block)")
    pg.evaluate("document.querySelector('#lipBox').scrollIntoView({block:'center'})"); pg.wait_for_timeout(300)
    pg.screenshot(path=OUT + f"{tag}_lip_flat_warning.png")
    pg.evaluate("(()=>{const e=document.querySelector('#lip_taper');e.value='outward';e.dispatchEvent(new Event('input'))})()")
    build(pg)
    lp = pg.evaluate("window.__photo3d?.current?.params")
    check(lp and lp.get("lip_taper") == "outward" and lp.get("taper_deg") == 45, f"{tag}: sloped lip built and saved")
    ov = pg.evaluate(OVER); check(not ov["o"] and not ov["sx"], f"{tag}: no overlaps after sleeve build {ov}")
    pg.screenshot(path=OUT + f"{tag}_sleeve_sloped_lip.png")
    b.close()

with sync_playwright() as p:
    run(p, 1280, 900, "w1280"); run(p, 390, 844, "w390")
print("PASS chrome" if not fails else "FAILS: " + str(fails)); sys.exit(1 if fails else 0)
