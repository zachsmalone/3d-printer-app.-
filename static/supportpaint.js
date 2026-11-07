/* Paint-on supports on the model that is already on screen.
   Left drag / one finger paints. Right drag orbits. Scroll or two fingers zoom.
   Green = need support (enforcer), red = never (blocker). Erase removes marks under the brush.
   The mesh material is not replaced. Marks are discs on the hit point. */
import * as THREE from "three";

let strokes = [];
let kind = "enforce";
let brushR = 4;
let tipR = 1.2;
let thickness = 2.5;
let filamentSlot = "same";
let armed = false;
let painting = false;
let viewer = null;
let getProjectId = () => null;
let onStale = () => {};
const MAX = 200;
const $ = (s, el = document) => el.querySelector(s);
const savedButtons = { mouse: null, touch: null };

export function getStrokes() { return strokes.filter(s => s.kind === "enforce" || s.kind === "block").map(s => ({ ...s })); }
export function clearStrokes() { strokes = []; drawMarks(); saveSoon(); }

export function bindViewer(v) { viewer = v; listen(); drawMarks(); }
export function bindProject(fn) { getProjectId = fn; }

export function setStrokes(next, opts = {}) {
  strokes = (next || []).map(s => ({ ...s }));
  drawMarks();
  if (opts.stale) onStale();
  const n = $("#spPaintCount");
  if (n) n.textContent = countText();
}

function countText() {
  const need = strokes.filter(s => s.kind === "enforce").length;
  const never = strokes.filter(s => s.kind === "block").length;
  return strokes.length + " mark" + (strokes.length === 1 ? "" : "s")
    + (strokes.length ? ` · ${need} need / ${never} never` : "");
}

function arm(on) {
  armed = on;
  const btn = $("#spPaintArm");
  if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
  const el = viewer && viewer.renderer && viewer.renderer.domElement;
  if (!el || !viewer.controls) return;
  if (!savedButtons.mouse) {
    savedButtons.mouse = { ...viewer.controls.mouseButtons };
    savedButtons.touch = { ...viewer.controls.touches };
  }
  if (on) {
    viewer.controls.mouseButtons.LEFT = -1;
    viewer.controls.mouseButtons.RIGHT = 0; // ROTATE, so orbit stays available
    viewer.controls.touches.ONE = -1;
    el.style.cursor = "crosshair";
  } else {
    Object.assign(viewer.controls.mouseButtons, savedButtons.mouse);
    Object.assign(viewer.controls.touches, savedButtons.touch);
    el.style.cursor = "";
    hideCursor();
  }
}

function modelMeshes() {
  if (!viewer) return [];
  return viewer.group.children.filter(o => o.isMesh && !o.userData.bed && !o.userData.paint);
}

export function raycastModel(v, ev) {
  const rect = v.renderer.domElement.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const ndc = new THREE.Vector2(
    ((ev.clientX - rect.left) / rect.width) * 2 - 1,
    -((ev.clientY - rect.top) / rect.height) * 2 + 1
  );
  const rc = new THREE.Raycaster();
  rc.setFromCamera(ndc, v.camera);
  const meshes = v.group.children.filter(o => o.isMesh && !o.userData.bed && !o.userData.paint);
  const hit = rc.intersectObjects(meshes, false)[0];
  if (!hit || !hit.object) return null;
  const local = hit.object.worldToLocal(hit.point.clone());
  const normal = hit.face ? hit.face.normal.clone().transformDirection(hit.object.matrixWorld).normalize() : new THREE.Vector3(0, 0, 1);
  return { local, normal, object: hit.object };
}

function overlay() {
  if (!viewer) return null;
  let g = viewer.scene.getObjectByName("zeim-support-paint");
  if (!g) {
    g = new THREE.Group();
    g.name = "zeim-support-paint";
    g.userData.paint = true;
    viewer.scene.add(g);
  }
  return g;
}

function hideCursor() {
  const g = viewer && viewer.scene.getObjectByName("zeim-support-paint");
  const c = g && g.getObjectByName("cursor");
  if (c) c.visible = false;
}

function disc(radius, color, opacity) {
  const m = new THREE.Mesh(
    new THREE.CircleGeometry(radius, 20),
    new THREE.MeshBasicMaterial({
      color, transparent: true, opacity, depthTest: true,
      polygonOffset: true, polygonOffsetFactor: -2, side: THREE.DoubleSide,
    })
  );
  m.userData.paint = true;
  m.renderOrder = 5;
  return m;
}

function place(mesh, local, normal, host) {
  const world = host.localToWorld(local.clone());
  mesh.position.copy(world);
  const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal.clone().normalize());
  mesh.quaternion.copy(q);
  mesh.position.addScaledVector(normal, 0.15);
}

function drawMarks() {
  const g = overlay();
  if (!g) return;
  const cursor = g.getObjectByName("cursor");
  for (const c of [...g.children]) if (c !== cursor) { g.remove(c); c.geometry.dispose(); c.material.dispose(); }
  const meshes = modelMeshes();
  if (!meshes.length) return;
  for (const s of strokes) {
    const host = meshes[s.mesh] || meshes[0];
    const color = s.kind === "block" ? 0xff1744 : 0x00e676;
    const m = disc(s.r, color, 0.82);
    const n = new THREE.Vector3(s.nx || 0, s.ny || 0, s.nz || 1);
    place(m, new THREE.Vector3(s.x, s.y, s.z), n, host);
    g.add(m);
  }
  if (!cursor) {
    const ring = disc(brushR, 0xffffff, 0.95);
    ring.name = "cursor";
    ring.visible = false;
    g.add(ring);
  }
  const n = $("#spPaintCount");
  if (n) n.textContent = countText();
}

function moveCursor(hit) {
  const g = overlay();
  if (!g) return;
  let cursor = g.getObjectByName("cursor");
  if (!cursor) return;
  if (!hit || !armed) { cursor.visible = false; return; }
  cursor.geometry.dispose();
  cursor.geometry = new THREE.CircleGeometry(Math.max(brushR, 0.8), 24);
  cursor.material.color.set(kind === "block" ? 0xff1744 : kind === "erase" ? 0xffffff : 0x00e676);
  const host = hit.object;
  place(cursor, hit.local, hit.normal, host);
  cursor.visible = true;
}

let saveTimer = 0;
function saveSoon() {
  const id = getProjectId && getProjectId();
  if (!id) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch("/api/edit/" + encodeURIComponent(id) + "/support-paint", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strokes: getStrokes() }),
    }).catch(() => {});
  }, 300);
}

function paintAt(hit) {
  if (!hit) return;
  const p = hit.local, n = hit.normal;
  if (kind === "erase") {
    const before = strokes.length;
    strokes = strokes.filter(s => {
      const dx = s.x - p.x, dy = s.y - p.y, dz = s.z - p.z;
      return Math.hypot(dx, dy, dz) > brushR;
    });
    if (strokes.length !== before) { drawMarks(); saveSoon(); }
    return;
  }
  if (strokes.length >= MAX) return;
  const last = strokes[strokes.length - 1];
  if (last && last.kind === kind && Math.hypot(last.x - p.x, last.y - p.y, last.z - p.z) < brushR * 0.45) return;
  const meshes = modelMeshes();
  strokes.push({
    kind, x: +p.x.toFixed(3), y: +p.y.toFixed(3), z: +p.z.toFixed(3),
    nx: +n.x.toFixed(3), ny: +n.y.toFixed(3), nz: +n.z.toFixed(3),
    r: brushR, h: Math.max(4, brushR * 2), tip_r: tipR, thickness,
    filament_slot: filamentSlot, mesh: Math.max(0, meshes.indexOf(hit.object)),
  });
  drawMarks();
}

let listening = false;
function listen() {
  if (listening || !viewer) return;
  const el = viewer.renderer.domElement;
  el.addEventListener("pointerdown", e => {
    if (!armed || e.button !== 0) return;
    if (e.pointerType === "touch" && e.isPrimary === false) return;
    const hit = raycastModel(viewer, e);
    if (!hit) return;
    painting = true;
    el.setPointerCapture(e.pointerId);
    paintAt(hit);
    moveCursor(hit);
  });
  el.addEventListener("pointermove", e => {
    if (!armed) return;
    const hit = raycastModel(viewer, e);
    moveCursor(hit);
    if (painting) paintAt(hit);
  });
  const up = () => { if (painting) { painting = false; saveSoon(); } };
  el.addEventListener("pointerup", up);
  el.addEventListener("pointercancel", up);
  listening = true;
}

export function mountPaint(host) {
  if (!host) return;
  host.innerHTML = `
    <details class="spPaint" id="spPaintBox" open>
      <summary>Paint-on supports</summary>
      <p class="help">The model stays on screen. Turn Paint on, then drag on the surface. Green must have support, red must not. Erase lifts marks. Right-drag orbits, scroll or two fingers zoom. Left-drag paints only while Paint is on.</p>
      <div class="row">
        <div class="segmented" role="group" aria-label="Brush kind">
          <button type="button" id="spPaintNeed" aria-pressed="true">Need support</button>
          <button type="button" id="spPaintNever" aria-pressed="false">Never support</button>
          <button type="button" id="spPaintErase" aria-pressed="false">Erase</button>
        </div>
        <button type="button" class="btn small" id="spPaintArm" aria-pressed="false">Paint</button>
        <button type="button" class="btn small" id="spPaintClear">Clear</button>
      </div>
      <div class="grid2" style="margin-top:6px">
        <label class="inl">Brush Ø <input type="range" id="spPaintR" min="1" max="12" step="0.5" value="4"> <span id="spPaintRlbl">4 mm</span></label>
        <label class="inl">Tip Ø <input type="range" id="spPaintTip" min="0.4" max="6" step="0.2" value="1.2"> <span id="spPaintTiplbl">1.2 mm</span></label>
        <label class="inl">Shaft Ø <input type="range" id="spPaintTh" min="1" max="10" step="0.5" value="2.5"> <span id="spPaintThlbl">2.5 mm</span></label>
      </div>
      <div class="field" style="margin-top:6px">
        <label for="spPaintSlot">Support filament</label>
        <select id="spPaintSlot">
          <option value="same">Same as print</option>
          <option value="2">Slot 2</option>
          <option value="3">Slot 3</option>
          <option value="4">Slot 4</option>
          <option value="5">Slot 5</option>
          <option value="pva">PVA (dissolve)</option>
          <option value="hips">HIPS</option>
        </select>
      </div>
      <p class="help" id="spPaintCount" aria-live="polite">0 marks</p>
    </details>`;
  const setKind = k => {
    kind = k;
    $("#spPaintNeed").setAttribute("aria-pressed", k === "enforce" ? "true" : "false");
    $("#spPaintNever").setAttribute("aria-pressed", k === "block" ? "true" : "false");
    $("#spPaintErase").setAttribute("aria-pressed", k === "erase" ? "true" : "false");
    arm(true);
  };
  $("#spPaintNeed").onclick = () => setKind("enforce");
  $("#spPaintNever").onclick = () => setKind("block");
  $("#spPaintErase").onclick = () => setKind("erase");
  $("#spPaintArm").onclick = () => arm(!armed);
  $("#spPaintR").oninput = () => { brushR = +$("#spPaintR").value; $("#spPaintRlbl").textContent = brushR + " mm"; };
  $("#spPaintTip").oninput = () => { tipR = +$("#spPaintTip").value; $("#spPaintTiplbl").textContent = tipR + " mm"; };
  $("#spPaintTh").oninput = () => { thickness = +$("#spPaintTh").value; $("#spPaintThlbl").textContent = thickness + " mm"; };
  $("#spPaintSlot").onchange = () => { filamentSlot = $("#spPaintSlot").value; };
  $("#spPaintClear").onclick = () => clearStrokes();
  onStale = () => {
    const n = $("#spPaintCount");
    if (n) n.textContent = "Paint was cleared because the model changed. Paint the new shape.";
  };
  listen();
  drawMarks();
  arm(armed);
}
