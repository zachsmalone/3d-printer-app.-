"""Plate object drag stays put after orbit (camera frozen mid-drag). python tests/ui_slicer_plate_drag.py URL"""
import json, os, sys, tempfile
import trimesh
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
bad = []

def ok(n, c, x=""):
    print(("PASS " if c else "FAIL ") + n + ((" — " + str(x)) if (not c and x) else ""))
    if not c: bad.append(n)

d = tempfile.mkdtemp(prefix="zeim-uidrag-")
files = []
for n, s in enumerate([(30, 30, 20), (20, 40, 15)]):
    m = trimesh.creation.box(s)
    f = os.path.join(d, f"part{n+1}.stl"); m.export(f); files.append(f)

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
    pg = b.new_page(viewport={"width": 1280, "height": 860})
    pg.add_init_script("try { localStorage.setItem('zeim.age.ok','yes'); } catch(e) {}")
    pg.goto(URL + "/#slicer"); pg.wait_for_timeout(1000)
    pg.evaluate("""() => { const g=document.getElementById('ageGate'); if(g)g.remove(); document.documentElement.classList.remove('gated'); }""")
    pg.set_input_files("#editFile", files)
    pg.wait_for_selector("#multiPlate", state="visible", timeout=60000)
    pg.click("#multiPlate", force=True)
    pg.wait_for_selector("#plateTool", timeout=90000)
    pg.wait_for_timeout(600)
    pg.click("[data-pact='arrange']"); pg.wait_for_timeout(1500)
    pg.click("[data-psel='0']"); pg.wait_for_timeout(200)

    # leave orbit damping in flight, then drag
    canvas = pg.locator("#editViewer canvas")
    box = canvas.bounding_box()
    cx, cy = box["x"] + box["width"] * 0.15, box["y"] + box["height"] * 0.2
    pg.mouse.move(cx, cy); pg.mouse.down()
    for i in range(12):
        pg.mouse.move(cx + i * 7, cy + i * 2); pg.wait_for_timeout(18)
    pg.mouse.up(); pg.wait_for_timeout(40)

    before = pg.evaluate("""async () => {
      const mod = await import('/static/plate.js');
      const PL = mod.plateState; const v = PL.ctx.viewer;
      return { c: PL.ctx.p.plate.objects[0].center.slice(0,2).map(n => +n.toFixed(3)),
               hasFreeze: typeof v.freezeControls === 'function' };
    }""")
    ok("freezeControls present", before["hasFreeze"])

    scr = pg.evaluate("""async () => {
      const mod = await import('/static/plate.js');
      const THREE = await import('/static/vendor/three.module.min.js');
      const PL = mod.plateState; const v = PL.ctx.viewer; const o = PL.ctx.p.plate.objects[0];
      const p = new THREE.Vector3(o.center[0], o.center[1], 0); p.project(v.camera);
      const r = v.renderer.domElement.getBoundingClientRect();
      return { x: r.left + (p.x+1)/2*r.width, y: r.top + (-p.y+1)/2*r.height };
    }""")
    pg.mouse.move(scr["x"], scr["y"]); pg.mouse.down()
    cams = []
    for i in range(1, 14):
        pg.mouse.move(scr["x"] + i * 9, scr["y"] - i * 3); pg.wait_for_timeout(35)
        if i % 4 == 0:
            cams.append(pg.evaluate("""async () => {
              const mod = await import('/static/plate.js');
              const v = mod.plateState.ctx.viewer;
              return [+v.camera.position.x.toFixed(4), +v.camera.position.y.toFixed(4), +v.camera.position.z.toFixed(4), !!v._controlsFrozen];
            }"""))
    pg.mouse.up(); pg.wait_for_timeout(3500)

    after = pg.evaluate("""async () => {
      const mod = await import('/static/plate.js');
      const PL = mod.plateState; const v = PL.ctx.viewer;
      return { c: PL.ctx.p.plate.objects[0].center.slice(0,2).map(n => +n.toFixed(3)),
               mesh: v.group.children.map(m => [+m.position.x.toFixed(3), +m.position.y.toFixed(3)]),
               frozen: !!v._controlsFrozen, ctrl: v.controls.enabled };
    }""")
    print("cams", json.dumps(cams)); print("before", before); print("after", after)
    ok("frozen during drag", cams and all(c[3] for c in cams), cams)
    if cams:
        span = max(abs(cams[i][a] - cams[0][a]) for i in range(len(cams)) for a in range(3))
        ok("camera still mid-drag", span < 0.05, f"span={span}")
    dx = after["c"][0] - before["c"][0]; dy = after["c"][1] - before["c"][1]
    ok("object moved and stayed", abs(dx) + abs(dy) > 2, f"dx={dx} dy={dy}")
    ok("preview offset cleared", all(abs(a) < 0.05 and abs(b) < 0.05 for a, b in after["mesh"]), after["mesh"])
    ok("controls restored", after["ctrl"] and not after["frozen"], after)
    b.close()

print("RESULT", "FAIL" if bad else "PASS", bad)
sys.exit(1 if bad else 0)
