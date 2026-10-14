import { Viewer } from "/static/viewer.js";

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const S = { mode: "lithophane", level: localStorage.level === "expert" ? "expert" : "beginner", me: null, preset: "standard", file: null,
            current: null, history: [], max: 5, settings: null };
const PRESET_HELP = {
  lithophane: { thin: "Lighter, glows brighter, more fragile (0.6–2.4 mm).", standard: "Balanced contrast and strength (0.8–3.2 mm).", thick: "Deep shadows, sturdy (1.0–4.0 mm)." },
  relief: { thin: "Shallow, subtle relief (≈4% of width).", standard: "Clear depth (≈7% of width).", thick: "Dramatic depth (≈11% of width)." },
  popart: { thin: "3 colour layers, small steps.", standard: "4 colour layers, medium steps.", thick: "5 colour layers, tall steps." } };

function toast(msg, kind = "") {
  const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg;
  $("#toasts").append(t); setTimeout(() => t.remove(), kind === "err" ? 8000 : 4500);
}
/* A refusal belongs INSIDE the dialog, next to the button, and stays until the next try (toasts vanish behind the scrim). Typed text is never cleared. */
function inlineMsg(near, msg, kind = "err") {
  if (!near) return toast(msg, kind);
  let p = near.previousElementSibling;
  if (!(p && p.classList.contains("inline-msg"))) { p = document.createElement("p"); p.setAttribute("role", "alert"); near.before(p); }
  p.className = "inline-msg " + kind; p.textContent = msg;
  p.scrollIntoView?.({ block: "nearest" });
}
function clearInline(near) { const p = near?.previousElementSibling; if (p?.classList.contains("inline-msg")) p.remove(); }
/** Accessible confirm dialog (replaces window.confirm). Resolves true/false. */
function askConfirm({ title = "Please confirm", message, okLabel = "OK", danger = true } = {}) {
  return new Promise(resolve => {
    const dlg = $("#dlgConfirm"); if (!dlg) { resolve(window.confirm(message || title)); return; }
    $("#confirmTitle").textContent = title;
    $("#confirmMsg").textContent = message || "";
    const ok = $("#confirmOk");
    ok.textContent = okLabel;
    ok.className = danger ? "btn danger" : "btn primary";
    let settled = false;
    const done = (v) => { if (settled) return; settled = true; dlg.close(); resolve(v); };
    ok.onclick = () => done(true);
    $("#confirmCancel").onclick = () => done(false);
    dlg.addEventListener("close", () => done(false), { once: true });
    dlg.showModal();
    (danger ? $("#confirmCancel") : ok).focus();
  });
}
// Server errors: a string detail is shown as-is; FastAPI 422 lists are turned into friendly field messages, never "[object Object]".
const FIELD_NAMES = { width_mm: "Width", height_mm: "Height", resolution: "Detail", mode: "Style", file: "Photo", dob: "Date of birth", display_name: "Display name",
  username: "Username", title: "Title", password: "Password", nickname: "Nickname", keep_ratio: "Keep ratio", wall: "Wall thickness" };
function errText(j, r) {
  const d = j?.detail ?? j?.message;
  if (typeof d === "string" && d) return d;
  // {detail: {code, message}} (slicer: "too big for the bed", busy, bad file…): show the friendly message, never "Unprocessable Content"
  if (d && typeof d === "object" && !Array.isArray(d) && typeof d.message === "string" && d.message) return d.message;
  if (Array.isArray(d) && d.length) {
    const names = [...new Set(d.map(x => { const k = Array.isArray(x?.loc) ? x.loc.at(-1) : ""; return FIELD_NAMES[k] || (typeof k === "string" && k && k !== "body" ? k.replace(/_/g, " ") : ""); }).filter(Boolean))];
    return names.length ? `Please check: ${names.join(", ")}. Something in the form isn't right.` : "Something in the form isn't right. Check the highlighted field.";
  }
  return r.status >= 500 ? "Something went wrong on the server. Please try again." : (r.statusText || "Something went wrong.");
}
const api = async (url, opt) => {
  const r = await fetch(url, opt); let j = null;
  try { j = await r.json(); } catch { }
  if (!r.ok) { const e = new Error(errText(j, r)); e.status = r.status; e.body = j; throw e; }
  return j;
};
const ago = iso => { const s = (Date.now() - new Date(iso)) / 1000; return s < 60 ? "just now" : s < 3600 ? Math.floor(s / 60) + " min ago" : s < 86400 ? Math.floor(s / 3600) + " h ago" : new Date(iso).toLocaleDateString(); };
const MODE_LABEL = { lithophane: "Lithophane", relief: "Relief", popart: "Pop-art", edit: "Edited model" };

let viewer;
try { viewer = new Viewer($("#viewer")); } catch (e) { console.warn("WebGL unavailable", e); }

/* ---------- level / mode ---------- */
const isExpert = () => S.level === "expert";
const LEVEL_NAME = { beginner: "Beginner", expert: "Experienced" };
const LEVEL_ICO = { beginner: "🌱", expert: "🛠" };
const LEVEL_LINE = { beginner: "Beginner mode: ZEIM picks the settings for you.", expert: "Experienced mode: every setting is yours." };
const LEVEL_SAY = { beginner: "Beginner mode on. ZEIM picks the settings for you.", expert: "Experienced mode on. All the settings are showing." };
function say(t) { const e = $("#modeStatus"); e.textContent = ""; setTimeout(() => e.textContent = t, 60); }
function applyLevel(announce = false) {
  localStorage.level = S.level;
  document.body.dataset.level = S.level;
  $("#modeSel").value = S.level; $("#modeIco").textContent = LEVEL_ICO[S.level]; $("#modeLine").textContent = LEVEL_LINE[S.level];
  document.dispatchEvent(new CustomEvent("zeim:level"));
  $("#beginnerOpts").hidden = isExpert();
  $("#expertOpts").hidden = !isExpert();
  if (announce) say(LEVEL_SAY[S.level]);
}
$("#modeSel").onchange = e => {
  const v = e.target.value;
  S.level = v; applyLevel(true);
};
/* Who is signed in. community.js tells us; the server still decides every real permission. */
document.addEventListener("zeim:me", e => { S.me = e.detail; });
function applyMode() {
  $$("#modeCards input").forEach(i => { i.checked = i.value === S.mode; i.closest(".card").classList.toggle("on", i.checked); });
  $$("#presetSeg input").forEach(i => { i.checked = i.value === S.preset; i.closest("label").classList.toggle("on", i.checked); });
  $$("#expertOpts [data-modes]").forEach(e => e.hidden = !e.dataset.modes.split(" ").includes(S.mode));
  applyShape();
  $("#presetHelp").textContent = PRESET_HELP[S.mode][S.preset];
}
/* lithophane shape picker: flat outlines + curved shells (globe / night-light); curved ones take diameter + height instead of width */
const CURVED = ["globe", "nightlight", "cup"];
const litShape = () => ($("#shapeCards input:checked") || {}).value || "rect";
function applyShape() {
  const lit = S.mode === "lithophane", curved = lit && CURVED.includes(litShape());
  $("#shapeCards").hidden = !lit; $("#shapeHelp").hidden = !lit; $("#curvedOpts").hidden = !curved;
  $("#width_mm").closest(".field").hidden = curved;
  $("#diaLbl").firstChild.textContent = { globe: "Globe diameter ", cup: "Cup inside diameter " }[litShape()] || "Light diameter ";
  $("#heightFld").hidden = litShape() === "globe";             // a globe is a sphere: diameter only
}
$("#shapeCards").onchange = applyShape;
$("#modeCards").onchange = () => { S.mode = ($("#modeCards input:checked") || {}).value || "lithophane"; applyMode(); };       // radios: the browser keeps "selected" for assistive tech; we just read input:checked
$("#presetSeg").onchange = () => { S.preset = ($("#presetSeg input:checked") || {}).value || "standard"; applyMode(); };
$("#widthRange").oninput = e => $("#width_mm").value = e.target.value;
$("#width_mm").oninput = e => $("#widthRange").value = e.target.value;

/* ---------- the three-step path: Photo -> Preview -> Print-ready (ticks AND a border, never colour alone; changes announced politely) ---------- */
function setPath(step, say) {
  $$("#path li").forEach(li => {
    const n = +li.dataset.step; li.classList.toggle("done", n < step); li.classList.toggle("cur", n === step);
    if (n === step) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    li.querySelector(".n").textContent = n < step ? "✓" : String(n);
  });
  if (say) $("#pathSay").textContent = say;
}

/* ---------- file ---------- */
import { photoBlock, mountPhoto } from "/static/photo.js";
$("#studioPhoto").innerHTML = photoBlock("s");
const pick = mountPhoto("s", f => setFile(f));
const MAX_PHOTO = 25 * 1024 * 1024;
const DROP_HINT0 = $("#dropHint").innerHTML;
/* QA-2: a photo the server refused is not "ready": forget it, restore the empty drop zone, disable Build */
function clearFile() {
  S.file = null;
  const img = $("#dropPreview"); img.onerror = null; img.hidden = true; img.removeAttribute("src");
  $("#dropHint").hidden = false; $("#dropHint").innerHTML = DROP_HINT0;
  $("#photoChosen").hidden = true; $("#photoChosenName").textContent = "";
  $("#btnBuild").disabled = true; $("#buildHint").textContent = "Choose or take a photo to begin."; setPath(1, "Step 1 of 3: choose a photo.");
}
function setFile(f) {
  if (!f) return;
  if (f.size > MAX_PHOTO) { pick.msg("That photo is over 25 MB. Try a smaller one (JPG or PNG)."); return; }
  if (!f.size) { pick.msg("We couldn't open that photo. Try a JPG or PNG."); return; }
  S.file = f; S.pending = null;
  const img = $("#dropPreview"); img.onerror = () => { img.hidden = true; $("#dropHint").hidden = false; $("#dropHint").innerHTML = "<b>Photo ready</b><span>(This browser can't preview it, ZEIM will still open it.)</span>"; };
  img.src = URL.createObjectURL(f); img.hidden = false; $("#dropHint").hidden = true;
  $("#btnBuild").disabled = false; $("#buildHint").textContent = "Photo ready: " + (f.name || "camera photo");
  setPath(1, "Photo chosen."); pick.msg(""); $("#photoChosen").hidden = false; $("#photoChosenName").textContent = "✔ " + (f.name || "camera photo");
  if (!isExpert()) build(false);                         // Beginner: the photo builds straight away, no hidden second step
  else $("#btnBuild").scrollIntoView({ block: "nearest", behavior: "smooth" });   // Expert: tune the settings, then press Build
}
const drop = $("#drop");
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (pick.allowed(f)) setFile(f); });
drop.addEventListener("click", () => pick.el("File").click());
$("#changePhoto").onclick = () => pick.el("File").click();
$("#sSample").onclick = async () => {
  try { const b = await (await fetch("/static/sample.png")).blob(); setFile(new File([b], "sample.png", { type: "image/png" })); }
  catch { pick.msg("We couldn't load the sample image. Please try again."); }
};

/* ---------- build ---------- */
function formData(autoDelete) {
  const fd = new FormData();
  fd.append("file", S.file); fd.append("mode", S.mode); fd.append("photo_ack", pick.acked());      // CR-5 (the built-in sample needs no tick: the server knows that file)
  fd.append("beginner", !isExpert()); fd.append("preset", S.preset);
  fd.append("width_mm", $("#width_mm").value);
  if (S.mode === "lithophane") {
    fd.append("shape", litShape());
    if (CURVED.includes(litShape())) { fd.append("diameter_mm", $("#diameter_mm").value); fd.append("height_mm", $("#height_mm").value); }
  }
  if (autoDelete) fd.append("auto_delete_oldest", "true");
  if (isExpert()) {
    $$("#expertOpts [name]").forEach(el => {
      if (el.name === "width_mm") return;
      fd.append(el.name, el.type === "checkbox" ? el.checked : el.value);
    });
  }
  return fd;
}
/* QA-4: on a phone the model is two screens below the photo area: scroll it into view and say so (respects reduced motion) */
function revealResult() {
  $("#buildHint").textContent = "Your 3D model is ready.";
  if (!matchMedia("(max-width:768px)").matches) { $("#resultH").focus({ preventScroll: true }); return; }
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const r = $("#resultH"); r.focus({ preventScroll: true });
  // wait until build() has put the page back (busy bar hidden) so the scroll target is final
  setTimeout(() => { const v = $("#viewer"); v.style.scrollMarginTop = ($(".topbar").offsetHeight + 8) + "px"; v.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" }); }, 60);
}
async function build(autoDelete = false) {
  if (!S.file) return;
  S.pending = null;
  setPath(2, "Making your 3D model. Step 2 of 3."); $("#busy").hidden = false; $("#makingLine").hidden = false; $("#btnBuild").disabled = true; $("#btnPrint").disabled = true; $("#btnSendSheet").disabled = true; S.building = true;   // no printing/sending a stale build mid-rebuild
  try {
    const r = await api("/api/generate", { method: "POST", body: formData(autoDelete) });
    showBuild(r); S.history = r.history; renderHistory(); $("#btnBuild").textContent = "✨ Make it again with these settings";
    setPath(3, "Model ready. Step 3 of 3: save or print it.");
    toast("Your model is ready ✔", "ok");
    revealResult();
  } catch (e) {
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); openFull(); pick.msg("Your recent builds are full (5 of 5). Delete one, then press Build."); }
    else if (e.status === 400 && /photo/i.test(e.message)) { clearFile(); pick.msg(e.message); }          // photo problems stay visible under the buttons; the refused photo is forgotten (QA-2)
    else { setPath(S.file ? 1 : 1, "That didn't work. Your photo is still here, so you can try again."); toast("We couldn't make your model: " + (e.message || "something went wrong") + " Your photo is still here. Try again.", "err"); }
  } finally { $("#busy").hidden = true; $("#makingLine").hidden = true; $("#btnBuild").disabled = !S.file; $("#btnPrint").disabled = false; $("#btnSendSheet").disabled = false; S.building = false; }
}
$("#btnBuild").onclick = () => build(false);

function showBuild(r) {
  S.current = r;
  r.visibility = r.visibility || "private";
  $("#viewerEmpty").hidden = true; $("#vtools").hidden = false; $("#result").hidden = false;
  viewer?.load(r.preview, r.mode);
  S.lightOn = false; syncLight();
  const st = r.stats, sz = st.size_mm.map(x => x.toFixed(1)).join(" × ");
  const nb = st.bodies?.length || 1;
  $("#viewer").setAttribute("aria-label", `3D preview: ${MODE_LABEL[r.mode] || "model"}, ${sz.replace(/ × /g, " by ")} millimetres, ${nb} ${nb > 1 ? "pieces" : "piece"}` +
    `${st.watertight ? "" : ", not watertight yet"}. Use the Turn left, Turn right and Reset view buttons to look around it.`);
  $("#stats").innerHTML = `<span class="pill">${MODE_LABEL[r.mode]}</span><span class="pill">${sz} mm</span>` +
    `<span class="pill">${st.triangles.toLocaleString()} triangles</span><span class="pill">${st.bodies.length} ${st.bodies.length > 1 ? "bodies" : "body"}</span>` +
    `<span class="pill ${st.watertight ? "ok" : "bad"}">${st.watertight ? "✔ watertight" : "✖ not watertight"}</span>`;
  const bw = (r.info?.warnings || []); $("#buildWarn").hidden = !bw.length; $("#buildWarn").innerHTML = bw.map(w => "⚠ " + esc(w)).join("<br>");
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
$("#vLeft").onclick = () => viewer?.turn(-30);
$("#vRight").onclick = () => viewer?.turn(30);
$("#vWire").onclick = () => viewer?.toggleWire();
/* "Light on": backlit lithophane preview estimate (thin = bright, thick = dark) */
const litShapeOf = r => r?.info?.shape || r?.params?.shape || "rect";
function syncLight() {
  const lit = S.current?.mode === "lithophane";
  $("#litLightBox").hidden = !lit;
  if (!lit) S.lightOn = false;
  $("#vLight").setAttribute("aria-pressed", S.lightOn ? "true" : "false");
  $("#vLightNote").hidden = !S.lightOn;
  viewer?.setBacklight(!!S.lightOn, litShapeOf(S.current), $("#vLightColor").value);
}
$("#vLight").onclick = () => { S.lightOn = !S.lightOn; syncLight(); };
$("#vLightColor").onchange = () => { if (S.lightOn) syncLight(); };

/* ---------- history ---------- */
function renderHistory() {
  $("#histCount").textContent = `${S.history.length} / ${S.max}`;
  const cards = S.history.slice().reverse().map(b => `
    <li class="hcard ${S.current?.id === b.id ? "cur" : ""}" data-id="${b.id}">
      <button type="button" class="thumbbtn" data-open="${b.id}" aria-label="Open ${esc(b.title)}"><img src="${b.thumb}" alt=""></button>
      <div class="meta"><b>${esc(b.title)}</b><span>${MODE_LABEL[b.mode]}${b.visibility && b.visibility !== "private" ? " · " + b.visibility : " · 🔒"} · ${b.beginner ? "Beginner" : "Experienced"} · ${ago(b.created)}</span></div>
      <div class="row2"><button data-open="${b.id}">Open</button>
        <button data-send="${b.id}" title="Save this build or send it somewhere">Send…</button>
        <button data-fav="${b.id}" class="star ${b.favorite ? "on" : ""}" aria-pressed="${!!b.favorite}" aria-label="${b.favorite ? "Starred: kept until you delete it. Tap to un-star" : "Star to keep this build"}" title="${b.favorite ? "Starred - kept until you delete it" : "Star to keep it (builds are removed after " + (S.keepDays || 7) + " days)"}">${b.favorite ? "★" : "☆"}</button>
        <button data-del="${b.id}" aria-label="Delete this build">🗑</button></div></li>`);
  while (cards.length < Math.min(S.max, 5)) cards.push(`<li class="hslot">Empty slot</li>`);
  const note = $("#histNote"); if (note) note.textContent = `Builds are removed after ${S.keepDays || 7} days. Tap ☆ to keep one.`;
  $("#histList").innerHTML = cards.join("");
}
const esc = s => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
$("#histList").onclick = async e => {
  const o = e.target.closest("[data-open]"), d = e.target.closest("[data-del]"), f = e.target.closest("[data-fav]");
  if (f) { const b = S.history.find(x => x.id === f.dataset.fav); try { await api(`/api/builds/${f.dataset.fav}/favorite`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ favorite: !b?.favorite }) }); await loadHistory(); } catch (er) { toast(er.message, "err"); } return; }
  if (o) { try {
    const hb = S.history.find(x => x.id === o.dataset.open);
    if (hb?.kind === "edit") { document.dispatchEvent(new CustomEvent("zeim:open-edit", { detail: hb.id })); location.hash = "slicer"; return; }
    const r = await api("/api/builds/" + o.dataset.open); S.mode = r.mode; applyMode(); showBuild(r); } catch (er) { toast(er.message, "err"); } }
  if (d) {
    const yes = await askConfirm({
      title: "Delete this build?",
      message: "This permanently removes the build and its files (including the photo). This cannot be undone.",
      okLabel: "Delete this build",
    });
    if (yes) { await api("/api/builds/" + d.dataset.del, { method: "DELETE" }); await loadHistory(); }
  }
};
async function loadHistory() { const r = await api("/api/builds"); S.history = r.builds; S.max = r.max; S.keepDays = r.keep_days; renderHistory(); }

/* ---------- history-full dialog ---------- */
function openFull() { renderFull(); $("#dlgFull").showModal(); }
function renderFull() {
  const allStar = S.history.length > 0 && S.history.every(b => b.favorite);
  $("#fullMsg").innerHTML = allStar ? `All <b>${S.max}</b> of your builds are starred ★, and ZEIM never removes a starred build. Un-star or delete one to make room.` : `You can keep <b>${S.max} builds</b>. Delete one yourself, or let ZEIM remove the oldest one that isn't starred.`;
  $("#btnAutoDel").hidden = allStar;
  $("#fullList").innerHTML = S.history.map(b => `<div class="fl"><img src="${b.thumb}" alt=""><span><b>${b.favorite ? "★ " : ""}${esc(b.title)}</b><br><small>${MODE_LABEL[b.mode]} · ${ago(b.created)}</small></span>${b.favorite ? `<button class="btn small" data-funstar="${b.id}">Un-star</button>` : ""}<button class="btn small danger" data-fdel="${b.id}">Delete</button></div>`).join("");
  $("#btnRetry").disabled = S.history.length >= S.max;
}
$("#fullList").onclick = async e => {
  const u = e.target.closest("[data-funstar]");
  if (u) { await api(`/api/builds/${u.dataset.funstar}/favorite`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ favorite: false }) }); await loadHistory(); renderFull(); return; }
  const d = e.target.closest("[data-fdel]"); if (!d) return;
  await api("/api/builds/" + d.dataset.fdel, { method: "DELETE" }); await loadHistory(); renderFull();
};
S.pending = null;   // other workspaces (Edit) set this so the same "history full" dialog can retry their action
$("#btnRetry").onclick = () => { $("#dlgFull").close(); (S.pending || build)(false); };
$("#btnAutoDel").onclick = () => { $("#dlgFull").close(); (S.pending || build)(true); };

/* ---------- print dialog ---------- */
let printInfo = null, printId = null, printLabel = "", printB = null;
const printBuild = () => printB;
const sliceOpts = () => { const fd = new FormData(); fd.append("layer_height", $("#s_layer").value); fd.append("fill_density", $("#s_fill").value); fd.append("brim", $("#s_brim").value); if ($("#printerBlock") && !$("#printerBlock").hidden && $("#printerSel").value) fd.append("printer_id", $("#printerSel").value); fd.append("upright", $("#s_up").checked); fd.append("supports", $("#s_sup").checked); return fd; };
const isPhone = () => matchMedia("(max-width:768px),(pointer:coarse)").matches;
/* Print dialog body. Phones: the Creality Cloud app first (K1 owners), desktop-only slicer links tucked under "On a computer".
   The Creality route is a plain authenticated download of the 3MF, then the phone's own share sheet - no link, no deep link, nothing
   leaves ZEIM except what the person hands to the app they pick (reports/send-privacy.md). */
/* "Default slicer": Automatic = Creality Print / Cloud on phones or when a K1 printer is set up, else PrusaSlicer. */
function slicerDefault() { const v = printInfo.default_slicer; return v === "auto" ? (isPhone() ? "creality" : printInfo.effective_slicer) : v; }
function slicerArea(b, caps) {
  const dl = b.downloads["3mf"];
  const links = printInfo.slicers.map(s => `<a class="btn ${s.slicer === slicerDefault() ? "def" : ""}" href="${s.url}" title="${s.note || "Opens " + s.label}">Open in ${s.label}${s.slicer === slicerDefault() ? " ★" : ""}</a>`).join("") +
    (printInfo.slicer_links_disabled ? `<p class="muted small" style="grid-column:1/-1">${esc(printInfo.slicer_links_disabled)}</p>` : "");
  if (!isPhone()) {
    // desktop: Creality Print has no verified deep link, so it is a plain download (open the file from your Downloads folder)
    return `<a class="btn ${slicerDefault() === "creality" ? "def" : ""}" id="crDl" href="${dl}" download="ZEIM-build.3mf" title="Saves a 3MF. Open it in Creality Print.">⬇ Download 3MF for Creality Print${slicerDefault() === "creality" ? " ★" : ""}</a>` + links +
      `<a class="btn ghost" href="${dl}" download>…or download 3MF for another slicer</a>`;
  }
  const share = caps.share_ui && navigator.share && navigator.canShare && isSecureContext
    ? `<button type="button" class="btn" id="crShare" disabled>📤 Share… (choose Creality)</button>` : "";
  return `<div class="cre" style="grid-column:1/-1">
      <h5 style="margin:0 0 6px">★ Creality Cloud app <small class="help">(Creality K1 and other Creality printers)</small></h5>
      <div class="row"><a class="btn primary def" id="crDl" href="${dl}" download="ZEIM-build.3mf">⬇ Download 3MF ★</a>${share}</div>
      <ol class="help cre-steps"><li>Tap <b>Download 3MF</b>. It is saved in your <b>Files</b> or Downloads.</li>
        <li>Open the file from there, tap <b>Share</b> (or <b>Open in…</b>), then choose <b>Creality</b>.</li>
        <li>Slice and print from the Creality app.</li></ol>
      <p class="help" id="crStatus" role="status" aria-live="polite">Button names differ between phones and app versions. ZEIM does not connect to Creality; the app you pick gets the file. The Creality K1 profile in Settings is <b>experimental</b>.</p>
    </div>
    <details class="more slicers-more" style="grid-column:1/-1"><summary>On a computer</summary>
      <p class="help">These open a slicer installed on the <b>same computer</b> as this browser, so they don't work on a phone.</p>
      <div class="slicers">${links}<a class="btn ghost" href="${dl}" download>Download 3MF</a></div></details>`;
}
let crFile = null;
async function wireCreality(b, caps) {
  crFile = null;
  const btn = $("#crShare"); if (!btn) return;
  const my = printId;
  try {                               // pre-fetch with the cookie-checked download so share() runs straight from the tap
    const blob = await (await fetch(b.downloads["3mf"], { credentials: "same-origin" })).blob();
    if (my !== printId) return;
    for (const t of ["model/3mf", "application/octet-stream"]) {
      const f = new File([blob], "ZEIM-build.3mf", { type: t });
      let ok = false; try { ok = navigator.canShare({ files: [f] }); } catch { ok = false; }
      if (ok) { crFile = f; btn.disabled = false; return; }
    }
    btn.remove();
  } catch { btn.remove(); }
}
document.addEventListener("click", async e => {
  if (e.target.id !== "crShare" || !crFile) return;
  try { await navigator.share({ files: [crFile], title: "My ZEIM build" }); $("#crStatus").textContent = "Sent to the app you chose."; }      // files + title only: no url, ever
  catch (er) { if (er.name !== "AbortError") $("#crStatus").textContent = "That didn't work on this device. Use Download 3MF, then Share from the Files app."; }
});
async function openPrint(b) {
  if (!b?.id) return toast("Build something first.", "err");
  const id = b.id;   // the dialog is bound to THIS build; slice/send below use printId, never "whatever is current later"
  let caps = {};
  try { printInfo = await api(`/api/print/${id}/links`); caps = (await api("/api/me")).send || {}; } catch (e) { return toast(e.message, "err"); }
  printId = id; printB = b; printLabel = `${b.title || "build"} (${b.beginner ? "Beginner" : "Experienced"}, ${MODE_LABEL[b.mode] || "Edit"})`;
  $("#printWhich").textContent = "Printing: " + printLabel;
  $("#printHint").textContent = printInfo.hint;
  $("#slicerBtns").innerHTML = slicerArea(b, caps);
  wireCreality(b, caps);
  const bs = printInfo.builtin_slicer;
  $("#builtinState").textContent = bs.available ? "(PrusaSlicer CLI detected)" : "(slicer not installed)";
  $("#btnSlice").disabled = !bs.available;
  $("#s_up").checked = b.mode === "lithophane";
  // Honest lithophane print defaults on the quick Print dialog (99% — PrusaSlicer refuses 100% on grid/line).
  // Edit → Slice has the full Lithophane preset (100% rectilinear, first layer = layer height).
  if (b.mode === "lithophane") {
    $("#s_layer").value = "0.12";
    $("#s_fill").value = "99";
    $("#sliceOut").textContent = (bs.available ? "" : bs.message + " ") +
      "Lithophane tip: ~0.12 mm layers and near-solid fill. For the full Lithophane preset (100% rectilinear), open Edit → Slice.";
  } else {
    $("#sliceOut").textContent = bs.available ? "" : bs.message;
  }
  // SEND-6: the printer block exists only where it can really work (ZEIM on the user's own computer); hosted ZEIM promises nothing
  $("#printerBlock").hidden = !caps.printer_ui; $("#printerHosted").hidden = !!caps.printer_ui;
  startNowOff(); fillPrinterSel(); $("#sendOut").textContent = "";
  $("#dlgPrint").showModal();
}
$("#btnPrint").onclick = () => openPrint(S.current);          // Studio's own build; Edit passes its project (they used to share S.current: QA-1)
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
    else if (!r.ok) $("#sliceOut").textContent = r.code === "too_big" ? r.message : "Slicer failed: " + (r.log || r.message);
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
    <small>${p.purpose} · posting/verification: <i>Coming soon</i></small>
    ${p.state === "not_configured" ? `<small>Set <code>${p.env_vars[0]}</code> and <code>${p.env_vars[1]}</code>, then restart the server.</small>` : ""}</div>
    ${p.state === "connected" ? `<button class="btn small" data-disc="${p.id}">Disconnect</button>` : `<a class="btn small ${p.state === "not_configured" ? "" : "primary"}" ${p.state === "not_configured" ? 'style="pointer-events:none;opacity:.4"' : `href="/api/accounts/${p.id}/connect"`}>Connect</a>`}</div>`).join("");
}
$("#accList").onclick = async e => { const d = e.target.closest("[data-disc]"); if (d) { await api("/api/accounts/" + d.dataset.disc, { method: "DELETE" }); renderAccounts(); } };
/* Settings sections are real tabs: aria-selected, one Tab stop, arrow keys / Home / End move between them. */
const _tabs = $$(".tabs [role=tab]");
const pickTab = (b, focus) => {
  _tabs.forEach(x => { const on = x === b; x.classList.toggle("on", on); x.setAttribute("aria-selected", String(on)); x.tabIndex = on ? 0 : -1; });
  $$(".tab").forEach(t => t.hidden = t.id !== b.dataset.tab);
  if (focus) b.focus();
};
_tabs.forEach((b, i) => {
  b.onclick = () => pickTab(b);
  b.onkeydown = e => {
    const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: _tabs.length - 1 }[e.key];
    if (j === undefined) return;
    e.preventDefault(); pickTab(_tabs[(j + _tabs.length) % _tabs.length], true);
  };
});
$("#btnSettings").onclick = openSettings;
$$("[data-close]").forEach(b => b.onclick = () => b.closest("dialog").close());

/* ---------- init ---------- */
applyLevel(); applyMode(); loadHistory();
const q = new URLSearchParams(location.search);
if (q.get("connected")) { toast("Connected " + q.get("connected"), "ok"); history.replaceState({}, "", "/"); }
window.__photo3d = S;  // debugging / tests

export { S, api, toast, inlineMsg, clearInline, askConfirm, $, $$, esc, MODE_LABEL, ago, openPrint, printBuild, loadHistory, renderHistory, openFull, applyLevel, applyMode, isExpert };

/* ---------- Look: Warm (default) or Dark. Remembered on this device; nothing is sent anywhere. ---------- */
(() => {
  const b = $("#themeBtn"); if (!b) return;
  const paint = () => { const dark = document.documentElement.dataset.theme === "dark"; b.textContent = "Look: " + (dark ? "Dark" : "Warm"); b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", "Look: " + (dark ? "Dark" : "Warm") + ". Press to switch to " + (dark ? "Warm" : "Dark")); };
  b.onclick = () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.theme = dark ? "dark" : "warm"; } catch { } paint(); };
  paint();
})();

/* Every ".field" (label text beside the box, not around it) gets a real label link, including fields drawn later
   (Edit tools, printer rows, account links, dialogs). Screen readers then say the field's name, and tapping the label focuses the box. */
let _flN = 0;
function linkFieldLabels(root = document) {
  const fields = root.matches?.(".field") ? [root] : [];
  fields.push(...(root.querySelectorAll ? root.querySelectorAll(".field") : []));
  for (const f of fields) {
    const lab = f.querySelector(":scope > label"), inp = f.querySelector("input:not([type=checkbox]):not([type=radio]):not([type=hidden]),select,textarea");
    if (!lab || !inp || lab.htmlFor || lab.contains(inp) || (inp.labels && inp.labels.length)) continue;     // already linked: leave it
    if (!inp.id) inp.id = (f.closest("#expertOpts") ? "xo_" + (inp.name || _flN) : "fl_" + (inp.name || inp.dataset.f || inp.dataset.link || "f") + "_" + (++_flN));
    lab.htmlFor = inp.id;
  }
}
linkFieldLabels();
new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) if (n.nodeType === 1) linkFieldLabels(n); })
  .observe(document.body, { childList: true, subtree: true });
$("#widthRange").setAttribute("aria-label", "Width in millimetres (slider)");

// Skip link: focus whichever main view is showing (the four views share one page)
document.getElementById("skipLink")?.addEventListener("click", e => {
  const m = [...document.querySelectorAll("main")].find(x => !x.hidden);
  if (!m) return;
  e.preventDefault(); m.tabIndex = -1; m.focus(); m.scrollIntoView?.({ block: "start" });
});
window.__errText = errText;   // tests
