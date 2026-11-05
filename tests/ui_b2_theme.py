"""Click through B2 sections and confirm the FDM wave stays in the top banner.
python tests/ui_b2_theme.py URL [shotdir]
"""
import sys
from playwright.sync_api import sync_playwright

U = sys.argv[1].rstrip("/")
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/workspace/redesign"
GRAIN = {
    "showcase": "grain-cherry.svg",
    "slicer": "grain-cypress.svg",
    "torchc0": "grain-maple.svg",
    "cad": "grain-wenge.svg",
    "lithophane": "grain-beech.svg",
    "account": "grain-walnut.svg",
}
CHROME = "/usr/local/bin/google-chrome"

PROBE = """() => {
  const cs = (el, pseudo) => el ? getComputedStyle(el, pseudo || null) : null;
  const top = document.querySelector('.topbar');
  const before = cs(top, '::before');
  const viewer = document.querySelector('#editViewer') || document.querySelector('.viewer');
  const bodyBefore = cs(document.body, '::before');
  const bodyAfter = cs(document.body, '::after');
  const wave = (before && before.backgroundImage) || '';
  const plate = viewer ? getComputedStyle(viewer).backgroundImage : '';
  const side = document.querySelector('#editSide');
  const sideBg = side ? getComputedStyle(side).backgroundImage : '';
  return {
    zsec: document.body.dataset.zsec,
    font: getComputedStyle(document.body).fontFamily,
    wave,
    plate,
    sideBg,
    bodyBefore: bodyBefore ? bodyBefore.content + ' ' + bodyBefore.backgroundImage : '',
    bodyAfter: bodyAfter ? bodyAfter.content + ' ' + bodyAfter.backgroundImage : '',
    overflow: document.documentElement.scrollWidth - innerWidth,
    sticky: top ? getComputedStyle(top).position : '',
    shGo: (() => { const b = document.querySelector('#shGo'); return b ? getComputedStyle(b).backgroundColor : ''; })(),
    accPri: (() => { const b = document.querySelector('#viewAccount .btn.primary'); return b ? getComputedStyle(b).backgroundColor : ''; })(),
    tex: getComputedStyle(document.body).getPropertyValue('--washi-tex'),
    page: (() => {
      const id = {showcase:'#viewShowcase', slicer:'#viewEdit', torchc0:'#viewTorch', cad:'#viewCad', lithophane:'#viewCreate', account:'#viewAccount'}[document.body.dataset.zsec];
      const el = id && document.querySelector(id);
      return el ? getComputedStyle(el).backgroundImage : '';
    })(),
    stage: (() => {
      const z = document.body.dataset.zsec;
      const el = z === 'slicer' ? document.querySelector('#editViewer')
        : z === 'lithophane' ? document.querySelector('#viewer')
        : z === 'torchc0' ? document.querySelector('.rzView')
        : null;
      return el ? getComputedStyle(el).backgroundImage : '';
    })(),
    side: (() => { const s = document.querySelector('#editSide'); return s ? getComputedStyle(s).backgroundImage : ''; })(),
  };
}"""


def main():
    bad = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--disable-dev-shm-usage"])
        for name, w, h in (("desktop", 1280, 900), ("phone", 390, 844)):
            page = browser.new_page(viewport={"width": w, "height": h})
            page.add_init_script("try{localStorage.setItem('zeim.adult','yes')}catch(e){}")
            page.goto(U + "/", wait_until="domcontentloaded")
            page.wait_for_function("() => window.__zeimStarted === true", timeout=20000)
            shots = [
                ("showcase", "showcase"),
                ("torchc0", "torchc0"),
                ("lithophane", "lithophane"),
                ("cad", "cad"),
                ("learn", "learn"),
                ("account", "account"),
                ("slicer", "slicer"),
            ]
            for view, label in shots:
                btn = page.locator(f'#mainNav button[data-view="{view}"]')
                if btn.is_visible():
                    btn.evaluate("el => el.scrollIntoView({block:'nearest', inline:'center'})")
                    btn.click()
                else:
                    # Learn is hidden under 420px by the existing nav rule. Open it by the same hash the button sets.
                    page.evaluate("(v) => { location.hash = v }", view)
                page.wait_for_function(
                    "(v) => document.body.dataset.zsec === v && document.body.dataset.view === v",
                    arg=view,
                    timeout=8000,
                )
                page.wait_for_timeout(350)
                if view == "slicer":
                    # Empty plate first: cypress is on the start panel, the wave is in the banner.
                    page.screenshot(path=f"{SHOTS}/live-b2-{label}-empty-{name}.png", full_page=False)
                    # Load the sample only after the other sections, so the bed-leave
                    # guard (unchanged behaviour) is not in the way of the click-through.
                    # The viewer canvas exists before a model does; wait until the empty
                    # start panel hides, which is when the mesh is on the plate.
                    page.locator("#editSample").click()
                    page.wait_for_function(
                        "() => { const s = document.querySelector('#editStart'); return !!s && s.hidden; }",
                        timeout=40000,
                    )
                    page.wait_for_timeout(600)
                info = page.evaluate(PROBE)
                tag = f"{label}-{name}"
                if info["zsec"] != view:
                    bad.append(f"{tag}: data-zsec {info['zsec']}")
                wood = GRAIN.get(view)
                if wood:
                    if wood not in info["tex"]:
                        bad.append(f"{tag}: --washi-tex {info['tex'][:160]}")
                    if view == "slicer":
                        if "grain-" in info["page"]:
                            bad.append(f"{tag}: cypress on the slicer page field")
                        if "grain-" in info["plate"] or "grain-" in info["stage"]:
                            bad.append(f"{tag}: wood on the build plate")
                        if wood not in info["side"]:
                            bad.append(f"{tag}: side panel missing cypress ({info['side'][:120]})")
                    else:
                        if wood not in info["page"]:
                            bad.append(f"{tag}: page wood missing ({info['page'][:120]})")
                        if info["stage"] and "grain-" in info["stage"]:
                            bad.append(f"{tag}: wood behind the model ({info['stage'][:120]})")
                if info["overflow"] > 2:
                    bad.append(f"{tag}: horizontal overflow {info['overflow']}")
                if "Inter" not in info["font"]:
                    bad.append(f"{tag}: font {info['font']}")
                if view == "slicer":
                    if "wave-dark.png" not in info["wave"]:
                        bad.append(f"{tag}: topbar wave missing ({info['wave'][:180]})")
                    if info["plate"] not in ("none", ""):
                        bad.append(f"{tag}: plate background {info['plate'][:180]}")
                    if "wave-dark" in info["plate"] or "wave-dark" in info["sideBg"] or "wave-dark" in info["bodyBefore"] or "wave-dark" in info["bodyAfter"]:
                        bad.append(f"{tag}: wave escaped the topbar")
                    if info["sticky"] != "sticky":
                        bad.append(f"{tag}: topbar position {info['sticky']}")
                    if "none" not in info["bodyBefore"]:
                        bad.append(f"{tag}: body::before {info['bodyBefore'][:120]}")
                if view == "showcase" and name == "desktop":
                    # search stays a dark neutral control, not the pink section fill
                    if info["shGo"] in ("rgb(244, 167, 185)", "rgb(244,167,185)"):
                        bad.append(f"{tag}: search button used the section fill")
                if view == "account" and name == "desktop":
                    if info["accPri"] not in ("rgb(201, 162, 39)", "rgb(201,162,39)"):
                        bad.append(f"{tag}: account primary {info['accPri']}")
                page.screenshot(path=f"{SHOTS}/live-b2-{tag}.png", full_page=False)
            page.close()
        browser.close()
    print("\n".join(bad) or "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
