/* Plate editor (Slicer tab): several objects on one bed. Click / tap to select, Shift-click to add to the selection,
   drag a selected object to move it. Every change is one server step ("plate" op), so Undo / Redo / the step list work. */
import * as THREE from "three";
import { $, $$, esc } from "/static/app.js";

const PL = { sel: new Set(), ctx: null, bed: null, drag: null };
const objs = () => PL.ctx?.p?.plate?.objects || [];
const groupOf = i => objs()[i]?.group;
const expand = set => { const gs = new Set([...set].map(groupOf)); return new Set(objs().filter(o => gs.has(o.group)).map(o => o.i)); };
const selList = () => [...PL.sel].sort((a, b) => a - b);
const r1 = x => Math.round(x * 10) / 10;

export function plateOp(action, extra = {}) {
  const sel = selList();
  return PL.ctx.doOp("plate", { action, sel, ...extra }, "Updating the plate…", $("#plateOut"));
}

export function renderPlate(ctx) {
  const prevIds = PL.ctx?.p?.id;
  PL.ctx = ctx;
  const p = ctx.p, pl = p.plate;
  if (!pl) return "";
  if (prevIds !== p.id) PL.sel.clear();
  PL.sel = new Set([...PL.sel].filter(i => i < pl.objects.length));
  const act = p.report?.action;
  if (act === "duplicate" || act === "separate") { /* keep it simple: clear selection after the count changes */ PL.sel.clear(); }
  drawBed(pl.bed_mm);
  paint();
  return panelHTML();
}

function panelHTML() {
  const pl = PL.ctx.p.plate, n = pl.objects.length, s = selList(), one = s.length === 1 ? pl.objects[s[0]] : null;
  const box = s.length ? selBox() : null;
  const grouped = s.length && new Set(s.map(groupOf)).size === 1 && pl.objects.filter(o => o.group === groupOf(s[0])).length > 1;
  const allHidden = s.length && s.every(i => pl.objects[i].hidden);
  const list = pl.objects.map(o => {
    const on = PL.sel.has(o.i), w = o.warnings.length ? `<span class="${o.hidden ? "muted" : "warn"}">${o.warnings.map(esc).join(" ")}</span>` : `<span class="ok">Fits the bed</span>`;
    const grp = pl.objects.filter(x => x.group === o.group).length > 1 ? ` <span class="pill">Group ${o.group + 1}</span>` : "";
    return `<li class="pobj ${on ? "on" : ""} ${o.hidden ? "hid" : ""}">
      <button type="button" class="pselect" data-psel="${o.i}" aria-pressed="${on}"><b>${esc(o.name)}</b>${grp}<small>${o.size.map(r1).join(" × ")} mm · ${w}</small></button>
      <button type="button" class="picon" data-peye="${o.i}" aria-pressed="${!o.hidden}" aria-label="${o.hidden ? "Show" : "Hide"} ${esc(o.name)}" title="${o.hidden ? "Hidden, won't print. Show it" : "Hide (won't print)"}">${o.hidden ? "🙈" : "👁"}</button>
      <button type="button" class="picon" data-pdel="${o.i}" aria-label="Delete ${esc(o.name)}" title="Delete (Undo brings it back)" ${n < 2 ? "disabled" : ""}>🗑</button></li>`;
  }).join("");
  const sz = box ? box.size : [0, 0, 0];
  return `<details class="tool plate" open id="plateTool"><summary>🧩 Plate (${n} object${n > 1 ? "s" : ""}${pl.visible < n ? `, ${n - pl.visible} hidden` : ""})</summary>
    <p class="help">Click or tap an object to select it. Shift-click to select more. Drag a selected object to move it on the bed.</p>
    ${pl.all_hidden ? `<p class="warn" role="alert">Every object is hidden. Show at least one to print.</p>` : ""}
    <ul class="plist" aria-label="Objects on the plate">${list}</ul>
    <div class="tool-row" role="group" aria-label="Whole plate">
      <button type="button" class="btn small" data-pact="center">⊕ Auto-center ${s.length ? "selection" : "all"}</button>
      <button type="button" class="btn small" data-pact="arrange">▦ Auto-arrange</button>
      <button type="button" class="btn small ghost" data-pact="selall">Select all</button>
    </div>
    <p class="help" id="plateOut" role="status" aria-live="polite">${esc(PL.ctx.p.report?.action ? PL.ctx.p.report.message || "" : "")}</p>
    <div id="plateSel" ${s.length ? "" : "hidden"}>
      <h3 class="ptitle">${s.length === 1 ? esc(one.name) : `${s.length} selected`}</h3>
      <form data-plate="transform" class="pform">
        <div class="grid3t">
          <div class="field"><label for="pX">X <em>mm</em></label><input id="pX" type="number" step="any" name="x" value="${box ? r1(box.c[0]) : 0}"></div>
          <div class="field"><label for="pY">Y <em>mm</em></label><input id="pY" type="number" step="any" name="y" value="${box ? r1(box.c[1]) : 0}"></div>
          <div class="field"><label for="pRz">Rotate Z <em>°</em></label><input id="pRz" type="number" step="any" name="rz" value="0"></div>
          <div class="field"><label for="pPct">Size <em>%</em></label><input id="pPct" type="number" step="any" min="1" name="scale_pct" value="100"></div>
        </div>
        <details><summary>Exact size per axis (mm)</summary><div class="grid3t">
          <div class="field"><label for="pSx">Width X</label><input id="pSx" type="number" step="any" name="sx" placeholder="${r1(sz[0])}"></div>
          <div class="field"><label for="pSy">Depth Y</label><input id="pSy" type="number" step="any" name="sy" placeholder="${r1(sz[1])}"></div>
          <div class="field"><label for="pSz">Height Z</label><input id="pSz" type="number" step="any" name="sz" placeholder="${r1(sz[2])}"></div></div>
          <p class="help">Leave blank to keep that size.</p></details>
        <button class="btn small primary">Apply</button>
      </form>
      <div class="tool-row" role="group" aria-label="Selected objects">
        <button type="button" class="btn small" data-pact="duplicate">⧉ Duplicate</button>
        <button type="button" class="btn small" data-pact="${allHidden ? "show" : "hide"}">${allHidden ? "👁 Show" : "🙈 Hide"}</button>
        <button type="button" class="btn small" data-pact="lay_flat">⤓ Lay flat</button>
        <button type="button" class="btn small" data-pact="delete" ${s.length >= n ? "disabled" : ""}>🗑 Delete</button>
      </div>
      <div class="tool-row" role="group" aria-label="Combine">
        ${grouped ? `<button type="button" class="btn small" data-pact="ungroup">Ungroup</button>` : `<button type="button" class="btn small" data-pact="group" ${s.length < 2 ? "disabled" : ""}>Group</button>`}
        <button type="button" class="btn small" data-pact="merge" ${s.length < 2 ? "disabled" : ""} title="Combine into one body">Merge</button>
        <button type="button" class="btn small" data-pact="separate" title="Split into its separate pieces">Separate</button>
      </div>
      <p class="help">Group: move together, still separate bodies. Merge: one body. Separate: split a model into its loose pieces.</p>
    </div></details>`;
}

function selBox() {
  const os = selList().map(i => objs()[i]);
  const lo = [0, 1, 2].map(a => Math.min(...os.map(o => o.min[a]))), hi = [0, 1, 2].map(a => Math.max(...os.map(o => o.max[a])));
  return { c: lo.map((v, a) => (v + hi[a]) / 2), size: lo.map((v, a) => hi[a] - v) };
}

/* ---------- viewer: bed outline, highlight, hidden ghosts ---------- */
function drawBed(bed) {
  const v = PL.ctx.viewer; if (!v) return;
  if (PL.bed) v.scene.remove(PL.bed);
  const [x, y] = bed, pts = [[-x / 2, -y / 2], [x / 2, -y / 2], [x / 2, y / 2], [-x / 2, y / 2], [-x / 2, -y / 2]].map(([a, b]) => new THREE.Vector3(a, b, 0));
  PL.bed = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x7aa2ff }));
  PL.bed.name = "bedOutline"; v.scene.add(PL.bed);
}
export function paint() {
  const v = PL.ctx?.viewer; if (!v) return;
  const os = objs();
  v.group.children.forEach((m, k) => {
    const i = m.userData.object ?? k, o = os[i]; if (!o || !m.material?.color) return;
    const on = PL.sel.has(i), bad = !o.hidden && o.warnings.length;
    m.material.transparent = !!o.hidden; m.material.opacity = o.hidden ? 0.22 : 1; m.material.depthWrite = !o.hidden;
    m.material.color.set(on ? "#ffb347" : bad ? "#e07a7a" : "#8fb0e0");
    if (m.material.emissive) m.material.emissive.set(on ? "#5a3300" : "#000000");
  });
  const live = $("#plateLive"); if (live) live.textContent = PL.sel.size ? `${PL.sel.size} selected` : "Nothing selected";
}
function rerender() { const t = $("#plateTool"); if (t) { t.outerHTML = panelHTML(); } paint(); }

export function select(i, add) {
  if (i == null) { if (!add) PL.sel.clear(); }
  else {
    const g = expand(new Set([i]));
    if (add) { const has = PL.sel.has(i); g.forEach(j => has ? PL.sel.delete(j) : PL.sel.add(j)); }
    else PL.sel = g;
  }
  rerender();
}

function hitObject(e) {
  const v = PL.ctx?.viewer; if (!v || !PL.ctx.p?.plate) return undefined;
  const r = v.renderer.domElement.getBoundingClientRect(), ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster(); rc.setFromCamera(ndc, v.camera);
  const hit = rc.intersectObjects(v.group.children, false)[0];
  return { obj: hit ? (hit.object.userData.object ?? v.group.children.indexOf(hit.object)) : null, rc };
}
export function pickAt(e) { const h = hitObject(e); if (h) select(h.obj, e.shiftKey); }

/* drag a selected object across the bed (plane z=0); one "transform" step on release */
export function wireDrag(v) {
  const el = v.renderer.domElement, plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  el.addEventListener("pointerdown", e => {
    if (e.shiftKey || e.button !== 0 || PL.ctx?.measuring?.()) return;
    const h = hitObject(e); if (!h || h.obj == null || !PL.sel.has(h.obj)) return;
    const p0 = h.rc.ray.intersectPlane(plane, new THREE.Vector3()); if (!p0) return;
    PL.drag = { p0, d: new THREE.Vector3(), id: e.pointerId }; v.controls.enabled = false; el.setPointerCapture(e.pointerId);
  });
  el.addEventListener("pointermove", e => {
    if (!PL.drag) return;
    const h = hitObject(e); const p = h?.rc.ray.intersectPlane(plane, new THREE.Vector3()); if (!p) return;
    PL.drag.d = p.sub(PL.drag.p0);
    v.group.children.forEach((m, k) => { if (PL.sel.has(m.userData.object ?? k)) m.position.set(PL.drag.d.x, PL.drag.d.y, 0); });
  });
  const end = () => {
    if (!PL.drag) return; const d = PL.drag.d; PL.drag = null; v.controls.enabled = true;
    if (Math.hypot(d.x, d.y) > 0.5) plateOp("transform", { dx: d.x, dy: d.y });
    else v.group.children.forEach(m => m.position.set(0, 0, 0));
  };
  el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
}

export function wirePanel(root) {
  root.addEventListener("click", e => {
    const s = e.target.closest("[data-psel]"); if (s) return select(+s.dataset.psel, e.shiftKey || e.ctrlKey || e.metaKey);
    const eye = e.target.closest("[data-peye]");
    if (eye) { const i = +eye.dataset.peye; return PL.ctx.doOp("plate", { action: objs()[i].hidden ? "show" : "hide", sel: [i] }, "Updating the plate…", $("#plateOut")); }
    const del = e.target.closest("[data-pdel]");
    if (del) { const i = +del.dataset.pdel; PL.sel.delete(i); return PL.ctx.doOp("plate", { action: "delete", sel: [i] }, "Deleting…", $("#plateOut")); }
    const a = e.target.closest("[data-pact]"); if (!a) return;
    const act = a.dataset.pact;
    if (act === "selall") { PL.sel = new Set(objs().map(o => o.i)); return rerender(); }
    if (act === "delete") { const s2 = selList(); PL.sel.clear(); return PL.ctx.doOp("plate", { action: "delete", sel: s2 }, "Deleting…", $("#plateOut")); }
    const sel = selList();
    if (act === "merge" && sel.length) PL.sel = new Set([sel[0]]);       // the merged body takes the first object's place
    return PL.ctx.doOp("plate", { action: act, sel }, "Updating the plate…", $("#plateOut"));
  });
  root.addEventListener("submit", e => {
    const f = e.target.closest("form[data-plate]"); if (!f) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const num = n => f[n].value === "" ? null : +f[n].value;
    const size = {}; [["sx", "x"], ["sy", "y"], ["sz", "z"]].forEach(([n, k]) => { if (num(n)) size[k] = num(n); });
    plateOp("transform", { x: num("x"), y: num("y"), rz: num("rz") || 0, scale_pct: num("scale_pct") || 100, size_mm: size });
  }, true);
}
export const plateState = PL;
