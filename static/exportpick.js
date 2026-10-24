/* One export picker for every workspace (Studio, Slicer, CAD, TorchC0).
   - Formats come from /api/export/formats, each with a one-line description. STEP is only offered with a true solid
     (never at the moment: ZEIM models are meshes) and the picker says why.
   - Remembers the last format per workspace (localStorage "zeim.exportfmt.<workspace>").
   - File name defaults to "Title - Printer - 0.2mm"; one tap on Rename edits it. Names are made safe on the server
     for Windows, Mac and phones; the same rules run here so the preview matches.
   Filament slots / multi-head controls are NOT here — they belong only in the FDM Slicer panel.
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
    <fieldset class="expslots" id="expSlots" hidden><legend>Filament slots (CFS / AMS)</legend>
      <p class="help" id="expSlotsHelp">Use one slot: only the slots you tick go in the file. Empty slots are never checked.</p>
      <div class="row" id="expSlotList">${[1, 2, 3, 4].map(n => `<label class="slotchk"><input type="checkbox" name="expSlot" value="${n}" ${n === 1 ? "checked" : ""}><span>Slot ${n}</span></label>`).join("")}</div>
      <div class="expwarn" id="expSlotWarn" role="status" hidden><span id="expSlotWarnT"></span> <button type="button" class="btn small ghost" id="expSlotWarnOk">Continue</button></div></fieldset>
    <fieldset class="expparts" id="expParts" hidden><legend>Parts</legend>
      <p class="help">This build has more than one piece. Download them together or one at a time.</p>
      <div id="expPartList"></div></fieldset>
    <fieldset class="exppreset" id="expPreset" hidden><legend>Print settings</legend>
      <label class="inl"><input type="checkbox" id="expPresetOn"> <span id="expPresetL"></span></label>
      <p class="help" id="expPresetD"></p><p class="help" id="expPresetN"></p></fieldset>
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
  let name = o.name || "", def = o.name || "ZEIM model", colours = 0, presets = [], parts = [];
  if (o.bid) {
    try { const j = await (await fetch(`/api/export/${encodeURIComponent(o.bid)}`, { credentials: "same-origin" })).json(); name = j.name || name; def = j.default_name || def; colours = j.colour_count || 0; presets = j.print_presets || []; parts = j.parts || []; }
    catch { }
  }
  name = safeName(name || def);
  const $ = s => d.querySelector(s);
  $("#expH").textContent = o.heading || "Export";
  $("#expList").innerHTML = list.map(f => `<label class="radrow expfmt"><input type="radio" name="expFmt" value="${esc(f.id)}" ${f.id === fmt ? "checked" : ""}><span><b>${esc(f.label)}</b> <small>${esc(f.desc)}</small></span></label>`).join("");
  $("#expStep").textContent = STEPNOTE;
  const pr = presets[0];                                    // lithophanes: optional Bambu print settings inside the 3MF
  if (pr) { $("#expPresetL").textContent = pr.label; $("#expPresetD").textContent = pr.desc; $("#expPresetN").textContent = pr.note;
    const sv = ls("zeim.exportpreset." + ws); $("#expPresetOn").checked = sv == null ? !!pr.suggested : sv === pr.id; }
  $("#expPresetOn").onchange = () => { ls("zeim.exportpreset." + ws, $("#expPresetOn").checked ? pr.id : ""); paint(); };
  const preset = () => pr && $("#expPresetOn").checked && (d.querySelector("input[name=expFmt]:checked")?.value || "3mf") === "3mf" ? pr.id : "";
  $("#expParts").hidden = parts.length < 2;
  $("#expPartList").innerHTML = parts.map((p, i) => `<label class="radrow"><input type="radio" name="expPart" value="${esc(p.id)}" ${i === 0 ? "checked" : ""}><span>${esc(p.label)}</span></label>`).join("");
  const part = () => parts.length >= 2 ? (d.querySelector("input[name=expPart]:checked")?.value || "") : "";
  $("#expMsg").textContent = "";
  // Multi-head / slot pickers live only in the FDM Slicer panel. Studio/Lithophane/CAD/TorchC0 exports use Slot 1.
  $("#expSlots").hidden = true;
  d.querySelectorAll("input[name=expSlot]").forEach(c => { c.checked = c.value === "1"; });
  const slots = () => [1];
  let warnOff = false;
  const slotWarn = () => {
    const s = slots(), need = Math.max(1, colours); let t = "";
    if (s.length > need) t = `This model has ${need === 1 ? "one colour" : need + " colours"}, so only slot ${s.slice(0, need).join(", ")} will be used. The others are left out of the file.`;
    else if (s.length < need) t = `This model has ${need} colours but you picked ${s.length} slot${s.length > 1 ? "s" : ""}. Extra colours print from slot ${s[s.length - 1]}.`;
    $("#expSlotWarnT").textContent = t; $("#expSlotWarn").hidden = !t || warnOff;
  };
  $("#expSlotsHelp").textContent = colours > 1
    ? `This model has ${colours} colours. Tick one slot per colour, or keep one slot to print it in a single colour.`
    : "Use one slot: only the slot you tick goes in the file. Unused slots are never checked or mapped.";
  $("#expSlotWarnOk").onclick = () => { warnOff = true; $("#expSlotWarn").hidden = true; };
  const url = () => {
    const f = d.querySelector("input[name=expFmt]:checked")?.value || "3mf";
    if (!o.rid) return `/api/export/${encodeURIComponent(o.bid)}/download?format=${f}&name=${encodeURIComponent(name)}&slots=${slots().join(",")}`
      + (preset() ? `&preset=${preset()}` : "") + (part() ? `&part=${encodeURIComponent(part())}` : "");
    return o.rid ? `/api/resin/${o.rid}/torchc0.${f}?name=${encodeURIComponent(name)}`
      : `/api/export/${encodeURIComponent(o.bid)}/download?format=${f}&name=${encodeURIComponent(name)}`;
  };
  const paint = () => {
    const f = d.querySelector("input[name=expFmt]:checked")?.value || "3mf";
    $("#expPreset").hidden = !pr || f !== "3mf";
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
  $("#expSlotList").onchange = () => { warnOff = false; slotWarn(); paint(); };
  $("#expList").onchange = e => { if (e.target.name === "expFmt") { ls("zeim.exportfmt." + ws, e.target.value); paint(); } };
  $("#expPartList").onchange = () => paint();
  $("#expGo").onclick = () => { ls("zeim.exportfmt." + ws, d.querySelector("input[name=expFmt]:checked")?.value || "3mf"); $("#expMsg").textContent = "Downloading…"; };
  editing(false); slotWarn(); paint();
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
