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
function setFile(f) {
  if (!f) return;
  S.file = f;
  const img = $("#dropPreview"); img.src = URL.createObjectURL(f); img.hidden = false; $("#dropHint").hidden = true;
  $("#btnBuild").disabled = false; $("#buildHint").textContent = f.name;
}
$("#file").onchange = e => setFile(e.target.files[0]);
const drop = $("#drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => setFile(e.dataTransfer.files[0]));
$("#btnSample").onclick = async () => { const b = await (await fetch("/static/sample.png")).blob(); setFile(new File([b], "sample.png", { type: "image/png" })); };

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
  $("#busy").hidden = false; $("#btnBuild").disabled = true;
  try {
    const r = await api("/api/generate", { method: "POST", body: formData(autoDelete) });
    showBuild(r); S.history = r.history; renderHistory();
    toast("Model built ✔", "ok");
  } catch (e) {
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); openFull(); }
    else toast("Build failed: " + e.message, "err");
  } finally { $("#busy").hidden = true; $("#btnBuild").disabled = false; }
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
  $("#downloads").innerHTML = Object.entries(r.downloads).map(([k, u]) => `<a class="btn" href="${u}" download>⬇ ${k.toUpperCase()}</a>`).join("");
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
        ${Object.entries(b.downloads).map(([k, u]) => `<a href="${u}" download>${k.toUpperCase()}</a>`).join("")}
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
let printInfo = null;
const sliceOpts = () => { const fd = new FormData(); fd.append("layer_height", $("#s_layer").value); fd.append("fill_density", $("#s_fill").value); fd.append("brim", $("#s_brim").value); fd.append("upright", $("#s_up").checked); fd.append("supports", $("#s_sup").checked); return fd; };
async function openPrint() {
  const id = S.current.id;
  try { printInfo = await api(`/api/print/${id}/links`); } catch (e) { return toast(e.message, "err"); }
  $("#printHint").textContent = printInfo.hint;
  $("#slicerBtns").innerHTML = printInfo.slicers.map(s => `<a class="btn ${s.slicer === printInfo.default_slicer ? "def" : ""}" href="${s.url}" title="${s.note || "Opens " + s.label}">Open in ${s.label}${s.slicer === printInfo.default_slicer ? " ★" : ""}</a>`).join("") +
    `<a class="btn ghost" href="${S.current.downloads["3mf"]}" download>…or download 3MF</a>`;
  const b = printInfo.builtin_slicer;
  $("#builtinState").textContent = b.available ? "(PrusaSlicer CLI detected)" : "(slicer not installed)";
  $("#btnSlice").disabled = !b.available;
  $("#s_up").checked = S.current.mode === "lithophane";
  $("#sliceOut").textContent = b.available ? "" : b.message;
  fillPrinterSel(); $("#sendOut").textContent = "";
  $("#dlgPrint").showModal();
}
$("#btnPrint").onclick = openPrint;
function fillPrinterSel() {
  const ps = printInfo.printers;
  $("#printerSel").innerHTML = ps.length ? ps.map(p => `<option value="${p.id}">${esc(p.name)} (${p.type})</option>`).join("") : `<option value="">No printers configured — add one in Settings</option>`;
  $("#btnSend").disabled = !ps.length;
}
$("#btnSlice").onclick = async () => {
  $("#sliceOut").textContent = "Slicing…";
  try {
    const r = await api(`/api/slice/${S.current.id}`, { method: "POST", body: sliceOpts() });
    if (!r.available) $("#sliceOut").textContent = r.message;
    else if (!r.ok) $("#sliceOut").textContent = "Slicer failed: " + (r.log || r.message);
    else $("#sliceOut").innerHTML = `Done: ${r.layers} layers, ${r.stats.print_time || "?"}, ${r.stats.filament_g || "?"} g · <a href="${r.download}" download>download G-code</a>`;
  } catch (e) { $("#sliceOut").textContent = e.message; }
};
$("#btnSend").onclick = async () => {
  const fd = sliceOpts(); fd.append("printer_id", $("#printerSel").value); fd.append("start", $("#startNow").checked);
  $("#sendOut").textContent = "Slicing and uploading…";
  try { const r = await api(`/api/send/${S.current.id}`, { method: "POST", body: fd }); $("#sendOut").textContent = (r.ok ? "✔ " : "✖ ") + (r.message || r.log || "failed"); }
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
      <div class="field"><label>Bed X mm</label><input data-f="bed_x" type="number" value="${p.bed_x || 250}"></div>
      <div class="field"><label>Bed Y mm</label><input data-f="bed_y" type="number" value="${p.bed_y || 210}"></div>
    </div><p class="help">${types.find(t => t.type === p.type)?.hint || ""}</p>
    <button class="btn small danger" data-rm="${i}">Remove</button></div>`).join("") || `<p class="help">No printers yet.</p>`;
}
function readPrinters() {
  return $$("#printerList .printer").map(el => {
    const p = { ...S.settings.printers[+el.dataset.i] };
    $$("[data-f]", el).forEach(i => p[i.dataset.f] = i.value); return p;
  });
}
$("#printerList").onclick = e => { const r = e.target.closest("[data-rm]"); if (!r) return; S.settings.printers = readPrinters(); S.settings.printers.splice(+r.dataset.rm, 1); renderPrinters(); };
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
