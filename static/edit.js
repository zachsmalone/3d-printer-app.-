import * as THREE from "three";
import { Viewer } from "/static/viewer.js";
import { openSend } from "/static/send.js";
import { S, api, toast, inlineMsg, clearInline, $, $$, esc, openPrint, loadHistory, renderHistory, openFull, isExpert } from "/static/app.js";
import { photoBlock, mountPhoto } from "/static/photo.js";
import { renderPlate, pickAt, wireDrag, wirePanel as wirePlatePanel, paint as paintPlate } from "/static/plate.js";
import { P, loadCatalog, panelHTML, wirePanel, badgeHTML, checkBuild } from "/static/printer.js";

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
  wireDrag(viewer);
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
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); S.pending = auto => { S.pending = null; const f2 = retry(); if (auto) f2.append("auto_delete_oldest", "true"); return create(f2, retry); }; openFull(); editPick.msg("Your recent builds are full (5 of 5). Delete one in the window, then continue."); }
    else if ((e.status === 415 && /photo/i.test(e.message)) || (E.photoTry && [400, 413, 415].includes(e.status))) editPick.msg(e.message);       // photo problems stay under the photo buttons (QA-3)
    else toast(e.message, "err");
  } finally { busy(false); }
}
const PHOTO_RE = /\.(png|jpe?g|webp|bmp|gif|heic|heif)$/i;
const MODEL_RE = /\.(stl|obj|3mf)(\.zip)?$/i;
// iPhones sometimes hand a 3MF over as "x.3mf.zip", with no extension, or typed model/3mf / application/zip / octet-stream:
// those go to the server, which identifies the format from the file's content.
const MODEL_MIME = /^(model\/|application\/(vnd\.ms-package\.3dmanufacturing|zip|x-zip|octet-stream|sla|vnd\.ms-pki\.stl))/i;
const isModel = f => MODEL_RE.test(f.name || "") || MODEL_MIME.test(f.type || "") || !/\.[a-z0-9]{1,5}$/i.test(f.name || "");
// iOS greys out files in the picker when `accept` lists bare extensions it can't map to a type, so #editFile has NO accept list:
// the file type is checked here by its name (any MIME, including empty or application/octet-stream), and again by the server.
function modelMsg(t) { const m = $("#editModelMsg"); m.textContent = t || ""; m.hidden = !t; }
function fromFile(file) {
  modelMsg("");
  if (!file) return;
  E.photoTry = /^image\//.test(file.type) || PHOTO_RE.test(file.name || "");
  if (!E.photoTry && !isModel(file)) return modelMsg("That doesn't look like a 3D model. Choose an .stl, .obj or .3mf file, or start from a photo below.");
  if (!E.photoTry && file.size > 50 * 1024 * 1024) return modelMsg("That file is over 50 MB. Try a smaller one, or simplify it first.");
  if (!E.photoTry && !file.size) return modelMsg("That file is empty. Choose another .stl, .obj or .3mf file.");
  if (E.photoTry && !file.size) return editPick.msg("We couldn't open that photo. Try a JPG or PNG.");            // same pre-checks as Studio, shown inline (QA-3)
  if (E.photoTry && file.size > 25 * 1024 * 1024) return editPick.msg("That photo is over 25 MB. Try a smaller one (JPG or PNG).");
  editPick.msg("");
  const mk = () => { const fd = new FormData(); fd.append("file", file); fd.append("units", $("#editUnits").value); fd.append("photo_mode", $("#editPhotoMode").value); fd.append("photo_ack", editPick.acked()); fd.append("beginner", !isExpert()); return fd; };
  create(mk(), mk);
}
const drop = $("#editDrop");
$("#btnHave3d")?.addEventListener("click", () => { location.hash = "slicer"; $("#editFile").click(); });     // Studio → Edit (same tap, so iOS opens the picker)
$("#editChooseModel").onclick = () => $("#editFile").click();
$("#editPhoto").innerHTML = photoBlock("e", { sample: true });
const editPick = mountPhoto("e", f => fromFile(f));   // defined BEFORE the file handlers below: fromFile() uses it (an early pick hit a TDZ error and the file silently never loaded)
// Import bug fix: a picked/dropped file must ALWAYS either load or say why. Any unexpected error is shown, never swallowed.
function takeFiles(list) {
  const files = [...(list || [])];
  try { fromFiles(files); }
  catch (e) { console.error(e); busy(false); modelMsg("We couldn't open that file. Please try again, or choose an .stl, .obj or .3mf file."); }
}
$("#editFile").onchange = e => { const l = [...e.target.files]; e.target.value = ""; takeFiles(l); };
drop.addEventListener("click", () => $("#editFile").click());
$("#eSample").onclick = async () => {
  try { const b = await (await fetch("/static/sample.jpg")).blob(); fromFile(new File([b], "sample.jpg", { type: "image/jpeg" })); }
  catch { editPick.msg("We couldn't load the sample image. Please try again."); }
};
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => { e.stopPropagation(); takeFiles(e.dataTransfer.files); });
// Dropping a model anywhere on the Slicer page (outside the small drop box, or onto the viewer while a model is open) used to make
// the browser open/download the file instead, so it never appeared in ZEIM. The whole page now accepts the drop.
const viewEl = $("#viewEdit");
["dragenter", "dragover"].forEach(ev => viewEl.addEventListener(ev, e => { if (e.dataTransfer?.types?.includes("Files")) e.preventDefault(); }));
viewEl.addEventListener("drop", e => { if (!e.dataTransfer?.files?.length) return; e.preventDefault(); takeFiles(e.dataTransfer.files); });

/* ---------- several files at once: 'Parts of one print' (one plate) or 'Separate prints' ---------- */
let multiFiles = [];
const MULTI_MAX_BYTES = 50 * 2 ** 20, MULTI_TOTAL_BYTES = 55 * 2 ** 20;   // server: 50 MB per file, 56 MB per request
function fromFiles(files) {
  files = files.filter(Boolean);
  if (files.length <= 1) return fromFile(files[0]);
  const bad = files.filter(f => !isModel(f));
  if (bad.length) return modelMsg("When you pick several files, they all need to be 3D models (.stl, .obj or .3mf).");
  if (files.length > 12) return modelMsg("Up to 12 files at a time.");
  const big = files.find(f => f.size > MULTI_MAX_BYTES);
  if (big) return modelMsg(`${big.name} is over 50 MB. Try a smaller file.`);
  if (files.reduce((t, f) => t + f.size, 0) > MULTI_TOTAL_BYTES) return modelMsg("Those files are over 55 MB together. Pick fewer files at a time.");
  modelMsg(""); multiFiles = files;
  $("#multiWhich").textContent = `${files.length} files: ${files.map(f => f.name).join(", ")}`;
  $("#multiMsg").textContent = "";
  $("#dlgMulti").showModal();
}
async function sendMulti(mode, auto = false) {
  const fd = new FormData();
  multiFiles.forEach(f => fd.append("files", f));
  fd.append("mode", mode); fd.append("units", $("#editUnits").value); fd.append("beginner", !isExpert());
  if (auto) fd.append("auto_delete_oldest", "true");
  try { await loadCatalog(); fd.append("printer_id", P.pref.printer_id); } catch { }   // one-plate bed check uses the chosen printer's bed
  $("#multiMsg").textContent = mode === "plate" ? "Arranging the parts on one plate…" : "Importing each file…";
  busy(true, "Importing…");
  try {
    const r = await api("/api/edit/multi", { method: "POST", body: fd });
    $("#dlgMulti").close();
    S.history = r.history; renderHistory(); loadProject(r.project);
    if (r.mode === "plate") toast(r.plate.fits ? `All ${r.plate.parts} parts fit on the bed (${r.plate.footprint_mm[0]} × ${r.plate.footprint_mm[1]} mm).` : `These parts don't fit on one ${r.plate.bed_mm[0]} × ${r.plate.bed_mm[1]} mm bed together. Try Separate prints or scale them down.`, r.plate.fits ? "ok" : "err");
    else toast(`Made ${r.projects.length} separate projects. Find them under Pick up where you left off.`, "ok");
  } catch (e) {
    if (e.status === 409 && e.body?.code === "history_full") { $("#dlgMulti").close(); S.history = e.body.builds; renderHistory(); S.pending = a => { S.pending = null; return sendMulti(mode, a); }; openFull(); }
    else $("#multiMsg").textContent = e.message;
  } finally { busy(false); }
}
$("#multiPlate").onclick = () => sendMulti("plate");
$("#multiSeparate").onclick = () => sendMulti("separate");
$("#editSample").onclick = async () => { const b = await (await fetch("/static/sample_model.stl")).blob(); fromFile(new File([b], "sample_cat.stl")); };
function fromBuild(id) {
  const mk = () => { const fd = new FormData(); fd.append("from_build", id); fd.append("beginner", !isExpert()); return fd; };
  create(mk(), mk);
}
$("#editFromBuildGo").onclick = () => { const v = $("#editFromBuild").value; if (v) fromBuild(v); };
$("#btnEditThis")?.addEventListener("click", () => { if (S.current) { location.hash = "slicer"; fromBuild(S.current.id); } });
function fillBuildSelect() {
  $("#editFromBuild").innerHTML = S.history.length ? S.history.slice().reverse().map(b => `<option value="${b.id}">${esc(b.title)} (${b.kind === "edit" ? "edited" : b.mode})</option>`).join("") : `<option value="">No builds yet — make one in the Studio</option>`;
  $("#editFromBuildGo").disabled = !S.history.length;
}
/* Send to Slicer sets the hash (which restores zeim.edit.last) and then opens the new project.
   Whichever request finishes last used to win, so a previous slicer model could replace the lithophane. */
let editLoadGen = 0;
document.addEventListener("zeim:edit-shown", async () => {
  const gen = editLoadGen;
  try { await loadHistory(); } catch { } fillBuildSelect(); ensureViewer(); setTimeout(() => viewer?.resize(), 50);
  if (gen !== editLoadGen || E.p) return;
  // returning from CAD (Back) reloads the page: reopen the model that was loaded (CAD edits are saved server-side on the same project)
  let last = null; try { last = sessionStorage.getItem("zeim.edit.last"); } catch { }
  if (!last) return;
  try {
    const p = await api("/api/edit/" + encodeURIComponent(last));
    if (gen !== editLoadGen || E.p) return;
    loadProject(p);
  } catch { try { sessionStorage.removeItem("zeim.edit.last"); } catch { } }
});
document.addEventListener("zeim:open-edit", async e => {
  const gen = ++editLoadGen;
  try {
    const p = await api("/api/edit/" + encodeURIComponent(e.detail));
    if (gen !== editLoadGen) return;
    loadProject(p);
  } catch (er) { if (gen === editLoadGen) toast(er.message, "err"); }
});
document.addEventListener("zeim:level", () => { if (E.p) renderTools(); });

/* ---------- applying a project payload ---------- */
function loadProject(p, keepCamera = false) {
  { const oc = $("#editOpenCad"); if (oc) oc.href = "/static/cad.html?bid=" + encodeURIComponent(p.id); }
  try { sessionStorage.setItem("zeim.edit.last", p.id); } catch { }   // so Back from CAD (full page load) can restore it
  E.p = p; E.measure = false; E.facePick = false; E.planes = null; clearFaceMark(); clearMeasure(); clearGhost();
  $("#editStart").hidden = true; $("#editPanel").hidden = false; $("#editEmpty").hidden = true; $("#editVtools").hidden = false; $("#editResult").hidden = false;
  ensureViewer()?.load(p.preview, "edit", { flat: true, keepCamera });
  const a = p.analysis;
  const q = p.quality_gate || { ok: true, issues: [], message: "Model is print-safe to export." };
  $("#editStats").innerHTML = `<span class="pill">${a.size_mm.map(x => fmt(x)).join(" × ")} ${E.unit}</span><span class="pill">${a.triangles.toLocaleString()} triangles</span>` +
    `<span class="pill">${(a.volume_mm3 / 1000).toFixed(2)} cm³</span><span class="pill ${q.ok ? "ok" : "bad"}">${q.ok ? "✔ print-safe" : "✖ needs repair"}</span>` +
    (a.internal_voids ? `<span class="pill bad" title="A sealed hollow inside the model. Hollow with a drain hole is intended; unexpected voids trap air or resin">${a.internal_voids} sealed void${a.internal_voids > 1 ? "s" : ""}</span>` : "") + (a.components > 1 ? `<span class="pill" title="Separate pieces in this model">${a.components} pieces</span>` : "") + (p.preview.decimated ? `<span class="pill" title="Exports use the full mesh">preview simplified</span>` : "");
  $("#editVis").value = p.visibility || "private";
  $("#eUndo").disabled = !p.can_undo; $("#eRedo").disabled = !p.can_redo;
  const msgs = [...(p.warnings || [])]; if (!q.ok && q.message) msgs.unshift(q.message); if (p.report?.message) msgs.unshift(p.report.message);
  if (p.report?.note) msgs.push(p.report.note);
  $("#editMsg").innerHTML = msgs.map(m => `<span class="${/not watertight|needs repair|Fix the model|isn't|Still/.test(m) ? "warn" : ""}">${esc(m)}</span>`).join("<br>");
  const total = p.ops.length;
  $("#editHeadNote").textContent = `(${p.head} of ${total} applied — click a step to jump)`;
  $("#editOps").innerHTML = `<li class="${p.head === 0 ? "cur" : ""}"><button type="button" class="stepbtn" data-goto="0"${p.head === 0 ? ' aria-current="step"' : ""}>0 · Original file (kept)</button></li>` + p.ops.map(o => `<li class="${o.i === p.head ? "cur" : o.i > p.head ? "future" : ""}"><button type="button" class="stepbtn" data-goto="${o.i}"${o.i === p.head ? ' aria-current="step"' : ""}>${o.i} · ${esc(o.label)}</button>${o.editable ? ` <button type="button" class="stepbtn" data-editstep="${o.i}" title="Change this step's numbers; later steps are replayed" aria-label="Edit step ${o.i}">✎</button> <button type="button" class="stepbtn" data-delstep="${o.i}" title="Delete this step; later steps are replayed" aria-label="Delete step ${o.i}"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>` : ""}</li>`).join("");
  renderTools();
  renderHistoryCard();
  renderSlicePanel();
}
async function renderSlicePanel() {
  if (!E.p) return;
  const id = E.p.id;
  try { await loadCatalog(); } catch { return; }
  const lithoHint = (E.p.mode === "lithophane" || E.p.base?.photo_mode === "lithophane" || E.p.base?.from_mode === "lithophane") ? "lithophane" : "";
  if (window.zeimSave && window.zeimSave.hold) window.zeimSave.hold("slicer");
  $("#slicePanel").innerHTML = panelHTML(lithoHint); wirePanel(() => E.p.id);
  if (window.zeimSave && window.zeimSave.setProject) window.zeimSave.setProject("slicer", id, { restore: true });
  $("#editWill").innerHTML = "";
  try { const r = await checkBuild(id); if (E.p?.id === id) $("#editWill").innerHTML = badgeHTML(r, { detail: true }); } catch { }
}
document.addEventListener("zeim:printer", renderSlicePanel);
function renderHistoryCard() { loadHistory().catch(() => { }); }
$("#editOps").onclick = async e => {
  const ed = e.target.closest("[data-editstep]"), del = e.target.closest("[data-delstep]");
  if (ed || del) {
    const i = +(ed || del).dataset[ed ? "editstep" : "delstep"], o = E.p.ops.find(x => x.i === i);
    if (!o) return;
    busy(true, ed ? "Replaying…" : "Deleting…");
    try {
      if (ed) {
        const t = prompt(`Edit step ${i} (${o.label}). Change the values and keep the format:`, JSON.stringify(o.params));
        if (t === null) return;
        let params; try { params = JSON.parse(t); } catch { toast("That isn't valid values text.", "err"); return; }
        loadProject(await api(`/api/edit/${E.p.id}/step/${i}`, J("PUT", { params })), true);
      } else {
        if (!confirm(`Delete step ${i} (${o.label})? Later steps are replayed; if they can't be, nothing changes.`)) return;
        loadProject(await api(`/api/edit/${E.p.id}/step/${i}`, J("DELETE")), true);
      }
    } catch (er) { toast(er.message, "err"); } finally { busy(false); }
    return;
  }
   const li = e.target.closest("[data-goto]"); if (li) act(`/api/edit/${E.p.id}/goto`, { head: +li.dataset.goto }, "Jumping…"); };

function wireDims() {
  const b = $("#dimSave"); if (!b) return;
  b.onclick = async () => {
    const dims = {}, msg = $("#dimMsg");
    for (const line of $("#dimTxt").value.split("\n").map(l => l.trim()).filter(Boolean)) {
      const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*(-?[0-9]*\.?[0-9]+)$/);
      if (!m) { msg.textContent = `Couldn't read “${line}”. Use: name = number`; return; }
      dims[m[1]] = +m[2];
    }
    b.disabled = true;
    try { loadProject(await api(`/api/edit/${E.p.id}/dims`, J("PUT", { dims })), true); }
    catch (er) { msg.textContent = er.message; }
    finally { b.disabled = false; }
  };
}

function wirePrintCheck() {
  const run = $("#pcRun"); if (!run) return;
  const box = $("#pcBox");
  run.onclick = async () => {
    run.disabled = true; run.textContent = "Checking…";
    try {
      const r = await api(`/api/edit/${E.p.id}/printcheck?process=${encodeURIComponent($("#pcProc").value)}`);
      E.lastCheck = r;
      const fixes = (r.fixes || []).map(fx =>
        `<button type="button" class="btn small" data-pcfix="${esc(fx.id)}" data-op="${esc(fx.op || "")}" data-action="${esc(fx.action || "")}">${esc(fx.label)}</button>`
      ).join(" ");
      box.innerHTML = (r.ok ? `<p class="help">No problems found.</p>` : `<ul class="pc-list">${(r.issues_meta || r.issues.map(i => ({ text: i }))).map(i => `<li class="warn">${esc(i.text || i)}</li>`).join("")}</ul>`)
        + (fixes ? `<div class="tool-row" style="flex-wrap:wrap;gap:6px;margin-top:8px"><b>One-tap fixes:</b> ${fixes}</div>` : "")
        + `<p class="help">Approximate check from sampling — a guide, not a guarantee. Slice and preview before printing.</p>`;
      if ($("#pcColor")?.checked && r.highlights) viewer?.setProblemHighlights(r.highlights);
      else viewer?.clearProblemHighlights();
    } catch (er) { box.innerHTML = `<p class="help warn">${esc(er.message)}</p>`; }
    finally { run.disabled = false; run.textContent = "Check bed fit, overhangs & thin walls"; }
  };
  box.onclick = e => {
    const b = e.target.closest("[data-pcfix]"); if (!b) return;
    const action = b.dataset.action, op = b.dataset.op;
    const fx = (E.lastCheck?.fixes || []).find(x => x.id === b.dataset.pcfix);
    if (action === "open_slicer_paint") { $("#editPrint")?.click(); return; }
    if (op && fx) doOp(op, fx.params || {}, fx.label + "…", b);
  };
  $("#pcColor")?.addEventListener("change", () => {
    if ($("#pcColor").checked && E.lastCheck?.highlights) viewer?.setProblemHighlights(E.lastCheck.highlights);
    else viewer?.clearProblemHighlights();
  });
}
function wireVolCost() {
  const run = $("#vcRun"); if (!run) return;
  run.onclick = async () => {
    run.disabled = true;
    try {
      const q = new URLSearchParams({
        material: $("#vcMat").value,
        infill_pct: $("#vcInfill").value,
        price_per_kg: $("#vcPrice").value,
      });
      const r = await api(`/api/edit/${E.p.id}/volcost?` + q);
      $("#vcBox").innerHTML = r.ok
        ? `<p><b>~${r.grams} g</b> ${esc(r.material)} · ~<b>${r.cost.toFixed(2)}</b> at ${r.price_per_kg}/kg</p><p class="help">${esc(r.note)}</p>`
        : `<p class="help warn">${esc(r.error || "Could not estimate.")}</p>`;
    } catch (er) { $("#vcBox").innerHTML = `<p class="help warn">${esc(er.message)}</p>`; }
    finally { run.disabled = false; }
  };
}
function wireEditUp10() {
  E.drainPts = E.drainPts || [];
  const drainPick = $("#drainPick");
  if (drainPick) {
    drainPick.onclick = () => {
      E.drainPick = !E.drainPick; E.textPick = false; E.facePick = false; E.measure = false;
      drainPick.textContent = E.drainPick ? "Click the model… (click here to cancel)" : "Click model to place drain holes";
      $("#drainMsg").textContent = E.drainPick ? "Click where resin should drain out." : "";
      $("#drainCount").textContent = String(E.drainPts.length);
    };
    $("#drainClear").onclick = () => { E.drainPts = []; $("#drainCount").textContent = "0"; clearDrainMarks(); };
  }
  const textPick = $("#textPick");
  if (textPick) {
    textPick.onclick = () => {
      E.textPick = !E.textPick; E.drainPick = false; E.facePick = false; E.measure = false;
      textPick.textContent = E.textPick ? "Click the model… (cancel)" : "Click model for text point";
      $("#textPickMsg").textContent = E.textPick ? "Click the surface where text should sit." : "";
    };
  }
  $("#textStyleSave")?.addEventListener("click", () => {
    const f = $("form[data-form=text]"); if (!f) return;
    const name = prompt("Name this text style:", val(f, "text") || "Style");
    if (!name) return;
    let styles = [];
    try { styles = JSON.parse(localStorage.getItem("zeim_text_styles") || "[]"); } catch { styles = []; }
    styles.push({ name, text: val(f, "text"), font: val(f, "font"), mode: val(f, "mode"), height: val(f, "height"), depth: val(f, "depth"), face: val(f, "face"), rotation: val(f, "rotation"), placement: val(f, "placement"), wrap: !!(f.wrap && f.wrap.checked) });
    localStorage.setItem("zeim_text_styles", JSON.stringify(styles.slice(-20)));
    loadTextStyles();
    toast("Saved text style “" + name + "”", "ok");
  });
  $("#fontUpload")?.addEventListener("change", async e => {
    const file = e.target.files?.[0]; if (!file || !E.p) return;
    const fd = new FormData(); fd.append("file", file);
    try {
      busy(true, "Uploading font…");
      const r = await fetch(`/api/edit/${E.p.id}/fonts`, { method: "POST", body: fd, credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || j.message || "Upload failed");
      if (E.p.capabilities) E.p.capabilities.fonts = j.fonts;
      toast(j.message || "Font saved", "ok");
      renderTools();
    } catch (er) { toast(er.message, "err"); }
    finally { busy(false); e.target.value = ""; }
  });
}
let drainMarks = [];
function clearDrainMarks() {
  drainMarks.forEach(o => { viewer?.scene.remove(o); o.geometry?.dispose(); });
  drainMarks = [];
}
function markDrain(pt) {
  if (!viewer) return;
  const s = new THREE.Mesh(new THREE.SphereGeometry(Math.max(...A().size_mm) * 0.012, 12, 8), new THREE.MeshBasicMaterial({ color: 0x22d3ee, depthTest: false }));
  s.position.set(pt.x, pt.y, pt.z); s.renderOrder = 9; viewer.scene.add(s); drainMarks.push(s);
}


function wireFaceTool() {
  const load = $("#faceLoad"); if (!load) return;
  const box = $("#faceBox"), id = E.p.id, f1 = n => (+n).toFixed(1);
  load.onclick = async () => {
    load.disabled = true; load.textContent = "Looking…";
    try {
      const r = await api(`/api/edit/${id}/features`);
      if (!r.ok) { box.innerHTML = `<p class="help warn">${esc(r.reason || "Could not analyse this model.")}</p>`; return; }
      const planes = r.planes.slice(0, 30); E.planes = planes;
      if (!planes.length) { box.innerHTML = `<p class="help">No flat faces found.</p>`; return; }
      box.innerHTML = `<div class="field"><label for="faceSel">Face (largest first)</label><select id="faceSel">${planes.map((p, i) => `<option value="${i}">${i + 1}. ${f1(p.area)} mm² — facing (${p.normal.map(x => (+x).toFixed(2)).join(", ")})</option>`).join("")}</select></div>
        <button type="button" class="btn small ghost" id="facePick">Click a face on the model</button>
        <div class="grid2"><div class="field"><label for="faceMode">Do</label><select id="faceMode"><option value="add">Add (boss)</option><option value="cut">Cut (hole / pocket)</option></select></div>
        <div class="field"><label for="faceShape">Shape</label><select id="faceShape"><option value="box">Box</option><option value="cylinder">Cylinder</option><option value="polygon">Outline (typed points)</option></select></div></div>
        <div class="field" data-fs="polygon" hidden><label for="facePts">Outline points, one “u, v” pair per line (mm from the face centre, in order round the shape)</label><textarea id="facePts" rows="4" placeholder="-5, -5&#10;5, -5&#10;0, 8"></textarea></div>
        <div class="grid3t" data-fs="box"><div class="field"><label for="faceW">Width mm</label><input id="faceW" type="text" inputmode="decimal" data-num value="10"></div><div class="field"><label for="faceD">Depth mm</label><input id="faceD" type="text" inputmode="decimal" data-num value="10"></div></div>
        <div class="grid3t" data-fs="cylinder" hidden><div class="field"><label for="faceDia">Diameter mm</label><input id="faceDia" type="text" inputmode="decimal" data-num value="6"></div></div>
        <div class="grid3t"><div class="field"><label for="faceH">Height / depth mm</label><input id="faceH" type="text" inputmode="decimal" data-num value="5"></div><div class="field"><label for="faceOff">Offset along face mm</label><input id="faceOff" type="text" inputmode="decimal" data-num value="0"></div></div>
        <button type="button" class="btn small" id="faceGo">Apply</button><p class="help" id="faceMsg" role="status" aria-live="polite"></p>`;
      const sync = () => box.querySelectorAll("[data-fs]").forEach(el => { el.hidden = el.dataset.fs !== $("#faceShape").value; });
      $("#faceShape").onchange = sync; sync();
      $("#faceSel").onchange = () => markFace(planes[+$("#faceSel").value]); markFace(planes[0]);
      $("#facePick").onclick = () => { E.facePick = !E.facePick; E.measure = false; clearMeasure(); $("#facePick").textContent = E.facePick ? "Click a face on the model… (click here to cancel)" : "Click a face on the model"; $("#faceMsg").textContent = E.facePick ? "Click a flat face on the 3D model." : ""; };
      $("#faceGo").onclick = () => {
        const p = planes[+$("#faceSel").value], shape = $("#faceShape").value, dn = E.p.dims || {};
        const num = (sel) => { const v = $(sel).value.trim(); return /^\$[A-Za-z_][A-Za-z0-9_]*$/.test(v) && v.slice(1) in dn ? v : (v === "" ? NaN : +v); };   // a number, or a named dimension ($name) that exists
        const params = { shape, mode: $("#faceMode").value, plane: { normal: p.normal, point: p.origin }, height: num("#faceH"), offset: num("#faceOff") };
        if (shape === "box") { params.width = num("#faceW"); params.depth = num("#faceD"); }
        else if (shape === "polygon") {
          params.points = $("#facePts").value.split("\n").map(l => l.trim()).filter(Boolean).map(l => l.split(/[\s,;]+/).filter(Boolean).map(Number));
          if (params.points.some(q => q.length !== 2 || !q.every(Number.isFinite))) { $("#faceMsg").textContent = "Each line needs two numbers, like: 5, -3"; return; }
        } else params.diameter = num("#faceDia");
        if (![params.height, params.offset, params.width ?? 1, params.depth ?? 1, params.diameter ?? 1].every(v => typeof v === "string" || Number.isFinite(v))) { $("#faceMsg").textContent = "Enter a number, or a named dimension that exists (like $wall) for every size."; return; }
        doOp("on_face", params, "Adding to the face…", $("#faceGo"));
      };
    } catch (e) { box.innerHTML = `<p class="help warn">${esc(e.message)}</p>`; }
    finally { load.disabled = false; load.textContent = "Find faces"; }
  };
}
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
    <details class="tool smartorient" open><summary><svg class=i aria-hidden=true focusable=false><use href=#i-compass></use></svg> Smart orient</summary>
      <p class="help">Turn the model so it prints well. Lay flat puts its largest flat face on the bed; Best position picks the side with the least overhang and support.</p>
      <div class="tool-row"><button type="button" class="btn small" data-orient="lay_flat">⤓ Lay flat</button><button type="button" class="btn small" data-orient="best_orient">✦ Best position</button></div>
      <div class="tool-row"><button type="button" class="btn small ghost" data-rot="rx">+90° X</button><button type="button" class="btn small ghost" data-rot="ry">+90° Y</button><button type="button" class="btn small ghost" data-rot="rz">+90° Z</button></div>
      <p class="help" data-orient-out role="status" aria-live="polite"></p></details>
    <div class="bigtools">
      <button class="bigtool ${E.tool === "fix" ? "on" : ""}" data-big="fix"><span class="ico"><svg class=i aria-hidden=true focusable=false><use href=#i-wrench></use></svg></span><b>Fix</b><small>Repair holes &amp; flipped faces, put it on the bed</small></button>
      <button class="bigtool ${E.tool === "scale" ? "on" : ""}" data-big="scale"><span class="ico">↔</span><b>Scale</b><small>Make it bigger or smaller</small></button>
      <button class="bigtool ${E.tool === "hollow" ? "on" : ""}" data-big="hollow" ${cap.hollow ? "" : "disabled"}><span class="ico"><svg class=i aria-hidden=true focusable=false><use href=#i-hole></use></svg></span><b>Hollow</b><small>Save filament with a wall</small></button>
      <button class="bigtool ${E.tool === "base" ? "on" : ""}" data-big="base" ${cap.boolean ? "" : "disabled"}><span class="ico">▭</span><b>Add base</b><small>Flat plate for a stronger first layer</small></button>
      <button class="bigtool ${E.tool === "split" ? "on" : ""}" data-big="split" type="button" aria-pressed="${E.tool === "split" ? "true" : "false"}"><span class="ico"><svg class=i aria-hidden=true focusable=false><use href=#i-scissors></use></svg></span><b>Split to fit my printer</b><small>Cut into pieces that fit the bed (connectors Simulated)</small></button>
    </div>
    <div id="bDrawer"></div></div>`;
  const expert = `<div data-lvl="expert">
    <details class="tool smartorient" open><summary><svg class=i aria-hidden=true focusable=false><use href=#i-compass></use></svg> Smart orient</summary>
      <p class="help">Turn the model so it prints well. Lay flat puts its largest flat face on the bed; Best position picks the side with the least overhang and support.</p>
      <div class="tool-row"><button type="button" class="btn small" data-orient="lay_flat">⤓ Lay flat</button><button type="button" class="btn small" data-orient="best_orient">✦ Best position</button></div>
      <div class="tool-row"><button type="button" class="btn small ghost" data-rot="rx">+90° X</button><button type="button" class="btn small ghost" data-rot="ry">+90° Y</button><button type="button" class="btn small ghost" data-rot="rz">+90° Z</button></div>
      <p class="help" data-orient-out role="status" aria-live="polite"></p></details>
    <details class="tool" open><summary><svg class=i aria-hidden=true focusable=false><use href=#i-ruler></use></svg> Move / Rotate / Scale</summary>
      <form data-form="translate"><div class="grid3t">${lenInput("dx", 0, "Move X")}${lenInput("dy", 0, "Move Y")}${lenInput("dz", 0, "Move Z")}</div><button class="btn small">Move</button></form>
      <form data-form="rotate"><div class="grid3t">${numInput("rx", 0, "Rot X", "°")}${numInput("ry", 0, "Rot Y", "°")}${numInput("rz", 0, "Rot Z", "°")}</div>
        <div class="tool-row"><button class="btn small">Rotate</button><button type="button" class="btn small ghost" data-rot="rx">+90° X</button><button type="button" class="btn small ghost" data-rot="ry">+90° Y</button><button type="button" class="btn small ghost" data-rot="rz">+90° Z</button></div></form>
      <form data-form="scale"><div class="grid3t">${lenInput("sx", sz[0], "Size X")}${lenInput("sy", sz[1], "Size Y")}${lenInput("sz", sz[2], "Size Z")}</div>
        <div class="row"><label class="inl"><input type="checkbox" name="uniform" checked> Keep proportions</label>${numInput("pct", 100, "or percent", "%", 'style="width:90px"')}</div>
        <div class="grid2" style="margin-top:6px">
          <div class="field"><label>Scale to…</label><select name="scale_mode"><option value="manual">Manual sizes / %</option><option value="longest">Longest side</option><option value="fit_bed">Fit my bed</option><option value="volume">Target volume</option></select></div>
          ${lenInput("target_longest", Math.max(...sz), "Target longest side")}
          ${numInput("target_volume_cm3", Math.max(0.1, (a.volume_mm3/1000)).toFixed(1), "Target volume", "cm³")}
          ${numInput("bed_margin", 2, "Bed margin", "mm")}
        </div>
        <button class="btn small">Scale</button></form>
      <div class="tool-row"><button class="btn small" data-op1="mirror:x">⇋ Mirror X</button><button class="btn small" data-op1="mirror:y">⇋ Mirror Y</button><button class="btn small" data-op1="mirror:z">⇋ Mirror Z</button></div>
      <div class="tool-row"><button class="btn small" data-op1="place:drop">⤓ Drop to bed</button><button class="btn small" data-op1="place:center">◎ Center on bed</button><button class="btn small" data-op1="place:both">Both</button></div>
    </details>
    <details class="tool smartsplit" open><summary><svg class=i aria-hidden=true focusable=false><use href=#i-scissors></use></svg> Smart Split</summary>
      <p class="help">When a model is bigger than your printer bed, ZEIM cuts it into pieces that fit. Join options add magnet holes, dovetail tabs, alignment pins, or plain glue faces. Connector fit is <b>Simulated</b> until you test-print — starting sizes come from ZEIM split specs (e.g. 6×3 mm magnets).</p>
      <form data-form="smart_split">
        <div class="grid2">
          <div class="field"><label for="ssMode">How to cut</label><select name="mode" id="ssMode"><option value="auto">Auto — fit my printer bed</option><option value="manual">Manual — one cut plane</option></select></div>
          <div class="field"><label for="ssJoin">Join with</label><select name="join" id="ssJoin"><option value="glue">Plain glue faces</option><option value="magnet">Magnet holes (6×3 mm)</option><option value="dovetail">Dovetail tabs</option><option value="pin">Alignment pins</option></select></div>
        </div>
        <div class="grid2" data-ss="manual" hidden>
          <div class="field"><label for="ssAxis">Plane axis</label><select name="axis" id="ssAxis"><option value="z">Z (horizontal)</option><option value="x">X</option><option value="y">Y</option></select></div>
          ${lenInput("position", ctr[0], "Position")}
        </div>
        <div class="grid2" data-ss="magnet" hidden>
          ${numInput("magnet_diameter", 6, "Magnet Ø", "mm")}${numInput("magnet_thickness", 3, "Magnet thickness", "mm")}
          ${numInput("clearance", 0.25, "Clearance", "mm")}${numInput("count", 2, "Pockets per cut", "")}
        </div>
        <div class="grid2" data-ss="pin" hidden>
          ${numInput("pin_diameter", 4, "Pin Ø", "mm")}${numInput("engagement", 6, "Engagement", "mm")}
          ${numInput("clearance", 0.2, "Hole clearance", "mm")}${numInput("count", 2, "Pins per cut", "")}
        </div>
        <div class="grid2" data-ss="dovetail" hidden>
          ${numInput("depth", 3, "Tab depth", "mm")}${numInput("mouth_width", 8.5, "Mouth width", "mm")}
          ${numInput("root_width", 6, "Root width", "mm")}${numInput("clearance", 0.15, "Clearance", "mm")}
        </div>
        <p class="help" role="status" aria-live="polite">Uses your chosen printer (${(typeof P !== "undefined" && P.pref) ? esc((P.cat?.printers||[]).find(x=>x.id===P.pref.printer_id)?.name || P.pref.printer_id) : "Creality K1"}). Label: Simulated.</p>
        <div><button type="submit" class="btn small primary">Split</button></div>
      </form>
      <details class="tool" open><summary>Classic single-plane cut + join</summary>
        <form data-form="cut" data-ghost="cut"><div class="grid2"><div class="field"><label>Plane axis</label><select name="axis" aria-label="Cut plane axis"><option value="z">Z (horizontal)</option><option value="x">X</option><option value="y">Y</option></select></div>${lenInput("position", ctr[2], "Position")}
          <div class="field"><label>Keep</label><select name="keep" aria-label="Which side to keep"><option value="above">Above / + side</option><option value="below">Below / − side</option><option value="both" selected>Both pieces</option></select></div>${lenInput("gap", 5, "Gap between pieces")}
          <div class="field"><label>Join on cut</label><select name="join"><option value="none">None</option><option value="glue">Glue faces</option><option value="magnet">Magnet holes</option><option value="dovetail">Dovetail</option><option value="pin">Alignment pins</option></select></div>
          </div>
          <div class="grid2" data-cutjoin="magnet" hidden>
            ${numInput("magnet_diameter", 6, "Magnet Ø", "mm")}${numInput("magnet_thickness", 3, "Magnet thickness", "mm")}
            ${numInput("clearance", 0.25, "Clearance (tolerance)", "mm")}${numInput("count", 2, "Pockets", "")}
          </div>
          <div class="grid2" data-cutjoin="pin" hidden>
            ${numInput("pin_diameter", 4, "Pin Ø", "mm")}${numInput("engagement", 6, "Engagement", "mm")}
            ${numInput("clearance", 0.2, "Hole clearance", "mm")}${numInput("count", 2, "Pins", "")}
          </div>
          <div class="grid2" data-cutjoin="dovetail" hidden>
            ${numInput("depth", 3, "Tab depth", "mm")}${numInput("mouth_width", 8.5, "Mouth width", "mm")}
            ${numInput("root_width", 6, "Root width", "mm")}${numInput("clearance", 0.15, "Clearance", "mm")}
          </div>
          <label class="inl"><input type="checkbox" name="lay_flat" checked> Lay cut face flat on the bed</label>
          <p class="help">Join fit is <b>Simulated</b> until you test-print. Clearance sliders are the tolerance.</p>
          <div><button class="btn small">Cut</button></div></form>
      </details>
    </details>
    <details class="tool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-hole></use></svg> Hollow</summary>${cap.hollow ? `<form data-form="hollow"><div class="grid2">${lenInput("wall", 2, "Wall thickness")}${lenInput("drain_diameter", 3, "Drain hole Ø (0 = none)")}</div>
      <div class="row"><button type="button" class="btn small ghost" id="drainPick">Click model to place drain holes</button>
        <button type="button" class="btn small ghost" id="drainClear">Clear placed</button></div>
      <p class="help" id="drainMsg" role="status">Auto drain at the lowest cavity point if you place none. Placed: <span id="drainCount">0</span>.</p>
      <button class="btn small">Hollow</button>
      <p class="help">Distance-field method, accurate to about one voxel (reported). Thin plates/lithophanes can't be hollowed.</p></form>` : `<p class="help">Needs manifold3d + scikit-image on the server.</p>`}</details>
    <details class="tool"><summary>▭ Base / brim</summary>${cap.boolean ? `<form data-form="base"><div class="grid3t"><div class="field"><label>Shape</label><select name="style"><option value="outline">Follow outline</option><option value="rect">Rectangle</option><option value="round">Round</option></select></div>${lenInput("margin", 3, "Margin")}${lenInput("thickness", 2, "Thickness")}</div><button class="btn small">Add base</button><p class="help">Thin (0.3–0.6 mm) = brim.</p></form>` : `<p class="help">Needs manifold3d.</p>`}</details>
    <details class="tool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-cube></use></svg> Add / subtract shapes</summary>${cap.boolean ? `<form data-form="boolean" data-ghost="boolean"><div class="grid2"><div class="field"><label>Operation</label><select name="kind"><option value="difference">Subtract (cut out)</option><option value="union">Add (union)</option><option value="intersection">Keep overlap</option></select></div>
      <div class="field"><label>Shape</label><select name="shape"><option value="cylinder">Cylinder</option><option value="box">Box</option><option value="sphere">Sphere</option></select></div></div>
      <div class="grid3t" data-shape="box">${lenInput("bx", 10, "Width X")}${lenInput("by", 10, "Depth Y")}${lenInput("bz", 10, "Height Z")}</div>
      <div class="grid3t" data-shape="cylinder sphere">${lenInput("dia", 10, "Diameter")}<span data-shape="cylinder">${lenInput("h", 20, "Height")}</span><div class="field" data-shape="cylinder"><label>Axis</label><select name="axis"><option>z</option><option>x</option><option>y</option></select></div></div>
      <div class="grid3t">${lenInput("px", ctr[0], "Center X")}${lenInput("py", ctr[1], "Center Y")}${lenInput("pz", ctr[2], "Center Z")}</div><button class="btn small">Apply</button></form>` : `<p class="help">Boolean operations need manifold3d on the server.</p>`}</details>
    <details class="tool" id="faceTool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-target></use></svg> On a face (add / cut)</summary>
      <p class="help">Pick a flat face found in your model, then add a box or cylinder on it, or cut a hole or pocket into it. Faces are found from the mesh, so sizes and positions are approximate, and the spot is fixed in space (moving the model later will not carry it).</p>
      <div id="faceBox"><button type="button" class="btn small" id="faceLoad">Find faces</button></div>
    </details>
    <details class="tool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-text></use></svg> Text (emboss / deboss)</summary>${cap.boolean ? `<form data-form="text"><div class="field"><label>Text</label><input name="text" maxlength="60" value="ZEIM"></div>
      <div class="grid2"><div class="field"><label>Font</label><select name="font">${cap.fonts.map(f => `<option>${f}</option>`).join("")}</select></div>
        <div class="field"><label>Mode</label><select name="mode"><option value="emboss">Emboss (raised)</option><option value="deboss">Deboss (engraved)</option></select></div>
      ${lenInput("height", 8, "Letter height")}${lenInput("depth", 1, "Depth")}
      <div class="field"><label>Placement</label><select name="placement"><option value="face">Flat bounding-box face</option><option value="surface">On clicked surface (curved OK)</option></select></div>
      <div class="field" data-textplace="face"><label>Face</label><select name="face"><option>top</option><option>front</option><option>back</option><option>left</option><option>right</option><option>bottom</option></select></div>
      ${numInput("rotation", 0, "Rotate", "°")}${lenInput("offset_u", 0, "Shift →")}${lenInput("offset_v", 0, "Shift ↑")}
      <label class="inl" data-textplace="surface" hidden><input type="checkbox" name="wrap" checked> Wrap letters to follow the curve</label>
      </div>
      <div class="row"><button type="button" class="btn small ghost" id="textPick" data-textplace="surface" hidden>Click model for text point</button>
        <button type="button" class="btn small ghost" id="textStyleSave">Save style</button>
        <select id="textStyleLoad" aria-label="Saved text styles"><option value="">Saved styles…</option></select></div>
      <p class="help" id="textPickMsg" role="status"></p>
      <div class="field"><label>Upload custom font (.ttf / .otf)</label><input type="file" id="fontUpload" accept=".ttf,.otf,font/ttf,font/otf"></div>
      <button class="btn small">Add text</button>
      <p class="help">Surface placement puts text on the clicked point; wrap follows gentle curves (approximate).</p></form>` : `<p class="help">Needs manifold3d.</p>`}</details>
    <details class="tool"><summary>Threaded connector</summary>${cap.boolean ? `<form data-form="thread">
      <div class="grid2">
        <div class="field"><label>Do</label><select name="mode"><option value="add">Add external (stud)</option><option value="cut">Cut internal (nut / hole)</option></select></div>
        <div class="field"><label>Axis</label><select name="axis"><option value="z">Z</option><option value="x">X</option><option value="y">Y</option></select></div>
        ${numInput("diameter", 6, "Major Ø (M)", "mm")}${numInput("length", 12, "Length", "mm")}
        ${numInput("pitch", 0, "Pitch (0=auto)", "mm")}${numInput("clearance", 0.2, "Clearance", "mm")}
        ${lenInput("px", ctr[0], "Base X")}${lenInput("py", ctr[1], "Base Y")}${lenInput("pz", a.max_mm[2], "Base Z")}
      </div>
      <button class="btn small">Apply thread</button>
      <p class="help">Approximate metric thread (stacked profile). Fit is <b>Simulated</b> until you test-print.</p></form>` : `<p class="help">Needs manifold3d.</p>`}</details>
    <details class="tool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-wrench></use></svg> Repair &amp; simplify</summary>
      <form data-form="repair"><label class="inl"><input type="checkbox" name="fix_normals" checked> Fix normals</label> <label class="inl"><input type="checkbox" name="fill_holes" checked> Fill holes</label> <label class="inl"><input type="checkbox" name="remove_duplicates" checked> Remove duplicates</label> <label class="inl"><input type="checkbox" name="keep_largest"> Drop floating bits</label><div><button class="btn small">Repair</button></div></form>
      ${cap.simplify ? `<form data-form="simplify"><div class="field"><label>Keep <em><span id="keepPct">50</span>% of triangles</em></label><input type="range" name="keep_ratio" min="0.05" max="0.95" step="0.05" value="0.5"></div><button class="btn small">Simplify</button></form>` : ""}</details>
    <details class="tool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-tag></use></svg> Named dimensions</summary>
      <p class="help">Give a size a name, then type <code>$name</code> instead of a number in a step (✎ on the history). Change it here and every step using it updates.</p>
      <div class="field"><label for="dimTxt">One per line, like: wall = 2.4</label><textarea id="dimTxt" rows="3">${esc(Object.entries(E.p.dims || {}).map(([k, v]) => `${k} = ${v}`).join("\n"))}</textarea></div>
      <button class="btn small" id="dimSave" type="button">Save &amp; update model</button><p class="help" id="dimMsg" role="status" aria-live="polite"></p></details>
    <details class="tool" open><summary><svg class=i aria-hidden=true focusable=false><use href=#i-check></use></svg> Print check &amp; cost</summary>
      <div class="grid2"><div class="field"><label for="pcProc">Process</label><select id="pcProc"><option value="fdm">FDM (filament)</option><option value="resin">Resin</option></select></div></div>
      <button class="btn small" id="pcRun" type="button">Check bed fit, overhangs &amp; thin walls</button>
      <label class="inl"><input type="checkbox" id="pcColor" checked> Colour problems on the model</label>
      <div id="pcBox" aria-live="polite"></div>
      <hr>
      <div class="grid2">
        <div class="field"><label for="vcMat">Material</label><select id="vcMat"><option>PLA</option><option>PETG</option><option>TPU</option><option>ABS</option><option>ASA</option><option>PC</option><option>PVA</option></select></div>
        <div class="field"><label for="vcInfill">Infill %</label><input id="vcInfill" type="number" value="20" min="0" max="100" step="1"></div>
        <div class="field"><label for="vcPrice">Price / kg</label><input id="vcPrice" type="number" value="20" min="0" step="0.5"></div>
      </div>
      <button class="btn small" id="vcRun" type="button">Estimate material &amp; cost from volume</button>
      <div id="vcBox" aria-live="polite"></div>
    </details>
    <details class="tool"><summary><svg class=i aria-hidden=true focusable=false><use href=#i-ruler></use></svg> Measure &amp; info</summary>
      <button class="btn small" id="toggleMeasure">${E.measure ? "Stop measuring" : "Measure two points"}</button>
      <table class="info-table"><tr><td>Size (${E.unit})</td><td>${sz.map(fmt).join(" × ")}</td></tr><tr><td>Volume</td><td>${(a.volume_mm3 / 1000).toFixed(2)} cm³</td></tr><tr><td>Surface area</td><td>${(a.area_mm2 / 100).toFixed(1)} cm²</td></tr>
      <tr><td>Triangles</td><td>${a.triangles.toLocaleString()}</td></tr><tr><td>Watertight</td><td>${a.watertight ? "yes" : "no"} (open edges: ${a.boundary_edges}, non-manifold: ${a.nonmanifold_edges})</td></tr>
      <tr><td>Pieces</td><td>${a.components ?? "n/a"}</td></tr><tr><td>Bounds min</td><td>${a.min_mm.map(fmt).join(", ")}</td></tr><tr><td>Bounds max</td><td>${a.max_mm.map(fmt).join(", ")}</td></tr><tr><td>Centre of mass</td><td>${a.center_of_mass_mm.map(fmt).join(", ")}</td></tr></table></details>
  </div>`;
  const plateHTML = renderPlate({ p: E.p, viewer, doOp, measuring: () => E.measure });
  $("#editPanel").innerHTML = unitSel + plateHTML + `<p class="sr-only" id="plateLive" aria-live="polite"></p>` + beginner + expert + `<button class="btn ghost small" id="editClose" style="margin-top:8px">＋ Open another model</button>`;
  if (E.tool && !isExpert()) renderDrawer();
  syncShapeFields();
  syncSmartSplit();
  syncCutJoin();
  syncTextPlace();
  loadTextStyles();
  wireFaceTool();
  wirePrintCheck();
  wireVolCost();
  wireEditUp10();
  wireDims();
  document.dispatchEvent(new CustomEvent("zeim:edit-loaded"));
}
wirePlatePanel($("#editPanel"));
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
  const ori = e.target.closest("[data-orient]");
  if (ori) { e.preventDefault(); return doOp(ori.dataset.orient, {}).then(() => { const r = E.p?.report || {}; $$("[data-orient-out]").forEach(x => x.textContent = r.message || (ori.dataset.orient === "lay_flat" ? "Laid flat." : "Turned to the best position.")); }); }
  const rot = e.target.closest("[data-rot]"); if (rot) { e.preventDefault(); return doOp("rotate", { rx: 0, ry: 0, rz: 0, [rot.dataset.rot]: 90 }); }
  if (e.target.id === "toggleMeasure") toggleMeasure();
  if (e.target.id === "editClose") { E.p = null; $("#editStart").hidden = false; $("#editPanel").hidden = true; $("#editResult").hidden = true; $("#editVtools").hidden = true; $("#editEmpty").hidden = false; viewer?.group.clear(); clearGhost(); clearFaceMark(); fillBuildSelect(); }
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
$("#editPanel").addEventListener("change", e => { const f = e.target.form; if (f?.dataset.form === "cut" && e.target.name === "axis") { const i = { x: 0, y: 1, z: 2 }[e.target.value]; f.position.value = fmt(A().center_mm[i]); } if (f?.dataset.form === "cut") syncCutJoin(f); if (f?.dataset.form === "text") syncTextPlace(f); if (f?.dataset.form === "smart_split") syncSmartSplit(f); if (f?.dataset.form === "boolean") syncShapeFields(); if (f?.dataset.ghost) updateGhost(f); if (e.target.id === "textStyleLoad" && e.target.value !== "") { const st = e.target._styles?.[+e.target.value]; const tf = $("form[data-form=text]"); if (st && tf) { for (const k of ["text","font","mode","height","depth","face","rotation","placement"]) if (st[k] != null && tf[k]) tf[k].value = st[k]; if (tf.wrap && st.wrap != null) tf.wrap.checked = !!st.wrap; syncTextPlace(tf); } } });
function syncSmartSplit(f) {
  if (!f) f = $("form[data-form=smart_split]"); if (!f) return;
  const mode = val(f, "mode") || "auto", join = val(f, "join") || "glue";
  $$("[data-ss]", f).forEach(el => {
    const keys = el.dataset.ss.split(" ");
    if (keys.includes("manual")) el.hidden = mode !== "manual";
    else el.hidden = !keys.includes(join);
  });
}
function syncCutJoin(f) {
  if (!f) f = $("form[data-form=cut]"); if (!f) return;
  const join = val(f, "join") || "none";
  $$("[data-cutjoin]", f).forEach(el => { el.hidden = el.dataset.cutjoin !== join; });
}
function syncTextPlace(f) {
  if (!f) f = $("form[data-form=text]"); if (!f) return;
  const pl = val(f, "placement") || "face";
  $$("[data-textplace]", f).forEach(el => { el.hidden = el.dataset.textplace !== pl; });
}
function loadTextStyles() {
  const sel = $("#textStyleLoad"); if (!sel) return;
  let styles = [];
  try { styles = JSON.parse(localStorage.getItem("zeim_text_styles") || "[]"); } catch { styles = []; }
  sel.innerHTML = `<option value="">Saved styles…</option>` + styles.map((s, i) => `<option value="${i}">${esc(s.name || ("Style " + (i + 1)))}</option>`).join("");
  sel._styles = styles;
}
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
    scale: () => {
      const sz = A().size_mm, mode = val(f, "scale_mode") || "manual";
      if (mode === "longest") return { mode: "longest", target_longest: len(f, "target_longest"), pivot: "base" };
      if (mode === "fit_bed") {
        const bed = (typeof window.P !== "undefined" && window.P.pref && window.P.cat)
          ? (window.P.cat.printers || []).find(x => x.id === window.P.pref.printer_id)?.bed_mm
          : null;
        return { mode: "fit_bed", bed: bed || [220, 220, 250], margin: +val(f, "bed_margin") || 2, pivot: "base" };
      }
      if (mode === "volume") return { mode: "volume", target_volume_cm3: +val(f, "target_volume_cm3"), pivot: "base" };
      return { sx: len(f, "sx") / sz[0], sy: len(f, "sy") / sz[1], sz: len(f, "sz") / sz[2], pivot: "base" };
    },
    cut: () => {
      const join = val(f, "join") || "none";
      const o = { axis: val(f, "axis"), position: len(f, "position"), keep: val(f, "keep"), lay_flat: f.lay_flat.checked, gap: len(f, "gap") };
      if (join && join !== "none") {
        o.join = join;
        if (join === "magnet") { o.magnet_diameter = +val(f, "magnet_diameter"); o.magnet_thickness = +val(f, "magnet_thickness"); o.clearance = +val(f, "clearance"); o.count = +val(f, "count"); }
        if (join === "pin") { o.pin_diameter = +val(f, "pin_diameter"); o.engagement = +val(f, "engagement"); o.clearance = +val(f, "clearance"); o.count = +val(f, "count"); }
        if (join === "dovetail") { o.depth = +val(f, "depth"); o.mouth_width = +val(f, "mouth_width"); o.root_width = +val(f, "root_width"); o.clearance = +val(f, "clearance"); }
      }
      return o;
    },
    smart_split: () => {
      const join = val(f, "join") || "glue", mode = val(f, "mode") || "auto";
      const o = { mode, join, printer_id: (typeof window.P !== "undefined" && window.P.pref) ? window.P.pref.printer_id : undefined, gap: 5 };
      if (mode === "manual") { o.axis = val(f, "axis"); o.position = len(f, "position"); }
      if (join === "magnet") { o.magnet_diameter = +val(f, "magnet_diameter"); o.magnet_thickness = +val(f, "magnet_thickness"); o.clearance = +val(f, "clearance"); o.count = +val(f, "count"); }
      if (join === "pin") { o.pin_diameter = +val(f, "pin_diameter"); o.engagement = +val(f, "engagement"); o.clearance = +val(f, "clearance"); o.count = +val(f, "count"); }
      if (join === "dovetail") { o.depth = +val(f, "depth"); o.mouth_width = +val(f, "mouth_width"); o.root_width = +val(f, "root_width"); o.clearance = +val(f, "clearance"); }
      return o;
    },
    hollow: () => {
      const o = { wall: len(f, "wall"), drain_diameter: len(f, "drain_diameter") };
      if (E.drainPts && E.drainPts.length) o.drain_points = E.drainPts.map(p => ({ x: p.x, y: p.y, z: p.z, diameter: o.drain_diameter || 3 }));
      return o;
    },
    base: () => ({ style: val(f, "style"), margin: len(f, "margin"), thickness: len(f, "thickness") }),
    boolean: () => ({ kind: val(f, "kind"), primitive: primSpec(f) }),
    text: () => {
      const o = { text: val(f, "text"), font: val(f, "font"), mode: val(f, "mode"), height: len(f, "height"), depth: len(f, "depth"), rotation: +val(f, "rotation"), offset_u: len(f, "offset_u"), offset_v: len(f, "offset_v"), placement: val(f, "placement") || "face" };
      if (o.placement === "face") o.face = val(f, "face");
      else {
        if (!E.textPt) { toast("Click a point on the model for surface text first.", "err"); return null; }
        o.point = E.textPt.point; o.normal = E.textPt.normal;
        o.wrap = !!(f.wrap && f.wrap.checked);
      }
      return o;
    },
    thread: () => ({ mode: val(f, "mode"), axis: val(f, "axis"), diameter: +val(f, "diameter"), length: +val(f, "length"), pitch: +val(f, "pitch") || 0, clearance: +val(f, "clearance"), position: [len(f, "px"), len(f, "py"), len(f, "pz")] }),
    repair: () => ({ fix_normals: f.fix_normals.checked, fill_holes: f.fill_holes.checked, remove_duplicates: f.remove_duplicates.checked, keep_largest: f.keep_largest.checked }),
    simplify: () => ({ keep_ratio: +val(f, "keep_ratio") }),
  }[kind];
  if (!P) return;
  const params = P();
  if (params == null) return;
  clearGhost();
  doOp(kind, params, ({ hollow: "Hollowing…", boolean: "Computing boolean…", text: "Building text…", base: "Adding base…", simplify: "Simplifying…", smart_split: "Smart Split…", thread: "Building thread…", cut: "Cutting…" })[kind], f.querySelector("button:not([type=button])"));
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
  if (t === "split") {
    const pname = (typeof P !== "undefined" && P.pref) ? ((P.cat?.printers || []).find(x => x.id === P.pref.printer_id)?.name || "your printer") : "your printer";
    d.innerHTML = `<div class="tooldrawer"><b>Split to fit my printer</b>
      <p class="help">Cuts this model into pieces that fit <em>${esc(pname)}</em>. Join faces are plain glue faces (Experienced mode has magnets, dovetails and pins). Connector fit is <b>Simulated</b> until you test-print.</p>
      <button type="button" class="btn primary small" id="bSplitGo">Split to fit my printer</button>
      <p class="help" id="bSplitOut" role="status" aria-live="polite"></p></div>`;
  }
}
$("#editPanel").addEventListener("click", e => {
  const id = e.target.id, d = e.target.closest("[data-pct]");
  if (d) { const k = +d.dataset.pct / 100; doOp("scale", { factor: k, pivot: "base" }); E.tool = null; }
  if (id === "bScaleGo") { const k = (+$("#bLong").value * U()) / Math.max(...A().size_mm); if (k > 0) doOp("scale", { factor: k, pivot: "base" }); E.tool = null; }
  if (e.target.closest("#bWall button")) { $$("#bWall button").forEach(b => b.classList.toggle("on", b === e.target.closest("button"))); }
  if (id === "bHollowGo") { const w = +($("#bWall .on")?.dataset.w || 2); doOp("hollow", { wall: w, drain_diameter: $("#bDrain").checked ? 3 : 0 }, "Hollowing…"); E.tool = null; }
  if (id === "bBaseGo") { doOp("base", { style: "outline", margin: 3, thickness: 2 }, "Adding base…"); E.tool = null; }
  if (id === "bSplitGo") {
    const pid = (typeof P !== "undefined" && P.pref) ? P.pref.printer_id : undefined;
    doOp("smart_split", { mode: "auto", join: "glue", printer_id: pid, gap: 5 }, "Smart Split…").then(() => {
      const r = E.p?.report || {};
      const out = $("#bSplitOut"); if (out) out.textContent = r.message || "Split done.";
    });
    E.tool = null;
  }
});

/* ---------- ghost previews (cut plane / boolean tool) ---------- */
let faceMark = null;
function clearFaceMark() { if (faceMark) { viewer?.scene.remove(faceMark); faceMark.geometry.dispose(); faceMark = null; } }
function markFace(p) {                                      // a translucent disc on the chosen face plane (area-equivalent size): a visual cue only
  clearFaceMark(); if (!viewer || !p) return;
  const n = new THREE.Vector3(...p.normal).normalize(), r = Math.sqrt(Math.max(p.area, 1) / Math.PI) * 0.6;
  const g = new THREE.CircleGeometry(r, 40), m = new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.45, side: THREE.DoubleSide, depthTest: false });
  faceMark = new THREE.Mesh(g, m); faceMark.renderOrder = 8;
  faceMark.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
  faceMark.position.set(...p.origin).addScaledVector(n, 0.05); viewer.scene.add(faceMark);
}
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
function pickFace(e) {
  const r = viewer.renderer.domElement.getBoundingClientRect(), ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const rc = new THREE.Raycaster(); rc.setFromCamera(ndc, viewer.camera);
  const hit = rc.intersectObjects(viewer.group.children, false)[0], msg = $("#faceMsg"); if (!hit || !hit.face || !msg) return;
  const n = hit.face.normal.clone().transformDirection(hit.object.matrixWorld), tol = Math.max(...A().size_mm) * 0.01;
  let best = -1, bestD = Infinity;
  (E.planes || []).forEach((p, i) => {                       // same plane = same direction and the click lies on it (detected on the server; approximate)
    const pn = new THREE.Vector3(...p.normal), d = Math.abs(hit.point.clone().sub(new THREE.Vector3(...p.origin)).dot(pn));
    if (pn.dot(n) > Math.cos(Math.PI * 3 / 180) && d < tol && d < bestD) { best = i; bestD = d; }
  });
  if (best < 0) { msg.textContent = "That spot isn't on a detected flat face. Try another, or choose from the list."; return; }
  $("#faceSel").value = best; markFace(E.planes[best]); E.facePick = false; $("#facePick").textContent = "Click a face on the model";
  msg.textContent = `Picked face ${best + 1}. Set the sizes and press Apply.`;
}
function onPick(e) {
  if (E.facePick && viewer) return pickFace(e);
  if ((E.drainPick || E.textPick) && viewer) {
    const r = viewer.renderer.domElement.getBoundingClientRect(), ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const rc = new THREE.Raycaster(); rc.setFromCamera(ndc, viewer.camera);
    const hit = rc.intersectObjects(viewer.group.children, false)[0]; if (!hit || !hit.face) return;
    const n = hit.face.normal.clone().transformDirection(hit.object.matrixWorld).normalize();
    const pt = { x: hit.point.x, y: hit.point.y, z: hit.point.z };
    if (E.drainPick) {
      E.drainPts = E.drainPts || [];
      E.drainPts.push(pt); markDrain(pt);
      $("#drainCount").textContent = String(E.drainPts.length);
      $("#drainMsg").textContent = `Placed ${E.drainPts.length} drain hole(s). Click more or Hollow.`;
      return;
    }
    if (E.textPick) {
      E.textPt = { point: [pt.x, pt.y, pt.z], normal: [n.x, n.y, n.z] };
      E.textPick = false;
      const btn = $("#textPick"); if (btn) btn.textContent = "Click model for text point";
      $("#textPickMsg").textContent = `Text point set at (${pt.x.toFixed(1)}, ${pt.y.toFixed(1)}, ${pt.z.toFixed(1)}).`;
      return;
    }
  }
  if (!E.measure && viewer) return pickAt(e);           // plate editor: select / shift-select objects
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

/* CAD workspace hand-off: /?edit=<project id>#slicer opens that project here (Slicer + plate editor). */
{ const id = new URLSearchParams(location.search).get("edit");
  if (id && /^[0-9a-f]{12}$/.test(id)) { location.hash = "slicer"; setTimeout(() => document.dispatchEvent(new CustomEvent("zeim:open-edit", { detail: id })), 0); } }
