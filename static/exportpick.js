/* One export picker for every workspace (Studio, Slicer, CAD, TorchC0).
   - Formats come from /api/export/formats, each with a one-line description. STEP is only offered with a true solid
     (never at the moment: ZEIM models are meshes) and the picker says why.
   - Remembers the last format per workspace (localStorage "zeim.exportfmt.<workspace>").
   - File name defaults to "Title - Printer - 0.2mm"; one tap on Rename edits it. Names are made safe on the server
     for Windows, Mac and phones; the same rules run here so the preview matches.
   Usage: zeimExport.open({ ws: "studio", bid }) or zeimExport.open({ ws: "torchc0", rid, name }). */
const FALLBACK = [
  { id: "stl", label: "STL", desc: "Works in every slicer. Shape only, no colour or units." },
  { id: "3mf", label: "3MF", desc: "Modern slicer format: keeps millimetres and placement. Best for Bambu, Orca, Prusa, Cura." },
  { id: "obj", label: "OBJ", desc: "Common 3D format for Blender and other 3D apps." },
  { id: "ply", label: "PLY", desc: "Mesh format used by 3D scanning and mesh tools like MeshLab." },
  { id: "glb", label: "GLB (glTF)", desc: "One-file glTF for the web, AR and game engines." },
  { id: "amf", label: "AMF", desc: "Older XML print format, still read by PrusaSlicer and Cura." }];
let FORMATS = null, STEPNOTE = "STEP is not offered: it needs a true solid (B-rep), and ZEIM models are triangle meshes.";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { return null; } };
export function safeName(n) {
  let s = String(n ?? "").normalize("NFC").replace(/[<>:"/\\|?*\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]/g, " ")
    .replace(/\s+/g, " ").trim().replace(/^\.+/, "").replace(/[. ]+$/, "");
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(s.split(".")[0].trim())) s = "_" + s;
  if (s.length > 120) s = s.slice(0, 120).replace(/[. ]+$/, "");
  return s || "ZEIM model";
}
async function formats() {
  if (FORMATS) return FORMATS;
  try { const j = await (await fetch("/api/export/formats", { credentials: "same-origin" })).json(); FORMATS = j.formats; if (j.step_note) STEPNOTE = j.step_note; }
  catch { FORMATS = FALLBACK; }
  return FORMATS;
}
function dlg() {
  let d = document.getElementById("dlgExport"); if (d) return d;
  d = document.createElement("dialog"); d.id = "dlgExport"; d.className = "exportdlg"; d.setAttribute("aria-labelledby", "expH");
  d.innerHTML = `<form method="dialog" class="exportform">
    <h2 id="expH">Export</h2>
    <div class="expname"><span class="help">File name</span>
      <div class="row"><output id="expNameOut"></output><button type="button" class="btn small" id="expRename" aria-controls="expName">Rename</button></div>
      <div class="row" id="expNameRow" hidden><label for="expName" class="sr-only">File name</label><input id="expName" maxlength="160" autocomplete="off" spellcheck="false"><button type="button" class="btn small" id="expNameOk">Done</button><button type="button" class="btn small ghost" id="expNameReset">Default</button></div>
      <p class="help" id="expNameHelp">Safe on Windows, Mac and phones.</p></div>
    <fieldset class="expfmts"><legend>Format</legend><div id="expList"></div></fieldset>
    <p class="help" id="expStep"></p>
    <p class="help" id="expMsg" role="status" aria-live="polite"></p>
    <div class="row end"><button type="button" class="btn ghost" id="expCancel">Close</button><a class="btn primary" id="expGo" href="#" download>Download</a></div></form>`;
  document.body.appendChild(d);
  d.querySelector("#expCancel").onclick = () => d.close();
  d.querySelector("form").addEventListener("submit", e => e.preventDefault());
  return d;
}
export async function open(o) {
  const d = dlg(), ws = o.ws || "studio", list = await formats();
  let fmt = ls("zeim.exportfmt." + ws); if (!list.some(f => f.id === fmt)) fmt = o.defaultFormat || "3mf";
  let name = o.name || "", def = o.name || "ZEIM model";
  if (o.bid) {
    try { const j = await (await fetch(`/api/export/${encodeURIComponent(o.bid)}`, { credentials: "same-origin" })).json(); name = j.name || name; def = j.default_name || def; }
    catch { }
  }
  name = safeName(name || def);
  const $ = s => d.querySelector(s);
  $("#expH").textContent = o.heading || "Export";
  $("#expList").innerHTML = list.map(f => `<label class="radrow expfmt"><input type="radio" name="expFmt" value="${esc(f.id)}" ${f.id === fmt ? "checked" : ""}><span><b>${esc(f.label)}</b> <small>${esc(f.desc)}</small></span></label>`).join("");
  $("#expStep").textContent = STEPNOTE;
  $("#expMsg").textContent = "";
  const url = () => {
    const f = d.querySelector("input[name=expFmt]:checked")?.value || "3mf";
    return o.rid ? `/api/resin/${o.rid}/torchc0.${f}?name=${encodeURIComponent(name)}`
      : `/api/export/${encodeURIComponent(o.bid)}/download?format=${f}&name=${encodeURIComponent(name)}`;
  };
  const paint = () => {
    const f = d.querySelector("input[name=expFmt]:checked")?.value || "3mf";
    $("#expNameOut").textContent = name + "." + f; const go = $("#expGo"); go.href = url(); go.setAttribute("download", name + "." + f);
    go.textContent = "Download " + (list.find(x => x.id === f)?.label || f.toUpperCase());
  };
  const editing = on => { $("#expNameRow").hidden = !on; $("#expRename").hidden = on; if (on) { $("#expName").value = name; $("#expName").focus(); $("#expName").select(); } };
  const commit = async (v) => {
    name = safeName(v); editing(false); paint();
    if (o.bid) {
      try { const r = await fetch(`/api/export/${encodeURIComponent(o.bid)}/name`, { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: v === def ? "" : name }) });
        const j = await r.json(); if (!r.ok) { $("#expMsg").textContent = j.detail || "Could not rename."; return; } name = j.name; paint(); $("#expMsg").textContent = "Renamed. Back up all uses this name too."; }
      catch { }
    }
  };
  $("#expRename").onclick = () => editing(true);
  $("#expNameOk").onclick = () => commit($("#expName").value);
  $("#expNameReset").onclick = () => commit(def);
  $("#expName").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); commit($("#expName").value); } else if (e.key === "Escape") { e.preventDefault(); editing(false); } };
  $("#expName").oninput = () => { $("#expNameHelp").textContent = "Will save as: " + safeName($("#expName").value) + ". Safe on Windows, Mac and phones."; };
  $("#expList").onchange = e => { if (e.target.name === "expFmt") { ls("zeim.exportfmt." + ws, e.target.value); paint(); } };
  $("#expGo").onclick = () => { ls("zeim.exportfmt." + ws, d.querySelector("input[name=expFmt]:checked")?.value || "3mf"); $("#expMsg").textContent = "Downloading…"; };
  editing(false); paint();
  if (!d.open) d.showModal();
  return d;
}
const ICON = '<svg class="i" aria-hidden="true" focusable="false"><use href="#i-download"></use></svg>';
function addBtn(after, id, ws, getBid) {
  const a = document.getElementById(after); if (!a || document.getElementById(id)) return;
  const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.id = id; b.setAttribute("aria-haspopup", "dialog");
  b.title = "Download in a format you pick (STL, 3MF, OBJ, PLY, GLB, AMF)"; b.innerHTML = ICON + " Export…";
  b.onclick = () => { const bid = getBid(); if (!bid) return; open({ ws, bid }); };
  a.after(b);
}
function wire() {
  addBtn("btnSendSheet", "studioExport", "studio", () => window.__photo3d?.current?.id);
  addBtn("editSend", "editExport", "slicer", () => window.__zeimEdit?.p?.id);
  const cw = document.getElementById("cwPick");
  if (cw) cw.addEventListener("click", e => { e.preventDefault(); const m = document.getElementById("cwExportMenu"); if (m) m.hidden = true;
    const bid = window.__cad?.S?.bid; if (!bid) return; open({ ws: "cad", bid }); });
  document.addEventListener("click", e => {       // TorchC0 result: <button data-export-rid data-export-name>
    const b = e.target.closest?.("[data-export-rid]"); if (!b) return; e.preventDefault();
    open({ ws: "torchc0", rid: b.dataset.exportRid, name: b.dataset.exportName, heading: "Export resin model" });
  });
}
window.zeimExport = { open, safeName };
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire); else wire();
