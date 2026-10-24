"""Section themes: every section shows its own art band, bands never overlap the page header, and reduced motion stops all theme animation.
python tests/ui_section_themes.py URL [shotdir] [chromium|webkit]"""
import sys
from playwright.sync_api import sync_playwright
U = sys.argv[1].rstrip("/"); SHOTS = sys.argv[2] if len(sys.argv) > 2 else ""; ENG = sys.argv[3] if len(sys.argv) > 3 else "chromium"
SECS = {"showcase": "showcase", "slicer": "slicer", "torchc0": "torchc0", "cad": "cad", "lithophane": "lithophane", "smartfix": "smartfix", "learn": "learn", "account": "account"}
JS = """k => { const b=[...document.querySelectorAll('main:not([hidden]) .zt-band')].filter(e=>e.offsetParent||getComputedStyle(e).display!=='none'&&e.getClientRects().length);
 if(b.length!==1) return {err:'visible bands '+b.length+' '+b.map(e=>e.dataset.zt)}; const e=b[0], r=e.getBoundingClientRect();
 const h=document.querySelector('main:not([hidden]) h1:not(.sr-only)'), hr=h&&h.getBoundingClientRect();
 const anims=[...e.querySelectorAll('*')].map(x=>getComputedStyle(x).animationName).filter(n=>n&&n!=='none');
 const img=e.querySelector('img'); return {zt:e.dataset.zt, h:r.height, overlap: hr? (hr.top < r.bottom-1 && hr.bottom > r.top+1):false, anims, ok: img? img.complete&&img.naturalWidth>0 : true,
   sw: document.documentElement.scrollWidth - innerWidth}; }"""
bad = []
with sync_playwright() as p:
    b = getattr(p, ENG).launch()
    for rm in ("no-preference", "reduce"):
        for w, h in ((1280, 900), (390, 844)):
            pg = b.new_page(viewport={"width": w, "height": h}, reduced_motion=rm, color_scheme="light")
            pg.add_init_script("try{localStorage.setItem('zeim.adult','yes')}catch(e){}")
            for sec, zt in SECS.items():
                pg.goto(U + "/#" + sec); pg.wait_for_timeout(900)
                r = pg.evaluate(JS, sec)
                tag = f"{sec} w{w} {rm}"
                if "err" in r: bad.append(tag + ": " + r["err"]); continue
                if r["zt"] != zt: bad.append(f"{tag}: band {r['zt']}")
                if r["overlap"]: bad.append(tag + ": band overlaps heading")
                if not r["ok"]: bad.append(tag + ": art did not load")
                if r["sw"] > 1: bad.append(tag + f": horizontal overflow {r['sw']}")
                if rm == "reduce" and r["anims"]: bad.append(tag + ": animates under reduced motion " + ",".join(r["anims"]))
                if rm != "reduce" and sec in ("torchc0", "showcase", "slicer", "lithophane", "account", "cad") and not r["anims"]: bad.append(tag + ": expected subtle motion")
                if SHOTS and rm == "no-preference":
                    pg.wait_for_timeout(300); pg.screenshot(path=f"{SHOTS}/{sec}-w{w}{'' if ENG=='chromium' else '-'+ENG}.png")
            pg.close()
    b.close()
print("\n".join(bad) or "ok"); sys.exit(1 if bad else 0)
