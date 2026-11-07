/* TorchC0: ZEIM's resin program, its own main tab (#torchc0). Resin only: no nozzle, filament or gcode settings here.
   Upload a model -> place supports on that mesh -> POST /api/resin/prepare -> STL / 3MF,
   then POST /api/resin/{id}/slice writes the layer file for the selected printer. */
import { api, esc, $ } from "/static/app.js";
import { money } from "/static/cost.js";
import * as THREE from "three";
import { postForm, progress as handoffProgress } from "/static/handoff-veil.js";

/* OrbitControls in static/vendor/OrbitControls.js: LEFT rotate, MIDDLE dolly, RIGHT pan.
   Ctrl, Shift, or Meta swaps the left and right actions. The wheel dollies. */
const CAM_HINT = "Camera: left drag orbits, right drag pans, scroll wheel or middle drag zooms. Ctrl, Shift, or ⌘ with the left button pans instead. Dragging does not turn the model.";

/* 3D view of the real STL (every triangle in the buffer, not a stand-in). Optional matrix puts the
   loaded mesh into the pose Prepare will use. Marks and a click handler live here so viewer.js stays shared. */
const views = new WeakMap();
const supportEdit = {
  mode: "orbit", manual: [], avoid: [], undo: [], matrix: null, buf: null, bed: null, name: "", size: 0,
};
const SUPPORT_KEY = "zeim.resinSupports.v1";
function eye4() { const m = new Array(16).fill(0); m[0] = m[5] = m[10] = m[15] = 1; return m; }
function parseMatrix(text) {
  if (!text) return eye4();
  const n = String(text).split(",").map(Number);
  return n.length === 16 && n.every(v => Number.isFinite(v)) ? n : eye4();
}
function applyPoint(M, p) {
  return [
    M[0] * p[0] + M[1] * p[1] + M[2] * p[2] + M[3],
    M[4] * p[0] + M[5] * p[1] + M[6] * p[2] + M[7],
    M[8] * p[0] + M[9] * p[1] + M[10] * p[2] + M[11],
  ];
}
function threeMatrix(M) {
  const e = new THREE.Matrix4();
  e.set(M[0], M[1], M[2], M[3], M[4], M[5], M[6], M[7], M[8], M[9], M[10], M[11], M[12], M[13], M[14], M[15]);
  return e;
}
function saveSupportLocal() {
  try {
    localStorage.setItem(SUPPORT_KEY, JSON.stringify({
      name: supportEdit.name, size: supportEdit.size, manual: supportEdit.manual, avoid: supportEdit.avoid,
    }));
  } catch { /* the prepare response still keeps the marks */ }
}
function loadSupportLocal(name, size) {
  try {
    const raw = JSON.parse(localStorage.getItem(SUPPORT_KEY) || "null");
    if (!raw || raw.name !== name || raw.size !== size) return false;
    supportEdit.manual = Array.isArray(raw.manual) ? raw.manual : [];
    supportEdit.avoid = Array.isArray(raw.avoid) ? raw.avoid : [];
    supportEdit.undo = [];
    return true;
  } catch { return false; }
}
function supportStatus() {
  const el = $("#rzSupStatus");
  if (!el) return;
  const n = supportEdit.manual.length, a = supportEdit.avoid.length;
  const mode = { orbit: "Orbit", add: "Add support", erase: "Erase", avoid: "Keep clear" }[supportEdit.mode] || "Orbit";
  el.textContent = n || a
    ? `${mode}. ${n} placed support${n === 1 ? "" : "s"}, ${a} keep-clear mark${a === 1 ? "" : "s"}. Automatic supports skip keep-clear marks. An unsupported island is still reported. Drag still orbits; a tap places or erases.`
    : `${mode}. Tap the model to place a support, or mark a spot automatic supports should skip. Drag orbits, right-drag pans. Nothing here promises an unmarked face.`;
}
async function show3D(el, url, lc, buf, bed, opts) {
  opts = opts || {};
  try {
    const { Viewer } = await import("/static/viewer.js");
    let viewer = views.get(el);
    if (!viewer || !el.contains(viewer.el)) { viewer = new Viewer(el); views.set(el, viewer); }
    if (!buf) buf = await (await fetch(url)).arrayBuffer();
    const dv = new DataView(buf), n = dv.getUint32(80, true);
    if (84 + n * 50 > buf.byteLength) throw new Error("not a binary STL");
    const pos = new Float32Array(n * 9);
    for (let i = 0; i < n; i++) for (let k = 0; k < 9; k++) pos[i * 9 + k] = dv.getFloat32(84 + i * 50 + 12 + k * 4, true);
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.computeVertexNormals();
    viewer.group.clear();
    viewer.setBed(bed);
    const model = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: "#8fb0e0", roughness: 0.6, transparent: true, opacity: 0.92, side: THREE.DoubleSide }));
    model.userData.model = true;
    const M = opts.matrix || eye4();
    model.matrixAutoUpdate = false;
    model.matrix.copy(threeMatrix(M));
    model.updateMatrixWorld(true);
    viewer.group.add(model);
    g.computeBoundingBox(); const sz = g.boundingBox.getSize(new THREE.Vector3()), r = Math.max(0.8, Math.max(sz.x, sz.y, sz.z) / 60);
    const mark = (p, color, kind, index) => {
      const m = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 10), new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true, opacity: kind === "avoid" ? 0.55 : 1 }));
      m.position.set(p[0], p[1], p[2]); m.renderOrder = 2; m.userData.mark = kind; m.userData.index = index; viewer.group.add(m);
    };
    ((lc && lc.islands) || []).forEach(i => i.xyz && mark(i.xyz, "#e5484d"));
    ((lc && lc.suction) || []).forEach(i => i.xyz && mark(i.xyz, "#f5a524"));
    (opts.manual || []).forEach((p, i) => mark(applyPoint(M, p), "#3dd68c", "manual", i));
    (opts.avoid || []).forEach((p, i) => mark(applyPoint(M, p), "#e5484d", "avoid", i));
    if (!opts.keepCamera) {
      const box = new THREE.Box3().setFromObject(model);
      const c = box.getCenter(new THREE.Vector3());
      const s = box.getSize(new THREE.Vector3());
      const rad = Math.max(s.x, s.y, s.z, 8);
      viewer.camera.position.set(c.x + rad * 0.2, c.y - rad * 1.6, c.z + rad);
      viewer.camera.far = rad * 40;
      viewer.camera.updateProjectionMatrix();
      viewer.controls.target.copy(c);
      viewer.controls.update();
    }
    const marks = viewer.group.children.filter(c => c.userData && (c.userData.mark || (lc && (c.userData.mark === undefined)))).length;
    el.dataset.markers = String(((lc && lc.islands) || []).filter(i => i.xyz).length + ((lc && lc.suction) || []).filter(i => i.xyz).length);
    el.dataset.supports = String((opts.manual || []).length);
    el.dataset.avoid = String((opts.avoid || []).length);
    const canvas = viewer.renderer.domElement;
    if (viewer._resinPick) canvas.removeEventListener("pointerup", viewer._resinPick);
    if (viewer._resinDownFn) canvas.removeEventListener("pointerdown", viewer._resinDownFn);
    viewer._resinDown = null;
    const down = ev => { viewer._resinDown = { x: ev.clientX, y: ev.clientY }; };
    const up = ev => {
      const start = viewer._resinDown; viewer._resinDown = null;
      if (!start || !opts.onPick || supportEdit.mode === "orbit") return;
      const dx = ev.clientX - start.x, dy = ev.clientY - start.y;
      if (dx * dx + dy * dy > 64) return;
      const rect = viewer.renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
      const ray = new THREE.Raycaster(); ray.setFromCamera(ndc, viewer.camera);
      const marksHit = ray.intersectObjects(viewer.group.children.filter(c => c.userData && c.userData.mark), false);
      const modelHit = ray.intersectObject(model, false);
      opts.onPick({ mark: marksHit[0] || null, hit: modelHit[0] || null, matrix: model.matrix });
    };
    viewer._resinDownFn = down;
    viewer._resinPick = up;
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointerup", up);
    void marks;
  } catch (e) { el.innerHTML = `<p class="help">3D preview unavailable here (${esc(e.message)}). The files below are still ready.</p>`; }
}

const PKEY = "zeim.resinPrice";   // remembered in this browser only: {price, unit, currency}
const CURS = ["$", "€", "£", "¥", "₹", "R$", "kr"];
const loadP = () => { try { return JSON.parse(localStorage.getItem(PKEY)) || {}; } catch { return {}; } };
const saveP = v => { try { localStorage.setItem(PKEY, JSON.stringify(v)); } catch { } };

let cat = null;
let sliceTimer = null;
let sliceJob = "";
function stopSlicePoll() { if (sliceTimer) { clearInterval(sliceTimer); sliceTimer = null; } }
const bedTol = 0.35;
function selectedPrinter() {
  return cat && cat.printers && cat.printers.find(p => p.id === ($("#rzPrinter") && $("#rzPrinter").value));
}
function bedsMatch(bed, plate) {
  if (!bed || bed.length < 3) return false;
  const pb = [plate.build_width_um / 1000, plate.build_depth_um / 1000, plate.build_height_um / 1000];
  return bed.every((v, i) => Math.abs(+v - pb[i]) <= bedTol);
}
function platesForPrinter(printer) {
  if (!printer) return [];
  return ((cat && cat.lumen_plates) || []).filter(p =>
    (p.manufacturer || "").toLowerCase() === (printer.brand || "").toLowerCase()
    && p.name === printer.model && bedsMatch(printer.bed_mm, p));
}
function plateBlock(plate, fmt) {
  return (plate.blocks && plate.blocks[fmt]) || "";
}
function plateOptions(size, fmt) {
  const printer = selectedPrinter();
  const plates = platesForPrinter(printer);
  const kind = fmt || "lumen";
  if (!plates.length) {
    const who = printer ? printer.name : "This printer";
    return `<option value="" disabled selected>${esc(who)} has no matching slice plate</option>`;
  }
  const why = p => {
    const block = plateBlock(p, kind);
    if (block) return " (not written)";
    if (size && (size[0] > p.build_width_um / 1000 + 1e-3 || size[1] > p.build_depth_um / 1000 + 1e-3 || size[2] > p.build_height_um / 1000 + 1e-3)) return " (model does not fit)";
    return "";
  };
  const open = plates.find(p => !why(p));
  return plates.map(p => {
    const reason = why(p);
    return `<option value="${esc(p.id)}"${open && p.id === open.id ? " selected" : ""}${reason ? " disabled" : ""}>${esc(p.manufacturer)} ${esc(p.name)}${esc(reason)}</option>`;
  }).join("");
}
function formatForPlate(plate) {
  if (!plate) return "lumen";
  const native = (plate.native_format || "").replace(/^\./, "");
  if (native && !plateBlock(plate, native)) return native;
  if (!plateBlock(plate, "lumen")) return "lumen";
  return native || "lumen";
}
const num = (id, label, v, min, max, step, unit) => `<div class="field"><label for="${id}">${label} <em>${unit}</em></label><input type="number" id="${id}" value="${v}" min="${min}" max="${max}" step="${step}" inputmode="decimal"></div>`;

function panelHTML() {
  const brands = [...new Set(cat.printers.map(p => p.brand))];
  return `<h2>Resin print settings</h2>
    <div class="grid2 rzRow"><div class="field"><label for="rzPrinter">Resin printer</label><select id="rzPrinter">${brands.map(b => `<optgroup label="${esc(b)}">${cat.printers.filter(p => p.brand === b).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</optgroup>`).join("")}</select></div>
    <div class="field"><label for="rzFile">Model (STL, 3MF or OBJ)</label><div class="drop rzDrop" id="rzDrop"><svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 15V3M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg><input type="file" id="rzFile" class="rzFileIn"><label for="rzFile" class="btn">Choose a model</label><span>or drop an STL, 3MF or OBJ file here</span></div>
      <p class="help" id="rzFileStatus" role="status" aria-live="polite"></p>
      <div id="rzPickView" class="rzView" role="img" aria-label="3D view of the chosen model" hidden style="position:relative;width:100%;height:min(60vw,300px);min-height:200px;border-radius:8px;overflow:hidden"></div>
      <p class="help" id="rzCamHint">${CAM_HINT}</p>
      <fieldset class="rzOrient" id="rzSupEdit" hidden><legend>Supports on the model</legend>
        <p class="help" id="rzSupStatus"></p>
        <div class="row"><button type="button" class="btn small" id="rzModeOrbit" aria-pressed="true">Orbit</button><button type="button" class="btn small" id="rzModeAdd">Add support</button><button type="button" class="btn small" id="rzModeErase">Erase</button><button type="button" class="btn small" id="rzModeAvoid">Keep clear</button><button type="button" class="btn small" id="rzSupUndo">Undo</button><button type="button" class="btn small" id="rzSupReset">Reset</button></div>
      </fieldset></div></div>
    <p class="help" id="rzInfo"></p>
    <div class="grid2"><div class="field"><label for="rzMaterial">Resin</label><select id="rzMaterial">${(cat.materials || []).map(m => `<option value="${m.id}" ${m.id === cat.default_material ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select></div>
    <div class="field"><label for="rzPreset">Preset</label><select id="rzPreset">${cat.presets.map(x => `<option value="${x.id}" ${x.id === cat.default_preset ? "selected" : ""}>${esc(x.label)} · ${x.layer_mm} mm</option>`).join("")}</select></div></div>
    <p class="help" id="rzMatNote"></p><div id="rzMatExtra"></div>
    <details class="rzAdv" id="rzAdv"${document.body.dataset.level === "expert" ? " open" : ""}><summary>Advanced resin settings</summary><div class="grid3">${num("rzLayer", "Layer height", 0.05, 0.01, 0.2, 0.01, "mm")}${num("rzExp", "Exposure", 2.5, 0.5, 30, 0.1, "s")}${num("rzBExp", "Bottom exposure", 30, 5, 120, 1, "s")}
      ${num("rzBL", "Bottom layers", 5, 1, 15, 1, "")}${num("rzLift", "Lift distance", 6, 1, 15, 0.5, "mm")}${num("rzLiftS", "Lift speed", 65, 10, 300, 5, "mm/min")}
      ${num("rzWall", "Hollow wall", 2, 0.5, 6, 0.5, "mm")}${num("rzDrain", "Drain hole Ø", 3, 0, 10, 0.5, "mm")}</div></details>
    <p class="help warn rzWarn" id="rzWallWarn" hidden>Walls under 1 mm crack easily in resin. Use 1 mm or more, or prepare anyway.
      <button type="button" class="btn small" id="rzWallAnyway">Prepare anyway</button> <button type="button" class="btn small" id="rzWallDismiss" aria-label="Dismiss this warning">Dismiss</button></p>
    <div class="grid3"><div class="field"><label for="rzCur">Currency</label><select id="rzCur">${CURS.map(c => `<option ${c === (loadP().currency || "$") ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
      ${num("rzCost", "Resin price", loadP().price ?? cat.default_price ?? "", 0, 10000, 0.5, "")}
      <div class="field"><label for="rzCostU">Price per</label><select id="rzCostU"><option value="l" ${(loadP().unit || cat.default_price_unit) === "l" ? "selected" : ""}>litre</option><option value="kg" ${loadP().unit === "kg" ? "selected" : ""}>kg</option></select></div></div>
    <p class="help" id="rzPriceNote"></p>
    <fieldset class="rzOrient"><legend>Model on the plate</legend>
      <p class="help">These angles turn the model before supports are built. They are not the camera. Supports grow on surfaces that face the plate, so turn the side you want unmarked away from the plate. Supports the print still needs stay.</p>
      <div class="grid2">${num("rzTilt", "Turn about X", 0, -180, 180, 5, "°")}${num("rzTiltY", "Turn about Y", 0, -180, 180, 5, "°")}</div>
      <div class="row"><button type="button" class="btn small" id="rzOriXp">+90° X</button><button type="button" class="btn small" id="rzOriXn">−90° X</button><button type="button" class="btn small" id="rzOriYp">+90° Y</button><button type="button" class="btn small" id="rzOriYn">−90° Y</button><button type="button" class="btn small" id="rzOri0">File orientation</button></div>
    </fieldset>
    <label class="inl chk"><input type="checkbox" id="rzHollow" checked> Hollow (saves resin; needs a drain hole)</label>
    <p class="help warn rzWarn" id="rzDrainWarn" role="status" hidden>Hollow with no drain hole: liquid resin stays trapped inside, and the part can crack or leak later. Set Drain hole Ø to 2 mm or more, or turn Hollow off.</p>
    <label class="inl chk"><input type="checkbox" id="rzSup" checked> Supports and raft</label>
    <p class="help">${esc(cat.test_note)} ${esc(cat.formats_note)}</p>
    <details><summary>Resin safety</summary><ul id="rzSafety">${cat.safety.map(s => `<li>${esc(s)}</li>`).join("")}</ul></details>
    <div class="row"><button class="btn primary big" id="rzGo">Prepare for resin</button><button type="button" class="btn" id="rzPublish" title="Open the Showcase form for this model. Nothing is published until you confirm in that form.">Send to Showcase</button></div>`;
}

function wire() {
  const pr = $("#rzPreset"), info = () => {
    const p = selectedPrinter();
    const el = $("#rzInfo");
    if (!p || !el) return;
    const bed = `Build volume ${p.bed_mm.map(v => +v).join(" × ")} mm.`;
    const plates = platesForPrinter(p);
    if (!plates.length) { el.textContent = `${bed} No slice plate matches ${p.name}. TorchC0 will not write another machine's file.`; return; }
    const plate = plates[0];
    const fmt = formatForPlate(plate);
    const block = plateBlock(plate, fmt);
    el.textContent = block
      ? `${bed} ${block}`
      : `${bed} The slice for this printer is a .${fmt} of ${plate.name} (${plate.width_px}×${plate.height_px}). It has not been printed on a machine.`;
  };
  const matOf = () => (cat.materials || []).find(m => m.id === $("#rzMaterial").value) || (cat.materials || [])[0];
  const applyPrint = n => { if (!n) return; $("#rzLayer").value = n.layer_mm; $("#rzExp").value = n.exposure_s; $("#rzBExp").value = n.bottom_exposure_s; $("#rzBL").value = n.bottom_layers; $("#rzLift").value = n.lift_mm; $("#rzLiftS").value = n.lift_speed_mm_min; };
  const paintMaterial = apply => {
    const mat = matOf(); if (!mat) return;
    const own = mat.settings;
    pr.disabled = !!own;
    pr.title = own ? "Quality presets apply to standard resin. Silicone uses its own starting profile." : "";
    if (apply) applyPrint(own || cat.presets.find(x => x.id === pr.value));
    $("#rzMatNote").textContent = mat.help || "";
    const src = mat.sources || [];
    $("#rzMatExtra").innerHTML = (mat.notes || []).map(t => `<p class="help">${esc(t)}</p>`).join("")
      + (src.length ? `<details><summary>Sources for these starting values</summary><ul>${src.map(s => `<li><a href="${esc(s.url)}">${esc(s.label)}</a></li>`).join("")}</ul></details>` : "");
    $("#rzSafety").innerHTML = cat.safety.concat(mat.safety || []).map(s => `<li>${esc(s)}</li>`).join("");
    const kg = mat.density_g_ml == null && $("#rzCostU").value === "kg";
    $("#rzPriceNote").textContent = kg ? "Silicone has no single density here, so a per-kg price cannot be turned into a cost. Enter a price per litre." : "";
  };
  const bedNow = () => { const p = cat.printers.find(x => x.id === $("#rzPrinter").value); return p && p.bed_mm; };
  const round3 = n => Math.round(n * 1000) / 1000;
  const pushUndo = () => { supportEdit.undo.push({ manual: supportEdit.manual.map(p => p.slice()), avoid: supportEdit.avoid.map(p => p.slice()) }); if (supportEdit.undo.length > 40) supportEdit.undo.shift(); };
  const setMode = mode => {
    supportEdit.mode = mode;
    for (const [id, key] of [["rzModeOrbit", "orbit"], ["rzModeAdd", "add"], ["rzModeErase", "erase"], ["rzModeAvoid", "avoid"]]) {
      const b = $(id); if (b) b.setAttribute("aria-pressed", key === mode ? "true" : "false");
    }
    supportStatus();
  };
  const redrawPick = keep => {
    const pv = $("#rzPickView");
    if (!pv || !supportEdit.buf) return;
    return show3D(pv, null, null, supportEdit.buf, supportEdit.bed || bedNow(), {
      matrix: supportEdit.matrix || eye4(), manual: supportEdit.manual, avoid: supportEdit.avoid,
      keepCamera: !!keep, onPick: onSupportPick,
    }).then(supportStatus);
  };
  function onSupportPick(ev) {
    if (supportEdit.mode === "erase") {
      if (!ev.mark) { const s = $("#rzSupStatus"); if (s) s.textContent = "Tap a green or red mark to remove it. Drag still orbits."; return; }
      pushUndo();
      const kind = ev.mark.object.userData.mark, i = ev.mark.object.userData.index;
      (kind === "avoid" ? supportEdit.avoid : supportEdit.manual).splice(i, 1);
      saveSupportLocal(); redrawPick(true); return;
    }
    if (supportEdit.mode !== "add" && supportEdit.mode !== "avoid") return;
    if (!ev.hit) { const s = $("#rzSupStatus"); if (s) s.textContent = "That tap missed the model. Tap the part itself. Drag orbits."; return; }
    let point = ev.hit.point.clone();
    const normal = ev.hit.face && ev.hit.face.normal ? ev.hit.face.normal.clone().transformDirection(ev.matrix) : new THREE.Vector3(0, 0, -1);
    if (normal.z > -0.2) {
      const ray = new THREE.Raycaster(point.clone().add(new THREE.Vector3(0, 0, 0.5)), new THREE.Vector3(0, 0, -1));
      const under = ray.intersectObject(ev.hit.object, false).find(h => h.face && h.face.normal.clone().transformDirection(ev.matrix).z < -0.2);
      if (under) point = under.point.clone();
    }
    const inv = ev.matrix.clone().invert();
    const base = new THREE.Vector3(point.x, point.y, point.z).applyMatrix4(inv);
    const stored = [round3(base.x), round3(base.y), round3(base.z)];
    pushUndo();
    (supportEdit.mode === "avoid" ? supportEdit.avoid : supportEdit.manual).push(stored);
    if (supportEdit.manual.length > 200) supportEdit.manual.length = 200;
    if (supportEdit.avoid.length > 200) supportEdit.avoid.length = 200;
    saveSupportLocal(); redrawPick(true);
  }
  $("#rzModeOrbit").onclick = () => setMode("orbit");
  $("#rzModeAdd").onclick = () => setMode("add");
  $("#rzModeErase").onclick = () => setMode("erase");
  $("#rzModeAvoid").onclick = () => setMode("avoid");
  $("#rzSupUndo").onclick = () => { const prev = supportEdit.undo.pop(); if (!prev) return; supportEdit.manual = prev.manual; supportEdit.avoid = prev.avoid; saveSupportLocal(); redrawPick(true); };
  $("#rzSupReset").onclick = () => { pushUndo(); supportEdit.manual = []; supportEdit.avoid = []; saveSupportLocal(); redrawPick(true); };
  $("#rzPrinter").onchange = () => { info(); const f = $("#rzFile") && $("#rzFile").files[0]; if (f) show(); if (last && last.rep) dropResult("Printer changed. Prepare again so the supports and the slice match this bed."); }; info();
  pr.onchange = () => { const mat = matOf(); if (mat && mat.settings) return; applyPrint(cat.presets.find(x => x.id === pr.value)); };
  $("#rzMaterial").onchange = () => paintMaterial(true);
  $("#rzCostU").onchange = () => paintMaterial(false);
  paintMaterial(false);
  // thin hollow wall: a dismissable warning, never a block (Prepare stays enabled; "Prepare anyway" just runs it)
  let wallOk = false;
  const wallWarn = () => { $("#rzWallWarn").hidden = wallOk || !($("#rzHollow").checked && +$("#rzWall").value > 0 && +$("#rzWall").value < 1); };
  $("#rzWall").addEventListener("input", () => { wallOk = false; wallWarn(); }); $("#rzHollow").addEventListener("change", wallWarn);
  const drainWarn = () => { $("#rzDrainWarn").hidden = !($("#rzHollow").checked && !(+$("#rzDrain").value > 0)); };   // UX10
  $("#rzDrain").addEventListener("input", drainWarn); $("#rzHollow").addEventListener("change", drainWarn);
  $("#rzWallDismiss").onclick = () => { wallOk = true; wallWarn(); };
  $("#rzWallAnyway").onclick = () => { wallOk = true; wallWarn(); $("#rzGo").click(); };
  // file pick / drop: show name + size right away; wrong types get a friendly note (never blocks anything else)
  const st = $("#rzFileStatus"), inp = $("#rzFile"), drop = $("#rzDrop");
  const kb = n => n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`;
  // soft hint only: the server checks the content and decides (it accepts e.g. no extension or iPhone ".3mf.zip")
  const okType = f => /\.(stl|3mf|obj)(\.zip)?$/i.test(f.name);
  // displayed name only: drop bidi overrides/isolates, zero-width and control chars so the name can't be misread
  const shownName = n => n.replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]/g, "");
  const show = () => { const f = inp.files[0]; st.classList.remove("warn");
    $("#torchOut").querySelector(".rzNeedFile")?.remove();   // P1: the "choose a file first" note goes as soon as a file is chosen
    if (!f) { st.textContent = ""; pickSeq++; $("#rzPickView").hidden = true; return; }
    const nm = shownName(f.name) || "(unnamed file)";
    if (!okType(f)) { st.textContent = `${nm}, ${kb(f.size)}. This doesn't look like an STL, 3MF or OBJ name, TorchC0 is checking the file itself…`; loadPick(f, nm); return; }
    st.textContent = `${nm}, ${kb(f.size)}, loading…`; loadPick(f, nm); };
  // Load the picked model into the view right away (any STL/3MF/OBJ, via the server), so a pick visibly loads.
  // pickLoad: the in-flight preview; picked: {f, id} once the server holds the loaded copy. Prepare waits for the
  // preview and sends the id, so a big file is uploaded and read once (no "busy" from a second copy racing it).
  let pickSeq = 0, pickLoad = null, picked = null;
  const loadPick = (f, nm) => { picked = null; pickLoad = loadPick1(f, nm); return pickLoad; };
  const loadPick1 = async (f, nm) => {
    const seq = ++pickSeq, pv = $("#rzPickView");
    try {
      const fd = new FormData(); fd.append("file", f); fd.append("printer_id", $("#rzPrinter").value);
      const r = await postForm("/api/resin/preview", fd, handoffProgress);   // real upload/download % for the hand-off veil
      if (seq !== pickSeq) return;
      if (!r.ok) { let m = `HTTP ${r.status}`; try { m = JSON.parse(new TextDecoder().decode(r.buf)).detail || m; } catch { }
        st.classList.add("warn"); st.textContent = `${nm}, ${kb(f.size)}: couldn't load it. ${m}`; pv.hidden = true; return; }
      const buf = r.buf; if (seq !== pickSeq) return;
      const n = +r.headers.get("X-Zeim-Faces") || 0, uid = r.headers.get("X-Zeim-Upload");
      if (uid) picked = { f, id: uid };
      const bed = bedNow();
      const sameFile = supportEdit.name === nm && supportEdit.size === f.size;
      if (sameFile && supportEdit.bed && bed) {
        const dx = bed[0] / 2 - supportEdit.bed[0] / 2, dy = bed[1] / 2 - supportEdit.bed[1] / 2;
        if (dx || dy) {
          const shift = p => [round3(p[0] + dx), round3(p[1] + dy), p[2]];
          supportEdit.manual = supportEdit.manual.map(shift);
          supportEdit.avoid = supportEdit.avoid.map(shift);
        }
      } else if (!sameFile) {
        supportEdit.manual = []; supportEdit.avoid = []; supportEdit.undo = [];
        loadSupportLocal(nm, f.size);
      }
      supportEdit.name = nm; supportEdit.size = f.size; supportEdit.bed = bed; supportEdit.buf = buf;
      supportEdit.matrix = parseMatrix(r.headers.get("X-Zeim-Matrix"));
      pv.hidden = false; $("#rzSupEdit").hidden = false;
      await show3D(pv, null, null, buf, bed, { matrix: supportEdit.matrix, manual: supportEdit.manual, avoid: supportEdit.avoid, onPick: onSupportPick });
      supportStatus();
      pv.scrollIntoView({ block: "nearest", behavior: "smooth" });
      st.textContent = `${nm}, ${kb(f.size)}${n ? `, ${n.toLocaleString()} triangles` : ""}, loaded. Press Prepare for resin.`;
    } catch (e) { if (seq !== pickSeq) return; st.classList.add("warn"); st.textContent = `${nm}, ${kb(f.size)}: couldn't load it (${e.message}). You can still press Prepare for resin.`; }
    finally { if (seq === pickSeq) document.dispatchEvent(new CustomEvent("zeim:torchc0-loaded")); }   // the hand-off veil lifts
  };
  inp.addEventListener("change", () => { delete document.body.dataset.torchStl; show(); });   // a new model: Send to… uses it, not the old result
  // tapping anywhere on the drop zone opens the picker (phones can't drop); the input itself already does
  drop.addEventListener("click", e => { if (e.target !== inp && !e.target.closest("a,button,label")) inp.click(); });
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => { const fs = e.dataTransfer?.files; if (!fs?.length) return;
    const dt = new DataTransfer(); dt.items.add(fs[0]); inp.files = dt.files; show(); });
  const publishTorch = () => document.dispatchEvent(new CustomEvent("zeim:send-showcase", { detail: { src: "torchc0" } }));
  if ($("#rzPublish")) $("#rzPublish").onclick = publishTorch;
  $("#rzGo").onclick = async () => {
    const out = $("#torchOut"), f = $("#rzFile").files[0];
    if (!f) { out.innerHTML = `<p class="help warn rzNeedFile" role="alert">Choose an STL, 3MF or OBJ file first.</p>`; return; }
    if (f.size > 500 * 1024 * 1024) { out.innerHTML = `<p class="help warn" role="alert">That file is over 500 MB. Try a smaller one, or simplify it first.</p>`; return; }
    const fd = new FormData();
    const v = { printer_id: $("#rzPrinter").value, material: $("#rzMaterial").value, preset: pr.value, layer_mm: $("#rzLayer").value, exposure_s: $("#rzExp").value,
      bottom_exposure_s: $("#rzBExp").value, bottom_layers: $("#rzBL").value, lift_mm: $("#rzLift").value, lift_speed_mm_min: $("#rzLiftS").value,
      tilt_deg: $("#rzTilt").value, tilt_y_deg: $("#rzTiltY").value, wall_mm: $("#rzWall").value, drain_mm: $("#rzDrain").value, hollow: $("#rzHollow").checked, supports: $("#rzSup").checked,
      price: $("#rzCost").value, price_unit: $("#rzCostU").value };
    last = { v, f, isl: [], drains: [] };
    await run();
  };
  let last = null;
  let preparedKey = "";
  const poseKey = () => `${$("#rzPrinter").value}|${$("#rzTilt").value}|${$("#rzTiltY").value}`;
  const dropResult = (msg) => {
    if (!last || !last.rep) return;
    stopSlicePoll();
    last.rep = null; last.isl = []; last.drains = [];
    delete document.body.dataset.torchStl;
    const box = $("#torchOut");
    if (box) { box.classList.remove("rzResult"); box.innerHTML = `<p class="help warn" id="rzStale" role="status">${msg}</p>`; }
  };
  const refreshPlacement = async () => {
    if (!picked) return;
    const fd = new FormData();
    fd.append("upload_id", picked.id);
    fd.append("tilt_deg", $("#rzTilt").value || "0");
    fd.append("tilt_y_deg", $("#rzTiltY").value || "0");
    fd.append("printer_id", $("#rzPrinter").value || "");
    try {
      const body = await api("/api/resin/placement", { method: "POST", body: fd });
      supportEdit.matrix = body.matrix || eye4();
      supportEdit.bed = bedNow();
      if (supportEdit.buf) await redrawPick(true);
      const note = $("#rzSupStatus");
      if (note && (supportEdit.manual.length || supportEdit.avoid.length)) note.textContent = `The model moved. ${supportEdit.manual.length} placed support${supportEdit.manual.length === 1 ? "" : "s"} and ${supportEdit.avoid.length} keep-clear mark${supportEdit.avoid.length === 1 ? "" : "s"} followed it. Prepare again so the built supports match.`;
    } catch (e) {
      supportEdit.manual = []; supportEdit.avoid = [];
      if (supportEdit.buf) await redrawPick(true);
      const note = $("#rzSupStatus");
      if (note) note.textContent = `The model moved and the support marks were cleared (${e.message}). Place them again on this pose.`;
    }
  };
  const onPose = () => {
    refreshPlacement();
    if (last && last.rep && poseKey() !== preparedKey) dropResult("Orientation or printer changed. Prepare again so the supports, island marks, and slice match this placement.");
  };
  const bump = (id, delta) => {
    const el = $(id); let v = Math.round((+el.value || 0) + delta);
    if (v > 180) v -= 360; if (v < -180) v += 360; el.value = String(v); onPose();
  };
  $("#rzOriXp").onclick = () => bump("#rzTilt", 90);
  $("#rzOriXn").onclick = () => bump("#rzTilt", -90);
  $("#rzOriYp").onclick = () => bump("#rzTiltY", 90);
  $("#rzOriYn").onclick = () => bump("#rzTiltY", -90);
  $("#rzOri0").onclick = () => { $("#rzTilt").value = "0"; $("#rzTiltY").value = "0"; onPose(); };
  $("#rzTilt").addEventListener("input", onPose);
  $("#rzTiltY").addEventListener("input", onPose);
  async function startSlice() {
    stopSlicePoll();
    const box = $("#rzSliceOut");
    const rid = last && last.rep && last.rep.export && last.rep.export.rid;
    if (!rid) { box.innerHTML = `<p class="help warn" role="alert">Prepare the model first.</p>`; return; }
    const fd = new FormData();
    fd.append("plate_id", $("#rzPlate").value);
    fd.append("anti_alias", $("#rzAA") && $("#rzAA").checked ? "true" : "false");
    fd.append("aa_level", "4");
    const sliceFmt = ($("#rzSliceFmt") && $("#rzSliceFmt").value) || "lumen";
    fd.append("file_format", sliceFmt);
    const btn = $("#rzSlice"); if (btn) { btn.disabled = true; btn.setAttribute("aria-busy", "true"); }
    box.innerHTML = `<p class="help" role="status">Slicing…</p>`;
    try {
      const job = await api(`/api/resin/${rid}/slice`, { method: "POST", body: fd });
      sliceJob = job.job_id;
      let keep = true;
      const tick = async () => {
        const j = await api(`/api/resin/jobs/${sliceJob}`);
        if (j.status === "done") {
          keep = false;
          stopSlicePoll();
          const layers = j.layers || 1;
          const ext = j.format || "lumen";
          const native = (j.report && j.report.native_format) || "";
          const hw = "It has not been printed on a machine.";
          const kind = ext === "lumen"
            ? `${layers} layers in a .lumen file. ${native ? `Stock files for this plate are ${native}. ` : ""}${hw}`
            : `${layers} layers in a .${ext} file from mslicer. ${native ? `Catalog stock file is ${native}. ` : ""}That name is not a firmware test. ${hw}`;
          const preview = ext === "lumen" ? `<img id="rzLayerImg" alt="Sliced layer preview" style="width:100%;max-width:320px;height:auto;background:#111;border-radius:8px">
            <div class="field"><label for="rzLayerN">Layer preview</label><input id="rzLayerN" type="range" min="0" max="${layers - 1}" value="0" style="width:100%;min-height:44px"></div>` : "";
          box.innerHTML = `<p class="help">${kind}</p>
            ${preview}
            <div class="row"><a class="btn primary" id="rzLumen" href="${j.download}" download style="min-height:44px">Download .${esc(ext)}</a></div>`;
          if (ext === "lumen") {
            const show = i => { const img = $("#rzLayerImg"); if (img) img.src = `/api/resin/jobs/${sliceJob}/layer/${i}.png`; };
            show(0);
            const range = $("#rzLayerN"); if (range) range.oninput = ev => show(ev.target.value);
          }
          return;
        }
        if (j.status === "error" || j.status === "cancelled") {
          keep = false;
          stopSlicePoll();
          box.innerHTML = `<p class="help ${j.status === "error" ? "warn" : ""}" role="status">${esc(j.error || "Slice cancelled.")}</p>`;
          return;
        }
        const n = j.layers ? `${j.done_layers || 0} of ${j.layers}` : "starting";
        box.innerHTML = `<p class="help" role="status">Slicing, ${esc(String(n))}.</p><button type="button" class="btn" id="rzSliceCancel" style="min-height:44px">Cancel slice</button>`;
      };
      await tick();
      if (keep) sliceTimer = setInterval(() => tick().catch(err => { stopSlicePoll(); box.innerHTML = `<p class="help warn" role="alert">${esc(err.message)}</p>`; }), 400);
    } catch (err) {
      box.innerHTML = `<p class="help warn" role="alert">${esc(err.message)}</p>`;
    } finally {
      const b = $("#rzSlice"); if (b) { b.disabled = false; b.removeAttribute("aria-busy"); }
    }
  }
  $("#torchOut").addEventListener("click", async e => {      // one-click fixes re-run the same job with the extra points
    if (e.target.closest("#rzPublishResult")) { document.dispatchEvent(new CustomEvent("zeim:send-showcase", { detail: { src: "torchc0" } })); return; }
    if (e.target.closest("#rzSlice")) { await startSlice(); return; }
    if (e.target.closest("#rzSliceCancel") && sliceJob) { await api(`/api/resin/jobs/${sliceJob}/cancel`, { method: "POST" }).catch(() => {}); return; }
    const b = e.target.closest("#rzFixIsl,#rzFixCup"); if (!b || !last || !last.rep) return;
    const lc = last.rep.layer_check;
    if (b.id === "rzFixIsl") last.isl = last.isl.concat(lc.islands.map(i => i.at).filter(Boolean));
    else last.drains = last.drains.concat(lc.suction.map(i => i.at).filter(Boolean));
    await run();
  });
  async function run() {
    stopSlicePoll();
    const out = $("#torchOut"), { v, f } = last, fd = new FormData();
    saveP({ price: $("#rzCost").value === "" ? null : +$("#rzCost").value, unit: $("#rzCostU").value, currency: $("#rzCur").value });
    Object.entries(v).forEach(([k, x]) => fd.append(k, x));
    if (pickLoad) { $("#torchOut").innerHTML = `<p class="help" role="status" aria-live="polite">Loading the model first…</p>`; await pickLoad.catch(() => { }); }
    const uid = picked && picked.f === f ? picked.id : "";
    if (uid) { fd.append("upload_id", uid); fd.append("file_name", f.name); } else fd.append("file", f);
    if (last.isl.length) fd.append("island_supports", JSON.stringify(last.isl));
    if (last.drains.length) fd.append("drains", JSON.stringify(last.drains));
    const M = supportEdit.matrix || eye4();
    const placed = supportEdit.manual.map(p => applyPoint(M, p).map(n => Math.round(n * 1000) / 1000));
    const kept = supportEdit.avoid.map(p => applyPoint(M, p).map(n => Math.round(n * 1000) / 1000));
    if (placed.length) fd.append("support_points", JSON.stringify(placed));
    if (kept.length) fd.append("avoid_points", JSON.stringify(kept));
    out.innerHTML = `<p class="help" role="status" aria-live="polite">Preparing… TorchC0 is hollowing, tilting and adding supports. Larger models can take a minute.</p>`;
    const go = $("#rzGo"); go.disabled = true; go.setAttribute("aria-busy", "true"); go.textContent = "Preparing…";
    try {
      let r;
      try { r = await api("/api/resin/prepare", { method: "POST", body: fd }); }
      catch (err) { if (err.status !== 410 || !uid) throw err;      // the loaded copy expired: send the file itself
        picked = null; fd.delete("upload_id"); fd.delete("file_name"); fd.append("file", f); r = await api("/api/resin/prepare", { method: "POST", body: fd }); }
      const e = r.estimate;
      last.rep = r; preparedKey = poseKey(); document.body.dataset.torchStl = r.downloads.stl;   // Send to… hands over the prepared model
      const lc = r.layer_check || { islands: [], suction: [] }, nI = lc.islands.length, nS = lc.suction.length;
      const costTxt = e.cost == null ? "<svg class=i aria-hidden=true focusable=false><use href=#i-coin></use></svg> enter a price for a cost estimate" : `<svg class=i aria-hidden=true focusable=false><use href=#i-coin></use></svg> about ${esc(money(e.cost, $("#rzCur").value))} (estimate)`;
      out.innerHTML = `<h2 class="rzResHead">Result</h2><div id="rzView" class="rzView" role="img" aria-label="3D view of the prepared model: red dots are islands, orange dots are suction cups" style="position:relative;width:100%;height:min(60vw,360px);min-height:220px;border-radius:8px;overflow:hidden"></div>
        <div class="rzChecks" id="rzChecks">
        <p class="help ${nI ? "warn rzWarn" : ""}" id="rzIslands"><span class="pill"><svg class=i i-red aria-hidden=true focusable=false><use href=#i-dot></use></svg> ${nI} island${nI === 1 ? "" : "s"}</span> ${nI ? "Parts that start in mid-air (red dots)." : "No unsupported islands found."}
          ${nI ? `<button type="button" class="btn small" id="rzFixIsl" style="min-height:44px">Add supports to islands</button> <button type="button" class="btn small rzDismiss" style="min-height:44px" aria-label="Dismiss the island warning">Dismiss</button>` : ""}</p>
        <p class="help ${nS ? "warn rzWarn" : ""}" id="rzCups"><span class="pill"><svg class=i i-amber aria-hidden=true focusable=false><use href=#i-dot></use></svg> ${nS} suction cup${nS === 1 ? "" : "s"}</span> ${nS ? "Hollows sealed on the plate side trap resin and pull a vacuum (orange dots)." : "No suction cups found."}
          ${nS ? `<button type="button" class="btn small" id="rzFixCup" style="min-height:44px">Add drain hole${nS === 1 ? "" : "s"}</button> <button type="button" class="btn small rzDismiss" style="min-height:44px" aria-label="Dismiss the suction cup warning">Dismiss</button>` : ""}</p></div>
        <p class="slicestats"><span class="pill"><svg class=i aria-hidden=true focusable=false><use href=#i-clock></use></svg> about ${esc(e.print_time_human)}</span><span class="pill"><svg class=i aria-hidden=true focusable=false><use href=#i-flask></use></svg> about ${e.resin_ml} ml</span><span class="pill" id="rzCostOut">${costTxt}</span><span class="pill">${e.layers} layers, estimate</span>${r.material && r.material.id !== "standard" ? `<span class="pill">${esc(r.material.label)}</span>` : ""}${r.support ? `<span class="pill">${r.support.supports} supports</span>` : ""}${r.fits === false ? `<span class="pill warn">Too big</span>` : ""}</p>
        <p class="help">${esc(r.placement || "")}</p>
        <p class="help">${esc(e.slice_note || "Slice writes the layer file for the printer selected above. It has not been printed on a machine.")}</p>
        <p class="help">${CAM_HINT}</p>
        <div class="row rzSliceRow">
          <div class="field"><label for="rzPlate">Plate</label><select id="rzPlate">${plateOptions(r.size_mm, "lumen")}</select></div>
          <div class="field"><label for="rzSliceFmt">Layer file</label><select id="rzSliceFmt"><option value="lumen">.lumen</option><option value="goo">.goo</option><option value="ctb">.ctb</option></select></div>
          <label class="inl chk" style="min-height:44px"><input type="checkbox" id="rzAA"> Anti-alias edges</label>
          <button type="button" class="btn primary" id="rzSlice" style="min-height:44px">Slice</button>
        </div>
        <p class="help" id="rzPlateNote"></p>
        <div id="rzSliceOut"></div>
        ${r.hollow ? `<p class="help">${esc(r.hollow.message)}</p>` : ""}
        ${(r.material_notes || []).map(n => `<p class="help">${esc(n)}</p>`).join("")}
        ${r.notes.filter(n => !/ island\(s\)| suction cup\(s\)/.test(n)).map(n => `<p class="help warn rzWarn">${esc(n)} <button type="button" class="btn small rzDismiss" style="min-height:44px" aria-label="Dismiss this warning">Dismiss</button></p>`).join("")}
        <p class="help">${esc(e.resin_note)} ${esc(e.cost_note)}</p>
        <div class="row"><button type="button" class="btn primary" id="rzExport" data-export-rid="${esc(r.export?.rid || "")}" data-export-name="${esc(r.export?.name || "")}" aria-haspopup="dialog"><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> Export…</button><a class="btn" href="${r.downloads.stl}" download id="rzQuickStl">Quick STL</a><button type="button" class="btn" id="rzPublishResult" title="Open the Showcase form for this prepared model. Nothing is published until you confirm in that form.">Send to Showcase</button></div>`;
      out.classList.add("rzResult");
      out.querySelectorAll(".rzDismiss").forEach(b => b.onclick = () => b.closest(".rzWarn").remove());   // warnings never block: the files are already made
      const plateSel = $("#rzPlate"), fmtSel = $("#rzSliceFmt");
      const sayPlate = () => {
        const note = $("#rzPlateNote");
        if (!note) return;
        const printer = selectedPrinter();
        const plates = platesForPrinter(printer);
        if (!plates.length) { note.textContent = printer ? `${printer.name} has no matching slice plate. TorchC0 will not write another machine's file.` : ""; return; }
        const p = plates.find(x => x.id === plateSel.value) || plates[0];
        const fmt = (fmtSel && fmtSel.value) || "lumen";
        const block = plateBlock(p, fmt);
        const fit = r.size_mm && (r.size_mm[0] > p.build_width_um / 1000 + 1e-3 || r.size_mm[1] > p.build_depth_um / 1000 + 1e-3 || r.size_mm[2] > p.build_height_um / 1000 + 1e-3);
        note.textContent = block || (fit ? "The prepared model does not fit this bed." : `${p.manufacturer} ${p.name}: ${p.width_px}×${p.height_px} px, build ${(p.build_width_um / 1000).toFixed(1)} × ${(p.build_depth_um / 1000).toFixed(1)} × ${(p.build_height_um / 1000).toFixed(1)} mm. This slice writes .${fmt} for the printer selected above. Not printed on a machine.`);
      };
      const paintPlates = () => {
        const prev = plateSel.value;
        plateSel.innerHTML = plateOptions(r.size_mm, fmtSel.value);
        const still = [...plateSel.options].find(o => o.value === prev && !o.disabled);
        const open = still || [...plateSel.options].find(o => !o.disabled);
        if (open) plateSel.value = open.value;
        sayPlate();
      };
      if (fmtSel) {
        const first = platesForPrinter(selectedPrinter())[0];
        const prefer = formatForPlate(first);
        if ([...fmtSel.options].some(o => o.value === prefer)) fmtSel.value = prefer;
      }
      if (plateSel) { paintPlates(); plateSel.onchange = sayPlate; if (fmtSel) fmtSel.onchange = paintPlates; }
      show3D($("#rzView"), r.downloads.stl, lc, null, bedNow());
    } catch (err) { out.innerHTML = `<p class="help warn" role="alert">${esc(err.message)}</p>`; }
    finally { const go = $("#rzGo"); go.disabled = false; go.removeAttribute("aria-busy"); go.textContent = "Prepare for resin"; }
  }
}

let loading = null;
function load() { return loading || (loading = load1().finally(() => { loading = null; })); }   // one build of the panel even when called twice
async function load1() {
  if (cat) return;
  try { cat = await api("/api/resin/catalog"); $("#torchPanel").innerHTML = panelHTML(); wire(); document.dispatchEvent(new CustomEvent("zeim:torchc0-ready")); }
  catch (e) { cat = null; $("#torchPanel").innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`; }
}
document.addEventListener("zeim:torchc0-shown", load);
document.addEventListener("zeim:level", () => { const d = $("#rzAdv"); if (d) d.open = document.body.dataset.level === "expert"; });   // S9: Beginner sees preset + Hollow/Supports
document.addEventListener("zeim:torchc0-file", () => load());   // Send to… (static/handoff.js) fills the file once the panel exists
document.addEventListener("zeim:new-build", e => {
  if (!e.detail || e.detail.section !== "torchc0" || e.detail.publish) return;
  const inp = $("#rzFile"); if (inp) inp.value = "";
  const st = $("#rzFileStatus"); if (st) { st.textContent = ""; st.classList.remove("warn"); }
  const pv = $("#rzPickView"); if (pv) pv.hidden = true;
  delete document.body.dataset.torchStl;
  stopSlicePoll();
  const out = $("#torchOut"); if (out) { out.innerHTML = ""; out.classList.remove("rzResult"); }
  document.dispatchEvent(new CustomEvent("zeim:torchc0-forget"));
});
if (location.hash.startsWith("#torchc0") || location.hash.startsWith("#resin")) load();
