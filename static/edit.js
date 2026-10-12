import * as THREE from "three";
import { Viewer } from "/static/viewer.js";
import { openSend } from "/static/send.js";
import { S, api, toast, inlineMsg, clearInline, $, $$, esc, openPrint, loadHistory, renderHistory, openFull, isExpert } from "/static/app.js";
import { photoBlock, mountPhoto } from "/static/photo.js";

const J = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const UNITS = { mm: 1, cm: 10, in: 25.4 };
const E = { p: null, unit: localStorage.eunit || "mm", tool: null, measure: false, pts: [], last: null };
let viewer = null, ghost = null, measureObjs = [];

/* ---------- helpers ---------- */
const U = () => UNITS[E.unit];
const fmt = mm => (mm / U()).toFixed(E.unit === "mm" ? 2 : 3).replace(/\.?0+$/, "");   // mm → display
const val = (root, name) => { const el = $(`[name=${name}]`, root); return el ? el.value : undefined; };
const len = (root, name) => +val(root, name) * U();                                       // display → mm
const busy = (on, text = "Working…") => { $("#editBusy").hidden = !on; $("#editBusyText").textContent = text; };
const lenInput = (name, mmVal, label, extra = "") => `<div class="field"><label>${label} <em>${E.unit}</em></label><input type="number" name="${name}" value="${fmt(mmVal)}" step="any" ${extra}></div>`;
const numInput = (name, v, label, unit = "", extra = "") => `<div class="field"><label>${label} <em>${unit}</em></label><input type="number" name="${name}" value="${v}" step="any" ${extra}></div>`;
const A = () => E.p.analysis;

function ensureViewer() {
  if (viewer) return viewer;
  try { viewer = new Viewer($("#editViewer")); } catch (e) { console.warn("WebGL unavailable", e); return null; }
  const grid = new THREE.GridHelper(300, 30, 0x3b4a6b, 0x26314a); grid.rotation.x = Math.PI / 2; grid.position.set(0, 0, -0.05);
  viewer.scene.add(grid);
  const el = viewer.renderer.domElement; let down = null;
  el.addEventListener("pointerdown", e => down = [e.clientX, e.clientY]);
  el.addEventListener("pointerup", e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 4) onPick(e); down = null; });
  return viewer;
}

/* ---------- opening / creating projects ---------- */
async function create(fd, retry) {
  busy(true, "Importing…");
  try {
    const r = await api("/api/edit/new", { method: "POST", body: fd });
    S.history = r.history; renderHistory(); loadProject(r);
    if (r.warnings?.length) toast(r.warnings[0]);
  } catch (e) {
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); S.pending = auto => { const f2 = retry(); if (auto) f2.append("auto_delete_oldest", "true"); return create(f2, retry); }; openFull(); editPick.msg("Your recent builds are full (5 of 5). Delete one in the window, then continue."); }
    else if ((e.status === 415 && /photo/i.test(e.message)) || (E.photoTry && [400, 413, 415].includes(e.status))) editPick.msg(e.message);       // photo problems stay under the photo buttons (QA-3)
    else toast(e.message, "err");
  } finally { busy(false); }
}
const PHOTO_RE = /\.(png|jpe?g|webp|bmp|gif|heic|heif)$/i;
const MODEL_RE = /\.(stl|obj|3mf)$/i;
// iOS greys out files in the picker when `accept` lists bare extensions it can't map to a type, so #editFile has NO accept list:
// the file type is checked here by its name (any MIME, including empty or application/octet-stream), and again by the server.
function modelMsg(t) { const m = $("#editModelMsg"); m.textContent = t || ""; m.hidden = !t; }
function fromFile(file) {
  modelMsg("");
  if (!file) return;
  E.photoTry = /^image\//.test(file.type) || PHOTO_RE.test(file.name || "");
  if (!E.photoTry && !MODEL_RE.test(file.name || "")) return modelMsg("That doesn't look like a 3D model. Choose an .stl, .obj or .3mf file, or start from a photo below.");
  if (E.photoTry && !file.size) return editPick.msg("We couldn't open that photo. Try a JPG or PNG.");            // same pre-checks as Studio, shown inline (QA-3)
  if (E.photoTry && file.size > 25 * 1024 * 1024) return editPick.msg("That photo is over 25 MB. Try a smaller one (JPG or PNG).");
  editPick.msg("");
  const mk = () => { const fd = new FormData(); fd.append("file", file); fd.append("units", $("#editUnits").value); fd.append("photo_mode", $("#editPhotoMode").value); fd.append("photo_ack", editPick.acked()); fd.append("beginner", !isExpert()); return fd; };
  create(mk(), mk);
}
const drop = $("#editDrop");
$("#editChooseModel").onclick = () => $("#editFile").click();
$("#editFile").onchange = e => { fromFile(e.target.files[0]); e.target.value = ""; };
drop.addEventListener("click", () => $("#editFile").click());
$("#editPhoto").innerHTML = photoBlock("e", { sample: true });
const editPick = mountPhoto("e", f => fromFile(f));
$("#eSample").onclick = async () => {
  try { const b = await (await fetch("/static/sample.png")).blob(); fromFile(new File([b], "sample.png", { type: "image/png" })); }
  catch { editPick.msg("We couldn't load the sample image. Please try again."); }
};
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => fromFile(e.dataTransfer.files[0]));
$("#editSample").onclick = async () => { const b = await (await fetch("/static/sample_model.stl")).blob(); fromFile(new File([b], "sample_vase.stl")); };
function fromBuild(id) {
  const mk = () => { const fd = new FormData(); fd.append("from_build", id); fd.append("beginner", !isExpert()); return fd; };
  create(mk(), mk);
}
$("#editFromBuildGo").onclick = () => { const v = $("#editFromBuild").value; if (v) fromBuild(v); };
$("#btnEditThis")?.addEventListener("click", () => { if (S.current) { location.hash = "edit"; fromBuild(S.current.id); } });
function fillBuildSelect() {
  $("#editFromBuild").innerHTML = S.history.length ? S.history.slice().reverse().map(b => `<option value="${b.id}">${esc(b.title)} (${b.kind === "edit" ? "edited" : b.mode})</option>`).join("") : `<option value="">No builds yet — make one in the Studio</option>`;
  $("#editFromBuildGo").disabled = !S.history.length;
}
document.addEventListener("zeim:edit-shown", async () => { try { await loadHistory(); } catch { } fillBuildSelect(); ensureViewer(); setTimeout(() => viewer?.resize(), 50); });
document.addEventListener("zeim:open-edit", async e => { try { loadProject(await api("/api/edit/" + e.detail)); } catch (er) { toast(er.message, "err"); } });
document.addEventListener("zeim:level", () => { if (E.p) renderTools(); });

/* ---------- applying a project payload ---------- */
function loadProject(p, keepCamera = false) {
  E.p = p; E.measure = false; clearMeasure(); clearGhost();
  $("#editStart").hidden = true; $("#editPanel").hidden = false; $("#editEmpty").hidden = true; $("#editVtools").hidden = false; $("#editResult").hidden = false;
  ensureViewer()?.load(p.preview, "edit", { flat: true, keepCamera });
  const a = p.analysis;
  $("#editStats").innerHTML = `<span class="pill">${a.size_mm.map(x => fmt(x)).join(" × ")} ${E.unit}</span><span class="pill">${a.triangles.toLocaleString()} triangles</span>` +
    `<span class="pill">${(a.volume_mm3 / 1000).toFixed(2)} cm³</span><span class="pill ${a.watertight ? "ok" : "bad"}">${a.watertight ? "✔ watertight" : "✖ not watertight"}</span>` +
    (a.internal_voids ? `<span class="pill bad" title="A sealed hollow inside the model. Hollow with a drain hole is intended; unexpected voids trap air or resin">${a.internal_voids} sealed void${a.internal_voids > 1 ? "s" : ""}</span>` : "") + (a.components > 1 ? `<span class="pill" title="Separate pieces in this model">${a.components} pieces</span>` : "") + (p.preview.decimated ? `<span class="pill" title="Exports use the full mesh">preview simplified</span>` : "");
  $("#editVis").value = p.visibility || "private";
  $("#eUndo").disabled = !p.can_undo; $("#eRedo").disabled = !p.can_redo;
  const msgs = [...(p.warnings || [])]; if (p.report?.message) msgs.unshift(p.report.message);
  if (p.report?.note) msgs.push(p.report.note);
  $("#editMsg").innerHTML = msgs.map(m => `<span class="${/not watertight|isn't|Still/.test(m) ? "warn" : ""}">${esc(m)}</span>`).join("<br>");
  const total = p.ops.length;
  $("#editHeadNote").textContent = `(${p.head} of ${total} applied — click a step to jump)`;
  $("#editOps").innerHTML = `<li class="${p.head === 0 ? "cur" : ""}"><button type="button" class="stepbtn" data-goto="0"${p.head === 0 ? ' aria-current="step"' : ""}>0 · Original file (kept)</button></li>` + p.ops.map(o => `<li class="${o.i === p.head ? "cur" : o.i > p.head ? "future" : ""}"><button type="button" class="stepbtn" data-goto="${o.i}"${o.i === p.head ? ' aria-current="step"' : ""}>${o.i} · ${esc(o.label)}</button></li>`).join("");
  renderTools();
  renderHistoryCard();
}
function renderHistoryCard() { loadHistory().catch(() => { }); }
$("#editOps").onclick = e => { const li = e.target.closest("[data-goto]"); if (li) act(`/api/edit/${E.p.id}/goto`, { head: +li.dataset.goto }, "Jumping…"); };

async function act(url, body, text = "Working…", near = null) {
  if (!E.p) return;
  busy(true, text);
  try { loadProject(await api(url, J("POST", body)), true); clearInline(near); }
  catch (e) { near ? inlineMsg(near, e.message) : toast(e.message, "err"); }
  finally { busy(false); }
}
const doOp = (op, params, text, near) => act(`/api/edit/${E.p.id}/op`, { op, params }, text, near);
$("#eUndo").onclick = () => act(`/api/edit/${E.p.id}/undo`, {});
$("#eRedo").onclick = () => act(`/api/edit/${E.p.id}/redo`, {});
$("#eReset").onclick = () => viewer?.reset();
$("#eWire").onclick = () => viewer?.toggleWire();
$("#editPrint").onclick = () => E.p && openPrint({ ...E.p, mode: "edit" });
$("#editSend").onclick = () => E.p && openSend({ ...E.p, kind: "edit" });
$("#editVis").onchange = async e => { try { await api(`/api/builds/${E.p.id}/visibility`, J("PUT", { visibility: e.target.value })); toast("Who can see this: " + e.target.value, "ok"); } catch (er) { toast(er.message, "err"); e.target.value = E.p.visibility; } };
addEventListener("keydown", e => {
  if ($("#viewEdit").hidden || !E.p || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
  if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); $("#eUndo").click(); }
  if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.shiftKey && e.key === "Z"))) { e.preventDefault(); $("#eRedo").click(); }
});

/* ---------- tool panel ---------- */
function renderTools() {
  const a = A(), cap = E.p.capabilities, sz = a.size_mm, ctr = a.center_mm;
  const unitSel = `<div class="row" style="justify-content:space-between"><b>${esc(E.p.title)}</b><span class="seg" id="unitSeg">${Object.keys(UNITS).map(u => `<button data-unit="${u}" class="${u === E.unit ? "on" : ""}">${u}</button>`).join("")}</span></div>`;
  const beginner = `<div data-lvl="beginner">
    <p class="help">Pick a job. ZEIM chooses sensible settings — switch to Experienced mode for every tool.</p>
    <div class="bigtools">
      <button class="bigtool ${E.tool === "fix" ? "on" : ""}" data-big="fix"><span class="ico">🩹</span><b>Fix</b><small>Repair holes &amp; flipped faces, put it on the bed</small></button>
      <button class="bigtool ${E.tool === "scale" ? "on" : ""}" data-big="scale"><span class="ico">↔</span><b>Scale</b><small>Make it bigger or smaller</small></button>
      <button class="bigtool ${E.tool === "hollow" ? "on" : ""}" data-big="hollow" ${cap.hollow ? "" : "disabled"}><span class="ico">🕳</span><b>Hollow</b><small>Save filament with a wall</small></button>
      <button class="bigtool ${E.tool === "base" ? "on" : ""}" data-big="base" ${cap.boolean ? "" : "disabled"}><span class="ico">▭</span><b>Add base</b><small>Flat plate for a stronger first layer</small></button>
    </div>
    <div id="bDrawer"></div></div>`;
  const expert = `<div data-lvl="expert">
    <details class="tool" open><summary>📐 Move / Rotate / Scale</summary>
      <form data-form="translate"><div class="grid3t">${lenInput("dx", 0, "Move X")}${lenInput("dy", 0, "Move Y")}${lenInput("dz", 0, "Move Z")}</div><button class="btn small">Move</button></form>
      <form data-form="rotate"><div class="grid3t">${numInput("rx", 0, "Rot X", "°")}${numInput("ry", 0, "Rot Y", "°")}${numInput("rz", 0, "Rot Z", "°")}</div>
        <div class="tool-row"><button class="btn small">Rotate</button><button type="button" class="btn small ghost" data-rot="rx">+90° X</button><button type="button" class="btn small ghost" data-rot="ry">+90° Y</button><button type="button" class="btn small ghost" data-rot="rz">+90° Z</button></div></form>
      <form data-form="scale"><div class="grid3t">${lenInput("sx", sz[0], "Size X")}${lenInput("sy", sz[1], "Size Y")}${lenInput("sz", sz[2], "Size Z")}</div>
        <div class="row"><label class="inl"><input type="checkbox" name="uniform" checked> Keep proportions</label>${numInput("pct", 100, "or percent", "%", 'style="width:90px"')}</div><button class="btn small">Scale</button></form>
      <div class="tool-row"><button class="btn small" data-op1="mirror:x">⇋ Mirror X</button><button class="btn small" data-op1="mirror:y">⇋ Mirror Y</button><button class="btn small" data-op1="mirror:z">⇋ Mirror Z</button></div>
      <div class="tool-row"><button class="btn small" data-op1="place:drop">⤓ Drop to bed</button><button class="btn small" data-op1="place:center">◎ Center on bed</button><button class="btn small" data-op1="place:both">Both</button></div>
    </details>
    <details class="tool"><summary>✂ Cut / split with a plane</summary>
      <form data-form="cut" data-ghost="cut"><div class="grid2"><div class="field"><label>Plane axis</label><select name="axis"><option value="z">Z (horizontal)</option><option value="x">X</option><option value="y">Y</option></select></div>${lenInput("position", ctr[2], "Position")}
        <div class="field"><label>Keep</label><select name="keep"><option value="above">Above / + side</option><option value="below">Below / − side</option><option value="both">Both pieces</option></select></div>${lenInput("gap", 5, "Gap between pieces")}</div>
        <label class="inl"><input type="checkbox" name="lay_flat" checked> Lay cut face flat on the bed</label><div><button class="btn small">Cut</button></div></form></details>
    <details class="tool"><summary>🕳 Hollow</summary>${cap.hollow ? `<form data-form="hollow"><div class="grid2">${lenInput("wall", 2, "Wall thickness")}${lenInput("drain_diameter", 0, "Drain hole Ø (0 = none)")}</div><button class="btn small">Hollow</button>
      <p class="help">Distance-field method, accurate to about one voxel (reported). Thin plates/lithophanes can't be hollowed.</p></form>` : `<p class="help">Needs manifold3d + scikit-image on the server.</p>`}</details>
    <details class="tool"><summary>▭ Base / brim</summary>${cap.boolean ? `<form data-form="base"><div class="grid3t"><div class="field"><label>Shape</label><select name="style"><option value="outline">Follow outline</option><option value="rect">Rectangle</option><option value="round">Round</option></select></div>${lenInput("margin", 3, "Margin")}${lenInput("thickness", 2, "Thickness")}</div><button class="btn small">Add base</button><p class="help">Thin (0.3–0.6 mm) = brim.</p></form>` : `<p class="help">Needs manifold3d.</p>`}</details>
    <details class="tool"><summary>🧊 Add / subtract shapes</summary>${cap.boolean ? `<form data-form="boolean" data-ghost="boolean"><div class="grid2"><div class="field"><label>Operation</label><select name="kind"><option value="difference">Subtract (cut out)</option><option value="union">Add (union)</option><option value="intersection">Keep overlap</option></select></div>
      <div class="field"><label>Shape</label><select name="shape"><option value="cylinder">Cylinder</option><option value="box">Box</option><option value="sphere">Sphere</option></select></div></div>
      <div class="grid3t" data-shape="box">${lenInput("bx", 10, "Width X")}${lenInput("by", 10, "Depth Y")}${lenInput("bz", 10, "Height Z")}</div>
      <div class="grid3t" data-shape="cylinder sphere">${lenInput("dia", 10, "Diameter")}<span data-shape="cylinder">${lenInput("h", 20, "Height")}</span><div class="field" data-shape="cylinder"><label>Axis</label><select name="axis"><option>z</option><option>x</option><option>y</option></select></div></div>
      <div class="grid3t">${lenInput("px", ctr[0], "Center X")}${lenInput("py", ctr[1], "Center Y")}${lenInput("pz", ctr[2], "Center Z")}</div><button class="btn small">Apply</button></form>` : `<p class="help">Boolean operations need manifold3d on the server.</p>`}</details>
    <details class="tool"><summary>🔤 Text (emboss / deboss)</summary>${cap.boolean ? `<form data-form="text"><div class="field"><label>Text</label><input name="text" maxlength="60" value="ZEIM"></div>
      <div class="grid2"><div class="field"><label>Font</label><select name="font">${cap.fonts.map(f => `<option>${f}</option>`).join("")}</select></div><div class="field"><label>Mode</label><select name="mode"><option value="emboss">Emboss (raised)</option><option value="deboss">Deboss (engraved)</option></select></div>
      ${lenInput("height", 8, "Letter height")}${lenInput("depth", 1, "Depth")}<div class="field"><label>Face</label><select name="face"><option>top</option><option>front</option><option>back</option><option>left</option><option>right</option><option>bottom</option></select></div>${numInput("rotation", 0, "Rotate", "°")}${lenInput("offset_u", 0, "Shift →")}${lenInput("offset_v", 0, "Shift ↑")}</div>
      <button class="btn small">Add text</button><p class="help">Placed on the model's flat bounding-box face — curved surfaces may not touch.</p></form>` : `<p class="help">Needs manifold3d.</p>`}</details>
    <details class="tool"><summary>🩹 Repair &amp; simplify</summary>
      <form data-form="repair"><label class="inl"><input type="checkbox" name="fix_normals" checked> Fix normals</label> <label class="inl"><input type="checkbox" name="fill_holes" checked> Fill holes</label> <label class="inl"><input type="checkbox" name="remove_duplicates" checked> Remove duplicates</label> <label class="inl"><input type="checkbox" name="keep_largest"> Drop floating bits</label><div><button class="btn small">Repair</button></div></form>
      ${cap.simplify ? `<form data-form="simplify"><div class="field"><label>Keep <em><span id="keepPct">50</span>% of triangles</em></label><input type="range" name="keep_ratio" min="0.05" max="0.95" step="0.05" value="0.5"></div><button class="btn small">Simplify</button></form>` : ""}</details>
    <details class="tool"><summary>📏 Measure &amp; info</summary>
      <button class="btn small" id="toggleMeasure">${E.measure ? "Stop measuring" : "Measure two points"}</button>
      <table class="info-table"><tr><td>Size (${E.unit})</td><td>${sz.map(fmt).join(" × ")}</td></tr><tr><td>Volume</td><td>${(a.volume_mm3 / 1000).toFixed(2)} cm³</td></tr><tr><td>Surface area</td><td>${(a.area_mm2 / 100).toFixed(1)} cm²</td></tr>
      <tr><td>Triangles</td><td>${a.triangles.toLocaleString()}</td></tr><tr><td>Watertight</td><td>${a.watertight ? "yes" : "no"} (open edges: ${a.boundary_edges}, non-manifold: ${a.nonmanifold_edges})</td></tr>
      <tr><td>Pieces</td><td>${a.components ?? "n/a"}</td></tr><tr><td>Bounds min</td><td>${a.min_mm.map(fmt).join(", ")}</td></tr><tr><td>Bounds max</td><td>${a.max_mm.map(fmt).join(", ")}</td></tr><tr><td>Centre of mass</td><td>${a.center_of_mass_mm.map(fmt).join(", ")}</td></tr></table></details>
  </div>`;
  $("#editPanel").innerHTML = unitSel + beginner + expert + `<button class="btn ghost small" id="editClose" style="margin-top:8px">＋ Open another model</button>`;
  if (E.tool && !isExpert()) renderDrawer();
  syncShapeFields();
}
$("#editPanel").addEventListener("click", e => {
  const u = e.target.closest("[data-unit]"); if (u) { E.unit = u.dataset.unit; localStorage.eunit = E.unit; loadProject(E.p, true); return; }
  const big = e.target.closest("[data-big]");
  if (big) {
    const t = big.dataset.big;
    if (t === "fix") { E.tool = null; return fix(); }
    E.tool = E.tool === t ? null : t; renderTools(); return;
  }
  const o1 = e.target.closest("[data-op1]");
  if (o1) { const [op, v] = o1.dataset.op1.split(":"); return doOp(op, op === "mirror" ? { axis: v } : { drop: v !== "center", center_xy: v !== "drop" }); }
  const rot = e.target.closest("[data-rot]"); if (rot) { e.preventDefault(); return doOp("rotate", { rx: 0, ry: 0, rz: 0, [rot.dataset.rot]: 90 }); }
  if (e.target.id === "toggleMeasure") toggleMeasure();
  if (e.target.id === "editClose") { E.p = null; $("#editStart").hidden = false; $("#editPanel").hidden = true; $("#editResult").hidden = true; $("#editVtools").hidden = true; $("#editEmpty").hidden = false; viewer?.group.clear(); clearGhost(); fillBuildSelect(); }
});
$("#editPanel").addEventListener("input", e => {
  const f = e.target.form; if (!f) return;
  if (e.target.name === "keep_ratio") $("#keepPct").textContent = Math.round(e.target.value * 100);
  if (f.dataset.form === "scale") {   // keep proportions / percent
    const sz = A().size_mm, cur = ["sx", "sy", "sz"];
    if (e.target.name === "pct") cur.forEach((n, i) => $(`[name=${n}]`, f).value = fmt(sz[i] * e.target.value / 100));
    else if (cur.includes(e.target.name) && f.uniform.checked) { const k = (+e.target.value * U()) / sz[cur.indexOf(e.target.name)]; cur.forEach((n, i) => { if (n !== e.target.name) $(`[name=${n}]`, f).value = fmt(sz[i] * k); }); f.pct.value = Math.round(k * 100); }
  }
  if (f.dataset.form === "boolean") syncShapeFields();
  if (f.dataset.ghost) updateGhost(f);
});
$("#editPanel").addEventListener("change", e => { const f = e.target.form; if (f?.dataset.form === "cut" && e.target.name === "axis") { const i = { x: 0, y: 1, z: 2 }[e.target.value]; f.position.value = fmt(A().center_mm[i]); } if (f?.dataset.form === "boolean") syncShapeFields(); if (f?.dataset.ghost) updateGhost(f); });
$("#editPanel").addEventListener("focusin", e => { const f = e.target.closest("form[data-ghost]"); if (f) updateGhost(f); });
function syncShapeFields() {
  const f = $("form[data-form=boolean]"); if (!f) return;
  const shape = f.shape.value;
  $$("[data-shape]", f).forEach(el => el.hidden = !el.dataset.shape.split(" ").includes(shape));
}
$("#editPanel").addEventListener("submit", e => {
  e.preventDefault(); const f = e.target, kind = f.dataset.form;
  const P = {
    translate: () => ({ dx: len(f, "dx"), dy: len(f, "dy"), dz: len(f, "dz") }),
    rotate: () => ({ rx: +val(f, "rx"), ry: +val(f, "ry"), rz: +val(f, "rz") }),
    scale: () => { const sz = A().size_mm; return { sx: len(f, "sx") / sz[0], sy: len(f, "sy") / sz[1], sz: len(f, "sz") / sz[2], pivot: "base" }; },
    cut: () => ({ axis: val(f, "axis"), position: len(f, "position"), keep: val(f, "keep"), lay_flat: f.lay_flat.checked, gap: len(f, "gap") }),
    hollow: () => ({ wall: len(f, "wall"), drain_diameter: len(f, "drain_diameter") }),
    base: () => ({ style: val(f, "style"), margin: len(f, "margin"), thickness: len(f, "thickness") }),
    boolean: () => ({ kind: val(f, "kind"), primitive: primSpec(f) }),
    text: () => ({ text: val(f, "text"), font: val(f, "font"), mode: val(f, "mode"), face: val(f, "face"), height: len(f, "height"), depth: len(f, "depth"), rotation: +val(f, "rotation"), offset_u: len(f, "offset_u"), offset_v: len(f, "offset_v") }),
    repair: () => ({ fix_normals: f.fix_normals.checked, fill_holes: f.fill_holes.checked, remove_duplicates: f.remove_duplicates.checked, keep_largest: f.keep_largest.checked }),
    simplify: () => ({ keep_ratio: +val(f, "keep_ratio") }),
  }[kind];
  if (!P) return;
  clearGhost();
  doOp(kind, P(), ({ hollow: "Hollowing…", boolean: "Computing boolean…", text: "Building text…", base: "Adding base…", simplify: "Simplifying…" })[kind], f.querySelector("button:not([type=button])"));
});
function primSpec(f) {
  const shape = val(f, "shape"), pos = [len(f, "px"), len(f, "py"), len(f, "pz")];
  if (shape === "box") return { type: "box", size: [len(f, "bx"), len(f, "by"), len(f, "bz")], position: pos };
  if (shape === "sphere") return { type: "sphere", diameter: len(f, "dia"), position: pos };
  return { type: "cylinder", diameter: len(f, "dia"), height: len(f, "h"), axis: val(f, "axis"), position: pos };
}

/* ---------- beginner big buttons ---------- */
async function fix() {
  busy(true, "Fixing…");
  try {
    let p = await api(`/api/edit/${E.p.id}/op`, J("POST", { op: "repair", params: {} }));
    const rep = p.report;
    p = await api(`/api/edit/${E.p.id}/op`, J("POST", { op: "place", params: { drop: true, center_xy: true } }));
    p.report = rep; loadProject(p, false);
    toast(rep?.message || "Fixed", p.analysis.watertight ? "ok" : "");
  } catch (e) { toast(e.message, "err"); } finally { busy(false); }
}
function renderDrawer() {
  const d = $("#bDrawer"); if (!d) return; const a = A(), t = E.tool, long = Math.max(...a.size_mm);
  if (t === "scale") d.innerHTML = `<div class="tooldrawer"><b>Scale</b><div class="tool-row">${[50, 75, 150, 200].map(p => `<button class="btn small" data-pct="${p}">${p}%</button>`).join("")}</div>
    <div class="row"><div class="field" style="flex:1;margin:0"><label>Or set the longest side to <em>${E.unit}</em></label><input type="number" id="bLong" value="${fmt(long)}" step="any"></div><button class="btn primary small" id="bScaleGo">Scale</button></div></div>`;
  if (t === "hollow") d.innerHTML = `<div class="tooldrawer"><b>Hollow</b><div class="seg wide" id="bWall">${[["1.2", "Thin"], ["2", "Standard"], ["3", "Thick"]].map(([v, n], i) => `<button data-w="${v}" class="${i === 1 ? "on" : ""}">${n} · ${v} mm</button>`).join("")}</div>
    <label class="inl"><input type="checkbox" id="bDrain" checked> Add a small drain hole (needed for resin; optional for filament)</label><div style="margin-top:8px"><button class="btn primary small" id="bHollowGo">Hollow it</button></div></div>`;
  if (t === "base") d.innerHTML = `<div class="tooldrawer"><b>Add base</b><p class="help">A 2 mm plate that follows the model's footprint, with 3 mm margin.</p><button class="btn primary small" id="bBaseGo">Add base</button></div>`;
}
$("#editPanel").addEventListener("click", e => {
  const id = e.target.id, d = e.target.closest("[data-pct]");
  if (d) { const k = +d.dataset.pct / 100; doOp("scale", { factor: k, pivot: "base" }); E.tool = null; }
  if (id === "bScaleGo") { const k = (+$("#bLong").value * U()) / Math.max(...A().size_mm); if (k > 0) doOp("scale", { factor: k, pivot: "base" }); E.tool = null; }
  if (e.target.closest("#bWall button")) { $$("#bWall button").forEach(b => b.classList.toggle("on", b === e.target.closest("button"))); }
  if (id === "bHollowGo") { const w = +($("#bWall .on")?.dataset.w || 2); doOp("hollow", { wall: w, drain_diameter: $("#bDrain").checked ? 3 : 0 }, "Hollowing…"); E.tool = null; }
  if (id === "bBaseGo") { doOp("base", { style: "outline", margin: 3, thickness: 2 }, "Adding base…"); E.tool = null; }
});

/* ---------- ghost previews (cut plane / boolean tool) ---------- */
function clearGhost() { if (ghost) { viewer.scene.remove(ghost); ghost.geometry.dispose(); ghost = null; } }
function updateGhost(f) {
  if (!viewer || !E.p) return; clearGhost();
  const a = A(), c = a.center_mm, sz = a.size_mm, mat = new THREE.MeshBasicMaterial({ color: f.dataset.ghost === "cut" ? 0x22d3ee : 0xff9e00, transparent: true, opacity: 0.35, side: THREE.DoubleSide, depthWrite: false });
  try {
    if (f.dataset.ghost === "cut") {
      const ax = val(f, "axis"), pos = len(f, "position"), big = Math.max(...sz) * 1.4;
      const g = new THREE.PlaneGeometry(big, big); ghost = new THREE.Mesh(g, mat);
      if (ax === "z") ghost.position.set(c[0], c[1], pos);
      if (ax === "x") { ghost.rotation.y = Math.PI / 2; ghost.position.set(pos, c[1], c[2]); }
      if (ax === "y") { ghost.rotation.x = Math.PI / 2; ghost.position.set(c[0], pos, c[2]); }
    } else {
      const sp = primSpec(f); let g;
      if (sp.type === "box") g = new THREE.BoxGeometry(...sp.size);
      else if (sp.type === "sphere") g = new THREE.SphereGeometry(sp.diameter / 2, 32, 16);
      else { g = new THREE.CylinderGeometry(sp.diameter / 2, sp.diameter / 2, sp.height, 40); g.rotateX(Math.PI / 2); if (sp.axis === "x") g.rotateY(Math.PI / 2); if (sp.axis === "y") g.rotateX(Math.PI / 2); }
      ghost = new THREE.Mesh(g, mat); ghost.position.set(...sp.position);
    }
    viewer.scene.add(ghost);
  } catch { }
}

/* ---------- measure tool ---------- */
function clearMeasure() { E.pts = []; measureObjs.forEach(o => viewer?.scene.remove(o)); measureObjs = []; $("#eMeasureOut").hidden = true; $("#eMeasure").classList.toggle("on", E.measure); }
function toggleMeasure() { E.measure = !E.measure; clearMeasure(); if (E.measure) { $("#eMeasureOut").hidden = false; $("#eMeasureOut").textContent = "Click the first point on the model…"; } const b = $("#toggleMeasure"); if (b) b.textContent = E.measure ? "Stop measuring" : "Measure two points"; }
$("#eMeasure").onclick = toggleMeasure;
function onPick(e) {
  if (!E.measure || !viewer) return;
  const r = viewer.renderer.domElement.getBoundingClientRect(), ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster(); rc.setFromCamera(ndc, viewer.camera);
  const hit = rc.intersectObjects(viewer.group.children, false)[0]; if (!hit) return;
  if (E.pts.length >= 2) clearMeasure(), E.measure = true, $("#eMeasureOut").hidden = false;
  E.pts.push(hit.point.clone());
  const dot = new THREE.Mesh(new THREE.SphereGeometry(Math.max(...A().size_mm) * 0.008, 12, 8), new THREE.MeshBasicMaterial({ color: 0xff3b6b, depthTest: false })); dot.position.copy(hit.point); dot.renderOrder = 9; viewer.scene.add(dot); measureObjs.push(dot);
  const out = $("#eMeasureOut");
  if (E.pts.length === 1) out.textContent = "Click the second point…";
  else {
    const [p, q] = E.pts, d = q.clone().sub(p);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([p, q]), new THREE.LineBasicMaterial({ color: 0xff3b6b, depthTest: false })); line.renderOrder = 9; viewer.scene.add(line); measureObjs.push(line);
    out.innerHTML = `<b>${fmt(d.length() * 1)} ${E.unit}</b> &nbsp; ΔX ${fmt(Math.abs(d.x))} · ΔY ${fmt(Math.abs(d.y))} · ΔZ ${fmt(Math.abs(d.z))} <small class="help">(click again to restart)</small>`;
  }
}
window.__zeimEdit = E;
window.__zeimEditStarted = true;               // (static/boot.js watchdog)
