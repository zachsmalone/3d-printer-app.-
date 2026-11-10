"""Manual supports on the resin view: one mesh build, marks survive context loss and a reload.

python tests/ui_resin_context.py URL
"""
import os
import sys
import tempfile

import trimesh
from playwright.sync_api import sync_playwright

URL = sys.argv[1].rstrip("/")
bad = []


def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond:
        bad.append(name)


def box_stl(folder):
    path = os.path.join(folder, "titan-stand-in.stl")
    trimesh.creation.box(extents=[20, 16, 12]).apply_translation([0, 0, 6]).export(path)
    return path


def load(page, path):
    page.goto(URL + "/#torchc0")
    page.wait_for_selector("#rzFile", timeout=20000)
    page.set_input_files("#rzFile", path)
    page.wait_for_selector("#rzPickView canvas", timeout=30000)
    page.wait_for_function("() => !document.querySelector('#rzSupEdit').hidden", timeout=20000)
    page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.meshBuilds) >= 1", timeout=20000)
    page.wait_for_timeout(250)


def click_model(page):
    box = page.locator("#rzPickView canvas").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.4)
    page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 1", timeout=8000)


BOX = box_stl(tempfile.mkdtemp(prefix="zeim-ctx-"))
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    load(page, BOX)
    page.click("#rzModeAdd")
    click_model(page)
    builds = page.get_attribute("#rzPickView", "data-mesh-builds")
    syncs = int(page.get_attribute("#rzPickView", "data-mark-syncs") or "0")
    ok("first mark uses one mesh build", builds == "1", builds)
    for i in range(3):
        box = page.locator("#rzPickView canvas").bounding_box()
        page.mouse.click(box["x"] + box["width"] * (0.42 + i * 0.06), box["y"] + box["height"] * 0.36)
        page.wait_for_timeout(200)
    page.wait_for_function("() => Number(document.querySelector('#rzPickView').dataset.supports) >= 2", timeout=8000)
    builds = page.get_attribute("#rzPickView", "data-mesh-builds")
    syncs2 = int(page.get_attribute("#rzPickView", "data-mark-syncs") or "0")
    supports = page.get_attribute("#rzPickView", "data-supports")
    ok("more marks do not rebuild the mesh", builds == "1", builds)
    ok("marks were redrawn", syncs2 > syncs, f"{syncs} -> {syncs2}")
    page.wait_for_timeout(400)
    saved = page.evaluate("""async () => {
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('zeim.resinSupports', 1);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      const rows = await new Promise(resolve => {
        const tx = db.transaction('edits', 'readonly');
        const req = tx.objectStore('edits').getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => resolve([]);
      });
      db.close();
      return { rows: rows.length, manual: rows[0] && rows[0].manual ? rows[0].manual.length : 0 };
    }""")
    ok("marks are in IndexedDB", saved["rows"] >= 1 and saved["manual"] >= 1, str(saved))
    lost = page.evaluate("""() => {
      const canvas = document.querySelector('#rzPickView canvas');
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      const ext = gl.getExtension('WEBGL_lose_context');
      window.__zeimLose = ext;
      ext.loseContext();
      return {
        lost: document.querySelector('#rzPickView').dataset.contextLost,
        canvas: !!document.querySelector('#rzPickView canvas'),
        supports: document.querySelector('#rzPickView').dataset.supports,
        glLost: gl.isContextLost(),
      };
    }""")
    page.wait_for_timeout(200)
    lost["lost"] = page.get_attribute("#rzPickView", "data-context-lost")
    ok("context loss keeps the canvas and the marks", lost["lost"] == "1" and lost["canvas"] and lost["supports"] == supports and lost["glLost"] is True, str(lost))
    page.screenshot(path="/tmp/resin-context-lost.png")
    page.evaluate("() => window.__zeimLose.restoreContext()")
    page.wait_for_function("() => document.querySelector('#rzPickView').dataset.contextLost === '0'", timeout=5000)
    restored = page.evaluate("""() => {
      const canvas = document.querySelector('#rzPickView canvas');
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      return gl.isContextLost();
    }""")
    ok("context restore clears the lost flag", page.get_attribute("#rzPickView", "data-context-lost") == "0" and restored is False)
    ok("restore did not rebuild the mesh", page.get_attribute("#rzPickView", "data-mesh-builds") == "1")
    ok("marks survived the context", page.get_attribute("#rzPickView", "data-supports") == supports, supports)
    page.screenshot(path="/tmp/resin-after-context-restore.png")
    page.reload()
    load(page, BOX)
    ok("reload keeps the saved marks", int(page.get_attribute("#rzPickView", "data-supports") or "0") >= 1, page.get_attribute("#rzPickView", "data-supports"))
    page.screenshot(path="/tmp/resin-after-reload.png")
    bench = page.evaluate("""async () => {
      const mod = await import('/static/resin-view.js');
      const tris = 1500000;
      const big = new Float32Array(tris * 9);
      for (let i = 0; i < tris; i++) {
        const x = (i % 1500) * 0.15, y = Math.floor(i / 1500) * 0.15, o = i * 9;
        big[o] = x; big[o + 1] = y; big[o + 2] = 0;
        big[o + 3] = x + 0.15; big[o + 4] = y; big[o + 5] = 0;
        big[o + 6] = x; big[o + 7] = y + 0.15; big[o + 8] = 0;
      }
      const mem = () => performance.memory ? performance.memory.usedJSHeapSize : null;
      const before = mem();
      const copies = [];
      const tCopy = performance.now();
      for (let i = 0; i < 5; i++) {
        const copy = new Float32Array(big.length);
        copy.set(big);
        copies.push(copy, new Float32Array(big.length));
      }
      const legacyMs = performance.now() - tCopy;
      const mid = mem();
      copies.length = 0;
      const t0 = performance.now();
      const grid = mod.buildGrid(big);
      const gridMs = performance.now() - t0;
      const t1 = performance.now();
      let hits = 0;
      for (let i = 0; i < 8; i++) {
        const x0 = (100 + i) * 0.15, y0 = 40 * 0.15;
        const h = mod.raycastGrid(grid, [x0 + 0.02, y0 + 0.02, 6], [0, 0, -1]);
        if (h && Math.abs(h.point[2]) < 1e-2) hits += 1;
      }
      const rayMs = performance.now() - t1;
      return {
        legacy_ms: Math.round(legacyMs), legacy_bytes: big.byteLength * 10,
        grid_ms: Math.round(gridMs), ray_ms: Math.round(rayMs), hits,
        heap_before: before, heap_while_copying: mid, heap_after_grid: mem(),
      };
    }""")
    ok("1.5M triangle rays hit", bench["hits"] == 8, str(bench))
    print("BENCH", bench)
    ok("no page errors", not errs, errs)
    page.close()
    browser.close()
print("\n".join(bad) or "ok")
sys.exit(1 if bad else 0)
