/* ZEIM CAD workspace — original code (three.js MIT for rendering). Every solid feature is a step in
   the project's edit history on the server (app/core/cadops.py); sketches are solved by ZEIM's own
   solver (app/core/sketch.py). Icons are ZEIM's own inline SVG. */
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";
import { offsetPlane, midPlane, parallel, hintsOn, setHintsOn } from "/static/cad-planes.js";
import { initLessons } from "/static/cad-lessons.js";
import { takeExit } from "/static/studio-library.js";
import { bindFlow } from "/static/project-flow.js";
import { clipHalfSpace, clipByW, screenOf, screenDist, inFrontOfHit, reconcileSelection as reconcileGeom } from "/static/pickgeom.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const b64 = (s, T) => { const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new T(u.buffer); };
const fmt = v => (Math.round(v * 100) / 100).toString();
async function api(url, opt = {}) {
  if (opt.json !== undefined) { opt.body = JSON.stringify(opt.json); opt.headers = { "Content-Type": "application/json" }; delete opt.json; }
  const r = await fetch(url, opt);
  let j = null; try { j = await r.json(); } catch { }
  if (!r.ok) { let d = j?.detail ?? j?.message; const info = d && typeof d === "object" && !Array.isArray(d) ? d : null; if (info) d = info.message; const er = new Error(typeof d === "string" ? d : (r.statusText || "Something went wrong.")); er.status = r.status; er.info = info; throw er; }
  return j;
}

/* ---------------------------------------------------------------- icons (ZEIM originals) */
const P = d => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const IC = {
  sketch: P('<path d="M4 20l4-1 11-11-3-3L5 16z"/><path d="M14 6l3 3"/>'),
  extrude: P('<path d="M5 15l7 4 7-4"/><path d="M5 15V9l7-4 7 4v6"/><path d="M12 13V5"/><path d="M9.5 7.5L12 5l2.5 2.5"/>'),
  revolve: P('<path d="M12 3v18" stroke-dasharray="2 2"/><path d="M7 6a8 3 0 1 0 10 0"/><path d="M15 4l2 2-2 2"/>'),
  shapes: P('<rect x="3" y="11" width="9" height="9" rx="1"/><circle cx="16.5" cy="7.5" r="4.5"/>'),
  boolean: P('<circle cx="9" cy="12" r="5"/><circle cx="15" cy="12" r="5"/>'),
  fillet: P('<path d="M4 20V10a6 6 0 0 1 6-6h10"/><path d="M4 20h4M20 4v4"/>'),
  shell: P('<path d="M4 8l8-4 8 4v8l-8 4-8-4z"/><path d="M8 10l4-2 4 2v4l-4 2-4-2z"/>'),
  offset: P('<path d="M4 16h16"/><path d="M4 10h16" stroke-dasharray="2 2"/><path d="M12 15V6M9 9l3-3 3 3"/>'),
  move: P('<path d="M12 3v18M3 12h18"/><path d="M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>'),
  scale: P('<rect x="4" y="10" width="10" height="10" rx="1"/><path d="M12 4h8v8M20 4l-8 8"/>'),
  pattern: P('<rect x="3" y="9" width="5" height="6" rx="1"/><rect x="10" y="9" width="5" height="6" rx="1"/><rect x="17" y="9" width="4" height="6" rx="1"/>'),
  align: P('<path d="M4 3v18"/><rect x="7" y="6" width="10" height="4" rx="1"/><rect x="7" y="14" width="6" height="4" rx="1"/>'),
  mirror: P('<path d="M12 3v18" stroke-dasharray="2 2"/><path d="M9 7L4 17h5zM15 7l5 10h-5z"/>'),
  visualize: P('<circle cx="12" cy="12" r="8"/><circle cx="9" cy="9" r="1.5"/><circle cx="15" cy="9" r="1.5"/><circle cx="9" cy="15" r="1.5"/>'),
  line: P('<path d="M4 20L20 4"/><circle cx="4" cy="20" r="1.5"/><circle cx="20" cy="4" r="1.5"/>'),
  rect: P('<rect x="4" y="6" width="16" height="12" rx="1"/>'),
  circle: P('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="1"/>'),
  ellipse: P('<ellipse cx="12" cy="12" rx="9" ry="5"/>'),
  polygon: P('<path d="M12 3l8 5v8l-8 5-8-5V8z"/>'),
  spline: P('<path d="M3 17c4-12 8 8 12-4 2-5 4-6 6-6"/>'),
  soffset: P('<rect x="7" y="7" width="10" height="10" rx="2"/><rect x="3" y="3" width="18" height="18" rx="4" stroke-dasharray="2 2"/>'),
  trim: P('<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M7.5 16L17 4M16.5 16L7 4"/>'),
  del: P('<path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13"/>'),
  done: P('<path d="M5 12l4 4 10-10"/>'),
  eye: P('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  eyeoff: P('<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3.2 3.9M6.6 6.6C3.8 8.4 2 12 2 12s4 7 10 7a9.6 9.6 0 0 0 4.4-1"/>'),
  lock: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  step: P('<circle cx="12" cy="12" r="3"/>'),
  joints: P('<rect x="3" y="13" width="8" height="4" rx="1"/><rect x="13" y="13" width="8" height="4" rx="1"/><circle cx="12" cy="11" r="3"/><circle cx="12" cy="11" r="1"/>'),
  merge: P('<path d="M4 6h6v12H4z"/><path d="M14 6h6v12h-6z"/><path d="M10 12h4"/><path d="M12 10l2 2-2 2"/>'),
  text: P('<path d="M5 6V4h14v2"/><path d="M12 4v14"/><path d="M9 18h6"/><path d="M3 21h18" stroke-dasharray="2 2"/>'),
};
const OP_ICON = { sketch_extrude: "extrude", revolve: "revolve", body_boolean: "boolean", round_edges: "fillet", hollow: "shell", face_offset: "offset",
  body_transform: "move", pattern: "pattern", align: "align", translate: "move", rotate: "move", scale: "scale", mirror: "mirror", parts: "boolean", cad_text: "text" };

/* ---------------------------------------------------------------- state */
const S = {
  bid: new URLSearchParams(location.search).get("bid"), scene: null, mode: "model", tool: null,
  grid: 10, snap: true, selBody: -1, selFace: null, selEdges: [], hidden: new Set(), openStep: 0,
  appearance: {}, section: false, measure: false, measPts: [],
  sk: null,   // sketch session: {plane, entities, constraints, sel:Set, tool, draft, editStep, auto, showCons}
};
const msg = (t, ok) => { const m = $("#cwMsg"); m.textContent = t || ""; m.style.color = ok ? "var(--ok)" : ""; };
const busy = (on, cancel) => {
  const el = $("#cwBusy"); if (!el) return;
  el.hidden = !on;
  let btn = $("#cwBusyCancel");
  if (!btn) {
    btn = document.createElement("button"); btn.type = "button"; btn.id = "cwBusyCancel"; btn.className = "cw-btn"; btn.textContent = "Cancel";
    el.append(btn);
  }
  btn.hidden = !on || typeof cancel !== "function";
  btn.onclick = typeof cancel === "function" ? cancel : null;
};
/* Coach hints: one compact pill (tap to expand). "Hints off" (toolbar chip, remembered per browser) hides every hint overlay. */
const LS = (() => { try { return localStorage; } catch { return null; } })();
let HINTS_ON = hintsOn(LS);
/* hint(): coach/tutorial text, hidden when Hints are off. status(): solver results, readouts and errors, always shown. */
const hint = (t, s, always = false) => { const h = $("#cwHint"); $("#cwHintT").textContent = t; $("#cwHintS").textContent = s; h.classList.remove("open"); h.hidden = !HINTS_ON && !always; };
const status = (t, s) => hint(t, s, true);
function emptyHint() { $("#cwEmpty").hidden = !HINTS_ON || !!(S.scene?.bodies?.length) || S.mode === "sketch"; }
function applyHints() {
  $("#cwHint").hidden = !HINTS_ON; emptyHint();
  const b = $("#cwHints"); b.setAttribute("aria-pressed", HINTS_ON); b.textContent = HINTS_ON ? "Hints on" : "Hints off";
}

/* ---------------------------------------------------------------- three.js stage */
/* render on demand: frames are scheduled only by invalidate() (camera/controls change, input, scene edits) */
let rafId = 0, dirtyN = 0, inFrame = false, lastPos, lastQuat;
window.__cadFrames = 0;
function invalidate(n = 2) { dirtyN = Math.max(dirtyN, n); if (!rafId) rafId = requestAnimationFrame(frame); }
window.__cadInvalidate = invalidate;
function frame() {
  rafId = 0; inFrame = true;
  controls.update(); inFrame = false;        // damping: keep going only while the camera actually still moves
  const tol = 2e-4 * camera.position.distanceTo(controls.target);   // stop once the damping tail is sub-pixel
  const moving = camera.position.distanceToSquared(lastPos) > tol * tol || 1 - Math.abs(camera.quaternion.dot(lastQuat)) > 1e-8;
  lastPos.copy(camera.position); lastQuat.copy(camera.quaternion);
  renderer.render(scene, camera); syncCube(); placeLabels(); placeCtx(); window.__cadFrames++;
  if (--dirtyN > 0 || moving) invalidate(Math.max(dirtyN, 1));
}
const stage = $("#cwStage");
// touch devices: skip MSAA and cap DPR at 1.5 (fill-rate is the phone bottleneck); desktop unchanged
const TOUCH = matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0 && matchMedia("(hover: none)").matches;
const renderer = new THREE.WebGLRenderer({ antialias: !TOUCH, alpha: true, preserveDrawingBuffer: true, powerPreference: TOUCH ? "low-power" : "default" });
renderer.setPixelRatio(Math.min(devicePixelRatio, TOUCH ? 1.5 : 2));
renderer.shadowMap.enabled = false;
renderer.localClippingEnabled = true;
stage.prepend(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 20000);
camera.up.set(0, 0, 1); camera.position.set(80, -120, 90);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.addEventListener("change", () => { if (!inFrame) invalidate(); });
lastPos = camera.position.clone(); lastQuat = camera.quaternion.clone();
scene.add(new THREE.HemisphereLight(0xffffff, 0x3a4256, 1.2));
const dl = new THREE.DirectionalLight(0xffffff, 1.8); dl.position.set(-1, -1.5, 2); scene.add(dl);
const dl2 = new THREE.DirectionalLight(0xb8c8ff, 0.5); dl2.position.set(2, 1, 1); scene.add(dl2);
const world = new THREE.Group(); scene.add(world);
const helpers = new THREE.Group(); scene.add(helpers);
const sketchG = new THREE.Group(); scene.add(sketchG);
let gridObj = null;
const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);
function disposeObj(obj) {
  if (!obj || !obj.traverse) return;
  obj.traverse(n => {
    if (n.geometry && n.geometry.dispose) n.geometry.dispose();
    const mats = n.material;
    if (Array.isArray(mats)) mats.forEach(m => m && m.dispose && m.dispose());
    else if (mats && mats.dispose) mats.dispose();
  });
}
function clearGroup(g) {
  const kids = g.children.slice();
  g.clear();
  for (const c of kids) disposeObj(c);
}
function makeGrid() {
  if (gridObj) { helpers.remove(gridObj); disposeObj(gridObj); gridObj = null; }
  const n = 40, size = S.grid * n;
  gridObj = new THREE.GridHelper(size, n, 0x6d7fa8, 0x3a4560);
  gridObj.rotation.x = Math.PI / 2; gridObj.material.transparent = true; gridObj.material.opacity = 0.45;
  helpers.add(gridObj);
  $("#cwGrid").textContent = `${S.grid} mm`;
}
makeGrid();
const axes = new THREE.AxesHelper(20); helpers.add(axes);
function resize() {
  const w = stage.clientWidth, h = stage.clientHeight; if (!w || !h) return;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); invalidate();
}
new ResizeObserver(resize).observe(stage); resize();
function loop() { invalidate(); }
// any user input may change what is drawn: one cheap passive listener covers UI-driven edits
for (const t of ["pointerdown", "pointermove", "pointerup", "pointercancel", "wheel", "keydown", "keyup", "input", "change", "click"])
  addEventListener(t, () => invalidate(), { capture: true, passive: true });
// async results (fetch -> buildWorld/drawSketch) mutate DOM too; ignore our own per-frame label/cube/ctx moves
new MutationObserver(recs => { if (recs.some(r => !r.target.closest?.(".cw-labels,.cw-cubewrap,.cw-ctx"))) invalidate(); })
  .observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden", "class", "aria-pressed"] });
/* coalesce heavy pointermove work (raycasts, snapping, highlight) to once per frame; flush before up/down */
function perFrame(fn) {
  let ev = null, id = 0;
  const run = () => { id = 0; const e = ev; ev = null; if (e) fn(e); };
  const w = e => { ev = e; if (!id) id = requestAnimationFrame(run); };
  w.flush = () => { if (id) cancelAnimationFrame(id); run(); };
  return w;
}

const FIN = { matte: [0.9, 0], satin: [0.55, 0.05], gloss: [0.2, 0.05], metal: [0.3, 0.9], glass: [0.05, 0] };
const PALETTE = ["#8fb0e0", "#e0a47a", "#9ad1a5", "#d6a3e0", "#e6d27a", "#7ad6d6", "#e08f9a"];
function bodyMaterial(i) {
  const a = S.appearance[i] || {}, [rough, metal] = FIN[a.finish || "satin"];
  const m = new THREE.MeshStandardMaterial({ color: a.color || PALETTE[i % PALETTE.length], roughness: rough, metalness: metal,
    clippingPlanes: S.section ? [clipPlane] : [], side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  if (a.finish === "glass") { m.transparent = true; m.opacity = 0.45; }
  if (i === S.selBody) m.emissive = new THREE.Color(0x2a3cff), m.emissiveIntensity = 0.35;
  return m;
}
function buildWorld(keepCam) {
  clearGroup(world); invalidate();
  for (const b of S.scene?.bodies || []) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(b64(b.positions, Float32Array), 3));
    g.setIndex(new THREE.BufferAttribute(b64(b.indices, Uint32Array), 1));
    const ng = g.toNonIndexed(); g.dispose(); ng.computeVertexNormals();
    const mesh = new THREE.Mesh(ng, bodyMaterial(b.index)); mesh.userData.body = b.index;
    const eg = new THREE.BufferGeometry(); eg.setAttribute("position", new THREE.BufferAttribute(b64(b.edges, Float32Array), 3));
    const lines = new THREE.LineSegments(eg, new THREE.LineBasicMaterial({ color: 0x10131a, clippingPlanes: S.section ? [clipPlane] : [] }));
    lines.userData.edges = true; lines.userData.body = b.index;
    const grp = new THREE.Group(); grp.add(mesh, lines); grp.userData.body = b.index; grp.visible = !S.hidden.has(b.index);
    world.add(grp);
  }
  emptyHint();
  if (!keepCam) fit();
  reconcileSelection();
  drawSelection();
}
function fit() {
  const box = new THREE.Box3().setFromObject(world);
  if (box.isEmpty()) box.set(new THREE.Vector3(-30, -30, 0), new THREE.Vector3(30, 30, 10));
  const c = box.getCenter(new THREE.Vector3()), r = Math.max(box.getSize(new THREE.Vector3()).length(), 40);
  const dir = camera.position.clone().sub(controls.target).normalize();
  controls.target.copy(c); camera.position.copy(c).addScaledVector(dir, r * 1.4); camera.far = r * 50; camera.updateProjectionMatrix();
}
function viewAlong(dir, up = new THREE.Vector3(0, 0, 1)) {
  const d = controls.target.distanceTo(camera.position) || 150;
  camera.up.copy(Math.abs(dir.dot(up)) > 0.99 ? new THREE.Vector3(0, 1, 0) : up);
  camera.position.copy(controls.target).addScaledVector(dir.clone().normalize(), d); camera.lookAt(controls.target); controls.update(); invalidate();
}

/* ---------------------------------------------------------------- exit workspace (save the browser draft first; the design itself is already on the server) */
$("#cwBack")?.addEventListener("click", ev => {
  ev.preventDefault(); ev.stopPropagation();
  const go = () => {
    const home = takeExit(sessionStorage);
    if (home.url) { location.href = home.url; return; }
    let same = false; try { same = !!document.referrer && new URL(document.referrer).origin === location.origin; } catch {}
    if (same && history.length > 1) history.back(); else location.href = "/";
  };
  if (window.zeimSave && typeof window.zeimSave.leave === "function") window.zeimSave.leave(go); else go();
});

/* ---------------------------------------------------------------- view cube (CSS 3D, own design) */
const CUBE = [["Top", [0, 0, 1], "rotateX(0deg)", "translateZ(30px)"], ["Bottom", [0, 0, -1], "rotateX(180deg) rotateZ(180deg)", "translateZ(30px)"],
  ["Front", [0, -1, 0], "rotateX(-90deg)", "translateZ(30px)"], ["Back", [0, 1, 0], "rotateX(90deg) rotateZ(180deg)", "translateZ(30px)"],
  ["Right", [1, 0, 0], "rotateY(90deg) rotateZ(-90deg)", "translateZ(30px)"], ["Left", [-1, 0, 0], "rotateY(-90deg) rotateZ(90deg)", "translateZ(30px)"]];
const cubeEl = $("#cwCube");
for (const [name, dir, rot, tz] of CUBE) {
  const b = document.createElement("button"); b.textContent = name; b.style.transform = `${rot} ${tz}`;
  b.setAttribute("aria-label", `View from ${name.toLowerCase()}`);
  // own pointer handling so the canvas/orbit listeners never swallow the tap (mouse + touch)
  b.addEventListener("pointerdown", ev => { ev.stopPropagation(); b._down = [ev.clientX, ev.clientY]; });
  b.addEventListener("pointerup", ev => {
    ev.stopPropagation(); const d = b._down; b._down = null;
    if (d && Math.hypot(ev.clientX - d[0], ev.clientY - d[1]) < 10) { ev.preventDefault(); tweenView(new THREE.Vector3(...dir)); }
  });
  b.addEventListener("click", ev => { ev.stopPropagation(); if (ev.detail === 0) tweenView(new THREE.Vector3(...dir)); });   // keyboard
  cubeEl.append(b);
}
cubeEl.parentElement.style.touchAction = "none";
let viewTween = 0;
function tweenView(dir, ms = 300) {   // rotate around the kept orbit target to look along dir
  dir = dir.clone().normalize();
  const t = controls.target.clone(), d = t.distanceTo(camera.position) || 150;
  const from = camera.position.clone().sub(t).normalize(), upFrom = camera.up.clone();
  const upTo = Math.abs(dir.z) > 0.99 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(0, 0, 1);
  const q = new THREE.Quaternion().setFromUnitVectors(from, dir), id = ++viewTween, t0 = performance.now();
  const step = now => {
    if (id !== viewTween) return;
    const k = Math.min(1, (now - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    const qi = new THREE.Quaternion().slerp(q, e);
    camera.position.copy(t).addScaledVector(from.clone().applyQuaternion(qi), d);
    camera.up.copy(upFrom).lerp(upTo, e).normalize(); camera.lookAt(t); controls.update(); invalidate();
    if (k < 1) requestAnimationFrame(step); else viewAlong(dir);
  };
  requestAnimationFrame(step);
}
function syncCube() {
  const m = new THREE.Matrix4().copy(camera.matrixWorldInverse); m.setPosition(0, 0, 0); if (window.__cubeT) m.transpose();
  const e = m.elements;   // css: y down -> flip
  cubeEl.style.transform = `matrix3d(${e[0]},${-e[1]},${e[2]},0,${-e[4]},${e[5]},${-e[6]},0,${e[8]},${-e[9]},${e[10]},0,0,0,0,1)`;
}

/* ---------------------------------------------------------------- picking */
const ray = new THREE.Raycaster();
function ndc(ev) { const r = renderer.domElement.getBoundingClientRect(); return new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1); }
function pickBody(ev) {
  ray.setFromCamera(ndc(ev), camera);
  const meshes = world.children.filter(g => g.visible).map(g => g.children[0]);
  const hit = ray.intersectObjects(meshes, false).find(h => (!S.section || clipPlane.distanceToPoint(h.point) >= 0) && clipOf(h.point).w > 1e-4);
  return hit ? { body: hit.object.userData.body, point: hit.point.clone(), normal: hit.face.normal.clone().transformDirection(hit.object.matrixWorld).normalize() } : null;
}
function clipOf(v) {
  const p = v.clone().applyMatrix4(camera.matrixWorldInverse);
  const e = camera.projectionMatrix.elements;
  const x = p.x, y = p.y, z = p.z;
  return {
    x: e[0] * x + e[4] * y + e[8] * z + e[12],
    y: e[1] * x + e[5] * y + e[9] * z + e[13],
    z: e[2] * x + e[6] * y + e[10] * z + e[14],
    w: e[3] * x + e[7] * y + e[11] * z + e[15],
  };
}
function toScreen(v) {
  const c = clipOf(v), r = renderer.domElement.getBoundingClientRect();
  if (!(c.w > 1e-4)) return [0, 0, 2];
  const [x, y] = screenOf(c, r.width, r.height);
  const nz = c.z / c.w;
  return [x, y, nz > 1 ? 2 : nz];
}
function pickEdge(ev) {
  const r = renderer.domElement.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const hit = pickBody(ev);
  let best = null, bd = ev.pointerType === "touch" ? 24 : 14;
  const minW = 1e-4;
  for (const g of world.children) {
    if (!g.visible) continue;
    const a = g.children[1].geometry.attributes.position.array;
    for (let i = 0; i < a.length; i += 6) {
      const origA = [a[i], a[i + 1], a[i + 2]], origB = [a[i + 3], a[i + 4], a[i + 5]];
      let A = origA, B = origB;
      if (S.section) {
        const kept = clipHalfSpace(A, B, clipPlane.distanceToPoint(new THREE.Vector3(...A)), clipPlane.distanceToPoint(new THREE.Vector3(...B)));
        if (!kept) continue;
        A = kept.a; B = kept.b;
      }
      const Av = new THREE.Vector3(...A), Bv = new THREE.Vector3(...B);
      const seg = clipByW(clipOf(Av), clipOf(Bv), minW);
      if (!seg) continue;
      const tAt = (w0, w1, w) => Math.abs(w1 - w0) < 1e-12 ? 0 : (w - w0) / (w1 - w0);
      const ca = clipOf(Av), cb = clipOf(Bv);
      const t0 = tAt(ca.w, cb.w, seg[0].w), t1 = tAt(ca.w, cb.w, seg[1].w);
      const at = t => new THREE.Vector3(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, A[2] + (B[2] - A[2]) * t);
      const p0 = at(t0), p1 = at(t1);
      const [ax, ay] = screenOf(seg[0], r.width, r.height), [bx, by] = screenOf(seg[1], r.width, r.height);
      const sd = screenDist(ax, ay, bx, by, mx, my);
      if (sd.d >= bd) continue;
      const q = p0.clone().lerp(p1, sd.t);
      if (hit && !inFrontOfHit(q.distanceTo(camera.position), hit.point.distanceTo(camera.position), 0.01)) continue;
      bd = sd.d; best = { a: new THREE.Vector3(...origA), b: new THREE.Vector3(...origB), body: g.userData.body };
    }
  }
  return best;
}
const selG = new THREE.Group(); scene.add(selG);
function drawSelection() {
  invalidate();
  clearGroup(selG);
  for (const e of S.selEdges) {
    const g = new THREE.BufferGeometry().setFromPoints([e.a, e.b]);
    selG.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0x29b6ff, linewidth: 3, depthTest: false })));
  }
  if (S.selFace) {
    const m = new THREE.Mesh(new THREE.CircleGeometry(3, 24), new THREE.MeshBasicMaterial({ color: 0x29b6ff, transparent: true, opacity: 0.6, depthTest: false, side: THREE.DoubleSide }));
    m.position.copy(S.selFace.point); m.lookAt(S.selFace.point.clone().add(S.selFace.normal)); selG.add(m);
  }
  for (const p of S.measPts) { const s = new THREE.Mesh(new THREE.SphereGeometry(0.8, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffb26b, depthTest: false })); s.position.copy(p); selG.add(s); }
  if (S.measPts.length === 2) selG.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(S.measPts), new THREE.LineBasicMaterial({ color: 0xffb26b, depthTest: false })));
  world.children.forEach(g => {
    const mesh = g.children[0]; if (!mesh) return;
    const prev = mesh.material;
    mesh.material = bodyMaterial(g.userData.body);
    if (prev && prev !== mesh.material && prev.dispose) prev.dispose();
  });
  renderItems();
}

/* ---------------------------------------------------------------- tools */
const MODEL_TOOLS = [
  { id: "shapes", key: "N", label: "Shapes", sub: "cube · cylinder · hole", tip: "Drop a ready-made shape: cube, cylinder, sphere, cone, ring, tube, wedge or a hole." },
  { id: "sketch", key: "K", label: "Sketch", sub: "on a plane or face", tip: "Draw a 2D shape on a plane (XY/XZ/YZ) or on a flat face you tapped first." },
  { id: "extrude", key: "E", label: "Extrude", sub: "up · down · both · cut", tip: "Pull a closed sketch into a solid, or cut it into the model." },
  { id: "revolve", key: "R", label: "Revolve", sub: "axis + angle", tip: "Spin a sketch profile around an axis (vases, knobs, wheels)." },
  { id: "boolean", key: "B", label: "Boolean", sub: "union · subtract · intersect", tip: "Combine two bodies, cut one from another or keep only the overlap." },
  { id: "fillet", key: "F", label: "Fillet/Chamfer", sub: "approximate", tip: "Round or bevel outside edges. Tap edges first to limit it; otherwise all outside edges. Approximate (mesh based)." },
  { id: "shell", key: "H", label: "Shell", sub: "wall thickness", tip: "Make the body hollow with walls of the thickness you choose (closed shell)." },
  { id: "faceoffset", key: "O", label: "Face extrude", sub: "in / out", tip: "Tap a flat face, then extrude it outward or inward." },
  { id: "move", key: "M", label: "Move/Rotate", sub: "body or all", tip: "Move and rotate a body you tapped (or everything)." },
  { id: "scale", key: "S", label: "Scale", sub: "uniform · per axis", tip: "Resize a body evenly or per axis." },
  { id: "pattern", key: "P", label: "Pattern", sub: "linear · circular", tip: "Repeat a body in a row or around a centre." },
  { id: "align", key: "A", label: "Align", sub: "to value or body", tip: "Line up a body's side or centre with a value or another body." },
  { id: "mirror", key: "I", label: "Mirror", sub: "copy or flip", tip: "Mirror a body across X, Y or Z (keep the original for symmetric parts)." },
  { id: "sculpt", key: "U", label: "Live Sculpt", sub: "brushes · remesh", tip: "Live Sculpt: every brush shows as you drag; strokes save in the background. Draw, carve, smooth, inflate, pinch, flatten, grab. One finger or mouse sculpts; two fingers (or drag off the model) orbit." },
  { id: "joints", key: "J", label: "Hinges/Joints", sub: "print-in-place", tip: "Add a hinge, ball joint, pin joint or chain whose parts move straight off the printer (a small clearance gap between them)." },
  { id: "merge", key: "G", label: "Merge", sub: "snap · fuse · rejoin", tip: "Drag bodies on the bed (they snap to each other), then fuse them into one. Smart merge puts Smart Split pieces back along their cuts." },
  { id: "repair", key: "Y", label: "Fix mesh", sub: "for imported files", tip: "Close holes and fix flipped faces in an imported mesh so solid tools can use it." },
  { id: "text", key: "T", label: "Text", sub: "emboss · engrave · plate", tip: "Raised or cut-in text on a spot you tap, or a standalone text plate." },
  { id: "visualize", key: "V", label: "Visualize", sub: "colour + finish", tip: "Pick body colours and finishes (display only; prints stay one colour)." },
];
const SKETCH_TOOLS = [
  { id: "line", key: "L", label: "Line/Arc", sub: "A toggles arc", tip: "Tap points to draw connected lines. Press A (or the Arc switch) for a 3-point arc. Tap the first point to close." },
  { id: "rect", key: "R", label: "Rectangle", sub: "corner · centre", tip: "Two taps: corner to corner (or centre to corner)." },
  { id: "circle", key: "C", label: "Circle", sub: "centre + radius", tip: "Tap the centre, then a point on the circle." },
  { id: "ellipse", key: "E", label: "Ellipse", sub: "centre + corner", tip: "Tap the centre, then a corner of its bounding box." },
  { id: "polygon", key: "G", label: "Polygon", sub: "n sides", tip: "Regular polygon: tap the centre, then a corner." },
  { id: "spline", key: "S", label: "Spline", sub: "through points", tip: "Tap points the curve passes through; double-tap or Enter to finish." },
  { id: "soffset", key: "O", label: "Offset", sub: "parallel copy", tip: "Tap a curve, type the distance." },
  { id: "trim", key: "T", label: "Trim", sub: "cut at crossings", tip: "Tap the piece of a line, arc or circle to remove (between crossings)." },
  { id: "sdelete", key: "⌫", label: "Delete", sub: "selected", tip: "Delete the selected curves (or tap a curve)." },
];
const CONS = [["horizontal", "Horizontal/Vertical", "H"], ["parallel", "Parallel", "∥"], ["perpendicular", "Perpendicular", "⊥"], ["equal", "Equal", "="],
  ["tangent", "Tangent", "T"], ["concentric", "Concentric", "◎"], ["coincident", "Coincident", "•"], ["lock", "Lock", "Fx"]];

function toolBtn(t, active) {
  return `<button class="cw-tool" data-tool="${t.id}" aria-pressed="${active === t.id}" data-tip="${esc(t.tip)}" aria-label="${esc(t.label)} (${esc(t.key)}). ${esc(t.tip)}">${IC[t.id] || IC[t.id === "faceoffset" ? "offset" : t.id === "sdelete" ? "del" : "step"]}<span class="lbl">${esc(t.label)}<span class="sub">${esc(t.sub)}</span></span><kbd>${esc(t.key)}</kbd></button>`;
}
function renderRail() {
  const r = $("#cwRail");
  if (S.mode === "sketch") {
    const s = S.sk;
    r.innerHTML = `<h3>Sketch</h3>${SKETCH_TOOLS.map(t => toolBtn(t, s.tool)).join("")}<h3>Constraints</h3>` +
      CONS.map(([id, label, g]) => `<button class="cw-tool" data-con="${id}" title="${esc(label)}: select curves first" aria-label="Add ${esc(label)} constraint to the selection"><b style="width:22px;text-align:center">${g}</b><span class="lbl">${esc(label)}</span></button>`).join("") +
      `<label class="cw-toggle"><span>Auto-constraint</span><input type="checkbox" id="skAuto" ${s.auto ? "checked" : ""}></label>
       <label class="cw-toggle"><span>Show constraints</span><input type="checkbox" id="skShow" ${s.showCons ? "checked" : ""}></label>
       <label class="cw-toggle"><span>Arc mode</span><input type="checkbox" id="skArc" ${s.arc ? "checked" : ""}></label>
       <button class="cw-tool" id="skDone" aria-label="Finish sketch (Enter)">${IC.done}<span class="lbl">Finish sketch</span><kbd>↵</kbd></button>
       <button class="cw-tool" id="skCancel" aria-label="Cancel sketch">${IC.del}<span class="lbl">Discard</span></button>`;
    $("#skAuto").onchange = e => { s.auto = e.target.checked; };
    $("#skShow").onchange = e => { s.showCons = e.target.checked; };
    $("#skArc").onchange = e => { s.arc = e.target.checked; };
    $("#skDone").onclick = finishSketch; $("#skCancel").onclick = () => exitSketch();
    r.querySelectorAll("[data-con]").forEach(b => b.onclick = () => addConstraint(b.dataset.con));
  } else {
    r.innerHTML = `<h3>Model</h3>` + MODEL_TOOLS.map(t => toolBtn(t, S.tool)).join("");
  }
  r.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => S.mode === "sketch" ? setSkTool(b.dataset.tool) : setTool(b.dataset.tool));
  syncSketchLocks();
}
function syncSketchLocks() {
  if (S.mode !== "sketch" || !S.sk) return;
  const n = S.sk.sel.size;
  const need2 = new Set(["parallel", "perpendicular", "equal", "tangent", "concentric", "coincident"]);
  document.querySelectorAll("#cwRail [data-con]").forEach(b => {
    const off = n === 0 || (need2.has(b.dataset.con) && n !== 2);
    b.disabled = off;
    b.setAttribute("aria-disabled", off ? "true" : "false");
    b.title = off ? (need2.has(b.dataset.con) ? "Select exactly two curves first" : "Select curves first") : "";
  });
}

/* ---------------------------------------------------------------- model tool panels */
const bodyCount = () => S.scene?.bodies?.length || 0;
const bodySel = (id, val = S.selBody, all = true) => `<select id="${id}">${all ? `<option value="-1" ${val < 0 ? "selected" : ""}>All bodies</option>` : ""}${(S.scene?.bodies || []).map(b => `<option value="${b.index}" ${b.index === val ? "selected" : ""}>${esc(b.name)}</option>`).join("")}</select>`;
const num = (id, v, step = "any") => `<input id="${id}" type="number" inputmode="decimal" step="${step}" value="${v}">`;
const v3 = (id, v) => `<div class="f3"><span>${id.split(":")[1] || ""}</span>${[0, 1, 2].map(k => `<input id="${id.split(":")[0]}${k}" type="number" inputmode="decimal" step="any" value="${v[k]}" aria-label="${"XYZ"[k]}">`).join("")}</div>`;
const val = id => parseFloat($("#" + id).value);
const vec = id => [0, 1, 2].map(k => parseFloat($("#" + id + k).value) || 0);
function seg(id, opts, cur) { return `<div class="cw-seg" id="${id}" role="group">${opts.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${v === cur}">${l}</button>`).join("")}</div>`; }
function segVal(id) { return $(`#${id} [aria-pressed=true]`)?.dataset.v; }
function wireSegs(root) { root.querySelectorAll(".cw-seg").forEach(g => g.querySelectorAll("button").forEach(b => b.onclick = () => { g.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); g.dispatchEvent(new Event("change")); })); }
function lockApply(reason) {
  const b = $("#tApply"); if (!b) return;
  b.disabled = !!reason;
  if (reason) { b.setAttribute("aria-disabled", "true"); b.title = reason; }
  else { b.removeAttribute("aria-disabled"); b.removeAttribute("title"); }
}
function panel(title, html, onApply, applyLabel = "Apply") {
  const p = $("#cwTool"); p.hidden = false;
  p.innerHTML = `<h2>${esc(title)}</h2>${html}<div class="cw-row"><button class="primary" id="tApply">${esc(applyLabel)}</button><button id="tCancel">Cancel</button></div>`;
  wireSegs(p);
  $("#tApply").onclick = onApply; $("#tCancel").onclick = () => setTool(null);
}
const HINTS = {
  repair: ["Fix mesh", "Repair an imported mesh."],
  sculpt: ["Live Sculpt", "Drag on the model — the shape updates live. Two fingers or drag off the model to orbit. Each stroke saves in the background (undo works)."],
  null: ["Select", "Tap a body to select it, or pick a tool on the left."],
  shapes: ["Shapes", "Tap a shape to drop it. Pick New, Join or Cut first."],
  sketch: ["Sketch", "Tap a flat face for a sketch plane, or choose XY / XZ / YZ."], extrude: ["Extrude", "Tap sketch regions to pick them, set the distance, then Apply."],
  revolve: ["Revolve", "Choose the axis and angle, then Apply."], boolean: ["Boolean", "Choose the target and tool bodies."],
  fillet: ["Fillet/Chamfer", "Tap edges to round only those (none = all outside edges)."], shell: ["Shell", "Hollow the model with this wall thickness."],
  faceoffset: ["Face extrude", "Tap a flat face, then choose outward or inward and a distance."], move: ["Move/Rotate", "Tap a body (or keep All), then enter the move and rotation."],
  scale: ["Scale", "Uniform or per axis, about the body's centre."], pattern: ["Pattern", "Linear: step between copies. Circular: centre + axis."],
  align: ["Align", "Line up a body's side with a value or another body."], mirror: ["Mirror", "Across X, Y or Z through a point; keep the original for a pair."],
  visualize: ["Visualize", "Pick a colour and finish for each body."],
  joints: ["Hinges/Joints", "Pick a joint and its size, then Add. It lands beside your model as new bodies."],
  merge: ["Merge", "Drag a body on the bed: it snaps to the grid and to other bodies' sides. Then pick bodies and Fuse."],
  text: ["Text", "Tap the model where the text should go (its centre), then Apply. Or choose Text plate."],
};
function setTool(id) {
  hideCtx();
  controls.touches.TWO = id === "sculpt" ? THREE.TOUCH.DOLLY_ROTATE : THREE.TOUCH.DOLLY_PAN;   // sculpt: one finger sculpts, two orbit
  if (id !== "sculpt") ring.visible = false;
  S.tool = id; renderRail(); $("#cwTool").hidden = true;
  const [t, s] = HINTS[id] || HINTS.null; hint(t, s);
  if (S.measure && id) toggleMeasure(false);
  if (!id) return;
  const needModel = !["sketch", "visualize"].includes(id);
  if (needModel && !bodyCount() && !["extrude", "revolve", "text", "shapes", "joints"].includes(id)) { msg("Make a solid first: Sketch, then Extrude."); S.tool = null; renderRail(); return; }
  TOOL_PANELS[id]?.();
}
/* Beginner shapes: one tap drops a ready-made solid (server op cad_shape, reusing the parts-builder primitives). */
const SHAPES = [["box", "Cube"], ["cylinder", "Cylinder"], ["sphere", "Sphere"], ["cone", "Cone"], ["torus", "Ring"], ["tube", "Tube"], ["wedge", "Wedge"], ["hole", "Hole"]];
const SH_IC = { box: '<rect x="5" y="7" width="12" height="12" rx="1"/><path d="M5 7l3-3h12v12l-3 3M17 7l3-3"/>', cylinder: '<ellipse cx="12" cy="6" rx="7" ry="2.5"/><path d="M5 6v12c0 1.4 3 2.5 7 2.5s7-1.1 7-2.5V6"/>',
  sphere: '<circle cx="12" cy="12" r="8"/><ellipse cx="12" cy="12" rx="8" ry="3"/>', cone: '<path d="M12 3L5 18c0 1.4 3 2.5 7 2.5s7-1.1 7-2.5z"/>',
  torus: '<ellipse cx="12" cy="12" rx="9" ry="5"/><ellipse cx="12" cy="12" rx="4" ry="1.8"/>', tube: '<ellipse cx="12" cy="6" rx="7" ry="2.5"/><ellipse cx="12" cy="6" rx="3.5" ry="1.2"/><path d="M5 6v12c0 1.4 3 2.5 7 2.5s7-1.1 7-2.5V6"/>',
  wedge: '<path d="M4 19h16L4 7z"/>', hole: '<circle cx="12" cy="12" r="8" stroke-dasharray="3 2"/><circle cx="12" cy="12" r="3"/>' };
function modelBox(all = false) {   // [min, max] of the picked body, or of everything
  const bs = (S.scene?.bodies || []).filter(b => all || S.selBody < 0 || b.index === S.selBody);
  if (!bs.length) return null;
  return [[0, 1, 2].map(k => Math.min(...bs.map(b => b.center[k] - b.size[k] / 2))), [0, 1, 2].map(k => Math.max(...bs.map(b => b.center[k] + b.size[k] / 2)))];
}
function shapeParams(kind, s, flat, mode, edge) {
  const h = flat ? 4 : s, B = modelBox();
  if (kind === "hole") {   // a round hole straight through, at the centre or near the +X edge (key rings)
    if (!B) return null;
    const d = { 10: 3, 20: 5, 40: 8 }[s] || 5, [lo, hi] = B, cx = (lo[0] + hi[0]) / 2, x = edge ? Math.max(cx, hi[0] - d / 2 - 3) : cx;
    return { kind: "cylinder", dims: { diameter: d, height: +(hi[2] - lo[2] + 2).toFixed(3) }, position: [x, (lo[1] + hi[1]) / 2, lo[2] - 1], mode: "cut" };
  }
  const dims = { box: { size: [s, s, h] }, cylinder: { diameter: s, height: h }, sphere: { diameter: s }, cone: { diameter: s, height: s },
    torus: { outer: s, tube: s / 4 }, tube: { outer: s, inner: s * 0.6, height: h }, wedge: { size: [s, s, h] } }[kind];
  const ht = { sphere: s, torus: s / 4, cone: s }[kind] ?? h;
  if (!B) return { kind, dims, position: [0, 0, 0], mode: "new" };
  const [lo, hi] = B, c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2];
  const pos = mode === "new" ? [modelBox(true)[1][0] + 5 + s / 2, c[1], 0]   // beside everything, on the bed
    : mode === "join" ? [c[0], c[1], hi[2] - 0.5]                             // on top, a little overlap so it fuses
    : [c[0], c[1], Math.max(lo[2] + 2, hi[2] - ht + 1)];                      // sinks in from the top, leaving a 2 mm floor
  return { kind, dims, position: pos, mode };
}
const JOINTS = [["hinge", "Hinge"], ["snap_hinge", "Snap hinge"], ["ball", "Ball joint"], ["pin", "Pin joint"], ["chain", "Chain"]];
function smartPieces() {   // the last Smart Split step (at or before the current step) that recorded its pieces
  const ops = (S.scene?.ops || []).filter(o => o.i <= (S.scene?.head ?? 0) && o.op === "smart_split" && o.params?.pieces?.length);
  return ops.length ? ops[ops.length - 1].params.pieces : null;
}
const TOOL_PANELS = {
  joints() {
    const J = S.jt || (S.jt = { kind: "hinge" });
    const rows = k => ({
      hinge: `<div class="f"><label for="jL">Length (mm)</label>${num("jL", 40)}</div><div class="f"><label for="jW">Leaf width (mm)</label>${num("jW", 15)}</div><div class="f"><label for="jT">Leaf thickness (mm)</label>${num("jT", 2)}</div><div class="f"><label for="jN">Knuckles (3, 5, 7, 9)</label>${num("jN", 5, 2)}</div>`,
      ball: `<div class="f"><label for="jS">Size (mm)</label>${num("jS", 20)}</div>`,
      pin: `<div class="f"><label for="jL">Arm length (mm)</label>${num("jL", 40)}</div><div class="f"><label for="jW">Arm width (mm)</label>${num("jW", 10)}</div><div class="f"><label for="jT">Arm thickness (mm)</label>${num("jT", 3)}</div>`,
      chain: `<div class="f"><label for="jK">Links</label>${num("jK", 5, 1)}</div><div class="f"><label for="jS">Link length (mm)</label>${num("jS", 16)}</div>`,
    })[k === "snap_hinge" ? "hinge" : k];
    const tips = { hinge: "Prints flat and assembled: the knuckles turn around a pin inside them. For box lids, Move it to the back edge and Join each leaf.", snap_hinge: "Two separate leaves: the C-shaped knuckles clip onto the other leaf's pin after printing.",
      ball: "A ball trapped in a socket with an open top; the stem comes out through the opening.", pin: "Two arms turning on a capped pin. The upper arm steps down to the bed, so it needs no supports.", chain: "Flat and standing links that print already linked. The flat links bridge a small gap." };
    const draw = () => {
      panel("Hinges & joints", `${seg("jKind", JOINTS, J.kind)}<div id="jRows">${rows(J.kind)}</div>
        <div class="f"><label for="jC">Clearance (mm)</label>${num("jC", 0.3)}</div>
        <p class="help">${esc(tips[J.kind])} 0.3 mm suits most FDM printers; use more if parts fuse. Fit is simulated, so print a small one first.</p>`,
        () => {
          const p = { kind: J.kind, clearance: val("jC") }, g = id => $("#" + id) ? val(id) : undefined;
          for (const [k, id] of [["length", "jL"], ["width", "jW"], ["thickness", "jT"], ["knuckles", "jN"], ["size", "jS"], ["links", "jK"]]) { const v = g(id); if (v !== undefined && !Number.isNaN(v)) p[k] = v; }
          const B = modelBox(true); if (B) p.position = [B[1][0] + 10 + (p.length || p.size || 20) / 2, (B[0][1] + B[1][1]) / 2, 0];
          addOp("cad_joint", p);
        }, "Add");
      $("#jKind").addEventListener("change", () => { J.kind = segVal("jKind"); draw(); });
    };
    draw();
  },
  merge() {
    const n = bodyCount(), pcs = smartPieces();
    if (n < 2 && !pcs) { msg("Merge needs two bodies. Add a shape or a joint, or Smart Split a model first."); return setTool(null); }
    const sel = S.mergeSel || (S.mergeSel = new Set());
    panel("Merge", `${pcs ? `<div class="f"><button type="button" class="cw-btn" id="mSmart">Smart merge: rejoin ${pcs.length} split pieces</button><p class="help">Puts the pieces back where Smart Split cut them, then fuses them. Pieces you moved since are left alone.</p></div>` : ""}
      ${n >= 2 ? `<div class="f"><label>Bodies to fuse (first = stays put)</label><div class="cw-checks" id="mBodies">${S.scene.bodies.map(b => `<label class="cw-toggle"><span>${esc(b.name)}</span><input type="checkbox" value="${b.index}" ${sel.has(b.index) || (!sel.size && b.index < 2) ? "checked" : ""}></label>`).join("")}</div></div>
      <div class="f"><label>Snap the others to the first</label>${seg("mSnap", [["none", "As placed"], ["x+", "+X side"], ["x-", "−X side"], ["y+", "+Y side"], ["y-", "−Y side"], ["z+", "On top"]], "none")}</div>
      <p class="help">Drag a body on the bed to place it by hand: it snaps to the grid and to the other bodies' sides. Snapped pieces overlap 0.2 mm so they fuse.</p>` : ""}`,
      () => {
        const ids = [...$("#cwTool").querySelectorAll("#mBodies input:checked")].map(i => +i.value);
        if (ids.length < 2) return msg("Pick at least two bodies to fuse.");
        addOp("merge_bodies", { bodies: ids, snap: segVal("mSnap") || "none" });
      }, "Fuse");
    if (n < 2) $("#tApply").hidden = true;
    $("#cwTool").querySelectorAll("#mBodies input").forEach(i => i.onchange = () => { i.checked ? sel.add(+i.value) : sel.delete(+i.value); });
    if (pcs) $("#mSmart").onclick = () => addOp("smart_merge", { pieces: pcs });
  },
  shapes() {
    const H = S.shp || (S.shp = { size: 20, flat: false, mode: "new", edge: false });
    const has = bodyCount() > 0;
    if (!has) H.mode = "new";
    panel("Shapes", `${has ? `<div class="f"><label>Adds as</label>${seg("shMode", [["new", "New piece"], ["join", "Join"], ["cut", "Cut out"]], H.mode)}</div>` : ""}
      <div class="f"><label>Size</label>${seg("shSize", [["10", "Small"], ["20", "Medium"], ["40", "Large"]], String(H.size))}</div>
      <label class="cw-toggle"><span>Flat (4 mm tall)</span><input type="checkbox" id="shFlat" ${H.flat ? "checked" : ""}></label>
      <div class="cw-shapes" role="group" aria-label="Shapes">${SHAPES.map(([k, l]) => `<button type="button" data-shape="${k}" ${k === "hole" && !has ? "disabled" : ""}><svg viewBox="0 0 24 24" aria-hidden="true">${SH_IC[k]}</svg><span>${l}</span></button>`).join("")}</div>
      ${has ? `<label class="cw-toggle"><span>Hole near the edge (key ring)</span><input type="checkbox" id="shEdge" ${H.edge ? "checked" : ""}></label>` : ""}
      <p class="help">Small 10 mm · Medium 20 mm · Large 40 mm. ${has ? "Join and Cut use the picked body, or the whole model." : "Your first shape starts the design."} Move or Scale it afterwards; each shape is a step in History.</p>`,
      () => setTool(null), "Done");
    $("#tCancel").hidden = true;
    const sync = () => { H.size = +segVal("shSize"); H.flat = $("#shFlat").checked; if (has) { H.mode = segVal("shMode"); H.edge = $("#shEdge").checked; } };
    $("#cwTool").querySelectorAll("[data-shape]").forEach(b => b.onclick = async () => {
      sync(); const p = shapeParams(b.dataset.shape, H.size, H.flat, H.mode, H.edge);
      if (!p) return msg("Add a shape first, then cut a hole in it.");
      await addOp("cad_shape", p); setTool("shapes");   // palette stays open for the next shape
    });
  },
  sketch() {
    const face = S.selFace, prev = S.prevFace;
    const pick = v => v === "face" ? planeFromFace(face) : v === "face2" ? planeFromFace(prev) : v;
    const bases = [...(face ? [["face", "Picked face"]] : []), ["XY", "XY (top)"], ["XZ", "XZ (front)"], ["YZ", "YZ (side)"]];
    const others = [...(prev ? [["face2", "Previous face"]] : []), ...bases];
    panel("New sketch", `<p class="help">${face ? "Sketch on the face you tapped, or choose a main plane:" : "Choose a plane (or Cancel, tap a flat face, then Sketch again):"}</p>
      ${seg("tPlane", bases, face ? "face" : "XY")}
      <div class="f"><label>Construction plane</label>${seg("tCons", [["none", "None"], ["offset", "Offset"], ["mid", "Midplane"]], "none")}</div>
      <div class="f" id="tOffRow" hidden><label for="tOff">Offset distance (mm, − = other side)</label>${num("tOff", 10)}</div>
      <div class="f" id="tMidRow" hidden><label>Midway to (must be parallel)</label>${seg("tPlane2", others, prev ? "face2" : face ? "XY" : "XY")}</div>`,
      () => {
        const base = pick(segVal("tPlane")), c = segVal("tCons");
        try {
          if (c === "offset") return startSketch(offsetPlane(base, val("tOff")));
          if (c === "mid") {
            const other = pick(segVal("tPlane2"));
            if (!parallel(base, other)) return msg("Midplane needs two parallel planes or faces (e.g. the two sides of a block).");
            return startSketch(midPlane(base, other));
          }
        } catch (e) { return msg(e.message); }
        startSketch(base);
      }, "Start sketch");
    $("#tCons").addEventListener("change", () => { const c = segVal("tCons"); $("#tOffRow").hidden = c !== "offset"; $("#tMidRow").hidden = c !== "mid"; });
  },
  extrude() { extrudePanel("extrude"); }, revolve() { extrudePanel("revolve"); },
  boolean() {
    if (bodyCount() < 2) { msg("Boolean needs two bodies. Extrude with 'New body' or Pattern first."); return setTool(null); }
    panel("Boolean", `${seg("tKind", [["union", "Union"], ["subtract", "Subtract"], ["intersect", "Intersect"]], "union")}
      <div class="f"><label for="tA">Target</label>${bodySel("tA", Math.max(0, S.selBody), false)}</div>
      <div class="f"><label for="tB">Tool</label>${bodySel("tB", S.selBody === 1 ? 0 : 1, false)}</div>`,
      () => addOp("body_boolean", { kind: segVal("tKind"), target: +$("#tA").value, tool: +$("#tB").value }));
  },
  fillet() {
    panel("Fillet / Chamfer", `${seg("tStyle", [["fillet", "Fillet (round)"], ["chamfer", "Chamfer (bevel)"]], "fillet")}
      <div class="f"><label for="tR">Radius / size (mm)</label>${num("tR", 1)}</div>
      <div class="f"><label for="tBody">Body</label>${bodySel("tBody")}</div>
      <p class="help" id="tEdges">${S.selEdges.length ? `${S.selEdges.length} edge(s) picked.` : "No edges picked: every outside edge is rounded."} Approximate mesh, not a precise solid fillet or chamfer: inside corners stay sharp and corners at the ends of picked edges blend a little. Can take a few seconds.</p>`,
      () => addOp("round_edges", { style: segVal("tStyle"), radius: val("tR"), body: +$("#tBody").value, edges: S.selEdges.map(e => [e.a.toArray(), e.b.toArray()]) }));
  },
  shell() {
    panel("Shell", `<div class="f"><label for="tW">Wall (mm)</label>${num("tW", 2)}</div><div class="f"><label for="tD">Drain hole Ø (mm, 0 = none)</label>${num("tD", 0)}</div>
      <p class="help">Makes a closed hollow inside (good for resin prints and saving material). Removing a face to open the shell is not available yet.</p>`,
      () => addOp("hollow", { wall: val("tW"), drain_diameter: val("tD") }));
  },
  faceoffset() {
    panel("Face extrude", `<p class="help">${S.selFace ? "Face picked." : "Tap a flat face on the model. Apply stays off until you do."}</p>
      ${seg("tDir", [["out", "Outward"], ["in", "Inward"]], "out")}
      <div class="f"><label for="tDist">Distance (mm)</label>${num("tDist", 2)}</div>
      <p class="help">Outward grows the face. Inward pushes it into the solid. This pushes one flat mesh region. It is not a precise solid offset: neighbouring triangles stretch, and a face that is not flat is refused. The distance here is always positive.</p>`,
      () => {
        if (!S.selFace) return msg("Tap a flat face first.");
        const d = Math.abs(val("tDist"));
        addOp("face_offset", { point: S.selFace.point.toArray(), normal: S.selFace.normal.toArray(), distance: segVal("tDir") === "in" ? -d : d });
      });
    if (!S.selFace) lockApply("Tap a flat face first");
  },
  move() {
    panel("Move / Rotate", `<div class="f"><label for="tBody">Body</label>${bodySel("tBody")}</div>${v3("tMv:Move", [0, 0, 0])}${v3("tRo:Rotate°", [0, 0, 0])}<p class="help">Rotation is about the body's centre.</p>`,
      () => addOp("body_transform", { body: +$("#tBody").value, move: vec("tMv"), rotate: vec("tRo") }));
  },
  scale() {
    panel("Scale", `<div class="f"><label for="tBody">Body</label>${bodySel("tBody")}</div>${seg("tSm", [["u", "Uniform"], ["n", "Per axis"]], "u")}
      <div class="f" id="tU"><label for="tF">Factor</label>${num("tF", 1.5)}</div><div id="tN" hidden>${v3("tSc:×", [1, 1, 1])}</div>`,
      () => { const u = segVal("tSm") === "u", f = val("tF"); addOp("body_transform", { body: +$("#tBody").value, scale: u ? [f, f, f] : vec("tSc") }); });
    $("#tSm").addEventListener("change", () => { const u = segVal("tSm") === "u"; $("#tU").hidden = !u; $("#tN").hidden = u; });
  },
  pattern() {
    panel("Pattern", `<div class="f"><label for="tBody">Body</label>${bodySel("tBody")}</div>${seg("tPk", [["linear", "Linear"], ["circular", "Circular"]], "linear")}
      <div class="f"><label for="tN">Count</label>${num("tN", 3, 1)}</div><div id="tLin">${v3("tStep:Step", [30, 0, 0])}</div>
      <div id="tCir" hidden>${v3("tCen:Centre", [0, 0, 0])}${v3("tAx:Axis", [0, 0, 1])}<div class="f"><label for="tAng">Total angle°</label>${num("tAng", 360)}</div></div>`,
      () => { const lin = segVal("tPk") === "linear";
        addOp("pattern", lin ? { kind: "linear", body: +$("#tBody").value, count: val("tN"), step: vec("tStep") } : { kind: "circular", body: +$("#tBody").value, count: val("tN"), center: vec("tCen"), axis: vec("tAx"), angle: val("tAng") }); });
    $("#tPk").addEventListener("change", () => { const l = segVal("tPk") === "linear"; $("#tLin").hidden = !l; $("#tCir").hidden = l; });
  },
  align() {
    panel("Align", `<div class="f"><label for="tBody">Body</label>${bodySel("tBody", Math.max(0, S.selBody), false)}</div>
      ${seg("tAx", [["x", "X"], ["y", "Y"], ["z", "Z"]], "z")}${seg("tSide", [["min", "Min"], ["center", "Centre"], ["max", "Max"]], "min")}
      <div class="f"><label for="tTo">To</label><select id="tTo"><option value="-1">A value</option>${(S.scene?.bodies || []).map(b => `<option value="${b.index}">${esc(b.name)}</option>`).join("")}</select></div>
      <div class="f"><label for="tVal">Value (mm)</label>${num("tVal", 0)}</div>`,
      () => addOp("align", { body: +$("#tBody").value, axis: segVal("tAx"), side: segVal("tSide"), to_body: +$("#tTo").value, value: val("tVal") }));
  },
  mirror() {
    panel("Mirror", `<div class="f"><label for="tBody">Body</label>${bodySel("tBody")}</div>${seg("tAx", [["x", "Across X"], ["y", "Across Y"], ["z", "Across Z"]], "x")}
      ${v3("tPv:Through", [0, 0, 0])}<label class="cw-toggle"><span>Keep the original</span><input type="checkbox" id="tKeep" checked></label>`,
      () => addOp("body_transform", { body: +$("#tBody").value, mirror: segVal("tAx"), pivot: vec("tPv"), copy: $("#tKeep").checked }));
  },
  sculpt() {
    const B = S.brush || (S.brush = { brush: "draw", radius: 5, strength: 0.5, sym: false, edge: 1 });
    panel("Live Sculpt", `<p class="help" id="cwLiveSculpt" role="status" aria-live="polite">Live Sculpt · drag to shape</p>
      ${seg("tBrush", [["draw", "Draw"], ["carve", "Carve"], ["smooth", "Smooth"], ["inflate", "Inflate"], ["pinch", "Pinch"], ["flatten", "Flatten"], ["grab", "Grab"]], B.brush)}
      <div class="f"><label for="tRad">Size <b id="tRadV">${B.radius} mm</b></label><input id="tRad" type="range" min="0.5" max="40" step="0.5" value="${B.radius}"></div>
      <div class="f"><label for="tStr">Strength <b id="tStrV">${Math.round(B.strength * 100)}%</b></label><input id="tStr" type="range" min="0.05" max="1" step="0.05" value="${B.strength}"></div>
      <label class="cw-toggle"><span>Symmetry X (mirror across X = 0)</span><input type="checkbox" id="tSym" ${B.sym ? "checked" : ""}></label>
      <div class="f"><label for="tEdge">Longest edge after subdivision (mm)</label>${num("tEdge", B.edge)}</div>
      <p class="help">Every brush shows live on the model as you drag. Strokes save in the background (no waiting spinner). Undo waits until the stroke has saved. The brush follows the surface you are looking at: the back of a thin wall stays put. A stroke that would fold the mesh or change size outside the brush is refused. Subdivide evenly splits long edges. It does not build a new surface.</p>`,
      () => addOp("remesh", { edge: val("tEdge") }).then(() => setTool("sculpt")), "Subdivide evenly");
    const sync = () => { B.brush = segVal("tBrush"); B.radius = val("tRad"); B.strength = val("tStr"); B.sym = $("#tSym").checked; B.edge = val("tEdge");
      $("#tRadV").textContent = B.radius + " mm"; $("#tStrV").textContent = Math.round(B.strength * 100) + "%"; };
    $("#cwTool").querySelectorAll("input").forEach(i => i.oninput = sync); $("#tBrush").addEventListener("change", sync);
    $("#tCancel").textContent = "Done";
  },
  repair() { panel("Fix mesh", `<p class="help">Repairs holes, flipped and duplicate faces. Imported files that aren't closed solids need this before Boolean, Fillet or Extrude join/cut.</p>`, () => addOp("repair", {})); },
  text() {
    const T = S.txt || (S.txt = { text: "ZEIM", font: "sans-bold", size: 8, depth: 1, style: "raised", target: bodyCount() ? "surface" : "plate", rotation: 0, nozzle: 0.4, plate_thickness: 2, margin: 3 });
    if (!bodyCount()) T.target = "plate";
    const face = S.selFace;
    if (face && face !== T.face && bodyCount()) { T.face = face; T.target = "surface"; }   // a fresh tap means "put it here"
    panel("Text & emboss", `<div class="f"><label for="tTxt">Text</label><input id="tTxt" type="text" maxlength="60" autocomplete="off" value="${esc(T.text)}"></div>
      ${seg("tStyle", [["raised", "Raised"], ["cut", "Cut in"]], T.style)}
      <div class="f"><label>Where</label>${seg("tTarget", [...(bodyCount() ? [["surface", "On model"]] : []), ["plate", "Text plate"]], T.target)}</div>
      <p class="help" id="tWhere">${T.target === "plate" ? (bodyCount() ? "A new plate is placed beside the model." : "A standalone plate with your text.") : face ? "Spot picked: tap again to move it." : "Tap the model where the text should be centred."}</p>
      ${T.target === "surface" ? `<label class="cw-toggle"><span>Center and fit on this face</span><input type="checkbox" id="tFit" checked></label>` : ""}
      ${bodyCount() ? `<div class="cw-row"><button type="button" id="tPick">${face ? "Move spot" : "Pick spot on model"}</button></div>` : ""}
      <div class="f"><label for="tFont">Font</label><select id="tFont">${[["sans-bold", "Sans bold (recommended)"], ["sans", "Sans"], ["serif", "Serif"], ["mono", "Mono"]].map(([v, l]) => `<option value="${v}" ${v === T.font ? "selected" : ""}>${l}</option>`).join("")}</select></div>
      <div class="f"><label for="tSize">Letter height (mm)</label>${num("tSize", T.size)}</div>
      <div class="f"><label for="tDepth">${T.style === "cut" ? "Depth" : "Height"} (mm)</label>${num("tDepth", T.depth)}</div>
      <details class="cw-adv"><summary>Advanced</summary>
        <div class="f"><label for="tRot">Rotation°</label>${num("tRot", T.rotation)}</div>
        <div class="f"><label for="tNoz">Nozzle (mm, for warnings)</label>${num("tNoz", T.nozzle)}</div>
        <div class="f"><label for="tPth">Plate thickness (mm)</label>${num("tPth", T.plate_thickness)}</div>
        <div class="f"><label for="tMg">Plate margin (mm)</label>${num("tMg", T.margin)}</div>
      </details>
      <p class="help">Recommended: Sans bold, 8 mm letters, 1 mm deep. The result is one solid; export as usual.</p>`,
      () => {
        sync();
        if (!T.text.trim()) return msg("Type some text first.");
        const p = { text: T.text, font: T.font, size: T.size, depth: T.depth, style: T.style, target: T.target, rotation: T.rotation, nozzle: T.nozzle };
        if (T.target === "plate") Object.assign(p, { plate_thickness: T.plate_thickness, margin: T.margin });
        else { if (!S.selFace) return msg("Tap the model where the text should go."); Object.assign(p, { point: S.selFace.point.toArray(), normal: S.selFace.normal.toArray() }); if ($("#tFit")?.checked) p.fit = true; }
        addOp("cad_text", p);
      });
    const sync = () => Object.assign(T, { text: $("#tTxt").value, font: $("#tFont").value, size: val("tSize"), depth: val("tDepth"), style: segVal("tStyle"), target: segVal("tTarget"),
      rotation: val("tRot") || 0, nozzle: val("tNoz") || 0.4, plate_thickness: val("tPth"), margin: val("tMg") });
    $("#cwTool").querySelectorAll("input,select").forEach(i => i.addEventListener("input", sync));
    if ($("#tPick")) $("#tPick").onclick = () => { sync(); $("#cwTool").hidden = true; hint("Text", "Tap the model where the text should be centred.", true); };   // panel steps aside (phones), the tap brings it back
    if (T.target === "surface" && !S.selFace) lockApply("Tap the model where the text should go");
    ["tStyle", "tTarget"].forEach(id => $("#" + id).addEventListener("change", () => { sync(); const open = $("#cwTool .cw-adv").open; TOOL_PANELS.text(); $("#cwTool .cw-adv").open = open; }));
  },
  visualize() {
    const bs = S.scene?.bodies || [];
    panel("Visualize", bs.map(b => { const a = S.appearance[b.index] || {}; return `<div class="f"><label for="vc${b.index}">${esc(b.name)}</label><span style="display:flex;gap:4px"><input type="color" id="vc${b.index}" value="${a.color || PALETTE[b.index % PALETTE.length]}" style="width:48px">
      <select id="vf${b.index}" aria-label="${esc(b.name)} finish">${Object.keys(FIN).map(f => `<option ${f === (a.finish || "satin") ? "selected" : ""}>${f}</option>`).join("")}</select></span></div>`; }).join("") +
      `<p class="help">Display only: exported files and prints stay a single colour.</p>`, async () => {
        const out = {}; bs.forEach(b => out[b.index] = { color: $("#vc" + b.index).value, finish: $("#vf" + b.index).value });
        S.appearance = out; buildWorld(true);
        if (S.bid) try { await api(`/api/cad/${S.bid}/appearance`, { method: "PUT", json: { bodies: out } }); msg("Appearance saved.", true); } catch (e) { msg(e.message); }
        setTool(null);
      }, "Save");
    $("#cwTool").querySelectorAll("input[type=color],select").forEach(el => el.oninput = () => { bs.forEach(b => S.appearance[b.index] = { color: $("#vc" + b.index).value, finish: $("#vf" + b.index).value }); buildWorld(true); });
  },
};

/* ---------------------------------------------------------------- server round trips */
async function load(keepCam) {
  hideCtx();
  if (!S.bid) { S.scene = null; buildWorld(); renderHist(); return; }
  try { S.scene = await api(`/api/cad/${S.bid}/scene`); }
  catch (e) { if (e.status === 413 && e.info?.keep_ratio) { bigModel(e); return; } throw e; }
  $("#cwBig")?.remove();
  displayLite(S.scene);
  S.appearance = S.scene.appearance || {};
  $("#cwTitle").value = S.scene.title || "My design";
  buildWorld(keepCam); renderHist(); updateTop(); lessons.tick();
}
function updateTop() {
  $("#cwUndo").disabled = sculptSaving || !S.scene?.can_undo;
  $("#cwUndo").title = sculptSaving ? "Undo waits until this stroke finishes saving" : "Undo · Ctrl/⌘+Z";
  $("#cwRedo").disabled = !S.scene?.can_redo;
  const d = S.scene?.downloads;
  $("#cwDlStl").href = d ? d.stl : "#"; $("#cwDl3mf").href = d ? d["3mf"] : "#";
  $("#cwToSlicer").href = S.bid ? `/?edit=${encodeURIComponent(S.bid)}#slicer` : "#";
}
/* Over the face limit: the scene is a lighter view. Downloads and the Slicer still use the full mesh. */
function commas(n) { return Math.round(Number(n) || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
function displayLite(scene) {
  $("#cwLite")?.remove();
  if (!scene?.display_simplified) return;
  const d = document.createElement("div"); d.id = "cwLite"; d.className = "cw-warn"; d.setAttribute("role", "status");
  d.innerHTML = `<div><b>Lighter view</b><p>This model has ${commas(scene.triangles)} triangles. CAD is showing a lighter view (${commas(scene.display_triangles)}) so you can see and edit it. Downloads and the Slicer still use the full model.</p></div><button type="button" class="cw-btn" data-b="x" aria-label="Dismiss"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
  d.querySelector("[data-b=x]").onclick = () => d.remove();
  $("#cwStage").append(d);
}
/* Decimation failed: offer a simplified copy as an undoable step. Never blocks: the editor link stays. */
function bigModel(e) {
  $("#cwBig")?.remove(); $("#cwLite")?.remove();
  const d = document.createElement("div"); d.id = "cwBig"; d.className = "cw-warn"; d.setAttribute("role", "status");
  d.innerHTML = `<div><b>Large model</b><p>${esc(e.message)}</p><div class="cw-row"><button type="button" class="cw-btn primary" data-b="simp">Open simplified copy</button><a class="cw-btn" href="/?edit=${encodeURIComponent(S.bid)}">Open in editor</a></div></div><button type="button" class="cw-btn" data-b="x" aria-label="Dismiss"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
  d.querySelector("[data-b=x]").onclick = () => d.remove();
  d.querySelector("[data-b=simp]").onclick = () => run(async () => {
    await api(`/api/edit/${S.bid}/op`, { method: "POST", json: { op: "simplify", params: { keep_ratio: e.info.keep_ratio } } });
    await load(true);
  }, "Simplified copy opened. Undo or History brings back the full detail.");
  $("#cwStage").append(d);
  S.scene = null; buildWorld(); renderHist(); msg(e.message);
}
async function run(fn, okText) {
  busy(true); msg("");
  try { await fn(); if (okText) msg(okText, true); return true; }
  catch (e) {
    if (e.name === "AbortError") { msg("Cancelled. This page stopped waiting. If the file already reached the server, it can still appear in Projects."); return false; }
    msg(e.message); return false;
  } finally { busy(false); }
}
/* Print warnings (e.g. text thinner than the nozzle): advisory only, dismissible, never block. */
function showWarn(list) {
  $("#cwWarn")?.remove();
  if (!list?.length) return;
  const d = document.createElement("div"); d.id = "cwWarn"; d.className = "cw-warn"; d.setAttribute("role", "status");
  d.innerHTML = `<div><b>Print tip</b>${list.map(w => `<p>${esc(w)}</p>`).join("")}</div><button type="button" class="cw-btn" aria-label="Dismiss print tip"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
  d.querySelector("button").onclick = () => d.remove();
  $("#cwStage").append(d);
}
async function addOp(op, params) {
  let rep = null;
  const ok = await run(async () => {
    if (!S.bid) {
      if (!["sketch_extrude", "revolve", "cad_text", "cad_shape", "cad_joint"].includes(op)) throw new Error("Start with a shape, or a sketch and Extrude.");
      const j = rep = await api("/api/cad/new", { method: "POST", json: { op, params, title: $("#cwTitle").value || "My design" } });
      if (!j.id) throw new Error("Your 5 recent builds are full. Delete one on the main page, then try again.");
      S.bid = j.id; history.replaceState(null, "", `?bid=${S.bid}`); document.dispatchEvent(new CustomEvent("zeim:flow"));
    } else {
      rep = await api(`/api/edit/${S.bid}/op`, { method: "POST", json: { op, params } });
    }
    S.selEdges = []; S.selFace = null;
    await load(true);
  }, "Done. It's a step in History: tap it to change it.");
  if (ok) { setTool(null); showWarn(rep?.report?.warnings); }
}
async function histAction(fn) { await run(async () => { await fn(); await load(true); }); }
$("#cwUndo").onclick = () => S.bid && histAction(() => api(`/api/edit/${S.bid}/undo`, { method: "POST" }));
$("#cwRedo").onclick = () => S.bid && histAction(() => api(`/api/edit/${S.bid}/redo`, { method: "POST" }));

/* ---------------------------------------------------------------- History panel */
/* Every user-influenced string in History/Items goes in via textContent: templates only hold
   placeholders (<span data-tx=N>) that fill() populates after the static markup is set. */
let TX = [];
const T = v => { TX.push(String(v ?? "")); return `<span data-tx="${TX.length - 1}"></span>`; };
function fillTx(root) { root.querySelectorAll("[data-tx]").forEach(el => { el.textContent = TX[+el.dataset.tx]; el.removeAttribute("data-tx"); }); TX = []; }
const PARAM_SKIP = new Set(["sketch", "plane", "picks", "replace", "edges", "layout", "axis", "solve"]);
function paramField(k, v, i) {
  const id = `hp${i}_${k}`;
  if (typeof v === "number") return `<label class="kv" for="${id}"><span>${esc(k.replace(/_/g, " "))}</span><input id="${id}" data-k="${esc(k)}" data-t="n" type="number" step="any" inputmode="decimal" value="${v}"></label>`;
  if (typeof v === "boolean") return `<label class="kv" for="${id}"><span>${esc(k.replace(/_/g, " "))}</span><input id="${id}" data-k="${esc(k)}" data-t="b" type="checkbox" ${v ? "checked" : ""}></label>`;
  if (typeof v === "string") {
    const choices = { direction: ["up", "down", "both"], mode: ["new", "join", "cut", "intersect"], kind: ["union", "subtract", "intersect", "linear", "circular"], style: ["fillet", "chamfer"], axis: ["x", "y", "z"], side: ["min", "center", "max"], mirror: ["x", "y", "z"] }[k];
    if (choices && choices.includes(v)) return `<label class="kv" for="${id}"><span>${esc(k)}</span><select id="${id}" data-k="${esc(k)}" data-t="s">${choices.map(c => `<option ${c === v ? "selected" : ""}>${c}</option>`).join("")}</select></label>`;
    return `<div class="kv"><span>${T(k)}</span><b>${T(v)}</b></div>`;
  }
  if (Array.isArray(v) && v.length === 3 && v.every(x => typeof x === "number"))
    return `<div class="kv"><span>${esc(k)}</span><span style="display:flex;gap:3px">${v.map((x, j) => `<input data-k="${esc(k)}" data-t="v${j}" type="number" step="any" value="${x}" aria-label="${esc(k)} ${"XYZ"[j]}">`).join("")}</span></div>`;
  return "";
}
function renderHist() {
  const ol = $("#cwHist"), ops = S.scene?.ops || [], head = S.scene?.head ?? 0;
  const base = S.scene?.base, imp = base && base.type !== "cad" ? `<li class="${head < 0 ? "future" : ""}"><div class="hrow" role="button" tabindex="0" data-act="goto" data-i="0" title="Roll back to the imported file"><span class="ic">${IC.step}</span><span class="nm">Import 01 · ${T(base.type === "upload" ? (base.format || "").toUpperCase() + " file" : base.type === "build" ? "from a build" : base.type)} (kept as-is)</span></div></li>` : "";
  if (!ops.length) { ol.innerHTML = imp || `<li><div class="hrow"><span class="nm" style="color:var(--mut)">No steps yet. Your sketch and solid steps will be listed here.</span></div></li>`; fillTx(ol); return; }
  ol.innerHTML = imp + ops.map(o => {
    const open = S.openStep === o.i, future = o.i > head, p = o.params || {};
    const nm = o.name || o.label;
    let body = "";
    if (open) {
      const fields = Object.entries(p).filter(([k]) => !PARAM_SKIP.has(k)).map(([k, v]) => paramField(k, v, o.i)).join("");
      const sk = p.sketch ? `<div class="kv"><span>Profile</span><b>${(p.sketch.entities || []).length} curves${p.picks?.length ? ` · ${p.picks.length} picked region(s)` : ""}</b></div>
        <div class="kv"><span>Plane</span><b>${T(typeof p.plane === "string" ? p.plane : p.plane?.construct === "midplane" ? "midplane" : p.plane?.construct === "offset" ? "offset plane" : "face")}</b></div>` : "";
      body = `<div class="hbody">${sk}${fields || (o.editable ? "" : `<p class="help">This step can't be edited here.</p>`)}
        <div class="hbtns">${o.editable ? `<button class="primary" data-act="save" data-i="${o.i}">Update</button>` : ""}
        ${p.sketch && o.editable ? `<button data-act="sketch" data-i="${o.i}">Edit sketch</button>` : ""}
        <button data-act="goto" data-i="${o.i}" title="Show the model as it was right after this step">Roll to here</button>
        <button data-act="rename" data-i="${o.i}">Rename</button><button data-act="delete" data-i="${o.i}">Delete</button></div></div>`;
    }
    return `<li class="${open ? "open" : ""} ${future ? "future" : ""}"><div class="hrow" role="button" tabindex="0" aria-expanded="${open}" data-open="${o.i}">
      <span class="ic">${IC[OP_ICON[o.op]] || IC.step}</span><span class="nm" data-title="${o.i}">${o.i}. ${T(nm)}</span>${open ? "▾" : "›"}</div>${body}</li>`;
  }).join("") + (head < ops.length ? `<li><div class="hrow" data-act="goto" data-i="${ops.length}" role="button" tabindex="0"><span class="nm" style="color:var(--accink)">Roll forward to the end</span></div></li>` : "");
  fillTx(ol);
  ol.querySelectorAll("[data-title]").forEach(el => { el.title = (ops[+el.dataset.title - 1] || {}).label || ""; });
}
$("#cwHist").addEventListener("click", async e => {
  const o = e.target.closest("[data-open]");
  if (o && !e.target.closest(".hbody")) { const i = +o.dataset.open; S.openStep = S.openStep === i ? 0 : i; renderHist(); return; }
  const b = e.target.closest("[data-act]"); if (!b) return;
  const i = +b.dataset.i, step = S.scene.ops[i - 1] || {}, act = b.dataset.act;
  if (act === "goto") return histAction(() => api(`/api/edit/${S.bid}/goto`, { method: "POST", json: { head: i } }));
  if (act === "delete") { if (!confirm(`Delete step ${i}? Later steps are replayed without it.`)) return; S.openStep = 0; return histAction(() => api(`/api/edit/${S.bid}/step/${i}`, { method: "DELETE" })); }
  if (act === "rename") { const n = prompt("Step name (empty = automatic):", step.name || step.label); if (n === null) return; return histAction(() => api(`/api/cad/${S.bid}/step/${i}/name`, { method: "PUT", json: { name: n.slice(0, 40) } })); }
  if (act === "sketch") return startSketch(step.params.plane, step.params.sketch, i);
  if (act === "save") {
    const params = structuredClone(step.params);
    b.closest(".hbody").querySelectorAll("[data-k]").forEach(el => {
      const k = el.dataset.k, t = el.dataset.t;
      if (t === "n") params[k] = parseFloat(el.value); else if (t === "b") params[k] = el.checked; else if (t === "s") params[k] = el.value;
      else if (t[0] === "v") { params[k] = [...params[k]]; params[k][+t[1]] = parseFloat(el.value); }
    });
    return histAction(() => api(`/api/edit/${S.bid}/step/${i}`, { method: "PUT", json: { params } }));
  }
});
$("#cwHist").addEventListener("keydown", e => { if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-open],[data-act]")) { e.preventDefault(); e.target.click(); } });
$("#cwHist").addEventListener("dblclick", e => { const o = e.target.closest("[data-open]"); if (o) { S.openStep = +o.dataset.open; renderHist(); $(`.hbody [data-act=rename]`)?.click(); } });

/* ---------------------------------------------------------------- Items panel */
function renderItems() {
  const box = $("#cwItems"), bs = S.scene?.bodies || [];
  const eye = (on, lbl, attr) => `<button class="cw-eye" ${attr} aria-pressed="${on}" aria-label="${on ? "Hide" : "Show"} ${esc(lbl)}">${on ? IC.eye : IC.eyeoff}</button>`;
  const sketches = (S.scene?.ops || []).filter(o => o.params?.sketch).map(o => `<div class="cw-item"><span class="nm">Sketch of step ${o.i}<br><small>${T(typeof o.params.plane === "string" ? o.params.plane + " plane" : o.params.plane?.construct === "midplane" ? "on a midplane" : o.params.plane?.construct === "offset" ? "on an offset plane" : "on a face")} · ${(o.params.sketch.entities || []).length} curves</small></span><button class="cw-eye" data-skedit="${o.i}" aria-label="Edit the sketch of step ${o.i}">✎</button></div>`).join("");
  box.innerHTML = `<h3>Bodies</h3>${bs.length ? bs.map(b => `<div class="cw-item ${b.index === S.selBody ? "sel" : ""}" data-body="${b.index}"><span class="sw" style="background:${(S.appearance[b.index] || {}).color || PALETTE[b.index % PALETTE.length]}"></span>
      <span class="nm">${T(b.name)}<br><small>${b.size.map(fmt).join(" × ")} mm</small></span>${eye(!S.hidden.has(b.index), b.name, `data-eye="${b.index}"`)}</div>`).join("") : `<p class="help">None yet.</p>`}
    <h3>Sketches</h3>${sketches || `<p class="help">None yet.</p>`}
    <h3>Planes &amp; axes</h3>
    <div class="cw-item"><span class="nm">Grid (XY plane)</span>${eye(gridObj.visible, "grid", 'data-h="grid"')}</div>
    <div class="cw-item"><span class="nm">Axes (X red · Y green · Z blue)</span>${eye(axes.visible, "axes", 'data-h="axes"')}</div>`;
  fillTx(box);
}
$("#cwItems").addEventListener("click", e => {
  const ey = e.target.closest("[data-eye]"); if (ey) {
    const i = +ey.dataset.eye; S.hidden.has(i) ? S.hidden.delete(i) : S.hidden.add(i);
    world.children.forEach(g => g.visible = !S.hidden.has(g.userData.body));
    if (S.hidden.has(i) && (S.selBody === i || S.selEdges.some(ed => ed.body === i))) {
      S.selEdges = S.selEdges.filter(ed => ed.body !== i);
      if (S.selBody === i) { S.selBody = -1; S.selFace = null; }
      hideCtx(); msg("Selection cleared. That body is hidden — show it, then tap it again.");
      drawSelection();
      if (S.mode === "model" && S.tool && TOOL_PANELS[S.tool]) TOOL_PANELS[S.tool]();
    }
    return renderItems();
  }
  const h = e.target.closest("[data-h]"); if (h) { const o = h.dataset.h === "grid" ? gridObj : axes; o.visible = !o.visible; return renderItems(); }
  const sk = e.target.closest("[data-skedit]"); if (sk) { const st = S.scene.ops[+sk.dataset.skedit - 1]; return startSketch(st.params.plane, st.params.sketch, st.i); }
  const b = e.target.closest("[data-body]"); if (b) { S.selBody = S.selBody === +b.dataset.body ? -1 : +b.dataset.body; drawSelection(); }
});
const tabs = [["#tabHist", "#cwHist"], ["#tabItems", "#cwItems"]];
tabs.forEach(([t, p]) => $(t).onclick = () => tabs.forEach(([t2, p2]) => { $(t2).setAttribute("aria-selected", t2 === t); $(p2).hidden = t2 !== t; }));

/* ---------------------------------------------------------------- Section view + Measure */
function sectionUpdate() {
  const ax = $("#cwSecAxis").value, k = "xyz".indexOf(ax), box = new THREE.Box3().setFromObject(world);
  const lo = box.isEmpty() ? -50 : box.min.getComponent(k), hi = box.isEmpty() ? 50 : box.max.getComponent(k);
  const v = lo + (hi - lo) * (+$("#cwSecPos").value / 1000);
  const n = new THREE.Vector3(); n.setComponent(k, -1); clipPlane.set(n, v);
  $("#cwSecVal").textContent = `${ax.toUpperCase()} = ${fmt(v)} mm`;
}
function toggleSection(on = !S.section) {
  S.section = on; $("#cwSection").setAttribute("aria-pressed", on); $("#cwSectionBar").hidden = !on;
  if (on) sectionUpdate(); buildWorld(true);
  if (on) hint("Section view", "Slide to cut the model open. Cut faces are not filled (you see inside).");
}
$("#cwSection").onclick = () => toggleSection(); $("#cwSecPos").oninput = sectionUpdate; $("#cwSecAxis").onchange = sectionUpdate;
/* angle between two tapped faces: 0° = parallel facing the same way, 90° = square, 180° = facing each other */
function measAngle(n1, n2) { return Math.acos(Math.max(-1, Math.min(1, n1.dot(n2)))) * 180 / Math.PI; }
window.__measAngle = (a, b) => measAngle(new THREE.Vector3(...a).normalize(), new THREE.Vector3(...b).normalize());
function toggleMeasure(on = !S.measure) {
  S.measure = on; S.measPts = []; $("#cwMeasure").setAttribute("aria-pressed", on); drawSelection();
  if (on) { S.tool = null; renderRail(); $("#cwTool").hidden = true; hint("Measure", "Tap two points on the model, or tap an edge for its length."); } else hint(...HINTS.null);
}
$("#cwMeasure").onclick = () => toggleMeasure();
let measLabel = null;
function setMeasLabel(text, at) { measLabel = text ? { text, at } : null; }
const SNAP_PX = 10;   // measure/edge snap: a constant on-screen distance, so it scales with camera zoom (was a fixed 2 mm)
function onEdge(e, h) {   // the tap is on this edge, not just near it on a face
  if (!e) return false; if (!h) return true;
  const [ax, ay] = toScreen(e.a), [bx, by] = toScreen(e.b), [px, py] = toScreen(h.point);
  const dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L));
  if (Math.hypot(ax + dx * t - px, ay + dy * t - py) >= SNAP_PX) return false;
  // B13: an edge hidden behind the tapped surface (e.g. the far bottom edge of a box seen from above) can project right
  // under the tap; only snap when the edge is not farther from the camera than the surface that was hit.
  const q = new THREE.Line3(e.a, e.b).closestPointToPoint(h.point, true, new THREE.Vector3());
  const dq = q.distanceTo(camera.position), dh = h.point.distanceTo(camera.position);
  return dq <= dh + Math.max(0.5, 0.01 * dh);
}
function showEdgeLen(e) {   // B13: a picked edge shows its length on the model and in the polite live hint
  const t = `${fmt(e.a.distanceTo(e.b))} mm`; setMeasLabel(t, e.a.clone().add(e.b).multiplyScalar(0.5)); renderSkLabels(); return t;
}

/* ---------------------------------------------------------------- Sketch mode */
const NAMED = { XY: [[0, 0, 0], [0, 0, 1], [1, 0, 0]], XZ: [[0, 0, 0], [0, -1, 0], [1, 0, 0]], YZ: [[0, 0, 0], [1, 0, 0], [0, 1, 0]] };
function frameOf(pl) {
  let o, n, x;
  if (typeof pl === "string") [o, n, x] = NAMED[pl].map(a => new THREE.Vector3(...a));
  else { o = new THREE.Vector3(...pl.origin); n = new THREE.Vector3(...pl.normal).normalize(); x = pl.xdir ? new THREE.Vector3(...pl.xdir) : null; }
  if (!x || Math.abs(x.clone().normalize().dot(n)) > 0.99) x = Math.abs(n.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  x = x.clone().sub(n.clone().multiplyScalar(x.dot(n))).normalize();
  const y = new THREE.Vector3().crossVectors(n, x);
  const m = new THREE.Matrix4().makeBasis(x, y, n).setPosition(o);
  return { o, n, x, y, m, inv: m.clone().invert() };
}
function planeFromFace(f) {
  const n = f.normal.clone().normalize(), x = Math.abs(n.x) < 0.9 ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 1, 0);
  x.sub(n.clone().multiplyScalar(x.dot(n))).normalize();
  const r = v => v.toArray().map(c => Math.round(c * 1e5) / 1e5);
  return { origin: r(f.point), normal: r(n), xdir: r(x) };
}
let eidN = 1;
const newId = () => { const used = new Set(S.sk.entities.map(e => e.id)); while (used.has("e" + eidN)) eidN++; return "e" + eidN++; };
function startSketch(plane, sketch = null, editStep = 0) {
  hideCtx();
  S.mode = "sketch"; S.tool = null; $("#cwTool").hidden = true;
  const F = frameOf(plane);
  S.sk = { plane, F, entities: structuredClone(sketch?.entities || []), constraints: structuredClone(sketch?.constraints || []), sel: new Set(), tool: "line",
    draft: null, editStep, auto: true, showCons: true, arc: false, undo: [], dimsEdit: null };
  sketchG.matrixAutoUpdate = false; sketchG.matrix.copy(F.m);
  controls.enableRotate = false;
  viewAlong(F.n.clone(), F.y.clone());
  controls.target.copy(F.o); if (!editStep && !(S.scene?.bodies?.length)) camera.position.copy(F.o).addScaledVector(F.n, 120); viewAlong(F.n.clone(), F.y.clone());
  $("#cwMode").textContent = editStep ? `Sketch (step ${editStep})` : "Sketch"; $("#cwEmpty").hidden = true;
  helpers.visible = typeof plane === "string" && plane === "XY";
  setSkTool("line"); drawSketch();
}
function exitSketch() {
  S.mode = "model"; S.sk = null; clearGroup(sketchG); controls.enableRotate = true; helpers.visible = true;
  $("#cwMode").textContent = "Modeling"; renderRail(); hint(...HINTS.null); $("#cwLabels").innerHTML = ""; buildWorld(true);
  camera.up.set(0, 0, 1); viewAlong(new THREE.Vector3(0.9, -1.3, 1)); if (world.children.length) fit();
}
const SK_HINTS = { line: "Tap points. Tap the first point to close. Esc or double-tap ends the chain. A = arc.", rect: "Tap one corner, then the opposite corner.",
  circle: "Tap the centre, then the edge.", ellipse: "Tap the centre, then a corner.", polygon: "Tap the centre, then a corner.", spline: "Tap through-points; double-tap or Enter to finish.",
  soffset: "Tap a curve to offset.", trim: "Tap the piece to remove.", sdelete: "Tap a curve to delete it.", null: "Tap curves to select; drag points to move. Tap a dimension to type a value." };
function setSkTool(t) {
  if (t === "sdelete" && S.sk.sel.size) { pushUndo(); deleteEntities([...S.sk.sel]); return; }
  S.sk.tool = S.sk.tool === t ? null : t; S.sk.draft = null;
  const T = SKETCH_TOOLS.find(x => x.id === S.sk.tool);
  hint(T ? T.label : "Sketch", SK_HINTS[S.sk.tool] || SK_HINTS.null);
  if (S.sk.tool === "polygon") S.sk.sides = Math.max(3, Math.min(64, parseInt(prompt("Number of sides (3-64):", S.sk.sides || 6)) || 6));
  renderRail(); drawSketch();
}
const pushUndo = () => { S.sk.undo.push(JSON.stringify([S.sk.entities, S.sk.constraints])); if (S.sk.undo.length > 60) S.sk.undo.shift(); };
function skUndo() { const u = S.sk.undo.pop(); if (u) { [S.sk.entities, S.sk.constraints] = JSON.parse(u); S.sk.sel.clear(); drawSketch(); } }

/* geometry helpers (JS mirror of the server's tessellation, display only) */
function tess(e) {
  const arc = (c, r, a0, a1) => { while (a1 <= a0) a1 += 360; const n = Math.max(6, Math.round(96 * (a1 - a0) / 360)), out = []; for (let i = 0; i <= n; i++) { const t = (a0 + (a1 - a0) * i / n) * Math.PI / 180; out.push([c[0] + r * Math.cos(t), c[1] + r * Math.sin(t)]); } return out; };
  switch (e.type) {
    case "line": return [e.p0, e.p1];
    case "arc": return arc(e.c, e.r, e.a0, e.a1);
    case "circle": return arc(e.c, e.r, 0, 360);
    case "ellipse": { const o = [], ro = e.rot * Math.PI / 180; for (let i = 0; i <= 96; i++) { const t = i / 96 * 2 * Math.PI, x = e.rx * Math.cos(t), y = e.ry * Math.sin(t); o.push([e.c[0] + x * Math.cos(ro) - y * Math.sin(ro), e.c[1] + x * Math.sin(ro) + y * Math.cos(ro)]); } return o; }
    case "polygon": { const o = []; for (let i = 0; i <= e.n; i++) { const t = e.rot * Math.PI / 180 + i * 2 * Math.PI / e.n; o.push([e.c[0] + e.r * Math.cos(t), e.c[1] + e.r * Math.sin(t)]); } return o; }
    case "spline": return catmull(e.pts, e.closed);
    default: return e.closed ? [...e.pts, e.pts[0]] : e.pts;
  }
}
function catmull(pts, closed) {
  let P = closed ? [pts[pts.length - 1], ...pts, pts[0], pts[1]] : [pts[0], ...pts, pts[pts.length - 1]]; const out = [];
  for (let i = 1; i < P.length - 2; i++) { const [p0, p1, p2, p3] = [P[i - 1], P[i], P[i + 1], P[i + 2]];
    for (let s = 0; s < 12; s++) { const t = s / 12, t2 = t * t, t3 = t2 * t; out.push([0, 1].map(k => 0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2 + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3))); } }
  out.push(P[P.length - 2]); return out;
}
function keyPoints(e) {   // [ref, [x,y]]
  const id = e.id, a = d => [e.c[0] + e.r * Math.cos(d * Math.PI / 180), e.c[1] + e.r * Math.sin(d * Math.PI / 180)];
  if (e.type === "line") return [[id + ".p0", e.p0], [id + ".p1", e.p1]];
  if (e.type === "arc") return [[id + ".c", e.c], [id + ".s", a(e.a0)], [id + ".e", a(e.a1)]];
  if (e.c) return [[id + ".c", e.c]];
  return e.pts.map((p, k) => [`${id}.pts.${k}`, p]);
}
const to3 = p => new THREE.Vector3(p[0], p[1], 0).applyMatrix4(S.sk.F.m);
function scr2(p) { const [x, y] = toScreen(to3(p)); return [x, y]; }
function local(ev) {
  ray.setFromCamera(ndc(ev), camera);
  const pl = new THREE.Plane().setFromNormalAndCoplanarPoint(S.sk.F.n, S.sk.F.o), hit = new THREE.Vector3();
  if (!ray.ray.intersectPlane(pl, hit)) return null;
  const l = hit.applyMatrix4(S.sk.F.inv); return [l.x, l.y];
}
function snapPt(ev, skipId) {
  const r = renderer.domElement.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  let best = null, bd = ev.pointerType === "touch" ? 22 : 12;
  for (const e of S.sk.entities) { if (e.id === skipId) continue; for (const [ref, p] of keyPoints(e)) { const [x, y] = scr2(p); const d = Math.hypot(x - mx, y - my); if (d < bd) { bd = d; best = { ref, p: [...p] }; } } }
  if (S.sk.draft?.pts) S.sk.draft.pts.forEach((p, k) => { const [x, y] = scr2(p); const d = Math.hypot(x - mx, y - my); if (d < bd && k === 0) { bd = d; best = { ref: "draft0", p: [...p] }; } });
  if (!best) { const [x, y] = scr2([0, 0]); const d = Math.hypot(x - mx, y - my); if (d < bd) best = { ref: null, p: [0, 0], origin: true }; }   // sketch origin
  if (best) return best;
  const p = local(ev); if (!p) return null;
  const g = S.snap ? S.grid / 10 : 0;
  return { ref: null, p: g ? p.map(v => Math.round(v / g) * g) : p };
}
function hitEntity(ev) {
  const r = renderer.domElement.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  let best = null, bd = ev.pointerType === "touch" ? 20 : 10;
  for (const e of S.sk.entities) { const pts = tess(e).map(scr2);
    for (let i = 0; i < pts.length - 1; i++) { const [ax, ay] = pts[i], [bx, by] = pts[i + 1], dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((mx - ax) * dx + (my - ay) * dy) / L)), d = Math.hypot(ax + dx * t - mx, ay + dy * t - my); if (d < bd) { bd = d; best = e; } } }
  return best;
}

/* drawing */
function drawSketch() {
  clearGroup(sketchG); invalidate();
  syncSketchLocks();
  if (!S.sk) return;
  const lineMat = (sel, cons) => new THREE.LineBasicMaterial({ color: sel ? 0x29b6ff : cons ? 0x8a93a8 : 0xf2f5ff, depthTest: false, transparent: true });
  const fill = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.MeshBasicMaterial({ color: 0x2b63ff, transparent: true, opacity: 0.05, depthWrite: false, side: THREE.DoubleSide }));
  sketchG.add(fill);
  const gl = new THREE.GridHelper(S.grid * 40, 40, 0x7f8db0, 0x46516c); gl.rotation.x = Math.PI / 2; gl.material.transparent = true; gl.material.opacity = 0.35; gl.material.depthTest = false; sketchG.add(gl);
  for (const e of S.sk.entities) {
    const pts = tess(e).map(p => new THREE.Vector3(p[0], p[1], 0));
    const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat(S.sk.sel.has(e.id), e.construction)); ln.renderOrder = 5; sketchG.add(ln);
    for (const [, p] of keyPoints(e)) { const d = new THREE.Mesh(new THREE.CircleGeometry(Math.max(0.25, S.grid * 0.04), 12), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false })); d.position.set(p[0], p[1], 0); d.renderOrder = 6; sketchG.add(d); }
  }
  const dr = S.sk.draft;
  if (dr?.preview) { const ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints(dr.preview.map(p => new THREE.Vector3(p[0], p[1], 0))), new THREE.LineDashedMaterial({ color: 0x29b6ff, dashSize: 1, gapSize: 0.6, depthTest: false })); ln.computeLineDistances(); ln.renderOrder = 7; sketchG.add(ln); }
  if (S.sk.regions) for (const r of S.sk.regions) {
    const sh = new THREE.Shape(r.outer.map(p => new THREE.Vector2(p[0], p[1]))); r.holes.forEach(h => sh.holes.push(new THREE.Path(h.map(p => new THREE.Vector2(p[0], p[1])))));
    const m = new THREE.Mesh(new THREE.ShapeGeometry(sh), new THREE.MeshBasicMaterial({ color: 0x29b6ff, transparent: true, opacity: 0.25, depthTest: false, side: THREE.DoubleSide })); m.renderOrder = 3; sketchG.add(m);
  }
  renderSkLabels();
}

/* labels: dimensions (tap to type; lock = it's a constraint) and constraint badges */
let LABELS = [];
function addLabel(html, cls, anchor, attrs = {}) {
  const el = document.createElement(attrs.tag || "div"); el.className = cls; el.innerHTML = html;
  for (const [k, v] of Object.entries(attrs)) if (k !== "tag") el.setAttribute(k, v);
  $("#cwLabels").append(el); LABELS.push({ el, anchor }); return el;
}
function placeLabels() {
  for (const L of LABELS) { const [x, y, z] = toScreen(L.anchor); L.el.style.left = x + "px"; L.el.style.top = y + "px"; L.el.style.display = z > 1 ? "none" : ""; }
}
const conFor = (type, a) => S.sk.constraints.find(c => c.type === type && c.a === a);
function renderSkLabels() {
  $("#cwLabels").innerHTML = ""; LABELS = [];
  if (S.mode !== "sketch") { if (measLabel) addLabel(esc(measLabel.text), "cw-meas", measLabel.at); return; }
  const sel = [...S.sk.sel], dimEnts = S.sk.entities.filter(e => sel.includes(e.id) || S.sk.constraints.some(c => ["length", "radius"].includes(c.type) && c.a === e.id) || S.sk.entities.length <= 12);
  for (const e of dimEnts) {
    let type, v, at;
    if (e.type === "line") { type = "length"; v = Math.hypot(e.p1[0] - e.p0[0], e.p1[1] - e.p0[1]); const mx = (e.p0[0] + e.p1[0]) / 2, my = (e.p0[1] + e.p1[1]) / 2, nx = -(e.p1[1] - e.p0[1]) / (v || 1), ny = (e.p1[0] - e.p0[0]) / (v || 1), off = S.grid * 0.35; at = [mx + nx * off, my + ny * off]; }
    else if (["circle", "arc", "polygon"].includes(e.type)) { type = "radius"; v = e.r; at = [e.c[0] + e.r * 0.7, e.c[1] + e.r * 0.7]; }
    else continue;
    const c = conFor(type, e.id), pre = type === "radius" ? "R " : "";
    const el = addLabel(`${c ? IC.lock : ""}<span>${pre}${fmt(c ? c.value : v)} mm</span>`, "cw-dim" + (c ? " locked" : ""), to3(at), { tag: "button", "aria-label": `${type} of ${e.id}: ${fmt(v)} millimetres. Tap to type a value.` });
    el.onclick = ev => { ev.stopPropagation(); editDim(el, type, e.id, null, c ? c.value : v); };
  }
  if (sel.length === 2) {   // angle between two selected lines
    const [A, B] = sel.map(id => S.sk.entities.find(e => e.id === id));
    if (A?.type === "line" && B?.type === "line") {
      const u = [A.p1[0] - A.p0[0], A.p1[1] - A.p0[1]], w = [B.p1[0] - B.p0[0], B.p1[1] - B.p0[1]];
      const ang = Math.abs(Math.atan2(u[0] * w[1] - u[1] * w[0], u[0] * w[0] + u[1] * w[1]) * 180 / Math.PI);
      const c = S.sk.constraints.find(k => k.type === "angle" && k.a === A.id && k.b === B.id);
      const el = addLabel(`${c ? IC.lock : ""}<span>${fmt(c ? c.value : ang)}°</span>`, "cw-dim" + (c ? " locked" : ""), to3(B.p0), { tag: "button", "aria-label": `Angle ${fmt(ang)} degrees. Tap to type.` });
      el.onclick = ev => { ev.stopPropagation(); editDim(el, "angle", A.id, B.id, c ? c.value : ang); };
    }
  }
  if (S.sk.showCons) {
    const G = Object.fromEntries(CONS.map(([id, , g]) => [id, g])); G.vertical = "V"; G.length = null; G.radius = null; G.angle = null; G.distance = null;
    S.sk.constraints.forEach((c, k) => {
      if (!G[c.type]) return;
      const e = S.sk.entities.find(x => x.id === c.a.split(".")[0]); if (!e) return;
      const kp = c.a.includes(".") ? keyPoints(e).find(([r]) => r === c.a)?.[1] : null;
      const p = kp || (e.type === "line" ? [(e.p0[0] * 0.3 + e.p1[0] * 0.7), (e.p0[1] * 0.3 + e.p1[1] * 0.7)] : e.c || e.pts[0]);
      const el = addLabel(esc(G[c.type]), "cw-con", to3([p[0] + S.grid * 0.15, p[1] - S.grid * 0.15]), { tag: "button", title: `${c.type} — tap to remove`, "aria-label": `${c.type} constraint. Tap to remove it.` });
      el.onclick = ev => { ev.stopPropagation(); pushUndo(); S.sk.constraints.splice(k, 1); drawSketch(); };
    });
  }
}
function editDim(el, type, a, b, cur) {
  el.innerHTML = `<input type="number" step="any" inputmode="decimal" value="${fmt(cur)}" aria-label="New ${type}">`;
  const inp = el.querySelector("input"); inp.focus(); inp.select();
  const done = async ok => {
    if (!ok) return drawSketch();
    const v = parseFloat(inp.value); if (!(v > 0)) return drawSketch();
    pushUndo();
    S.sk.constraints = S.sk.constraints.filter(c => !(c.type === type && c.a === a && (c.b || null) === b));
    S.sk.constraints.push(b ? { type, a, b, value: v } : { type, a, value: v });
    await solveSketch();
  };
  inp.onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); };
  inp.onblur = () => done(true);
}
async function solveSketch() {
  if (!S.sk.constraints.length) return drawSketch();
  try {
    const r = await api("/api/cad/sketch/solve", { method: "POST", json: { sketch: { entities: S.sk.entities, constraints: S.sk.constraints } } });
    S.sk.entities = r.sketch.entities;
    status(r.ok ? "Solved" : "Over-constrained", r.ok ? `${r.dof_estimate} degree(s) of freedom left.` : r.message);
  } catch (e) { msg(e.message); }
  drawSketch();
}
function addConstraint(type) {
  const sel = [...S.sk.sel].map(id => S.sk.entities.find(e => e.id === id)).filter(Boolean);
  const need2 = ["parallel", "perpendicular", "equal", "tangent", "concentric", "coincident"].includes(type);
  if (!sel.length || (need2 && sel.length !== 2)) return status("Constraints", need2 ? "Select exactly two curves first." : "Select curves first.");
  pushUndo();
  if (type === "horizontal") sel.filter(e => e.type === "line").forEach(e => S.sk.constraints.push({ type: Math.abs(e.p1[0] - e.p0[0]) >= Math.abs(e.p1[1] - e.p0[1]) ? "horizontal" : "vertical", a: e.id }));
  else if (type === "lock") sel.forEach(e => keyPoints(e).forEach(([ref]) => S.sk.constraints.push({ type: "lock", a: ref })));
  else if (type === "coincident") {
    let best = null; for (const [ra, pa] of keyPoints(sel[0])) for (const [rb, pb] of keyPoints(sel[1])) { const d = Math.hypot(pa[0] - pb[0], pa[1] - pb[1]); if (!best || d < best[0]) best = [d, ra, rb]; }
    S.sk.constraints.push({ type, a: best[1], b: best[2] });
  } else S.sk.constraints.push({ type, a: sel[0].id, b: sel[1].id });
  solveSketch();
}
function deleteEntities(ids) {
  const set = new Set(ids);
  S.sk.entities = S.sk.entities.filter(e => !set.has(e.id));
  S.sk.constraints = S.sk.constraints.filter(c => !set.has(c.a.split(".")[0]) && !set.has((c.b || "").split(".")[0]));
  S.sk.sel.clear(); drawSketch();
}
function autoCons(e, startRef, endRef) {
  if (!S.sk.auto) return;
  if (e.type === "line") {
    const dx = e.p1[0] - e.p0[0], dy = e.p1[1] - e.p0[1], a = Math.abs(Math.atan2(dy, dx) * 180 / Math.PI);
    if (a < 3 || a > 177) { e.p1[1] = e.p0[1]; S.sk.constraints.push({ type: "horizontal", a: e.id }); }
    else if (Math.abs(a - 90) < 3) { e.p1[0] = e.p0[0]; S.sk.constraints.push({ type: "vertical", a: e.id }); }
  }
  const first = e.type === "line" ? ".p0" : ".s", last = e.type === "line" ? ".p1" : ".e";
  if (startRef && startRef !== "draft0") S.sk.constraints.push({ type: "coincident", a: e.id + first, b: startRef });
  if (endRef && endRef !== "draft0") S.sk.constraints.push({ type: "coincident", a: e.id + last, b: endRef });
}
function arc3(a, b, m) {   // circle through start a, end b, passing m
  const ax = a[0], ay = a[1], bx = b[0], by = b[1], cx = m[0], cy = m[1], d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  if (Math.abs(d) < 1e-9) return null;
  const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
  const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
  const r = Math.hypot(ax - ux, ay - uy), ang = p => Math.atan2(p[1] - uy, p[0] - ux) * 180 / Math.PI;
  let a0 = ang(a), a1 = ang(b), am = ang(m); const norm = v => ((v - a0) % 360 + 360) % 360;
  let swapped = false;
  if (norm(am) > norm(a1)) { [a0, a1] = [a1, a0]; swapped = true; }   // go the way that passes m (counter-clockwise a0 -> a1)
  return { c: [ux, uy], r, a0, a1, swapped };
}

/* sketch pointer input: mouse, touch and Apple Pencil (pointer events). One finger / pen draws;
   two fingers pan and zoom (rotation is off while sketching). */
let drag = null;
function skDown(ev) {
  const sk = S.sk, t = sk.tool;
  if (!t) {   // select / drag point
    const sp = snapPt(ev);
    if (sp?.ref && sp.ref !== "draft0") { drag = { ref: sp.ref, moved: false }; pushUndo(); return; }
    const e = hitEntity(ev);
    if (e) { if (!(ev.shiftKey || ev.metaKey || ev.ctrlKey) && !sk.sel.has(e.id) && sk.sel.size >= 2) sk.sel.clear(); sk.sel.has(e.id) ? sk.sel.delete(e.id) : sk.sel.add(e.id); }
    else sk.sel.clear();
    return drawSketch();
  }
  if (t === "soffset" || t === "trim" || t === "sdelete") {
    const e = hitEntity(ev); if (!e) return;
    if (t === "sdelete") { pushUndo(); return deleteEntities([e.id]); }
    const body = { sketch: { entities: sk.entities, constraints: [] }, id: e.id };
    if (t === "soffset") { const d = parseFloat(prompt("Offset distance in mm (negative = inward/other side):", S.grid / 2)); if (!d) return; pushUndo();
      api("/api/cad/sketch/offset", { method: "POST", json: { ...body, distance: d } }).then(r => { sk.entities.push(r.entity); drawSketch(); }).catch(er => msg(er.message)); }
    else { const at = local(ev); pushUndo();
      api("/api/cad/sketch/trim", { method: "POST", json: { ...body, at } }).then(r => { const k = sk.entities.findIndex(x => x.id === r.replace); deleteEntities([r.replace]); sk.entities.splice(k, 0, ...r.entities.map(x => ({ ...x, id: newId() }))); drawSketch(); }).catch(er => msg(er.message)); }
    return;
  }
  const sp = snapPt(ev); if (!sp) return;
  const p = sp.p, dr = sk.draft;
  if (t === "line") {
    if (!dr) { sk.draft = { pts: [p], refs: [sp.ref], first: sp.ref, firstP: p, arcMid: null }; return; }
    const prev = dr.pts[dr.pts.length - 1], prevRef = dr.lastRef || dr.refs[0];
    const closing = sp.ref === "draft0";
    if (sk.arc && !dr.arcEnd) { dr.arcEnd = { p, ref: closing ? null : sp.ref, closing }; hint("Arc", "Now tap a point the arc passes through."); return; }
    pushUndo();
    let e;
    if (sk.arc && dr.arcEnd) {
      const A = arc3(prev, dr.arcEnd.p, p); if (!A) return;
      e = { id: newId(), type: "arc", c: A.c, r: A.r, a0: A.a0, a1: A.a1 };
      sk.entities.push(e);
      const sRef = A.swapped ? (dr.arcEnd.closing ? dr.firstRef : dr.arcEnd.ref) : prevRef, eRef = A.swapped ? prevRef : (dr.arcEnd.closing ? dr.firstRef : dr.arcEnd.ref);
      autoCons(e, sRef, eRef);
      const endP = dr.arcEnd.p, wasClosing = dr.arcEnd.closing; dr.arcEnd = null;
      dr.lastRef = e.id + (A.swapped ? ".s" : ".e");
      if (!dr.firstRef) dr.firstRef = e.id + (A.swapped ? ".e" : ".s");
      dr.pts.push(endP);
      if (wasClosing) { sk.draft = null; status("Closed", "Shape closed. Finish the sketch to extrude it."); }
      return drawSketch();
    }
    e = { id: newId(), type: "line", p0: [...prev], p1: closing ? [...dr.firstP] : [...p] };
    sk.entities.push(e);
    autoCons(e, prevRef, closing ? dr.firstRef : sp.ref);
    if (!dr.firstRef) dr.firstRef = e.id + ".p0";
    dr.lastRef = e.id + ".p1"; dr.pts.push(e.p1);
    if (closing) { sk.draft = null; status("Closed", "Shape closed. Finish the sketch (Enter) to extrude it."); }
    return drawSketch();
  }
  if (t === "spline") { if (!dr) sk.draft = { pts: [p] }; else dr.pts.push(p); return drawSketch(); }
  if (!dr) { sk.draft = { pts: [p], ref: sp.ref }; return; }
  pushUndo();
  const a = dr.pts[0];
  if (t === "rect") {
    const center = ev.altKey || sk.rectCenter;
    const [x0, y0, x1, y1] = center ? [2 * a[0] - p[0], 2 * a[1] - p[1], p[0], p[1]] : [a[0], a[1], p[0], p[1]];
    if (Math.abs(x1 - x0) < 1e-6 || Math.abs(y1 - y0) < 1e-6) return;
    const P4 = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], ids = P4.map(() => newId());
    P4.forEach((q, k) => sk.entities.push({ id: ids[k], type: "line", p0: [...q], p1: [...P4[(k + 1) % 4]] }));
    ids.forEach((id, k) => { sk.constraints.push({ type: "coincident", a: id + ".p1", b: ids[(k + 1) % 4] + ".p0" }); if (sk.auto) sk.constraints.push({ type: k % 2 ? "vertical" : "horizontal", a: id }); });
  } else if (t === "circle") { const r = Math.hypot(p[0] - a[0], p[1] - a[1]); if (r < 1e-6) return; sk.entities.push({ id: newId(), type: "circle", c: a, r }); }
  else if (t === "ellipse") { const rx = Math.abs(p[0] - a[0]), ry = Math.abs(p[1] - a[1]); if (rx < 1e-6 || ry < 1e-6) return; sk.entities.push({ id: newId(), type: "ellipse", c: a, rx, ry, rot: 0 }); }
  else if (t === "polygon") { const r = Math.hypot(p[0] - a[0], p[1] - a[1]); if (r < 1e-6) return; sk.entities.push({ id: newId(), type: "polygon", c: a, r, n: sk.sides || 6, rot: Math.atan2(p[1] - a[1], p[0] - a[0]) * 180 / Math.PI }); }
  if (dr.ref && sk.auto && ["circle", "ellipse", "polygon"].includes(t)) sk.constraints.push({ type: "coincident", a: sk.entities[sk.entities.length - 1].id + ".c", b: dr.ref });
  sk.draft = null; drawSketch();
}
function skMove(ev) {
  const sk = S.sk;
  if (drag) {
    const p = snapPt(ev, drag.ref.split(".")[0])?.p; if (!p) return;
    const [id, part, k] = drag.ref.split("."), e = sk.entities.find(x => x.id === id); drag.moved = true;
    if (part === "p0" || part === "p1" || part === "c") e[part] = p; else if (part === "pts") e.pts[+k] = p;
    else if (part === "s" || part === "e") { const a = Math.atan2(p[1] - e.c[1], p[0] - e.c[0]) * 180 / Math.PI; e[part === "s" ? "a0" : "a1"] = a; }
    return drawSketch();
  }
  const dr = sk.draft; if (!dr) return;
  const sp = snapPt(ev); if (!sp) return; const p = sp.p, a = dr.pts[0], t = sk.tool;
  if (t === "line") { const prev = dr.pts[dr.pts.length - 1]; if (sk.arc && dr.arcEnd) { const A = arc3(prev, dr.arcEnd.p, p); dr.preview = A ? tess({ type: "arc", ...A }) : [prev, dr.arcEnd.p]; } else dr.preview = [prev, p]; }
  else if (t === "spline") dr.preview = dr.pts.length > 1 ? catmull([...dr.pts, p], false) : [a, p];
  else if (t === "rect") { const c = ev.altKey || sk.rectCenter; const [x0, y0] = c ? [2 * a[0] - p[0], 2 * a[1] - p[1]] : a; dr.preview = [[x0, y0], [p[0], y0], p, [x0, p[1]], [x0, y0]]; }
  else if (t === "circle") dr.preview = tess({ type: "circle", c: a, r: Math.hypot(p[0] - a[0], p[1] - a[1]) });
  else if (t === "ellipse") dr.preview = tess({ type: "ellipse", c: a, rx: Math.abs(p[0] - a[0]) || 1e-3, ry: Math.abs(p[1] - a[1]) || 1e-3, rot: 0 });
  else if (t === "polygon") dr.preview = tess({ type: "polygon", c: a, r: Math.hypot(p[0] - a[0], p[1] - a[1]), n: sk.sides || 6, rot: Math.atan2(p[1] - a[1], p[0] - a[0]) * 180 / Math.PI });
  drawSketch();
}
function endChain() {
  const sk = S.sk; if (!sk?.draft) return false;
  if (sk.tool === "spline" && sk.draft.pts.length >= 2) {
    pushUndo(); const pts = sk.draft.pts, closed = pts.length > 2 && Math.hypot(pts[0][0] - pts[pts.length - 1][0], pts[0][1] - pts[pts.length - 1][1]) < S.grid / 5;
    sk.entities.push({ id: newId(), type: "spline", pts: closed ? pts.slice(0, -1) : pts, closed });
  }
  sk.draft = null; drawSketch(); return true;
}
async function finishSketch() {
  const sk = S.sk;
  endChain();
  if (!sk.entities.length) return exitSketch();
  const sketch = { entities: sk.entities, constraints: sk.constraints };
  if (sk.editStep) {
    const st = S.scene.ops[sk.editStep - 1], i = sk.editStep;
    const { picks, ...rest } = st.params;   // picked regions may not exist any more
    exitSketch();
    return histAction(() => api(`/api/edit/${S.bid}/step/${i}`, { method: "PUT", json: { params: { ...rest, sketch } } }));
  }
  S.pending = { plane: sk.plane, sketch, F: sk.F };
  exitSketch();
  setTool("extrude");
}

/* ---------------------------------------------------------------- Extrude / Revolve from the pending sketch */
async function drawPending() {
  clearGroup(sketchG); invalidate();
  const pd = S.pending; if (!pd) return;
  sketchG.matrixAutoUpdate = false; sketchG.matrix.copy(pd.F.m);
  try {
    const r = await api("/api/cad/sketch/regions", { method: "POST", json: { sketch: pd.sketch, picks: pd.picks?.length ? pd.picks : null } });
    pd.faces = r.faces; pd.regions = r.regions;
  } catch (e) { msg(e.message); return; }
  for (const e of pd.sketch.entities) sketchG.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(tess(e).map(p => new THREE.Vector3(p[0], p[1], 0))), new THREE.LineBasicMaterial({ color: 0xf2f5ff, depthTest: false })));
  for (const rg of pd.regions) {
    const sh = new THREE.Shape(rg.outer.map(p => new THREE.Vector2(...p))); rg.holes.forEach(h => sh.holes.push(new THREE.Path(h.map(p => new THREE.Vector2(...p)))));
    const m = new THREE.Mesh(new THREE.ShapeGeometry(sh), new THREE.MeshBasicMaterial({ color: 0x29b6ff, transparent: true, opacity: 0.35, depthTest: false, side: THREE.DoubleSide })); m.renderOrder = 3; sketchG.add(m);
  }
  if (!pd.regions.length) msg("This sketch has no closed shape. Edit it so the outline closes.");
}
function extrudePanel(kind) {
  const pd = S.pending;
  if (!pd) { panel(kind === "extrude" ? "Extrude" : "Revolve", `<p class="help">Draw a closed sketch first. ${S.selFace ? "A face is picked: the sketch goes on it." : ""}</p>`, () => setTool("sketch"), "New sketch"); return; }
  drawPending();
  const hasBody = bodyCount() > 0, modes = [["new", "New body"], ...(hasBody ? [["join", "Join"], ["cut", "Cut"], ["intersect", "Intersect"]] : [])];
  const lines = pd.sketch.entities.filter(e => e.type === "line");
  const common = `${seg("tMode", modes, "new")}<p class="help">Tap regions on the sketch to use only those (none picked = all closed shapes; a shape inside another is a hole).</p>
    <p class="help" id="tPicks">${pd.picks?.length ? pd.picks.length + " region(s) picked." : "All regions."}</p>`;
  const go = (op, extra) => addOp(op, { sketch: pd.sketch, plane: pd.plane, picks: pd.picks || [], mode: segVal("tMode"), ...extra }).then(() => { if (S.tool === null) { S.pending = null; clearGroup(sketchG); } if (hasBody) modePop(); });
  if (kind === "extrude")
    panel("Extrude", `<div class="f"><label for="tDist">Distance (mm)</label>${num("tDist", 10)}</div>${seg("tDir", [["up", "Up"], ["down", "Down"], ["both", "Both (symmetric)"]], "up")}
      <div class="f"><label for="tTaper">Taper angle°</label>${num("tTaper", 0)}</div>${common}`,
      () => go("sketch_extrude", { distance: val("tDist"), direction: segVal("tDir"), taper: val("tTaper") }));
  else
    panel("Revolve", `<div class="f"><label for="tAxis">Axis</label><select id="tAxis"><option value="y">Sketch vertical axis (through origin)</option><option value="x">Sketch horizontal axis (through origin)</option>
      ${lines.map(l => `<option value="${l.id}">Line ${esc(l.id)}</option>`).join("")}</select></div><div class="f"><label for="tAng">Angle°</label>${num("tAng", 360)}</div>${common}`,
      () => { const a = $("#tAxis").value, L = lines.find(l => l.id === a);
        const axis = a === "y" ? { p: [0, 0], d: [0, 1] } : a === "x" ? { p: [0, 0], d: [1, 0] } : { p: L.p0, d: [L.p1[0] - L.p0[0], L.p1[1] - L.p0[1]] };
        go("revolve", { axis, angle: val("tAng") }); });
}
/* Right after an extrude/revolve onto existing bodies: a big, obvious "what should this do?" pop-up.
   Changing it re-runs the step with the new mode (history edit), so a wrong default costs one tap. */
function modePop() {
  const ops = S.scene?.ops || [], last = ops[ops.length - 1]; if (!last || !last.params?.sketch) return;
  document.getElementById("cwModePop")?.remove();
  const box = document.createElement("div"); box.id = "cwModePop"; box.className = "cw-modepop"; box.setAttribute("role", "dialog"); box.setAttribute("aria-label", "Combine the new shape");
  const lab = document.createElement("span"); lab.textContent = "New shape:"; box.append(lab);
  for (const [m, t] of [["join", "Union"], ["cut", "Subtract"], ["new", "New body"], ["intersect", "Intersect"]]) {
    const b = document.createElement("button"); b.textContent = t; b.dataset.mode = m; b.setAttribute("aria-pressed", String(last.params.mode === m));
    b.onclick = () => { box.remove(); if (last.params.mode !== m) histAction(() => api(`/api/edit/${S.bid}/step/${last.i}`, { method: "PUT", json: { params: { ...last.params, mode: m } } })); };
    box.append(b);
  }
  const x = document.createElement("button"); x.innerHTML = '<svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg>'; x.setAttribute("aria-label", "Keep as is"); x.onclick = () => box.remove(); box.append(x);
  stage.append(box); setTimeout(() => box.remove(), 12000);
}
function pickRegion(ev) {
  const pd = S.pending; if (!pd?.faces) return false;
  ray.setFromCamera(ndc(ev), camera);
  const pl = new THREE.Plane().setFromNormalAndCoplanarPoint(pd.F.n, pd.F.o), hit = new THREE.Vector3();
  if (!ray.ray.intersectPlane(pl, hit)) return false;
  const l = hit.applyMatrix4(pd.F.inv), q = [l.x, l.y];
  const inside = (poly, p) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if ((yi > p[1]) !== (yj > p[1]) && p[0] < (xj - xi) * (p[1] - yi) / (yj - yi) + xi) c = !c; } return c; };
  const f = pd.faces.filter(f => inside(f.outer, q)).sort((a, b) => a.area - b.area)[0]; if (!f) return false;
  pd.picks = pd.picks || [];
  const k = pd.picks.findIndex(p => inside(f.outer, p) && pd.faces.filter(g => inside(g.outer, p)).sort((a, b) => a.area - b.area)[0] === f);
  if (k >= 0) pd.picks.splice(k, 1); else pd.picks.push(f.inside);
  const el = $("#tPicks"); if (el) el.textContent = pd.picks.length ? pd.picks.length + " region(s) picked." : "All regions.";
  drawPending(); return true;
}

/* ---------------------------------------------------------------- sculpt strokes (capture phase: before the orbit controls) */
let stroke = null; const pointers = new Set();
const ring = new THREE.Mesh(new THREE.RingGeometry(0.92, 1, 48), new THREE.MeshBasicMaterial({ color: 0xffb26b, depthTest: false, side: THREE.DoubleSide, transparent: true, opacity: 0.9 }));
ring.visible = false; scene.add(ring);
function previewDab(c, n, k) {   // Live Sculpt: approximate feedback for every brush; server result replaces it on release
  const B = S.brush, r = B.radius, brush = B.brush;
  const dir = brush === "carve" ? -1 : 1;
  for (const g of world.children) {
    const geo = g.children[0].geometry, pos = geo.attributes.position, a = pos.array;
    // Flatten uses a plane through the first dab (stored on stroke); fall back to camera-facing
    const planeN = (brush === "flatten" && stroke?.flatN) ? stroke.flatN : n;
    const planeC = (brush === "flatten" && stroke?.flatC) ? stroke.flatC : c;
    const facing = n || stroke?.n;
    if (facing && !geo.attributes.normal) geo.computeVertexNormals();
    const na = geo.attributes.normal?.array;
    for (let i = 0; i < a.length; i += 3) {
      const dx = a[i] - c.x, dy = a[i + 1] - c.y, dz = a[i + 2] - c.z, d2 = dx * dx + dy * dy + dz * dz;
      if (d2 >= r * r) continue;
      if (facing && na && na[i] * facing.x + na[i + 1] * facing.y + na[i + 2] * facing.z <= 0.2) continue;
      const fall = (1 - d2 / (r * r)) ** 2, s = B.strength;
      if (brush === "grab") {
        a[i] += k.x * fall; a[i + 1] += k.y * fall; a[i + 2] += k.z * fall;
      } else if (brush === "smooth") {
        // Pull toward the brush centre (cheap Laplacian stand-in)
        const t = fall * s * 0.35;
        a[i] += (c.x - a[i]) * t; a[i + 1] += (c.y - a[i + 1]) * t; a[i + 2] += (c.z - a[i + 2]) * t;
      } else if (brush === "pinch") {
        const t = fall * s * 0.25;
        a[i] += (c.x - a[i]) * t; a[i + 1] += (c.y - a[i + 1]) * t; a[i + 2] += (c.z - a[i + 2]) * t;
      } else if (brush === "flatten" && planeN) {
        const px = a[i] - planeC.x, py = a[i + 1] - planeC.y, pz = a[i + 2] - planeC.z;
        const d = px * planeN.x + py * planeN.y + pz * planeN.z;
        const t = fall * s * 0.4;
        a[i] -= planeN.x * d * t; a[i + 1] -= planeN.y * d * t; a[i + 2] -= planeN.z * d * t;
      } else if (n) {
        const w = fall * s * 0.15 * r * dir;
        a[i] += n.x * w; a[i + 1] += n.y * w; a[i + 2] += n.z * w;
      }
    }
    pos.needsUpdate = true; geo.computeVertexNormals();
  }
}
stage.addEventListener("pointerdown", ev => {
  pointers.add(ev.pointerId);
  if (S.tool !== "sculpt" || S.mode !== "model") return;
  if (pointers.size > 1) { if (stroke) { stroke = null; load(true); } controls.enabled = true; return; }   // two fingers: orbit
  if (ev.button > 0) return;
  const h = pickBody(ev); if (!h) return;                                                                // off the model: orbit
  controls.enabled = false; ev.stopPropagation();
  stroke = { pts: [h.point.clone()], n: h.normal.clone(), start: h.point.clone(), plane: new THREE.Plane().setFromNormalAndCoplanarPoint(camera.getWorldDirection(new THREE.Vector3()), h.point), last: h.point.clone() };
  if (S.brush.brush === "flatten") { stroke.flatC = h.point.clone(); stroke.flatN = h.normal.clone(); }
  if (S.brush.brush !== "grab") previewDab(h.point, h.normal);
}, true);
const sculptMove = perFrame(ev => {
  if (S.tool !== "sculpt") { if (ring.visible) { ring.visible = false; invalidate(); } return; }
  invalidate();
  const h = stroke && S.brush.brush === "grab" ? null : pickBody(ev);
  if (h) { ring.visible = true; ring.position.copy(h.point); ring.scale.setScalar(S.brush.radius); ring.lookAt(h.point.clone().add(h.normal)); } else if (!stroke) ring.visible = false;
  if (!stroke) return;
  if (S.brush.brush === "grab") {
    ray.setFromCamera(ndc(ev), camera); const q = new THREE.Vector3(); if (!ray.ray.intersectPlane(stroke.plane, q)) return;
    const k = q.clone().sub(stroke.last); stroke.last = q; stroke.delta = q.clone().sub(stroke.start); previewDab(stroke.start.clone().add(stroke.delta).sub(k), null, k); return;
  }
  if (h && h.point.distanceTo(stroke.pts[stroke.pts.length - 1]) > S.brush.radius / 3 && stroke.pts.length < 400) {
    stroke.pts.push(h.point.clone()); if (S.brush.brush !== "grab") previewDab(h.point, stroke.n);
  }
});
stage.addEventListener("pointermove", sculptMove, { capture: true, passive: true });
let sculptSaving = false;
const strokeQueue = [];
function setLiveSculptStatus(text) {
  const el = document.getElementById("cwLiveSculpt");
  if (el) el.textContent = text || "";
}
async function pumpStrokes() {
  if (sculptSaving) return;
  sculptSaving = true; updateTop();
  try {
    while (strokeQueue.length) {
      const params = strokeQueue.shift();
      setLiveSculptStatus("Saving stroke…");
      try {
        await api(`/api/edit/${S.bid}/op`, { method: "POST", json: { op: "sculpt_stroke", params } });
      } catch (e) {
        strokeQueue.length = 0;
        if (!stroke) await load(true);
        msg(e.message || "The stroke did not save. The model was put back. Redo that stroke.");
        setLiveSculptStatus("Save failed — mesh restored");
        return;
      }
    }
    if (!stroke) { try { await load(true); } catch (e) { msg(e.message); } }
    setLiveSculptStatus("Live Sculpt · stroke saved");
    setTimeout(() => { if (!sculptSaving) setLiveSculptStatus("Live Sculpt · drag to shape"); }, 1200);
  } finally { sculptSaving = false; updateTop(); if (strokeQueue.length) pumpStrokes(); }
}
async function endStroke(ev) {
  sculptMove.flush();
  pointers.delete(ev.pointerId);
  if (!stroke) return;
  const st = stroke, B = S.brush; stroke = null; controls.enabled = true;
  const r = (v) => v.toArray().map(x => Math.round(x * 1e4) / 1e4);
  const params = { brush: B.brush, radius: B.radius, strength: B.strength, symmetry_x: B.sym, points: st.pts.map(r), normal: r(st.n) };
  if (B.brush === "grab") { if (!st.delta) return; params.delta = r(st.delta); params.strength = 1; }
  if (!S.bid) { msg("Make a solid first."); if (!stroke) load(true); return; }
  strokeQueue.push(params);
  pumpStrokes();
}
stage.addEventListener("pointerup", endStroke, true);
stage.addEventListener("pointercancel", endStroke, true);

/* ---------------------------------------------------------------- in-canvas context actions + push/pull handle */
let CTX = null;
function hideCtx() { if (CTX) { CTX.bar.remove(); CTX.handle?.remove(); CTX = null; } }
function placeCtx() {
  if (!CTX) return;
  const [x, y] = toScreen(CTX.at); CTX.bar.style.left = x + "px"; CTX.bar.style.top = y + "px";
  if (CTX.handle) { const [hx, hy] = toScreen(CTX.at.clone().addScaledVector(S.selFace.normal, CTX.len + (CTX.d || 0))); CTX.handle.style.left = hx + "px"; CTX.handle.style.top = hy + "px"; }
}
function showCtx(kind, at) {
  hideCtx();
  const bar = document.createElement("div"); bar.className = "cw-ctx"; bar.setAttribute("role", "toolbar"); bar.setAttribute("aria-label", kind === "face" ? "Face actions" : "Edge actions");
  if (kind === "face") bar.innerHTML = `<label class="sr-only" for="ctxD">Push or pull distance in mm</label><input id="ctxD" type="number" step="any" inputmode="decimal" value="0" title="Push/pull distance (mm): type a value or drag the arrow">
    <button class="primary" data-c="pp" title="Move this face by the distance (push/pull)">Push/Pull</button><button data-c="sk" title="Sketch on this face">Sketch</button>
    <button data-c="sh" title="Shell (hollow) the body">Shell</button><button data-c="fa" title="Round all outside edges">Fillet all</button><button data-c="sc" title="Sculpt mode">Sculpt</button><button data-c="x" aria-label="Close"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
  else bar.innerHTML = `<label class="sr-only" for="ctxD">Radius in mm</label><input id="ctxD" type="number" step="any" inputmode="decimal" value="1" title="Radius / size (mm)">
    <button class="primary" data-c="fi">Fillet</button><button data-c="ch">Chamfer</button><button data-c="ms" title="Measure this edge">Length</button><button data-c="x" aria-label="Close"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
  stage.append(bar);
  CTX = { bar, at: at.clone(), kind, len: 0, d: 0 };
  if (kind === "face") {
    const box = new THREE.Box3().setFromObject(world); CTX.len = Math.max(6, box.getSize(new THREE.Vector3()).length() * 0.12);
    const hd = document.createElement("div"); hd.className = "cw-handle"; hd.textContent = "⇕"; hd.setAttribute("role", "slider"); hd.setAttribute("aria-label", "Drag to push or pull the face"); hd.tabIndex = 0;
    stage.append(hd); CTX.handle = hd;
    hd.addEventListener("pointerdown", ev => { ev.stopPropagation(); ev.preventDefault(); hd.setPointerCapture(ev.pointerId); CTX.drag = true; controls.enabled = false; CTX.base = facePreviewStart(); });
    hd.addEventListener("pointermove", ev => {
      if (!CTX?.drag) return;
      ray.setFromCamera(ndc(ev), camera);   // closest point on the face-normal line to the pointer ray
      const p0 = CTX.at, n = S.selFace.normal, w0 = p0.clone().sub(ray.ray.origin), b = n.dot(ray.ray.direction), dd = n.dot(w0), e = ray.ray.direction.dot(w0), den = 1 - b * b;
      if (Math.abs(den) < 1e-6) return;
      let t = (b * e - dd) / den - CTX.len; const g = S.snap ? S.grid / 10 : 0; if (g) t = Math.round(t / g) * g;
      CTX.d = t; $("#ctxD").value = fmt(t); facePreview(t);
    });
    hd.addEventListener("pointerup", () => { if (!CTX?.drag) return; CTX.drag = false; controls.enabled = true; if (Math.abs(CTX.d) > 1e-6) ctxRun("pp"); });
  }
  bar.addEventListener("click", e => { const b = e.target.closest("[data-c]"); if (b) ctxRun(b.dataset.c); });
  bar.querySelector("#ctxD").addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") ctxRun(kind === "face" ? "pp" : "fi"); });
  hint(kind === "face" ? "Face" : "Edge", kind === "face" ? "Drag the arrow or type a distance to push/pull; or sketch on it." : `${showEdgeLen(S.selEdges[0])} long. Type a radius, then Fillet or Chamfer this edge (approximate).`);
}
function facePreviewStart() {   // remember positions on the picked face's plane for a live preview
  const out = [], { point, normal } = S.selFace, tol = 1e-3 * Math.max(1, new THREE.Box3().setFromObject(world).getSize(new THREE.Vector3()).length());
  for (const g of world.children) { if (g.userData.body !== S.selBody) continue; const a = g.children[0].geometry.attributes.position.array, idx = [];
    for (let i = 0; i < a.length; i += 3) if (Math.abs((a[i] - point.x) * normal.x + (a[i + 1] - point.y) * normal.y + (a[i + 2] - point.z) * normal.z) < tol) idx.push(i);
    out.push({ g, idx, orig: idx.map(i => [a[i], a[i + 1], a[i + 2]]) }); }
  return out;
}
function facePreview(t) {
  const n = S.selFace.normal;
  for (const { g, idx, orig } of CTX.base || []) { const pos = g.children[0].geometry.attributes.position; idx.forEach((i, k) => { pos.array[i] = orig[k][0] + n.x * t; pos.array[i + 1] = orig[k][1] + n.y * t; pos.array[i + 2] = orig[k][2] + n.z * t; }); pos.needsUpdate = true; g.children[0].geometry.computeVertexNormals(); }
}
async function ctxRun(c) {
  if (!CTX) return;
  const v = parseFloat($("#ctxD").value), f = S.selFace, e = S.selEdges[0];
  if (c === "x") { hideCtx(); return deselect(); }
  hideCtx();
  if (c === "pp") { if (!v) return msg("Type or drag a distance first."); return addOp("face_offset", { point: f.point.toArray(), normal: f.normal.toArray(), distance: v }); }
  if (c === "sk") return startSketch(planeFromFace(f));
  if (c === "sh") return setTool("shell");
  if (c === "fa") { S.selEdges = []; return setTool("fillet"); }
  if (c === "sc") return setTool("sculpt");
  if (c === "fi" || c === "ch") return addOp("round_edges", { style: c === "fi" ? "fillet" : "chamfer", radius: v || 1, body: e.body, edges: [[e.a.toArray(), e.b.toArray()]] });
  if (c === "ms") { S.measPts = [e.a, e.b]; status("Edge length", showEdgeLen(e)); drawSelection(); }
}

/* ---------------------------------------------------------------- Merge: drag a body on the bed, snapping to grid + other bodies' sides */
let mdrag = null;
const MSNAP = 3, MOVERLAP = 0.2;   // mm: snap distance, and how far a snapped body overlaps so Fuse joins them
function mergeSnap(b, d) {          // b = scene body, d = [dx, dy] proposed -> snapped [dx, dy] + what it snapped to
  const g = S.snap ? S.grid / 10 : 0, out = d.map(v => g ? Math.round(v / g) * g : v); let hit = null;
  for (const k of [0, 1]) {
    const lo = b.center[k] - b.size[k] / 2 + out[k], hi = b.center[k] + b.size[k] / 2 + out[k];
    let best = MSNAP + 1, fix = 0;
    for (const o of S.scene.bodies) {
      if (o.index === b.index) continue;
      const olo = o.center[k] - o.size[k] / 2, ohi = o.center[k] + o.size[k] / 2, oc = o.center[k], c = (lo + hi) / 2;
      for (const [cur, want] of [[lo, ohi - MOVERLAP], [hi, olo + MOVERLAP], [c, oc], [lo, olo], [hi, ohi]]) { const e = want - cur; if (Math.abs(e) < best) { best = Math.abs(e); fix = e; } }
    }
    if (best <= MSNAP) { out[k] += fix; hit = (hit ? hit + " + " : "") + "XY"[k]; }
  }
  return [out, hit];
}
stage.addEventListener("pointerdown", ev => {
  if (S.tool !== "merge" || S.mode !== "model" || ev.button > 0 || pointers.size > 1) return;
  const h = pickBody(ev); if (!h) return;
  const g = world.children.find(x => x.userData.body === h.body), b = S.scene?.bodies?.[h.body]; if (!g || !b) return;
  controls.enabled = false; ev.stopPropagation();
  mdrag = { g, b, plane: new THREE.Plane(new THREE.Vector3(0, 0, 1), -h.point.z), start: h.point.clone(), d: [0, 0] };
}, true);
stage.addEventListener("pointermove", ev => {
  if (!mdrag) return;
  ray.setFromCamera(ndc(ev), camera); const q = new THREE.Vector3(); if (!ray.ray.intersectPlane(mdrag.plane, q)) return;
  const [d, hit] = mergeSnap(mdrag.b, [q.x - mdrag.start.x, q.y - mdrag.start.y]);
  mdrag.d = d; mdrag.g.position.set(d[0], d[1], 0); invalidate();
  status("Move", `ΔX ${fmt(d[0])} · ΔY ${fmt(d[1])} mm${hit ? ` · snapped (${hit})` : ""}`);
}, { capture: true, passive: true });
async function endMergeDrag() {
  if (!mdrag) return;
  const { g, b, d } = mdrag; mdrag = null; controls.enabled = true;
  if (Math.hypot(d[0], d[1]) < 1e-3) { g.position.set(0, 0, 0); return; }
  const r = v => Math.round(v * 1e4) / 1e4;
  const ok = await run(async () => { await api(`/api/edit/${S.bid}/op`, { method: "POST", json: { op: "body_transform", params: { body: b.index, move: [r(d[0]), r(d[1]), 0] } } }); await load(true); });
  if (!ok) { g.position.set(0, 0, 0); invalidate(); }
  if (S.tool === "merge") setTool("merge");
}
stage.addEventListener("pointerup", endMergeDrag, true);
stage.addEventListener("pointercancel", endMergeDrag, true);
window.__mergeSnap = mergeSnap;

/* ---------------------------------------------------------------- stage pointer routing */
let downAt = null;
renderer.domElement.addEventListener("pointerdown", ev => {
  if (ev.button > 0) return;
  skMoveF.flush();
  downAt = { x: ev.clientX, y: ev.clientY, t: performance.now(), id: ev.pointerId };
  if (S.mode === "sketch" && (ev.pointerType !== "touch" || ev.isPrimary)) { renderer.domElement.setPointerCapture(ev.pointerId); skDown(ev); }
});
const skMoveF = perFrame(ev => { if (S.mode === "sketch") { skMove(ev); invalidate(); } });
renderer.domElement.addEventListener("pointermove", skMoveF, { passive: true });
renderer.domElement.addEventListener("pointerup", ev => {
  skMoveF.flush();
  if (S.mode === "sketch") { if (drag) { const moved = drag.moved; drag = null; if (moved) solveSketch(); } return; }
  if (!downAt || Math.hypot(ev.clientX - downAt.x, ev.clientY - downAt.y) > 6) return;   // it was an orbit drag
  modelTap(ev);
});
renderer.domElement.addEventListener("dblclick", () => { if (S.mode === "sketch") endChain(); });
function modelTap(ev) {
  if (S.tool === "sculpt") return;
  if (!S.tool && !S.measure) {               // direct modelling: tap an edge or a face -> floating actions
    const e = pickEdge(ev), h = pickBody(ev);
    if (onEdge(e, h)) {
      S.selEdges = [e]; S.selFace = null; S.selBody = e.body; S.measPts = []; drawSelection(); showCtx("edge", e.a.clone().add(e.b).multiplyScalar(0.5)); return;
    }
    if (h) { S.selBody = h.body; S.selFace = { point: h.point, normal: h.normal }; S.selEdges = []; setMeasLabel(null); renderSkLabels(); drawSelection(); showCtx("face", h.point); return; }
    hideCtx(); deselect(); return;
  }
  if (S.measure) {
    const e = pickEdge(ev), h = pickBody(ev);
    if (onEdge(e, h)) { S.measPts = [e.a, e.b]; S.measN = []; }
    else if (h) { if (S.measPts.length >= 2) { S.measPts = []; S.measN = []; } S.measPts.push(h.point); (S.measN ||= []).push(h.normal); }
    if (S.measPts.length === 2) { const [a, b] = S.measPts, d = a.distanceTo(b), dv = b.clone().sub(a);
      const ang = S.measN?.length === 2 ? measAngle(S.measN[0], S.measN[1]) : null;
      setMeasLabel(`${fmt(d)} mm  (ΔX ${fmt(Math.abs(dv.x))} · ΔY ${fmt(Math.abs(dv.y))} · ΔZ ${fmt(Math.abs(dv.z))})${ang === null ? "" : ` · faces ${fmt(ang)}°`}`, a.clone().add(b).multiplyScalar(0.5)); status("Measure", measLabel.text); }
    else setMeasLabel(null);
    drawSelection(); renderSkLabels(); return;
  }
  if ((S.tool === "extrude" || S.tool === "revolve") && pickRegion(ev)) return;
  if (S.tool === "fillet") { const e = pickEdge(ev); if (e) { const k = S.selEdges.findIndex(x => x.a.equals(e.a) && x.b.equals(e.b)); k >= 0 ? S.selEdges.splice(k, 1) : S.selEdges.push(e); const el = $("#tEdges"); if (el) el.firstChild.textContent = `${S.selEdges.length || "No"} edge(s) picked. `; drawSelection(); return; } }
  const h = pickBody(ev);
  if (!h) { if (!S.tool) deselect(); return; }
  if (S.selFace && !S.selFace.point.equals(h.point)) S.prevFace = S.selFace;
  S.selBody = h.body; S.selFace = { point: h.point, normal: h.normal };
  hint("Selected", `Body ${h.body + 1} and a face. Sketch (K) draws on this face; Face extrude (O) moves it in or out.`);
  drawSelection();
  if (S.tool && TOOL_PANELS[S.tool] && !["extrude", "revolve", "visualize"].includes(S.tool)) TOOL_PANELS[S.tool]();
}
function reconcileSelection() {
  if (S.mode === "sketch") return;
  if (!S.selEdges.length && !S.selFace && !(S.selBody >= 0)) return;
  const need = new Set(S.selEdges.map(e => e.body));
  if (S.selBody >= 0) need.add(S.selBody);
  const bodies = [];
  for (const g of world.children) {
    if (!need.has(g.userData.body)) continue;
    const edges = g.children[1]?.geometry?.attributes?.position?.array;
    const tris = g.children[0]?.geometry?.attributes?.position?.array;
    bodies.push({
      index: g.userData.body,
      visible: g.visible !== false,
      edges: edges ? Array.from(edges) : [],
      tris: tris ? Array.from(tris) : [],
    });
  }
  const had = S.selEdges.length || S.selFace || S.selBody >= 0;
  let edges = S.selEdges.map(e => ({ a: [e.a.x, e.a.y, e.a.z], b: [e.b.x, e.b.y, e.b.z], body: e.body }));
  if (S.section) {
    const vis = edges.filter(e => clipHalfSpace(e.a, e.b, clipPlane.distanceToPoint(new THREE.Vector3(...e.a)), clipPlane.distanceToPoint(new THREE.Vector3(...e.b))));
    if (vis.length !== edges.length) edges = vis;
  }
  let face = S.selFace ? [S.selFace.point.x, S.selFace.point.y, S.selFace.point.z] : null;
  if (S.section && face && clipPlane.distanceToPoint(S.selFace.point) < -1e-6) face = null;
  const out = reconcileGeom({ body: S.selBody, edges, face }, bodies, 0.75);
  const dropped = out.droppedEdge || out.droppedFace || out.droppedBody || edges.length !== S.selEdges.length || (S.selFace && !face);
  S.selEdges = out.edges.map(e => ({ a: new THREE.Vector3(...e.a), b: new THREE.Vector3(...e.b), body: e.body }));
  if (!out.face) S.selFace = null;
  if (out.droppedBody) { S.selBody = -1; S.selFace = null; S.selEdges = []; }
  if (had && dropped) {
    hideCtx();
    msg("Selection cleared. The shape changed — tap the model again.");
    if (S.mode === "model" && S.tool && TOOL_PANELS[S.tool]) TOOL_PANELS[S.tool]();
  }
}
function deselect() {
  hideCtx();
  S.selBody = -1; S.selFace = null; S.selEdges = []; S.measPts = []; setMeasLabel(null); renderSkLabels();
  if (S.sk) { S.sk.sel.clear(); drawSketch(); }
  drawSelection();
}
$("#cwDesel").onclick = deselect;

/* ---------------------------------------------------------------- chips, search, keyboard */
$("#cwGrid").onclick = () => { const g = [1, 5, 10, 20, 50], k = g.indexOf(S.grid); S.grid = g[(k + 1) % g.length]; makeGrid(); if (S.sk) drawSketch(); };
$("#cwSnap").onclick = () => { S.snap = !S.snap; $("#cwSnap").setAttribute("aria-pressed", S.snap); $("#cwSnap").textContent = S.snap ? "Snap on" : "Snap off"; };
$("#cwHome").onclick = fit;
$("#cwExport").onclick = () => { const m = $("#cwExportMenu"), open = m.hidden; m.hidden = !open; $("#cwExport").setAttribute("aria-expanded", open); };
document.addEventListener("click", e => { if (!e.target.closest(".cw-menu")) { $("#cwExportMenu").hidden = true; $("#cwExport").setAttribute("aria-expanded", "false"); } });
for (const id of ["#cwDlStl", "#cwDl3mf", "#cwToSlicer"]) $(id).addEventListener("click", e => { if (!S.bid) { e.preventDefault(); msg("Make a solid first: nothing to export yet."); } });
function allCommands() {
  const c = S.mode === "sketch" ? [...SKETCH_TOOLS.map(t => ({ label: t.label, key: t.key, run: () => setSkTool(t.id) })), ...CONS.map(([id, l]) => ({ label: l + " constraint", key: "", run: () => addConstraint(id) })), { label: "Finish sketch", key: "↵", run: finishSketch }]
    : MODEL_TOOLS.map(t => ({ label: t.label, key: t.key, run: () => setTool(t.id) }));
  return [...c, { label: "Section view", key: "X", run: () => toggleSection() }, { label: "Measure", key: "D", run: () => toggleMeasure() }, { label: "Deselect all", key: "Esc", run: deselect },
    { label: "Undo", key: "Ctrl+Z", run: () => $("#cwUndo").click() }, { label: "Redo", key: "Ctrl+Shift+Z", run: () => $("#cwRedo").click() }, { label: "Fit view", key: "Home", run: fit },
    ...CUBE.map(([n, d]) => ({ label: `View ${n}`, key: "", run: () => viewAlong(new THREE.Vector3(...d)) })), { label: "Download STL", key: "", run: () => S.bid && (location.href = S.scene.downloads.stl) }];
}
let searchSel = 0;
function openSearch() {
  const dlg = $("#cwSearchDlg"), inp = $("#cwSearchIn"), list = $("#cwSearchList");
  const draw = () => { const q = inp.value.toLowerCase(), cs = allCommands().filter(c => c.label.toLowerCase().includes(q)); searchSel = Math.min(searchSel, Math.max(0, cs.length - 1));
    list.innerHTML = cs.map((c, k) => `<li role="option" aria-selected="${k === searchSel}" data-k="${k}"><span>${esc(c.label)}</span><kbd>${esc(c.key)}</kbd></li>`).join(""); return cs; };
  let cs = draw(); inp.value = ""; cs = draw(); dlg.showModal(); inp.focus();
  inp.oninput = () => { searchSel = 0; cs = draw(); };
  inp.onkeydown = e => { if (e.key === "ArrowDown") { searchSel++; cs = draw(); e.preventDefault(); } if (e.key === "ArrowUp") { searchSel = Math.max(0, searchSel - 1); cs = draw(); e.preventDefault(); } if (e.key === "Enter" && cs[searchSel]) { dlg.close(); cs[searchSel].run(); } };
  list.onclick = e => { const li = e.target.closest("li"); if (li) { dlg.close(); cs[+li.dataset.k].run(); } };
}
$("#cwSearch").onclick = openSearch;
document.addEventListener("keydown", e => {
  if (e.target.matches("input,select,textarea") || $("#cwSearchDlg").open) return;
  const mod = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
  if (mod && k === "f") { e.preventDefault(); return openSearch(); }
  if (mod && k === "z") { e.preventDefault(); if (S.mode === "sketch") return skUndo(); return e.shiftKey ? $("#cwRedo").click() : $("#cwUndo").click(); }
  if (mod && k === "y") { e.preventDefault(); return $("#cwRedo").click(); }
  if (mod) return;
  if (k === "escape") { if (S.mode === "sketch") { if (!endChain()) { if (S.sk.tool) setSkTool(S.sk.tool); else deselect(); } } else if (S.tool) setTool(null); else deselect(); return; }
  if (k === "home") return fit();
  if (k === "x" && S.mode !== "sketch") return toggleSection();
  if (k === "d") return toggleMeasure();
  if (S.mode === "sketch") {
    if (k === "enter") { if (!endChain() || S.sk.tool !== "spline") finishSketch(); return; }
    if (k === "delete" || k === "backspace") { if (S.sk.sel.size) { pushUndo(); deleteEntities([...S.sk.sel]); } return; }
    if (k === "a" && S.sk.tool === "line") { S.sk.arc = !S.sk.arc; renderRail(); hint("Line/Arc", S.sk.arc ? "Arc: tap the end point, then a point on the arc." : SK_HINTS.line); return; }
    const t = SKETCH_TOOLS.find(t => t.key.toLowerCase() === k); if (t) setSkTool(t.id);
    return;
  }
  const t = MODEL_TOOLS.find(t => t.key.toLowerCase() === k); if (t) setTool(t.id);
});
$("#cwTitle").addEventListener("change", () => {
  const t = ($("#cwTitle").value || "").trim();
  if (!S.bid || !t) return;
  api(`/api/export/${encodeURIComponent(S.bid)}/name`, { method: "PUT", json: { name: t, save_title: true } })
    .then(r => { if (S.scene) S.scene.title = t; msg("Saved as " + (r.name || t) + ".", true); }, e => msg(e.message));
});

/* ---------------------------------------------------------------- open / import a user's own file or build */
function openProject(id) { S.bid = id; S.openStep = 0; S.hidden.clear(); history.replaceState(null, "", `?bid=${id}`); document.dispatchEvent(new CustomEvent("zeim:flow")); return load(); }
$("#cwOpen").onclick = () => { const m = $("#cwOpenMenu"), open = m.hidden; m.hidden = !open; $("#cwOpen").setAttribute("aria-expanded", open); };
document.addEventListener("click", e => { if (!e.target.closest(".cw-menu")) $("#cwOpenMenu").hidden = true; });
$("#cwImport").onclick = e => { e.preventDefault(); $("#cwFile").click(); };
/* File units (QA B8): what an STL/OBJ was drawn in; the server adds a "Units: in → mm" step. Remembered per browser. */
const UNITS = ["mm", "cm", "in", "m"];
try { const u = localStorage.getItem("zeim.cad.units"); if (UNITS.includes(u)) $("#cwUnits").value = u; } catch { }
$("#cwUnits").onchange = () => { try { localStorage.setItem("zeim.cad.units", $("#cwUnits").value); } catch { } };
/* The import's title (QA B12): the name the user typed for a still-empty design, otherwise "Imported model".
   Never the file's name (file names can hold a person's name) and never the open design's "My design". */
function importTitle() {
  const t = ($("#cwTitle").value || "").trim();
  return (!S.bid && t && t !== "My design" ? t : "Imported model").slice(0, 60);
}
let importCtl = null;
async function importFile(f) {
  if (f && f.size > 500 * 1024 * 1024) return msg("That file is over 500 MB. Try a smaller one, or simplify it first.");
  if (importCtl) importCtl.abort();
  const ctl = importCtl = new AbortController();
  let warn = []; $("#cwOpenMenu").hidden = true; $("#cwOpen").setAttribute("aria-expanded", false);
  busy(true, () => ctl.abort()); msg("");
  try {
    const fd = new FormData(); fd.append("file", f); fd.append("title", importTitle());
    fd.append("units", UNITS.includes($("#cwUnits").value) ? $("#cwUnits").value : "mm");
    const j = await api("/api/edit/new", { method: "POST", body: fd, signal: ctl.signal });
    if (ctl.signal.aborted || ctl !== importCtl) return;
    const id = j.id || j.project?.id; if (!id) throw new Error("Your recent builds are full. Delete one on the main page, then try again.");
    warn = j.warnings || j.project?.warnings || [];
    await openProject(id);
    if (ctl !== importCtl) return;
    msg(warn.length ? "Imported. " + warn.join(" ") : "Imported. It's Import 01 in History; edit it with any tool.", true);
  } catch (e) {
    if (e.name === "AbortError") {
      if (ctl === importCtl) msg("Cancelled. This page stopped waiting. If the file already reached the server, it can still appear in Projects.");
      return;
    }
    msg(e.message);
  } finally { if (ctl === importCtl) busy(false); }
}
$("#cwFile").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) importFile(f); };
stage.addEventListener("dragover", e => e.preventDefault());
stage.addEventListener("drop", e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) importFile(f); });
$("#cwSaveCopy").onclick = async e => {
  e.preventDefault(); if (!S.bid) return msg("Nothing to save yet.");
  await run(async () => { const fd = new FormData(); fd.append("from_build", S.bid); fd.append("title", (() => { const t = ($("#cwTitle").value || "My design").trim(), mm = t.match(/^(.*?) v(\d+)$/); return (mm ? `${mm[1]} v${+mm[2] + 1}` : `${t} v2`).slice(0, 60); })());
    const r = await api("/api/edit/new", { method: "POST", body: fd }); const id = r.id || r.project?.id; if (!id) throw new Error("Your recent builds are full.");
    await openProject(id); }, "Saved as a new version with its full History. The previous one is unchanged in your builds.");
};
$("#cwBuildsClose").onclick = () => $("#cwBuildsDlg").close();
$("#cwFromBuild").onclick = async e => {
  e.preventDefault(); $("#cwOpenMenu").hidden = true;
  try {
    const j = await api("/api/builds"), list = $("#cwBuildsList");
    list.innerHTML = (j.builds || []).map(b => `<li role="option" data-id="${esc(b.id)}" data-kind="${esc(b.kind || "")}"><span>${esc(b.title || "Untitled")}</span><small>${esc(b.kind === "edit" ? "editable" : b.mode || "")}</small></li>`).join("") || "<li>No builds yet.</li>";
    list.onclick = async ev => { const li = ev.target.closest("[data-id]"); if (!li) return; $("#cwBuildsDlg").close();
      if (li.dataset.kind === "edit") return run(() => openProject(li.dataset.id));
      await run(async () => { const fd = new FormData(); fd.append("from_build", li.dataset.id); const r = await api("/api/edit/new", { method: "POST", body: fd });
        const id = r.id || r.project?.id; if (!id) throw new Error("Your recent builds are full."); await openProject(id); }, "Opened as an editable copy (the original build is unchanged)."); };
    $("#cwBuildsDlg").showModal();
  } catch (er) { msg(er.message); }
};

/* ---------------------------------------------------------------- start */
$("#cwHints").onclick = () => { HINTS_ON = setHintsOn(LS, !HINTS_ON); applyHints(); };
$("#cwHint").onclick = () => $("#cwHint").classList.toggle("open");
renderRail(); hint(...HINTS.null); applyHints(); loop();
/* Never silently drop a project (QA B4): if it exists but can't be shown here (e.g. too detailed),
   keep it and offer Undo / the editor instead of an empty workspace. */
load().then(() => {   // S8: deep link to a tool, e.g. /static/cad.html?tool=text
  const q = new URLSearchParams(location.search).get("tool"); if (q && HINTS[q] && q !== "null") setTool(q);
}).catch(e => {
  if (S.bid && e.status && e.status !== 404 && e.status !== 403) return lockedOut(e.message);
  msg(e.message); S.bid = null; history.replaceState(null, "", location.pathname); load();
});
function lockedOut(text) {
  const box = document.createElement("div"); box.className = "cw-modepop"; box.setAttribute("role", "alert");
  const t = document.createElement("span"); t.textContent = text; box.append(t);
  const u = document.createElement("button"); u.textContent = "Undo last step";
  u.onclick = () => api(`/api/edit/${S.bid}/undo`, { method: "POST" }).then(() => location.reload(), er => msg(er.message));
  const ed = document.createElement("a"); ed.textContent = "Open in the editor"; ed.className = "btn"; ed.href = `/?edit=${encodeURIComponent(S.bid)}`;
  box.append(u, ed); stage.append(box);
}
const lessons = initLessons({ S, setTool, hint, LS, $, esc });
$("#cwDlStl").addEventListener("click", () => lessons.event("export")); $("#cwDl3mf").addEventListener("click", () => lessons.event("export")); $("#cwToSlicer").addEventListener("click", () => lessons.event("export"));
$("#cwHome").addEventListener("click", () => lessons.event("fit"));
window.__cad = { lessons, V3: THREE.Vector3, cam: camera, S, startSketch, setTool, finishSketch, addConstraint, solveSketch, viewAlong, toggleSection, openStep: i => { S.openStep = i; renderHist(); } };

/* saving: the design itself is saved on the server after every step; this keeps the open design, units and name */
{
  const units = () => { try { return localStorage.getItem("zeim.cad.units") || "mm"; } catch { return "mm"; } };
  const reg = () => {
    if (!window.zeimSave || reg.done) return; reg.done = true;
    window.zeimSave.register("cad", {
      collect: () => S.bid ? { bid: S.bid, units: units(), title: $("#cwTitle").value } : null,
      restore: st => {
        if (S.bid || !st?.bid || !/^[0-9a-f]{12}$/.test(st.bid)) return true;
        const box = document.createElement("div"); box.className = "savetoast"; box.setAttribute("role", "status");
        box.innerHTML = `<span>Reopen your last design?</span><a class="btn small primary" href="/static/cad.html?bid=${st.bid}">Reopen</a><button type="button" class="btn small ghost" aria-label="Dismiss">Not now</button>`;
        box.querySelector("button").onclick = () => box.remove(); document.body.append(box); return true;
      }
    }, ".cw-main");
    new MutationObserver(() => window.zeimSave._markDirty("cad")).observe($("#cwHist") || document.body, { childList: true, subtree: false });
  };
  reg(); if (!reg.done) addEventListener("DOMContentLoaded", reg);
}

/* E: Send to… (CAD → FDM Slicer / TorchC0) and the one-tap way back. The Studio / Slicer / TorchC0 side is static/handoff.js. */
{
  const units = () => { try { return localStorage.getItem("zeim.cad.units") || "mm"; } catch { return "mm"; } };
  const sl = $("#cwSendSlicer"), tc = $("#cwSendTorch");
  const applyKind = () => {
    let kind = "fdm"; try { kind = localStorage.getItem("zeim.printKind") === "resin" ? "resin" : "fdm"; } catch { }
    document.body.dataset.printKind = kind; sl.hidden = kind !== "fdm"; tc.hidden = kind !== "resin";
    $("#cwSendNote").textContent = kind === "resin" ? "Your printer type is Resin. Switch to FDM on the main page to use the Slicer." : "Your printer type is FDM. Switch to Resin on the main page to use TorchC0.";
  };
  applyKind();
  addEventListener("pageshow", () => { document.documentElement.classList.remove("handing"); applyKind(); });
  addEventListener("storage", e => { if (e.key === "zeim.printKind") applyKind(); });
  const mark = to => { try { localStorage.setItem("eunit", units()); sessionStorage.setItem("zeim.back", JSON.stringify({ label: "CAD", url: `/static/cad.html?bid=${S.bid}`, to, t: Date.now() })); } catch { } };
  const leave = (url, to) => {
    if (!S.bid) { msg("Make a solid first: nothing to send yet."); return; }
    document.dispatchEvent(new CustomEvent("zeim:save-now")); mark(to);
    document.documentElement.classList.add("handing"); setTimeout(() => { location.href = url; }, 120);
  };
  const close = () => { $("#cwSendToMenu").hidden = true; $("#cwSendTo").setAttribute("aria-expanded", "false"); };
  $("#cwSendTo").onclick = () => { const m = $("#cwSendToMenu"), open = m.hidden; m.hidden = !open; $("#cwSendTo").setAttribute("aria-expanded", String(open)); if (open) m.querySelector("a:not([hidden])")?.focus(); };
  $("#cwSendToMenu").addEventListener("keydown", e => { if (e.key === "Escape") { close(); $("#cwSendTo").focus(); } });
  document.addEventListener("click", e => { if (!e.target.closest("#cwSendTo, #cwSendToMenu")) close(); });
  sl.onclick = e => { e.preventDefault(); leave(`/?edit=${encodeURIComponent(S.bid || "")}#slicer`, "FDM Slicer"); };
  tc.onclick = e => { e.preventDefault(); leave(`/?resin=${encodeURIComponent(S.bid || "")}#torchc0`, "TorchC0"); };
  $("#cwSendShowcase").onclick = e => {
    e.preventDefault(); close();
    if (!S.bid) { msg("Make a solid first: nothing to send yet."); return; }
    document.dispatchEvent(new CustomEvent("zeim:save-now"));
    const title = ($("#cwTitle").value || "").trim();
    location.href = `/?publish=${encodeURIComponent(S.bid)}&title=${encodeURIComponent(title)}`;
  };
  $("#cwToSlicer").addEventListener("click", () => { if (S.bid) { document.dispatchEvent(new CustomEvent("zeim:save-now")); mark("FDM Slicer"); } });
  function cadKind() { try { return localStorage.getItem("zeim.printKind") === "resin" ? "resin" : "fdm"; } catch { return "fdm"; } }
  bindFlow(() => ({ view: "cad", tool: "", photoId: "", editId: S.bid || "", copyId: "", kind: cadKind() }), plan => {
    if (!plan || plan.stay) return;
    const id = plan.editId || plan.id || S.bid || "";
    if (plan.open === "send" && plan.target === "torchc0" && id) {
      location.href = "/?resin=" + encodeURIComponent(id) + "#torchc0";
      return;
    }
    if ((plan.open === "edit" || plan.hash && plan.hash.indexOf("slicer") === 1) && id && plan.hash) {
      location.href = "/?edit=" + encodeURIComponent(id) + plan.hash;
      return;
    }
    if (plan.url) { location.href = plan.url; return; }
    if (plan.hash) location.href = "/" + plan.hash;
  });
  const q = new URLSearchParams(location.search), from = q.get("from"), back = q.get("back");
  if (from && back && back.startsWith("/") && !back.startsWith("//")) {
    const a = document.createElement("a"); a.className = "backchip cad"; a.id = "backChip"; a.href = back;
    a.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg> Back to ${esc(from)}`;
    a.addEventListener("click", ev => {
      ev.preventDefault();
      const href = a.getAttribute("href");
      const go = () => { location.href = href; };
      if (window.zeimSave && typeof window.zeimSave.leave === "function") window.zeimSave.leave(go); else go();
    });
    document.body.append(a);
  }
}
