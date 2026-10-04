import { Viewer } from "/static/viewer.js";

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const S = { mode: "lithophane", level: localStorage.level || "beginner", preset: "standard", file: null,
            current: null, history: [], max: 5, settings: null };
const PRESET_HELP = {
  lithophane: { thin: "Lighter, glows brighter, more fragile (0.6–2.4 mm).", standard: "Balanced contrast and strength (0.8–3.2 mm).", thick: "Deep shadows, sturdy (1.0–4.0 mm)." },
  relief: { thin: "Shallow, subtle relief (≈4% of width).", standard: "Clear depth (≈7% of width).", thick: "Dramatic depth (≈11% of width)." },
  popart: { thin: "3 colour layers, small steps.", standard: "4 colour layers, medium steps.", thick: "5 colour layers, tall steps." } };

function toast(msg, kind = "") {
  const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg;
  $("#toasts").append(t); setTimeout(() => t.remove(), kind === "err" ? 8000 : 4500);
}
const api = async (url, opt) => {
  const r = await fetch(url, opt); let j = null;
  try { j = await r.json(); } catch { }
  if (!r.ok) { const e = new Error(j?.detail || j?.message || r.statusText); e.status = r.status; e.body = j; throw e; }
  return j;
};
const ago = iso => { const s = (Date.now() - new Date(iso)) / 1000; return s < 60 ? "just now" : s < 3600 ? Math.floor(s / 60) + " min ago" : s < 86400 ? Math.floor(s / 3600) + " h ago" : new Date(iso).toLocaleDateString(); };
const MODE_LABEL = { lithophane: "Lithophane", relief: "Relief", popart: "Pop-art", edit: "Edited model" };

let viewer;
try { viewer = new Viewer($("#viewer")); } catch (e) { console.warn("WebGL unavailable", e); }

/* ---------- level / mode ---------- */
function applyLevel() {
  localStorage.level = S.level;
  document.body.dataset.level = S.level;
  document.dispatchEvent(new CustomEvent("zeim:level"));
  $$("#levelSwitch button").forEach(b => b.classList.toggle("on", b.dataset.level === S.level));
  $("#beginnerOpts").hidden = S.level !== "beginner";
  $("#expertOpts").hidden = S.level !== "expert";
}
function applyMode() {
  $$("#modeCards .card").forEach(c => c.classList.toggle("on", c.dataset.mode === S.mode));
  $$("#expertOpts [data-modes]").forEach(e => e.hidden = !e.dataset.modes.split(" ").includes(S.mode));
  $("#presetHelp").textContent = PRESET_HELP[S.mode][S.preset];
}
$$("#levelSwitch button").forEach(b => b.onclick = () => { S.level = b.dataset.level; applyLevel(); });
$$("#modeCards .card").forEach(c => c.onclick = () => { S.mode = c.dataset.mode; applyMode(); });
$$("#presetSeg button").forEach(b => b.onclick = () => { S.preset = b.dataset.preset; $$("#presetSeg button").forEach(x => x.classList.toggle("on", x === b)); applyMode(); });
$("#widthRange").oninput = e => $("#width_mm").value = e.target.value;
$("#width_mm").oninput = e => $("#widthRange").value = e.target.value;

/* ---------- file ---------- */
import { photoBlock, mountPhoto } from "/static/photo.js";
$("#studioPhoto").innerHTML = photoBlock("s");
const pick = mountPhoto("s", f => setFile(f));
const MAX_PHOTO = 25 * 1024 * 1024;
function setFile(f) {
  if (!f) return;
  if (f.size > MAX_PHOTO) { pick.msg("That photo is over 25 MB. Try a smaller one (JPG or PNG)."); return; }
  if (!f.size) { pick.msg("We couldn't open that photo. Try a JPG or PNG."); return; }
  S.file = f; S.pending = null;
  const img = $("#dropPreview"); img.onerror = () => { img.hidden = true; $("#dropHint").hidden = false; $("#dropHint").innerHTML = "<b>Photo ready</b><span>(This browser can't preview it, ZEIM will still open it.)</span>"; };
  img.src = URL.createObjectURL(f); img.hidden = false; $("#dropHint").hidden = true;
  $("#btnBuild").disabled = false; $("#buildHint").textContent = "Photo ready: " + (f.name || "camera photo");
  pick.msg(""); $("#photoChosen").hidden = false; $("#photoChosenName").textContent = "✔ " + (f.name || "camera photo");
  if (S.level === "beginner") build(false);                         // Beginner: the photo builds straight away, no hidden second step
  else $("#btnBuild").scrollIntoView({ block: "nearest", behavior: "smooth" });   // Expert: tune the settings, then press Build
}
const drop = $("#drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => setFile(e.dataTransfer.files[0]));
drop.addEventListener("click", () => pick.el("File").click());
$("#changePhoto").onclick = () => pick.el("File").click();
$("#sSample").onclick = async () => {
  try { const b = await (await fetch("/static/sample.png")).blob(); setFile(new File([b], "sample.png", { type: "image/png" })); }
  catch { pick.msg("We couldn't load the sample image. Please try again."); }
};

/* ---------- build ---------- */
function formData(autoDelete) {
  const fd = new FormData();
  fd.append("file", S.file); fd.append("mode", S.mode);
  fd.append("beginner", S.level === "beginner"); fd.append("preset", S.preset);
  fd.append("width_mm", $("#width_mm").value);
  if (autoDelete) fd.append("auto_delete_oldest", "true");
  if (S.level === "expert") {
    $$("#expertOpts [name]").forEach(el => {
      if (el.name === "width_mm") return;
      fd.append(el.name, el.type === "checkbox" ? el.checked : el.value);
    });
  }
  return fd;
}
async function build(autoDelete = false) {
  if (!S.file) return;
  S.pending = null;
  $("#busy").hidden = false; $("#makingLine").hidden = false; $("#btnBuild").disabled = true; $("#btnPrint").disabled = true; $("#btnSendSheet").disabled = true; S.building = true;   // no printing/sending a stale build mid-rebuild
  try {
    const r = await api("/api/generate", { method: "POST", body: formData(autoDelete) });
    showBuild(r); S.history = r.history; renderHistory(); $("#btnBuild").textContent = "✨ Build again with these settings";
    toast("Model built ✔", "ok");
  } catch (e) {
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); openFull(); pick.msg("Your recent builds are full (5 of 5). Delete one, then press Build."); }
    else if (e.status === 400 && /photo/i.test(e.message)) pick.msg(e.message);          // photo problems stay visible under the buttons
    else toast("Build failed: " + e.message, "err");
  } finally { $("#busy").hidden = true; $("#makingLine").hidden = true; $("#btnBuild").disabled = false; $("#btnPrint").disabled = false; $("#btnSendSheet").disabled = false; S.building = false; }
}
$("#btnBuild").onclick = () => build(false);

function showBuild(r) {
  S.current = r;
  r.visibility = r.visibility || "private";
  $("#viewerEmpty").hidden = true; $("#vtools").hidden = false; $("#result").hidden = false;
  viewer?.load(r.preview, r.mode);
  const st = r.stats, sz = st.size_mm.map(x => x.toFixed(1)).join(" × ");
  $("#stats").innerHTML = `<span class="pill">${MODE_LABEL[r.mode]}</span><span class="pill">${sz} mm</span>` +
    `<span class="pill">${st.triangles.toLocaleString()} triangles</span><span class="pill">${st.bodies.length} ${st.bodies.length > 1 ? "bodies" : "body"}</span>` +
    `<span class="pill ${st.watertight ? "ok" : "bad"}">${st.watertight ? "✔ watertight" : "✖ not watertight"}</span>`;
  const notes = r.auto_notes || [];
  $("#autoBox").hidden = !notes.length;
  $("#autoTable").innerHTML = notes.map(n => `<tr><td>${n.label}</td><td><b>${n.value}</b></td><td>${n.why}</td></tr>`).join("");
  $$("#histList .hcard").forEach(c => c.classList.toggle("cur", c.dataset.id === r.id));
  $("#resVis").value = r.visibility || "private";
}
$("#resVis").onchange = async e => {
  try { await api(`/api/builds/${S.current.id}/visibility`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ visibility: e.target.value }) }); toast("Who can see this build: " + e.target.value, "ok"); loadHistory(); }
  catch (er) { toast(er.message, "err"); e.target.value = S.current.visibility || "private"; }
};
$("#vReset").onclick = () => viewer?.reset();
$("#vWire").onclick = () => viewer?.toggleWire();

/* ---------- history ---------- */
function renderHistory() {
  $("#histCount").textContent = `${S.history.length} / ${S.max}`;
  const cards = S.history.slice().reverse().map(b => `
    <div class="hcard ${S.current?.id === b.id ? "cur" : ""}" data-id="${b.id}">
      <img src="${b.thumb}" alt="" data-open="${b.id}" title="Open">
      <div class="meta"><b>${esc(b.title)}</b><span>${MODE_LABEL[b.mode]}${b.visibility && b.visibility !== "private" ? " · " + b.visibility : " · 🔒"} · ${b.beginner ? "Beginner" : "Expert"} · ${ago(b.created)}</span></div>
      <div class="row2"><button data-open="${b.id}">Open</button>
        <button data-send="${b.id}" title="Save this build or send it somewhere">Send…</button>
        <button data-del="${b.id}">🗑</button></div></div>`);
  while (cards.length < S.max) cards.push(`<div class="hslot">Empty slot</div>`);
  $("#histList").innerHTML = cards.join("");
}
const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
$("#histList").onclick = async e => {
  const o = e.target.closest("[data-open]"), d = e.target.closest("[data-del]");
  if (o) { try {
    const hb = S.history.find(x => x.id === o.dataset.open);
    if (hb?.kind === "edit") { document.dispatchEvent(new CustomEvent("zeim:open-edit", { detail: hb.id })); location.hash = "edit"; return; }
    const r = await api("/api/builds/" + o.dataset.open); S.mode = r.mode; applyMode(); showBuild(r); } catch (er) { toast(er.message, "err"); } }
  if (d && confirm("Delete this build and its files?")) { await api("/api/builds/" + d.dataset.del, { method: "DELETE" }); await loadHistory(); }
};
async function loadHistory() { const r = await api("/api/builds"); S.history = r.builds; S.max = r.max; renderHistory(); }

/* ---------- history-full dialog ---------- */
function openFull() { renderFull(); $("#dlgFull").showModal(); }
function renderFull() {
  $("#fullList").innerHTML = S.history.map(b => `<div class="fl"><img src="${b.thumb}"><span><b>${esc(b.title)}</b><br><small>${MODE_LABEL[b.mode]} · ${ago(b.created)}</small></span><button class="btn small danger" data-fdel="${b.id}">Delete</button></div>`).join("");
  $("#btnRetry").disabled = S.history.length >= S.max;
}
$("#fullList").onclick = async e => {
  const d = e.target.closest("[data-fdel]"); if (!d) return;
  await api("/api/builds/" + d.dataset.fdel, { method: "DELETE" }); await loadHistory(); renderFull();
};
S.pending = null;   // other workspaces (Edit) set this so the same "history full" dialog can retry their action
$("#btnRetry").onclick = () => { $("#dlgFull").close(); (S.pending || build)(false); };
$("#btnAutoDel").onclick = () => { $("#dlgFull").close(); (S.pending || build)(true); };

/* ---------- print dialog ---------- */
let printInfo = null, printId = null, printLabel = "";
const sliceOpts = () => { const fd = new FormData(); fd.append("layer_height", $("#s_layer").value); fd.append("fill_density", $("#s_fill").value); fd.append("brim", $("#s_brim").value); if ($("#printerBlock") && !$("#printerBlock").hidden && $("#printerSel").value) fd.append("printer_id", $("#printerSel").value); fd.append("upright", $("#s_up").checked); fd.append("supports", $("#s_sup").checked); return fd; };
async function openPrint() {
  const id = S.current.id;   // the dialog is bound to THIS build; slice/send below use printId, never "whatever is current later"
  let caps = {};
  try { printInfo = await api(`/api/print/${id}/links`); caps = (await api("/api/me")).send || {}; } catch (e) { return toast(e.message, "err"); }
  printId = id; printLabel = `${S.current.title || "build"} (${S.current.beginner ? "Beginner" : "Expert"}, ${MODE_LABEL[S.current.mode] || "Edit"})`;
  $("#printWhich").textContent = "Printing: " + printLabel;
  $("#printHint").textContent = printInfo.hint;
  $("#slicerBtns").innerHTML = printInfo.slicers.map(s => `<a class="btn ${s.slicer === printInfo.default_slicer ? "def" : ""}" href="${s.url}" title="${s.note || "Opens " + s.label}">Open in ${s.label}${s.slicer === printInfo.default_slicer ? " ★" : ""}</a>`).join("") +
    `<a class="btn ghost" href="${S.current.downloads["3mf"]}" download>${printInfo.slicers.length ? "…or download 3MF" : "Download 3MF"}</a>` +
    (printInfo.slicer_links_disabled ? `<p class="muted small" style="flex-basis:100%">${esc(printInfo.slicer_links_disabled)}</p>` : "");
  const b = printInfo.builtin_slicer;
  $("#builtinState").textContent = b.available ? "(PrusaSlicer CLI detected)" : "(slicer not installed)";
  $("#btnSlice").disabled = !b.available;
  $("#s_up").checked = S.current.mode === "lithophane";
  $("#sliceOut").textContent = b.available ? "" : b.message;
  // SEND-6: the printer block exists only where it can really work (ZEIM on the user's own computer); hosted ZEIM promises nothing
  $("#printerBlock").hidden = !caps.printer_ui; $("#printerHosted").hidden = !!caps.printer_ui;
  startNowOff(); fillPrinterSel(); $("#sendOut").textContent = "";
  $("#dlgPrint").showModal();
}
$("#btnPrint").onclick = openPrint;
const startNowOff = () => { $("#startNow").checked = false; };          // "Start print" is always a separate, unchecked choice
const TYPE_LABEL = { octoprint: "OctoPrint", moonraker: "Moonraker (Klipper)" };
function fillPrinterSel() {
  const ps = printInfo.printers;
  $("#printerSel").innerHTML = ps.length ? ps.map(p => `<option value="${p.id}">${esc(p.name)} (${esc(p.profile_label || TYPE_LABEL[p.type] || p.type)})</option>`).join("") : `<option value="">No printers configured — add one in Settings</option>`;
  $("#btnSend").disabled = !ps.length;
}
$("#btnSlice").onclick = async () => {
  $("#sliceOut").textContent = "Slicing…";
  try {
    const r = await api(`/api/slice/${printId}`, { method: "POST", body: sliceOpts() });
    if (!r.available) $("#sliceOut").textContent = r.message;
    else if (!r.ok) $("#sliceOut").textContent = "Slicer failed: " + (r.log || r.message);
    else {
      const t = r.stats.print_time, g = r.stats.filament_g;
      const est = [t ? "about " + esc(t) : "", g ? "about " + Number(g).toFixed(1) + " g of filament" : ""].filter(Boolean).join(", ");
      $("#sliceOut").innerHTML = `Done: ${r.layers} layers${est ? ", " + est : " (the slicer gave no time/filament estimate)"} · <a href="${r.download}" download>download G-code</a>` +
        `<br><small>${esc(r.stats_note || "")}</small>`;
    }
  } catch (e) { $("#sliceOut").textContent = e.message; }
};
$("#btnSend").onclick = async () => {
  const fd = sliceOpts(); fd.set("printer_id", $("#printerSel").value); fd.append("start", $("#startNow").checked);
  $("#sendOut").textContent = "Slicing and uploading…";
  try { const r = await api(`/api/send/${printId}`, { method: "POST", body: fd }); $("#sendOut").textContent = (r.ok ? "✔ " : "✖ ") + (r.message || r.log || "failed"); }
  catch (e) { $("#sendOut").textContent = "✖ " + e.message; }
};

/* ---------- settings ---------- */
async function openSettings() {
  S.settings = await api("/api/settings");
  $("#set_slicer").value = S.settings.default_slicer; $("#set_base").value = S.settings.public_base_url || "";
  renderPrinters(); await renderAccounts(); $("#dlgSettings").showModal();
}
function renderPrinters() {
  const types = S.settings.printer_types;
  $("#printerList").innerHTML = S.settings.printers.map((p, i) => `<div class="printer" data-i="${i}">
    <div class="grid2">
      <div class="field"><label>Name</label><input data-f="name" value="${esc(p.name || "")}"></div>
      <div class="field"><label>Type</label><select data-f="type">${types.map(t => `<option value="${t.type}" ${t.type === p.type ? "selected" : ""}>${t.label}</option>`).join("")}</select></div>
      <div class="field"><label>URL</label><input data-f="url" value="${esc(p.url || "")}" placeholder="http://printer.local"></div>
      <div class="field"><label>API key ${p.has_key ? "<em>(stored — leave blank to keep)</em>" : ""}</label><input data-f="api_key" type="password" placeholder="${p.has_key ? "••••••••" : ""}"></div>
      <div class="field"><label>Preset</label><select data-f="profile"><option value="">None (generic)</option>${(S.settings.printer_presets || []).map(x => `<option value="${x.id}" ${x.id === p.profile ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select></div>
      <div class="field"><label>Bed X mm</label><input data-f="bed_x" type="number" value="${p.bed_x || 250}"></div>
      <div class="field"><label>Bed Y mm</label><input data-f="bed_y" type="number" value="${p.bed_y || 210}"></div>
    </div><p class="help">${types.find(t => t.type === p.type)?.hint || ""}</p>
    ${(S.settings.printer_presets || []).find(x => x.id === p.profile) ? `<p class="help"><b>Experimental.</b> ${esc(S.settings.printer_presets.find(x => x.id === p.profile).hint)}</p>` : ""}
    <p class="help">Tested with a pretend printer only. Not tried on a real printer yet.</p>
    <button class="btn small" data-test="${i}" ${p.id ? "" : "disabled title='Save first, then test'"}>Test connection</button> <button class="btn small danger" data-rm="${i}">Remove</button>
    <p class="help" data-testout="${i}" role="status" aria-live="polite">${p.id ? "A test only asks the printer if it is there. It never starts a print." : "Save settings first, then you can test the connection."}</p></div>`).join("") || `<p class="help">No printers yet.</p>`;
}
function readPrinters() {
  return $$("#printerList .printer").map(el => {
    const p = { ...S.settings.printers[+el.dataset.i] };
    $$("[data-f]", el).forEach(i => p[i.dataset.f] = i.value); return p;
  });
}
$("#printerList").onclick = async e => {
  const tb = e.target.closest("[data-test]");
  if (tb) {
    const i = +tb.dataset.test, out = $(`[data-testout="${i}"]`), id = S.settings.printers[i]?.id; out.textContent = "Testing…";
    try { const r = await api(`/api/printers/${id}/test`, { method: "POST" }); out.textContent = (r.ok ? "✔ " : "✖ ") + r.message; } catch (er) { out.textContent = "✖ " + er.message; }
    return;
  }
  const r = e.target.closest("[data-rm]"); if (!r) return; S.settings.printers = readPrinters(); S.settings.printers.splice(+r.dataset.rm, 1); renderPrinters(); };
$("#printerList").addEventListener("change", e => {
  if (!e.target.matches('[data-f="profile"]')) return;
  const pre = (S.settings.printer_presets || []).find(x => x.id === e.target.value), el = e.target.closest(".printer"), i = +el.dataset.i;
  S.settings.printers = readPrinters();
  if (pre) Object.assign(S.settings.printers[i], { type: pre.type, bed_x: pre.bed[0], bed_y: pre.bed[1] });
  renderPrinters();
});
$("#btnAddPrinter").onclick = () => { S.settings.printers = readPrinters(); S.settings.printers.push({ name: "My printer", type: "octoprint", url: "", bed_x: 250, bed_y: 210 }); renderPrinters(); };
$("#btnSaveSettings").onclick = async () => {
  const body = { default_slicer: $("#set_slicer").value, public_base_url: $("#set_base").value.trim(), printers: readPrinters() };
  await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  toast("Settings saved", "ok"); $("#dlgSettings").close();
};
const PLAT = { tiktok: "TikTok", instagram: "Instagram", reddit: "Reddit", patreon: "Patreon" };
async function renderLinkInputs() {
  const me = await api("/api/me");
  $("#linkInputs").innerHTML = me.signed_up ? Object.entries(PLAT).map(([k, n]) => `<div class="field"><label>${n} handle</label><input data-link="${k}" value="${esc(me.links?.[k]?.handle || "")}" placeholder="yourname"></div>`).join("")
    : `<p class="help wide2">Create an account (top right) to add link-outs.</p>`;
  $("#btnSaveLinks").hidden = !me.signed_up;
}
$("#btnSaveLinks").onclick = async () => {
  const body = {}; $$("[data-link]").forEach(i => body[i.dataset.link] = i.value);
  try { await api("/api/me/links", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); toast("Link-outs saved (shown as unverified)", "ok"); } catch (e) { toast(e.message, "err"); }
};
async function renderAccounts() {
  await renderLinkInputs();
  const r = await api("/api/accounts"); $("#accNote").textContent = r.note;
  const label = { not_configured: "Not configured", disconnected: "Ready to connect", connected: "Connected" };
  $("#accList").innerHTML = r.providers.map(p => `<div class="acc"><div class="info"><b>${p.label}</b> <span class="pill ${p.state === "connected" ? "ok" : ""}">${label[p.state]}</span>
    <small>${p.purpose} · posting/verification: <i>not implemented yet</i></small>
    ${p.state === "not_configured" ? `<small>Set <code>${p.env_vars[0]}</code> and <code>${p.env_vars[1]}</code>, then restart the server.</small>` : ""}</div>
    ${p.state === "connected" ? `<button class="btn small" data-disc="${p.id}">Disconnect</button>` : `<a class="btn small ${p.state === "not_configured" ? "" : "primary"}" ${p.state === "not_configured" ? 'style="pointer-events:none;opacity:.4"' : `href="/api/accounts/${p.id}/connect"`}>Connect</a>`}</div>`).join("");
}
$("#accList").onclick = async e => { const d = e.target.closest("[data-disc]"); if (d) { await api("/api/accounts/" + d.dataset.disc, { method: "DELETE" }); renderAccounts(); } };
$$(".tabs button").forEach(b => b.onclick = () => { $$(".tabs button").forEach(x => x.classList.toggle("on", x === b)); $$(".tab").forEach(t => t.hidden = t.id !== b.dataset.tab); });
$("#btnSettings").onclick = openSettings;
$$("[data-close]").forEach(b => b.onclick = () => b.closest("dialog").close());

/* ---------- init ---------- */
applyLevel(); applyMode(); loadHistory();
const q = new URLSearchParams(location.search);
if (q.get("connected")) { toast("Connected " + q.get("connected"), "ok"); history.replaceState({}, "", "/"); }
window.__photo3d = S;  // debugging / tests

export { S, api, toast, $, $$, esc, MODE_LABEL, ago, openPrint, loadHistory, renderHistory, openFull, applyLevel };
