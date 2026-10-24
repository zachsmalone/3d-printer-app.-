/* Plate editor (Slicer tab): several objects on one bed. Click / tap to select, Shift-click to add to the selection,
   drag a selected object to move it. Every change is one server step ("plate" op), so Undo / Redo / the step list work. */
import * as THREE from "three";
import { $, $$, esc } from "/static/app.js";

const PL = { sel: new Set(), ctx: null, bed: null, drag: null, plane: null, gap: 5, rotate: true, copies: 2,
  txt: { open: false, text: "", mode: "emboss", face: "top", height: 8, depth: 1, font: "sans", rotation: 0, offset_u: 0, offset_v: 0 },
  cut: { open: false, axis: "z", offset: null, join: "none", material: "PLA", magnet_diameter: 6, magnet_thickness: 3, pin_diameter: 4, count: 2, lay_flat: false, for: null } };
const objs = () => PL.ctx?.p?.plate?.objects || [];
const groupOf = i => objs()[i]?.group;
const expand = set => { const gs = new Set([...set].map(groupOf)); return new Set(objs().filter(o => gs.has(o.group)).map(o => o.i)); };
const selList = () => [...PL.sel].sort((a, b) => a - b);
const r1 = x => Math.round(x * 10) / 10;
/* the user's selected printer (Slicer tab picker) so Auto-arrange packs for that bed; the server resolves its size */
const printerId = () => { try { return (typeof P !== "undefined" && P.pref?.printer_id) || undefined; } catch { return undefined; } };
const SNAP_MM = 1;

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
  if (act === "duplicate" || act === "separate" || act === "cut") { /* keep it simple: clear selection after the count changes */ PL.sel.clear(); }
  drawBed(pl.bed_mm);
  paint();
  const html = panelHTML();
  setTimeout(drawCutPlane, 0);       // after the panel is in the page
  return html;
}

function overflowHTML() {
  const a = PL.ctx.p.report?.action === "arrange" ? PL.ctx.p.report.arrange : null;
  if (!a || a.fits || !(a.overflow || []).length) return "";
  return `<div class="warn pover" role="alert" id="plateOverflow"><p>${a.overflow.length} object${a.overflow.length > 1 ? "s don't" : " doesn't"} fit on the ${a.bed_mm[0]} × ${a.bed_mm[1]} mm bed${a.plates > 1 ? ` (needs ${a.plates} plates)` : ""}. They're placed beside the bed. You can still edit; slicing needs them on the bed.</p>
    <button type="button" class="btn small" data-pact="split">Split onto another plate</button></div>`;
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
      <button type="button" class="picon" data-peye="${o.i}" aria-pressed="${!o.hidden}" aria-label="${o.hidden ? "Show" : "Hide"} ${esc(o.name)}" title="${o.hidden ? "Hidden, won't print. Show it" : "Hide (won't print)"}">${o.hidden ? "<svg class=i aria-hidden=true focusable=false><use href=#i-eyeoff></use></svg>" : "<svg class=i aria-hidden=true focusable=false><use href=#i-eye></use></svg>"}</button>
      <button type="button" class="picon" data-pdup="${o.i}" aria-label="Duplicate ${esc(o.name)}" title="Duplicate">⧉</button>
      <button type="button" class="picon" data-pdel="${o.i}" aria-label="Delete ${esc(o.name)}" title="Delete (Undo brings it back)" ${n < 2 ? "disabled" : ""}><svg class=i aria-hidden=true focusable=false><use href=#i-trash></use></svg></button></li>`;
  }).join("");
  const sz = box ? box.size : [0, 0, 0];
  return `<details class="tool plate" open id="plateTool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-grid></use></svg> Plate (${n} object${n > 1 ? "s" : ""}${pl.visible < n ? `, ${n - pl.visible} hidden` : ""})</summary>
    <p class="help">Click or tap an object to select it. Shift-click to select more. Drag a selected object to move it on the bed.</p>
    ${pl.all_hidden ? `<p class="warn" role="alert">Every object is hidden. Show at least one to print.</p>` : ""}
    <ul class="plist" aria-label="Objects on the plate">${list}</ul>
    <div class="tool-row" role="group" aria-label="Whole plate">
      <button type="button" class="btn small" data-pact="center">⊕ Auto-center ${s.length ? "selection" : "all"}</button>
      <button type="button" class="btn small" data-pact="arrange"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 4h16v16H4zM4 12h16M12 4v16"/></svg> Auto-arrange</button>
      <button type="button" class="btn small ghost" data-pact="selall">Select all</button>
    </div>
    <div class="tool-row parr" role="group" aria-label="Auto-arrange settings">
      <label class="inl">Spacing <input type="number" id="pGap" min="0" max="50" step="0.5" value="${PL.gap}" inputmode="decimal" aria-label="Spacing between objects in mm"> mm</label>
      <label class="inl"><input type="checkbox" id="pRot" ${PL.rotate ? "checked" : ""}> Allow 90° turns</label>
    </div>
    <div class="tool-row parr" role="group" aria-label="Add copies">
      <label class="inl">Copies <input type="number" id="pCopies" min="1" max="50" step="1" value="${PL.copies}" inputmode="numeric" aria-label="Number of copies to add"></label>
      <button type="button" class="btn small" data-pact="copies" ${s.length ? "" : "disabled"} title="${s.length ? "Add copies of the selection, then auto-arrange" : "Select an object first"}">＋ Add copies</button>
    </div>
    ${overflowHTML()}
    <p class="help" id="plateOut" role="status" aria-live="polite">${esc(PL.ctx.p.report?.action ? PL.ctx.p.report.message || "" : "")}</p>
    ${PL.ctx.p.report?.action === "text" && PL.ctx.p.report.text?.note ? `<p class="help" id="plateTextNote">${esc(PL.ctx.p.report.text.note)}</p>` : ""}
    ${PL.ctx.p.report?.action === "cut" && PL.ctx.p.report.cut ? `<p class="help simnote" id="plateCutNote"><span class="pill">Simulated</span> ${esc(PL.ctx.p.report.cut.note || "")}</p>` : ""}
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
        <button type="button" class="btn small" data-pact="${allHidden ? "show" : "hide"}">${allHidden ? "<svg class=i aria-hidden=true focusable=false><use href=#i-eye></use></svg> Show" : "<svg class=i aria-hidden=true focusable=false><use href=#i-eyeoff></use></svg> Hide"}</button>
        <button type="button" class="btn small" data-pact="lay_flat">⤓ Lay flat</button>
        <button type="button" class="btn small" data-pact="delete" ${s.length >= n ? "disabled" : ""}><svg class=i aria-hidden=true focusable=false><use href=#i-trash></use></svg> Delete</button>
      </div>
      <div class="tool-row" role="group" aria-label="Combine">
        ${grouped ? `<button type="button" class="btn small" data-pact="ungroup">Ungroup</button>` : `<button type="button" class="btn small" data-pact="group" ${s.length < 2 ? "disabled" : ""}>Group</button>`}
        <button type="button" class="btn small" data-pact="merge" ${s.length < 2 ? "disabled" : ""} title="Combine into one body">Merge</button>
        <button type="button" class="btn small" data-pact="separate" title="Split into its separate pieces">Separate</button>
      </div>
      <p class="help">Group: move together, still separate bodies. Merge: one body. Separate: split a model into its loose pieces.</p>
      ${one ? cutHTML(one) + textHTML(one) : ""}
    </div></details>`;
}

/* ---------- cut tool: one selected object, a flat plane across X / Y / Z, optional Smart Split connector ---------- */
const AX = { x: 0, y: 1, z: 2 };
const SIDE = { x: "left", y: "front", z: "bottom" };
const JOINS = [["none", "Nothing (plain flat faces)"], ["glue", "Glue (small bumps to line the pieces up)"], ["magnet", "Magnets (a pocket in each piece)"],
  ["dovetail", "Dovetail (a tab that slides in)"], ["pin", "Pins (printed pins + matching holes)"]];
function cutOffset(o) {
  const c = PL.cut, ext = o.size[AX[c.axis]];
  if (c.for !== `${o.i}:${c.axis}:${ext}` || c.offset == null) { c.offset = r1(ext / 2); c.for = `${o.i}:${c.axis}:${ext}`; }
  return Math.min(Math.max(c.offset, 0.5), r1(ext - 0.5));
}
function cutHTML(o) {
  const c = PL.cut, ext = o.size[AX[c.axis]], off = cutOffset(o), j = c.join;
  const num = (id, name, label, val, mn, mx, st) => `<div class="field"><label for="${id}">${label}</label><input id="${id}" type="number" name="${name}" value="${val}" min="${mn}" max="${mx}" step="${st}"></div>`;
  return `<details class="pcut" id="pCut" ${c.open ? "open" : ""}><summary><svg class=i aria-hidden=true focusable=false><use href=#i-scissors></use></svg> Cut this object</summary>
    <form data-plate="cut" class="pform" aria-describedby="pCutHelp">
      <fieldset class="seg-radio"><legend>Cut across</legend>
        ${["z", "x", "y"].map(a => `<label><input type="radio" name="axis" value="${a}" ${c.axis === a ? "checked" : ""}> ${a.toUpperCase()}${a === "z" ? " (flat, like slicing the top off)" : ""}</label>`).join("")}
      </fieldset>
      <div class="field"><label for="pCutAt">Where: mm from the ${SIDE[c.axis]} of the object (0.5 to ${r1(ext - 0.5)})</label>
        <div class="row"><input id="pCutAtR" type="range" min="0.5" max="${r1(ext - 0.5)}" step="0.1" value="${off}" aria-label="Cut position slider">
        <input id="pCutAt" type="number" name="offset" min="0.5" max="${r1(ext - 0.5)}" step="0.1" value="${off}" style="max-width:6em"></div></div>
      <p class="help" id="pCutPlane" aria-live="polite">The red plane on the model shows where it will cut.</p>
      <div class="field"><label for="pJoin">Join the two pieces with</label><select id="pJoin" name="join">${JOINS.map(([v, t]) => `<option value="${v}" ${j === v ? "selected" : ""}>${t}</option>`).join("")}</select></div>
      <div class="grid3t" ${j === "magnet" ? "" : "hidden"} data-cutfor="magnet">
        ${num("pMagD", "magnet_diameter", "Magnet Ø <em>mm</em>", c.magnet_diameter, 2, 30, 0.5)}${num("pMagT", "magnet_thickness", "Thickness <em>mm</em>", c.magnet_thickness, 0.5, 20, 0.5)}</div>
      <div class="grid3t" ${j === "pin" ? "" : "hidden"} data-cutfor="pin">${num("pPinD", "pin_diameter", "Pin Ø <em>mm</em>", c.pin_diameter, 1.5, 12, 0.5)}</div>
      <div class="grid3t" ${j === "magnet" || j === "pin" ? "" : "hidden"} data-cutfor="magnet pin">${num("pCount", "count", "How many", c.count, 1, j === "pin" ? 4 : 6, 1)}</div>
      <div class="field" ${j === "none" || j === "glue" ? "hidden" : ""} data-cutfor="magnet pin dovetail"><label for="pCutMat">Material (sets the starting gap)</label>
        <select id="pCutMat" name="material"><option ${c.material === "PLA" ? "selected" : ""}>PLA</option><option ${c.material === "PETG" ? "selected" : ""}>PETG</option></select></div>
      <label class="check" ${c.axis === "z" ? "hidden" : ""} data-cutfor="xy"><input type="checkbox" name="lay_flat" id="pCutLay" ${c.lay_flat ? "checked" : ""}> Lay the pieces on their cut face (flat side down)</label>
      <p class="help" id="pCutHelp">Fit is <b>Simulated</b>: connector sizes are starting values from ZEIM's split specs, not tested on your printer. Print a small test piece first. The cut is one step: Undo puts the object back.</p>
      <button class="btn small primary" id="pCutGo"><svg class=i aria-hidden=true focusable=false><use href=#i-scissors></use></svg> Cut into 2 pieces</button>
    </form></details>`;
}
/* ---------- text tool: raised or engraved words on one side of the selected object ---------- */
const FACES = [["top", "Top"], ["front", "Front"], ["back", "Back"], ["left", "Left"], ["right", "Right"], ["bottom", "Bottom (underside)"]];
const FONT_NAMES = { "sans": "Plain", "sans-bold": "Plain bold", "serif": "Classic", "serif-bold": "Classic bold", "mono": "Typewriter" };
function textHTML(o) {
  const t = PL.txt, fonts = PL.ctx.p.capabilities?.fonts || Object.keys(FONT_NAMES);
  const hMax = Math.max(1, Math.floor(Math.max(o.size[0], o.size[1], o.size[2])));
  const num = (id, name, label, val, mn, mx, st) => `<div class="field"><label for="${id}">${label}</label><input id="${id}" type="number" name="${name}" value="${val}" min="${mn}" max="${mx}" step="${st}"></div>`;
  return `<details class="pcut ptext" id="pText" ${t.open ? "open" : ""}><summary><svg class=i aria-hidden=true focusable=false><use href=#i-text></use></svg> Add text</summary>
    <form data-plate="text" class="pform" aria-describedby="pTextHelp">
      <div class="field"><label for="pTxt">Words (up to 60 letters)</label><input id="pTxt" name="text" maxlength="60" value="${esc(t.text)}" placeholder="Your name" autocomplete="off" required></div>
      <fieldset class="seg-radio"><legend>Style</legend>
        <label><input type="radio" name="mode" value="emboss" ${t.mode === "emboss" ? "checked" : ""}> Raised</label>
        <label><input type="radio" name="mode" value="deboss" ${t.mode === "deboss" ? "checked" : ""}> Engraved (cut in)</label></fieldset>
      <div class="grid2">
        <div class="field"><label for="pTxtFace">Side</label><select id="pTxtFace" name="face">${FACES.map(([v, l]) => `<option value="${v}" ${t.face === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div class="field"><label for="pTxtFont">Letters</label><select id="pTxtFont" name="font">${fonts.map(f => `<option value="${f}" ${t.font === f ? "selected" : ""}>${FONT_NAMES[f] || f}</option>`).join("")}</select></div>
      </div>
      <div class="grid3t">${num("pTxtH", "height", "Letter height <em>mm</em>", t.height, 1, hMax, 0.5)}${num("pTxtD", "depth", "Depth <em>mm</em>", t.depth, 0.2, 10, 0.1)}${num("pTxtR", "rotation", "Turn <em>°</em>", t.rotation, -360, 360, 1)}</div>
      <details><summary>Move the text on that side (mm)</summary><div class="grid2">
        ${num("pTxtU", "offset_u", "Right / left", t.offset_u, -1000, 1000, 0.5)}${num("pTxtV", "offset_v", "Up / down", t.offset_v, -1000, 1000, 0.5)}</div></details>
      <p class="help" id="pTextHelp">The text sits on the flat side of the object's box; on curved parts some letters may float or sink, and ZEIM tells you. Words are checked like any other words others can see. Undo removes it.</p>
      <button class="btn small primary" id="pTextGo"><svg class=i aria-hidden=true focusable=false><use href=#i-text></use></svg> Add text</button>
    </form></details>`;
}
function readText(f) {
  const t = PL.txt, n = k => (f[k].value === "" ? null : +f[k].value);
  t.text = f.text.value; t.mode = f.querySelector("input[name=mode]:checked")?.value || "emboss"; t.face = f.face.value; t.font = f.font.value;
  ["height", "depth", "rotation", "offset_u", "offset_v"].forEach(k => { if (n(k) != null) t[k] = n(k); });
  return t;
}

function readCut(f) {
  const c = PL.cut, n = k => (f[k] && f[k].value !== "" ? +f[k].value : null);
  c.axis = f.querySelector("input[name=axis]:checked")?.value || "z";
  c.offset = n("offset"); c.join = f.join.value; c.material = f.material.value; c.lay_flat = !!f.lay_flat?.checked;
  ["magnet_diameter", "magnet_thickness", "pin_diameter", "count"].forEach(k => { if (n(k) != null) c[k] = n(k); });
  return c;
}
function syncCut(f, changed) {
  const c = PL.cut, prevAxis = c.axis;
  if (changed?.id === "pCutAtR") f.offset.value = changed.value;
  readCut(f);
  if (c.axis !== prevAxis) {
    c.offset = null; const t = $("#plateTool"); if (t) { t.outerHTML = panelHTML(); }
    $(`#pCut input[name=axis][value=${c.axis}]`)?.focus(); return drawCutPlane();
  }
  const r = $("#pCutAtR", f); if (r && changed?.id !== "pCutAtR" && c.offset != null) r.value = c.offset;
  $$("[data-cutfor]", f).forEach(el => { const k = el.dataset.cutfor.split(" "); el.hidden = !(k.includes(c.join) || (k.includes("xy") && c.axis !== "z")); });
  drawCutPlane();
}
function clearCutPlane() { const v = PL.ctx?.viewer; if (PL.plane && v) v.scene.remove(PL.plane); PL.plane = null; $("#pCut")?.removeAttribute("data-plane"); }
function drawCutPlane() {
  clearCutPlane();
  const v = PL.ctx?.viewer, s = selList(), d = $("#pCut");
  if (!v || !d || !d.open || s.length !== 1) return;
  const o = objs()[s[0]], c = PL.cut, a = AX[c.axis], off = cutOffset(o);
  const pos = o.min[a] + off, pad = 8, [sx, sy, sz] = o.size;
  const [w, h] = c.axis === "z" ? [sx + pad, sy + pad] : c.axis === "x" ? [sz + pad, sy + pad] : [sx + pad, sz + pad];
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: 0xff5a5a, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false }));
  if (c.axis === "x") m.rotation.y = Math.PI / 2;
  if (c.axis === "y") m.rotation.x = Math.PI / 2;
  const ctr = [...o.center]; ctr[a] = pos; m.position.set(...ctr);
  m.name = "cutPlane"; m.renderOrder = 2; v.scene.add(m); PL.plane = m;
  d.dataset.plane = `${c.axis}:${r1(pos)}`;
  const t = $("#pCutPlane"); if (t) t.textContent = `The red plane shows the cut: ${c.axis.toUpperCase()} = ${r1(pos)} mm on the bed (${r1(off)} mm from the ${SIDE[c.axis]} of the object).`;
}

function selBox() {
  const os = selList().map(i => objs()[i]);
  const lo = [0, 1, 2].map(a => Math.min(...os.map(o => o.min[a]))), hi = [0, 1, 2].map(a => Math.max(...os.map(o => o.max[a])));
  return { c: lo.map((v, a) => (v + hi[a]) / 2), size: lo.map((v, a) => hi[a] - v), min: lo, max: hi };
}

/* ---------- viewer: bed outline, highlight, hidden ghosts ---------- */
function drawBed(bed) {
  const v = PL.ctx.viewer; if (!v) return;
  clearCutPlane();
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
    m.material.color.set(on ? "#0066FF" : bad ? "#e07a7a" : "#8fb0e0");
    if (m.material.emissive) m.material.emissive.set(on ? "#5a3300" : "#000000");
  });
  const live = $("#plateLive"); if (live) live.textContent = PL.sel.size ? `${PL.sel.size} selected` : "Nothing selected";
}
function rerender() { const t = $("#plateTool"); if (t) { t.outerHTML = panelHTML(); } paint(); drawCutPlane(); }

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

/* drag snapping: whole millimetres (hold Alt for free movement), and a selection that starts on the bed is
   kept inside it (it snaps to the edge instead of hanging off). */
function snapDrag(d, free) {
  if (!free) { d.x = Math.round(d.x / SNAP_MM) * SNAP_MM; d.y = Math.round(d.y / SNAP_MM) * SNAP_MM; }
  const b = PL.ctx?.p?.plate?.bed_mm, box = PL.sel.size ? selBox() : null;
  if (b && box && box.min && box.max) {
    const hx = b[0] / 2, hy = b[1] / 2;
    if (box.min[0] >= -hx && box.max[0] <= hx) d.x = Math.max(-hx - box.min[0], Math.min(hx - box.max[0], d.x));
    if (box.min[1] >= -hy && box.max[1] <= hy) d.y = Math.max(-hy - box.min[1], Math.min(hy - box.max[1], d.y));
  }
  return d;
}

/* screen → bed (z=0) in mm; camera must stay still during a drag or this point jumps under the cursor */
function bedPoint(e, v, plane) {
  const r = v.renderer.domElement.getBoundingClientRect(); if (!r.width || !r.height) return null;
  const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster(); rc.setFromCamera(ndc, v.camera);
  return rc.ray.intersectPlane(plane, new THREE.Vector3());
}
function resetDragOffsets(v) { v.group.children.forEach(m => m.position.set(0, 0, 0)); }

/* drag a selected object across the bed (plane z=0); one "transform" step on release.
   Capture-phase + stopPropagation so OrbitControls never starts the same gesture; freezeControls so
   leftover orbit damping can't move the camera (that made the object jump all over the bed). */
export function wireDrag(v) {
  const el = v.renderer.domElement, plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  el.addEventListener("pointerdown", e => {
    if (e.shiftKey || e.button !== 0 || PL.ctx?.measuring?.()) return;
    const h = hitObject(e); if (!h || h.obj == null || !PL.sel.has(h.obj)) return;
    const p0 = bedPoint(e, v, plane); if (!p0) return;
    e.preventDefault(); e.stopPropagation();
    try { el.setPointerCapture(e.pointerId); } catch { /* already captured: fine */ }
    if (v.freezeControls) v.freezeControls(); else v.controls.enabled = false;
    PL.drag = { p0: p0.clone(), d: new THREE.Vector3(), id: e.pointerId };
  }, true);
  el.addEventListener("pointermove", e => {
    if (!PL.drag || e.pointerId !== PL.drag.id) return;
    const p = bedPoint(e, v, plane); if (!p) return;
    PL.drag.d = snapDrag(p.sub(PL.drag.p0), e.altKey);
    v.group.children.forEach((m, k) => { if (PL.sel.has(m.userData.object ?? k)) m.position.set(PL.drag.d.x, PL.drag.d.y, 0); });
  });
  const end = e => {
    if (!PL.drag || (e && e.pointerId != null && e.pointerId !== PL.drag.id)) return;
    const d = PL.drag.d; PL.drag = null;
    if (v.unfreezeControls) v.unfreezeControls(); else v.controls.enabled = true;
    if (Math.hypot(d.x, d.y) > 0.5) {
      // on success load() replaces meshes at position 0; on failure (act swallows errors) snap the preview back
      Promise.resolve(plateOp("transform", { dx: d.x, dy: d.y })).then(() => {
        if (v.group.children.some(m => Math.hypot(m.position.x, m.position.y) > 0.01)) resetDragOffsets(v);
      });
    } else resetDragOffsets(v);
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
    const dup = e.target.closest("[data-pdup]");
    if (dup) { const i = +dup.dataset.pdup; return PL.ctx.doOp("plate", { action: "duplicate", sel: [i] }, "Duplicating…", $("#plateOut")); }
    const a = e.target.closest("[data-pact]"); if (!a) return;
    const act = a.dataset.pact;
    if (act === "arrange") return PL.ctx.doOp("plate", { action: "arrange", sel: [], gap: PL.gap, rotate: PL.rotate, printer_id: printerId() }, "Arranging…", $("#plateOut"));
    if (act === "copies") {
      const sel = selList(); if (!sel.length) return;
      const count = Math.max(1, Math.min(50, Math.round(PL.copies) || 1));
      return PL.ctx.doOp("plate", { action: "duplicate", sel, count }, "Adding copies…", $("#plateOut"))
        .then(() => PL.ctx.doOp("plate", { action: "arrange", sel: [], gap: PL.gap, rotate: PL.rotate, printer_id: printerId() }, "Arranging…", $("#plateOut")));
    }
    if (act === "split") return splitPlate();
    if (act === "selall") { PL.sel = new Set(objs().map(o => o.i)); return rerender(); }
    if (act === "delete") { const s2 = selList(); PL.sel.clear(); return PL.ctx.doOp("plate", { action: "delete", sel: s2 }, "Deleting…", $("#plateOut")); }
    const sel = selList();
    if (act === "merge" && sel.length) PL.sel = new Set([sel[0]]);       // the merged body takes the first object's place
    return PL.ctx.doOp("plate", { action: act, sel }, "Updating the plate…", $("#plateOut"));
  });
  root.addEventListener("toggle", e => {
    if (e.target.id === "pCut") { PL.cut.open = e.target.open; drawCutPlane(); }
    if (e.target.id === "pText") PL.txt.open = e.target.open;
  }, true);
  const onArr = e => {
    if (e.target.id === "pGap") { const v = parseFloat(e.target.value); if (Number.isFinite(v)) PL.gap = Math.max(0, Math.min(50, v)); }
    if (e.target.id === "pRot") PL.rotate = e.target.checked;
    if (e.target.id === "pCopies") { const v = parseInt(e.target.value, 10); if (Number.isFinite(v)) PL.copies = Math.max(1, Math.min(50, v)); }
  };
  root.addEventListener("input", onArr); root.addEventListener("change", onArr);
  const onCut = e => {
    const f = e.target.closest("form[data-plate=cut]"); if (f) return syncCut(f, e.target);
    const t = e.target.closest("form[data-plate=text]"); if (t) readText(t);
  };
  root.addEventListener("input", onCut); root.addEventListener("change", onCut);
  root.addEventListener("submit", e => {
    const f = e.target.closest("form[data-plate]"); if (!f) return;
    e.preventDefault(); e.stopImmediatePropagation();
    if (f.dataset.plate === "text") {
      const t = readText(f);
      if (!t.text.trim()) { $("#plateOut").textContent = "Type some words first."; return f.text.focus(); }
      const q = { text: t.text.trim(), mode: t.mode, face: t.face, font: t.font, height: t.height, depth: t.depth, rotation: t.rotation, offset_u: t.offset_u, offset_v: t.offset_v };
      return PL.ctx.doOp("plate", { action: "text", sel: selList(), ...q }, "Adding text…", $("#plateOut"));
    }
    if (f.dataset.plate === "cut") {
      const c = readCut(f), q = { axis: c.axis, offset: c.offset, join: c.join, lay_flat: c.lay_flat && c.axis !== "z" };
      if (["magnet", "pin", "dovetail"].includes(c.join)) q.material = c.material;
      if (c.join === "magnet") Object.assign(q, { magnet_diameter: c.magnet_diameter, magnet_thickness: c.magnet_thickness, count: c.count });
      if (c.join === "pin") Object.assign(q, { pin_diameter: c.pin_diameter, count: c.count });
      return PL.ctx.doOp("plate", { action: "cut", sel: selList(), ...q }, "Cutting…", $("#plateOut"));
    }
    const num = n => f[n].value === "" ? null : +f[n].value;
    const size = {}; [["sx", "x"], ["sy", "y"], ["sz", "z"]].forEach(([n, k]) => { if (num(n)) size[k] = num(n); });
    plateOp("transform", { x: num("x"), y: num("y"), rz: num("rz") || 0, scale_pct: num("scale_pct") || 100, size_mm: size });
  }, true);
}
async function splitPlate() {
  const out = $("#plateOut"), id = PL.ctx.p.id;
  if (out) out.textContent = "Moving the extra objects to a new plate…";
  try {
    const r = await fetch(`/api/edit/${id}/plate/split`, { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ gap: PL.gap, rotate: PL.rotate, printer_id: printerId() }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { if (out) out.textContent = (typeof j.detail === "string" ? j.detail : j.detail?.message) || "Couldn't split the plate."; return; }
    PL.sel.clear();
    if (PL.ctx.refresh) await PL.ctx.refresh(j.project); else await PL.ctx.doOp("plate", { action: "arrange", sel: [], gap: PL.gap, rotate: PL.rotate, printer_id: printerId() }, "Arranging…", out);
    const o2 = $("#plateOut"); if (o2) o2.textContent = j.message;
    if (j.new_project && o2) o2.insertAdjacentHTML("beforeend", ` <a href="/?edit=${encodeURIComponent(j.new_project)}#slicer">Open plate 2</a>`);
  } catch { if (out) out.textContent = "Couldn't reach the server. Try again."; }
}

export const plateState = PL;
