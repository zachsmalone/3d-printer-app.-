import { effectRGB, defaultEffect, lightRGB as fxBase, materialRGB, transmit, backingRGB, toHex } from "/static/lithlight.js";
import { Viewer } from "/static/viewer.js";

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const S = { mode: "lithophane", level: localStorage.level === "expert" ? "expert" : "beginner", me: null, preset: "standard", file: null, collageFiles: [],
            current: null, history: [], max: 5, settings: null };
const PRESET_HELP = {
  lithophane: { thin: "Lighter, glows brighter, more fragile (0.6–2.4 mm).", standard: "Balanced contrast and strength (0.8–3.2 mm).", thick: "Deep shadows, sturdy (1.0–4.0 mm)." },
  relief: { thin: "Shallow, subtle relief (≈4% of width).", standard: "Clear depth (≈7% of width).", thick: "Dramatic depth (≈11% of width)." },
  bust: { thin: "Shallower face, shorter pedestal, lighter rounded back.", standard: "Clear face depth, rounded back, solid round pedestal.", thick: "Deeper face, taller pedestal, fuller rounded back." },
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
window.zeimPhotoAck = () => (typeof pick !== "undefined" && pick.acked ? pick.acked() : "true");
const MODE_LABEL = { lithophane: "Lithophane", relief: "Relief", bust: "Bust", popart: "Pop-art", trace2d: "Logo & Drawing", ai3d: "2D→3D", edit: "Edited model" };

let viewer;
try { viewer = new Viewer($("#viewer")); } catch (e) { console.warn("WebGL unavailable", e); }

/* ---------- level / mode ---------- */
const isExpert = () => S.level === "expert";
const LEVEL_NAME = { beginner: "Beginner", expert: "Experienced" };
const LEVEL_ICO = { beginner: "<svg class=i aria-hidden=true focusable=false><use href=#i-leaf></use></svg>", expert: "<svg class=i aria-hidden=true focusable=false><use href=#i-wrench></use></svg>" };
const LEVEL_LINE = { beginner: "Beginner mode: ZEIM picks the settings for you.", expert: "Experienced mode: every setting is yours." };
const LEVEL_SAY = { beginner: "Beginner mode on. ZEIM picks the settings for you.", expert: "Experienced mode on. All the settings are showing." };
function say(t) { const e = $("#modeStatus"); e.textContent = ""; setTimeout(() => e.textContent = t, 60); }
function applyLevel(announce = false) {
  localStorage.level = S.level;
  document.body.dataset.level = S.level;
  $("#modeSel").value = S.level; $("#modeIco").innerHTML = LEVEL_ICO[S.level]; $("#modeLine").textContent = LEVEL_LINE[S.level];
  document.dispatchEvent(new CustomEvent("zeim:level"));
  $("#beginnerOpts").hidden = isExpert() || S.mode === "trace2d";
  $("#expertOpts").hidden = !isExpert() || S.mode === "trace2d"; $("#lithThk").hidden = !isExpert();
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
  $("#lithMatBox").hidden = S.mode !== "lithophane"; $("#backingBox").hidden = S.mode !== "lithophane"; $("#mboxBox").hidden = S.mode !== "lithophane"; $("#lithThk").hidden = !isExpert();
  const tr = S.mode === "trace2d";               // 'Logo & Drawing to 3D' has its own settings panel at both levels
  $("#traceOpts").hidden = !tr;
  $("#beginnerOpts").hidden = tr || isExpert(); $("#expertOpts").hidden = tr || !isExpert();
  if (!tr) $("#presetHelp").textContent = PRESET_HELP[S.mode][S.preset];
  document.dispatchEvent(new CustomEvent("zeim:mode", { detail: S.mode }));
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
  $("#lipBox").hidden = !(curved && litShape() !== "globe");     // sleeve / cup: the band and its slope
  if ($("#lightFitBox")) $("#lightFitBox").hidden = !(curved && litShape() === "nightlight");
  const FLAT = ["rect", "square", "circle", "heart", "star", "hexagon", "diamond", "oval", "triangle", "scallop"];
  if ($("#frameSizeBox")) $("#frameSizeBox").hidden = !(lit && FLAT.includes(litShape()));
  if ($("#frameStyleBox")) $("#frameStyleBox").hidden = !(lit && FLAT.includes(litShape()));
  if ($("#collageBox")) $("#collageBox").hidden = !(lit && FLAT.includes(litShape()));
  const curve = lit && litShape() === "curve";
  $("#curveOpts").hidden = !curve; syncBend();
  const hangOk = lit && FLAT.includes(litShape());
  $("#hangOpts").hidden = !hangOk; if (!hangOk) { $("#hang").value = ""; $("#stand").checked = false; if ($("#stand_caps")) $("#stand_caps").checked = false; }
  $("#hangHoleFld").hidden = !$("#hang").value;
  syncStandCaps();
  $("#placeEditor").hidden = !lit || litShape() === "rect" || curve || !S.file;   // curved panel: whole photo, its own aspect
  if (place && !$("#placeEditor").hidden) place.redraw();
}
function syncStandCaps() {
  const on = $("#stand")?.checked && !$("#hangOpts")?.hidden;
  if ($("#standCapsRow")) $("#standCapsRow").hidden = !on;
  if (!on && $("#stand_caps")) $("#stand_caps").checked = false;
}
$("#stand")?.addEventListener("change", syncStandCaps);
function syncCollage() {
  const on = $("#collageOn")?.checked;
  if ($("#collageOpts")) $("#collageOpts").hidden = !on;
  if (!on) { S.collageFiles = []; if ($("#collageExtra")) $("#collageExtra").value = ""; }
}
$("#collageOn")?.addEventListener("change", syncCollage);
$("#collageExtra")?.addEventListener("change", e => {
  S.collageFiles = [...(e.target.files || [])].slice(0, 5);
});
/* curved panel: bend 0..180 deg, optional built-in stand; the bed check uses the printer picked in Will-it-print */
let PRN = null; import("/static/printer.js").then(m => { PRN = m; }).catch(() => { });
function syncLip() {
  const w = +$("#lip_mm").value, t = $("#lip_taper").value;
  $("#lipOut").textContent = w ? w + " mm" : "0 (no band)";
  $("#taperOut").textContent = $("#taper_deg").value + "°";
  $("#lip_taper").disabled = $("#taper_deg").disabled = !w;
  $("#taper_deg").closest(".range").hidden = t === "none";
  const wn = $("#lipWarn");
  wn.hidden = !(w && t === "none"); wn.textContent = "A flat ledge overhangs at 90° and usually needs supports. You can still build it.";
}
["#lip_mm", "#lip_taper", "#taper_deg"].forEach(s => $(s).addEventListener("input", syncLip)); syncLip();

/* litho-up2: tone sliders, seamless tile, night-light fits, plate sizes */
const LIGHT_FITS = { tealight: 38, puck50: 50, puck70: 70, e12: 16 };
const FRAME_SIZES = { "4x6": 152.4, "5x7": 177.8, "8x10": 254, a6: 148, a5: 210 };
function syncToneLabels() {
  const b = $("#xo_bright"), c = $("#xo_contrast"), s = $("#xo_sharpen"), m = $("#xo_mmrep");
  if (b) $("#brightOut").textContent = (+b.value).toFixed(2).replace(/\.?0+$/, "") || "0";
  if (c) $("#contrastOut").textContent = (+c.value).toFixed(2).replace(/\.?0+$/, "") || "0";
  if (s) $("#sharpenOut").textContent = (+s.value).toFixed(1).replace(/\.0$/, "");
  if (m) $("#mmrepOut").textContent = (+m.value || 40) + " mm";
  if ($("#xo_tile") && m) m.disabled = !$("#xo_tile").checked;
}
["#xo_bright", "#xo_contrast", "#xo_sharpen", "#xo_mmrep", "#xo_tile"].forEach(s => {
  const el = $(s); if (el) el.addEventListener("input", syncToneLabels);
});
syncToneLabels();
function applyLightFit() {
  const id = $("#lightFit")?.value || "";
  if (id && LIGHT_FITS[id] != null) { $("#diameter_mm").value = LIGHT_FITS[id]; place.redraw?.(); }
}
function applyFrameSize() {
  const id = $("#frameSize")?.value || "";
  if (id && FRAME_SIZES[id] != null) {
    const w = Math.round(FRAME_SIZES[id]);
    $("#width_mm").value = w;
    if ($("#widthRange")) { $("#widthRange").value = Math.min(300, Math.max(30, w)); }
  }
}
if ($("#lightFit")) $("#lightFit").addEventListener("change", applyLightFit);
if ($("#frameSize")) $("#frameSize").addEventListener("change", applyFrameSize);
$("#diameter_mm")?.addEventListener("input", () => { if ($("#lightFit")) $("#lightFit").value = ""; });
$("#width_mm")?.addEventListener("input", () => { if ($("#frameSize")) $("#frameSize").value = ""; });
function syncBend() { const b = +$("#bend_deg").value; $("#bendOut").textContent = b + "°" + (b === 0 ? " (flat)" : b === 180 ? " (half circle)" : ""); }
$("#bend_deg").addEventListener("input", syncBend);
function curveFitNote(r) {
  const el = $("#curveFit"), f = r?.info?.bed_fit;
  if (!el || r?.info?.shape !== "curve" || !f) { if (el) el.textContent = ""; return; }
  el.textContent = f.ok ? `About ${f.size_mm.join(" × ")} mm. Fits a ${f.bed_mm.join(" × ")} mm bed.`
    : `About ${f.size_mm.join(" × ")} mm, larger than a ${f.bed_mm.join(" × ")} mm bed. A smaller width or more bend may help. You can still export it.`;
}
/* image placement inside the shape (Zach: shapes cut the photo off) - see /static/lithoplace.js */
import { mountPlace } from "/static/lithoplace.js";
const litAspect = () => {
  const sh = litShape(); if (sh === "globe") return 2; if (!CURVED.includes(sh)) return 1;
  const d = +$("#diameter_mm").value || 40, h = +$("#height_mm").value || 60;
  return Math.min(8, Math.max(0.3, Math.PI * (d + (sh === "nightlight" ? 1 : 0)) / Math.max(4, h - (sh === "cup" ? 2 : 0) - 4)));
};
var place = mountPlace($("#placeRoot"), { shape: litShape, aspect: litAspect });
["#diameter_mm", "#height_mm"].forEach(s => $(s).addEventListener("input", () => place.redraw()));
$("#shapeCards").onchange = applyShape;
$("#hang").onchange = applyShape;
$("#modeCards").onchange = () => { S.mode = ($("#modeCards input:checked") || {}).value || "lithophane"; applyMode(); document.dispatchEvent(new CustomEvent("zeim:mode", { detail: S.mode })); };       // radios: the browser keeps "selected" for assistive tech; we just read input:checked
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
  place.setImage(null); $("#placeEditor").hidden = true;
  $("#btnBuild").disabled = true; $("#buildHint").textContent = "Choose or take a photo to begin."; setPath(1, "Step 1 of 3: choose a photo.");
}
function setFile(f) {
  if (!f) return;
  if (f.size > MAX_PHOTO) { pick.msg("That photo is over 25 MB. Try a smaller one (JPG or PNG)."); return; }
  if (!f.size) { pick.msg("We couldn't open that photo. Try a JPG or PNG."); return; }
  S.file = f; S.pending = null;
  const img = $("#dropPreview"); img.onerror = () => { img.hidden = true; $("#dropHint").hidden = false; $("#dropHint").innerHTML = "<b>Photo ready</b><span>(This browser can't preview it, ZEIM will still open it.)</span>"; };
  img.src = URL.createObjectURL(f); img.hidden = false; $("#dropHint").hidden = true;
  place.setImage(img.src); applyShape();
  $("#btnBuild").disabled = false; $("#buildHint").textContent = "Photo ready: " + (f.name || "camera photo");
  setPath(1, "Photo chosen."); pick.msg(""); $("#photoChosen").hidden = false; $("#photoChosenName").textContent = "✔ " + (f.name || "camera photo");
  document.dispatchEvent(new CustomEvent("zeim:file", { detail: f }));
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
  try { const b = await (await fetch("/static/sample.jpg")).blob(); setFile(new File([b], "sample.jpg", { type: "image/jpeg" })); }
  catch { pick.msg("We couldn't load the sample image. Please try again."); }
};

/* ---------- build ---------- */
function formData(autoDelete) {
  const fd = new FormData();
  fd.append("file", S.file); fd.append("mode", S.mode); fd.append("photo_ack", pick.acked());      // CR-5 (the built-in sample needs no tick: the server knows that file)
  fd.append("beginner", !isExpert()); fd.append("preset", S.preset);
  fd.append("width_mm", $("#width_mm").value);
  if (S.mode === "lithophane") {
    fd.append("material", $("#lithMaterial").value);
    fd.append("shape", litShape());
    if (backingVal()) fd.append("backing", backingVal());
    if (litShape() === "curve") {
      fd.append("bend_deg", $("#bend_deg").value); if ($("#curveStand").checked) fd.append("stand", "true");
      if (PRN?.P?.pref?.printer_id) fd.append("printer_id", PRN.P.pref.printer_id);
    }
    if (CURVED.includes(litShape())) { fd.append("diameter_mm", $("#diameter_mm").value); fd.append("height_mm", $("#height_mm").value);
      if (litShape() !== "globe") { fd.append("lip_mm", $("#lip_mm").value); fd.append("lip_taper", $("#lip_taper").value); fd.append("taper_deg", $("#taper_deg").value); } }
    if (!$("#hangOpts").hidden) {
      if ($("#hang").value) { fd.append("hang", $("#hang").value); fd.append("hole_d", $("#hole_d").value); }
      if ($("#stand").checked) fd.append("stand", "true");
      if ($("#stand_caps")?.checked) fd.append("stand_caps", "true");
    }
    if ($("#frameStyleBox") && !$("#frameStyleBox").hidden && $("#frame_style")?.value)
      fd.append("frame_style", $("#frame_style").value);
    if ($("#collageOn")?.checked && S.collageFiles?.length) {
      fd.append("collage_layout", $("#collage_layout")?.value || "grid");
      S.collageFiles.forEach(f => fd.append("extra", f));
    }
    if (!["rect", "curve"].includes(litShape()) && !place.isDefault()) {
      const p = place.get(); fd.append("place_x", p.x.toFixed(4)); fd.append("place_y", p.y.toFixed(4));
      fd.append("place_scale", p.scale.toFixed(4)); fd.append("place_rotation", p.rotation.toFixed(2));
    }
  }
  if (autoDelete) fd.append("auto_delete_oldest", "true");
  if (S.mode !== "trace2d" && window.zeimSelect) { const sel = window.zeimSelect(S.mode); if (sel) fd.append("select", sel); }   // Select mode (selectmode.js)
  if (S.mode === "trace2d") { fd.set("beginner", "false"); fd.append("trace", JSON.stringify(window.zeimTraceOpts ? window.zeimTraceOpts() : {})); return fd; }
  if (isExpert()) {
    $$("#expertOpts [name]").forEach(el => {
      if (el.name === "width_mm") return;
      if (el.closest("[hidden]")) return;   // bust vs relief share base_mm/relief_mm names; only the visible panel counts
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
function buildDone(r) {                 /* shared success tail: a real build came back */
  showBuild(r); S.history = r.history; renderHistory(); $("#btnBuild").textContent = "Make it again with these settings";
  setPath(3, "Model ready. Step 3 of 3: save or print it.");
  toast("Your model is ready ✔", "ok");
  revealResult();
}
async function resumePending() {        /* the scanner was down: re-check the parked upload */
  setPath(2, "Checking your parked upload. Step 2 of 3."); $("#busy").hidden = false; $("#btnBuild").disabled = true; S.building = true;
  try {
    const r = await api(`/api/uploads/resume/${S.pending}`, { method: "POST" });
    if (r && r.status === "pending_scan") {   /* still parked: keep the resume action offered */
      pick.msg(r.detail || "The malware scanner is still unavailable — your upload is parked, not lost. Try again shortly.");
      return;
    }
    S.pending = null; $("#btnBuild").textContent = "Build my model";
    buildDone(r);
  } catch (e) {
    if (e.status === 422) { S.pending = null; $("#btnBuild").textContent = "Build my model"; pick.msg(e.message || "That file was flagged by the malware scanner. Nothing of it was kept — please choose a different photo."); return; }   /* terminal: the parked upload was discarded */
    if (e.status === 404) { S.pending = null; $("#btnBuild").textContent = "Build my model"; pick.msg("Your parked upload is no longer available — please choose your photo again."); return; }
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); openFull(); pick.msg("Your recent builds are full (5 of 5). Delete one, then press Build."); return; }   /* parked upload RETAINED: press Build to retry */
    toast("Resume didn't work: " + (e.message || "something went wrong") + " Your upload is still parked — try again.", "err");
  } finally { $("#busy").hidden = true; $("#btnBuild").disabled = !S.file; S.building = false; }
}
async function build(autoDelete = false) {
  if (S.pending) return resumePending();          /* parked earlier: re-check instead of re-uploading */
  if (!S.file) return;
  setPath(2, "Making your 3D model. Step 2 of 3."); $("#busy").hidden = false; $("#makingLine").hidden = false; $("#btnBuild").disabled = true; $("#btnPrint").disabled = true; $("#btnSendSheet").disabled = true; ["btnSaveWork","btnSendSlicer","btnSendCad"].forEach(id => { const b = $(id); if (b) b.disabled = true; }); S.building = true;   // no printing/sending a stale build mid-rebuild
  try {
    const r = await api("/api/generate", { method: "POST", body: formData(autoDelete) });
    if (r && r.status === "pending_scan") {        /* scanner down: parked, NOT built */
      S.pending = r.pending_id;
      setPath(2, "Your upload is parked — the malware scanner is temporarily unavailable.");
      pick.msg(r.detail || "The malware scanner is temporarily unavailable, so your upload is parked — not lost, and not shared.");
      $("#btnBuild").textContent = "▶ Resume my upload";
      toast("Your upload is parked, not lost — press Resume in a little while.", "ok");
      return;
    }
    buildDone(r);
  } catch (e) {
    if (e.status === 409 && e.body?.code === "history_full") { S.history = e.body.builds; renderHistory(); openFull(); pick.msg("Your recent builds are full (5 of 5). Delete one, then press Build."); }
    else if (e.status === 400 && /photo/i.test(e.message)) { clearFile(); pick.msg(e.message); }          // photo problems stay visible under the buttons; the refused photo is forgotten (QA-2)
    else { setPath(S.file ? 1 : 1, "That didn't work. Your photo is still here, so you can try again."); toast("We couldn't make your model: " + (e.message || "something went wrong") + " Your photo is still here. Try again.", "err"); }
  } finally { $("#busy").hidden = true; $("#makingLine").hidden = true; $("#btnBuild").disabled = !S.file; $("#btnPrint").disabled = false; $("#btnSendSheet").disabled = false; ["btnSaveWork","btnSendSlicer","btnSendCad"].forEach(id => { const b = $(id); if (b) b.disabled = false; }); S.building = false; }
}
$("#btnBuild").onclick = () => build(false);

function showBuild(r) {
  S.current = r; curveFitNote(r);
  document.dispatchEvent(new CustomEvent("zeim:build", { detail: r }));   // Select mode keeps the saved selection (selectmode.js)
  r.visibility = r.visibility || "private";
  $("#viewerEmpty").hidden = true; $("#vtools").hidden = false; $("#result").hidden = false;
  viewer?.load(r.preview, r.mode);
  if (r.mode === "lithophane" && r.params) setBacking(r.params.backing || "");   // the build's own backing (none if it had none)
  S.lightOn = r.mode === "lithophane" && !!backingVal(); syncLight();
  const st = r.stats, sz = st.size_mm.map(x => x.toFixed(1)).join(" × ");
  const nb = st.bodies?.length || 1;
  $("#viewer").setAttribute("aria-label", `3D preview: ${MODE_LABEL[r.mode] || "model"}, ${sz.replace(/ × /g, " by ")} millimetres, ${nb} ${nb > 1 ? "pieces" : "piece"}` +
    `${st.watertight ? "" : ", not watertight yet"}. Use the Turn left, Turn right and Reset view buttons to look around it.`);
  $("#stats").innerHTML = `<span class="pill">${MODE_LABEL[r.mode]}</span><span class="pill">${sz} mm</span>` +
    `<span class="pill">${st.triangles.toLocaleString()} triangles</span><span class="pill">${st.bodies.length} ${st.bodies.length > 1 ? "bodies" : "body"}</span>` +
    `<span class="pill ${st.watertight ? "ok" : "bad"}">${st.watertight ? "✔ watertight" : "✖ not watertight"}</span>`;
  const bw = (r.info?.warnings || []); $("#buildWarn").hidden = !bw.length; $("#buildWarn").innerHTML = bw.map(w => "<svg class=i aria-hidden=true focusable=false><use href=#i-alert></use></svg> " + esc(w)).join("<br>");
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
/* Lithophane printer type: Resin = thinner walls + finer detail. Starting suggestions (keep in step with app/core/autotune.py LITHO_MATERIALS, standard preset). */
const LITH_MAT = {   // [thin, standard, thick] min/max thickness; starting suggestions
  filament: { thk: [[0.6, 2.4], [0.8, 3.0], [1.0, 4.0]], resolution: 200, help: "Filament: 0.8–3.2 mm walls. Starting suggestions; test a small strip first." },
  resin: { thk: [[0.5, 2.5], [0.5, 2.8], [0.6, 3.0]], resolution: 400, help: "Resin: thinner 0.5–2.8 mm walls and finer detail. Starting suggestions; resins vary, so test a small strip first." },
};
const THK_IX = { thin: 0, standard: 1, thick: 2 };
function fillLithMat() {
  const d = LITH_MAT[$("#lithMaterial").value] || LITH_MAT.filament, [mn, mx] = d.thk[THK_IX[$("#lithThk").value] ?? 1];
  $("#lithMatHelp").textContent = d.help;
  const set = (k, v) => { const el = $(`#expertOpts [name="${k}"]`); if (el) el.value = v; };
  set("min_thickness", mn); set("max_thickness", mx); set("resolution", d.resolution);
}
$("#lithMaterial").onchange = fillLithMat; $("#lithThk").onchange = fillLithMat;
/* Memory box: 4 photos round a light (stateless API; preview is the assembled cube, downloads are the print parts) */
$("#lithMaterial").addEventListener("change", () => { $("#mbClear").value = $("#lithMaterial").value === "resin" ? 0.1 : 0.2; });
$("#mbHole").onchange = () => { $("#mbCustom").hidden = $("#mbHole").value !== "custom"; $("#mbLightH").value = $("#mbHole").value === "puck" ? 22 : 24; };
/* One photo per side. Choosing files fills sides 1..n; "Try the sample box" loads the 4 rose photos; any side can be replaced. */
const MB_SAMPLE = [1, 2, 3, 4].map(i => `/static/samples/membox/rose${i}.jpg`);
const mbSlots = [null, null, null, null];
function mbShowSides() {
  mbSlots.forEach((f, i) => {
    const img = $(`#mbSideImg${i + 1}`); if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    if (f) { img.dataset.url = URL.createObjectURL(f); img.src = img.dataset.url; img.alt = `Side ${i + 1} photo`; }
    else { delete img.dataset.url; img.removeAttribute("src"); img.alt = ""; }
  });
}
$("#mbFiles").addEventListener("change", () => {
  const fs = [...$("#mbFiles").files].slice(0, 4); mbSlots.fill(null); fs.forEach((f, i) => { mbSlots[i] = f; }); mbShowSides();
});
$("#mbTrySample").onclick = async () => {
  const st = $("#mbStatus");
  try {
    const fs = await Promise.all(MB_SAMPLE.map(async (u, i) => {
      const r = await fetch(u); if (!r.ok) throw new Error("sample photo missing");
      return new File([await r.blob()], `sample-rose-${i + 1}.jpg`, { type: "image/jpeg" });
    }));
    fs.forEach((f, i) => { mbSlots[i] = f; }); $("#mbFiles").value = ""; mbShowSides();
    st.textContent = "Sample box loaded: four rose photos on sides 1 to 4. Tap Preview box.";
  } catch (e) { st.textContent = "Couldn't load the sample box: " + (e.message || "try again"); }
};
let mbReplacing = 0;
document.querySelectorAll("#mbSides button[data-side]").forEach(b => { b.onclick = () => { mbReplacing = +b.dataset.side; $("#mbSideFile").click(); }; });
$("#mbSideFile").addEventListener("change", () => {
  const f = $("#mbSideFile").files[0]; if (f && mbReplacing) { mbSlots[mbReplacing - 1] = f; mbShowSides(); }
  $("#mbSideFile").value = "";
});
function mbForm(fmt) {
  const fs = mbSlots.filter(Boolean);
  if (fs.length > 4 || (fs.length < 4 && !$("#mbSample").checked)) throw new Error("Choose up to 4 photos, one per side, or let the sample photo fill empty sides.");
  const fd = new FormData();
  fs.forEach(f => fd.append("files", f));
  const kv = { fmt, style: $("#mbStyle").value, panel_mm: $("#mbSize").value, material: $("#lithMaterial").value, clearance_mm: $("#mbClear").value,
    hole_preset: $("#mbHole").value, hole_shape: $("#mbHoleShape").value, hole_w: $("#mbHoleW").value, hole_d: $("#mbHoleD").value,
    notch_mm: $("#mbNotch").value, lid: $("#mbLid").checked, photo_ack: $("#mbAck").checked,
    base: $("#mbBase").checked, light_h: $("#mbLightH").value, base_notch_mm: $("#mbBaseNotch").value, fill_sample: $("#mbSample").checked };
  for (const [k, v] of Object.entries(kv)) fd.append(k, v);
  return fd;
}
async function mbRun(fmt) {
  const st = $("#mbStatus");
  try {
    const fd = mbForm(fmt); st.textContent = "Making your memory box…";
    const r = await fetch("/api/memorybox", { method: "POST", body: fd });
    if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (_) {} throw new Error(m); }
    if (fmt !== "preview") {
      const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob());
      a.download = fmt === "3mf" ? "memory-box.3mf" : "memory-box-stls.zip"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      st.textContent = "Downloaded. Every part is its own object."; return;
    }
    const j = await r.json();
    S.current = { id: j.id, mode: "lithophane", info: j.info, params: { shape: "memorybox" }, preview: j.preview, stats: j.stats };
    $("#mbExport").disabled = !j.id; window.zeimMembox?.dims(j.info, $("#mbDims"));
    $("#viewerEmpty").hidden = true; $("#vtools").hidden = false;
    viewer?.load(j.preview, "lithophane"); S.lightOn = false; syncLight();
    const w = j.info.warnings || [];
    st.textContent = `Parts: ${j.info.parts.join(", ")}.` + (w.length ? " " + w.join(" ") : "") + " Tap Light on to see it lit.";
  } catch (e) { st.textContent = "Couldn't make the box: " + (e.message || "something went wrong"); }
}
$("#mbPreview").onclick = () => mbRun("preview"); $("#mbZip").onclick = () => mbRun("zip");
$("#mbExport").onclick = () => { if (S.current?.id) window.zeimExport?.open({ ws: "studio", bid: S.current.id }); };
/* "Light on": backlit lithophane preview estimate (thin = bright, thick = dark) */
const litShapeOf = r => r?.info?.shape || r?.params?.shape || "rect";
/* backing colour (Lithophane panel): what sits behind the print; it tints the Light on preview and is saved with the build */
const HEX6 = /^#[0-9a-f]{6}$/i;
function backingVal() { const v = $("#backing").value; if (v !== "custom") return v; const h = $("#backingHex").value.trim(); return HEX6.test(h) ? h.toLowerCase() : $("#backingRGB").value; }
const withBacking = light => toHex(transmit(fxBase(light), backingRGB(backingVal())));
function setBacking(v) {
  v = v || ""; const preset = ["", "warm", "cool", "paper"].includes(v);
  $("#backing").value = preset ? v : "custom";
  if (!preset && HEX6.test(v)) { $("#backingRGB").value = v; $("#backingHex").value = v; }
  $("#backingCustom").hidden = $("#backing").value !== "custom";
}
const saveBacking = () => { try { localStorage.lithBacking = backingVal(); } catch (_) {} };
function backingChanged() {
  $("#backingCustom").hidden = $("#backing").value !== "custom"; saveBacking();
  if (S.current?.mode === "lithophane") { S.lightOn = !!backingVal() || S.lightOn; syncLight(); }   // show the tint straight away
}
try { setBacking(localStorage.lithBacking || ""); } catch (_) {}
$("#backing").onchange = backingChanged;
$("#backingRGB").oninput = () => { $("#backingHex").value = $("#backingRGB").value; $("#backingHex").removeAttribute("aria-invalid"); backingChanged(); };
$("#backingHex").oninput = () => { const h = $("#backingHex").value.trim(), ok = HEX6.test(h);
  if (ok) { $("#backingRGB").value = h.toLowerCase(); $("#backingHex").removeAttribute("aria-invalid"); backingChanged(); } else $("#backingHex").setAttribute("aria-invalid", "true"); };
function syncLight() {
  const lit = S.current?.mode === "lithophane";
  $("#litLightBox").hidden = !lit;
  if (!lit) S.lightOn = false;
  $("#vLight").setAttribute("aria-pressed", S.lightOn ? "true" : "false");
  $("#vLightNote").hidden = !S.lightOn;
  const lc = $("#vLightColor").value; $("#vLightRGB").hidden = lc !== "custom";
  viewer?.setBacklight(!!S.lightOn, litShapeOf(S.current), withBacking(lc === "custom" ? $("#vLightRGB").value : lc));
  syncFx();
}
$("#vLight").onclick = () => { S.lightOn = !S.lightOn; syncLight(); };
/* remember the last light (named preset or custom #rrggbb bulb) */
try {
  const sv = localStorage.lithLight, rgb = localStorage.lithLightRGB;
  if (sv && [...$("#vLightColor").options].some(o => o.value === sv)) $("#vLightColor").value = sv;
  if (/^#[0-9a-f]{6}$/i.test(rgb || "")) $("#vLightRGB").value = rgb;
  $("#vLightRGB").hidden = $("#vLightColor").value !== "custom";
} catch (_) { /* private mode: no storage */ }
const saveLight = () => { try { localStorage.lithLight = $("#vLightColor").value; localStorage.lithLightRGB = $("#vLightRGB").value; } catch (_) {} };
$("#vLightColor").onchange = () => { saveLight(); syncLight(); };
$("#vLightRGB").oninput = () => { saveLight(); if (S.lightOn) syncLight(); };
/* LED-strip effects: one rAF loop that only runs while the light is on, the tab is visible and a viewer exists; it retints in place */
const reduceMotion = () => !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
try {
  $("#vLightFx").value = defaultEffect(localStorage.lithFx, reduceMotion(), localStorage.lithFxOptIn === "1");
  const sp = +localStorage.lithFxSpeed; if (sp >= 1 && sp <= 10) $("#vLightSpeed").value = sp;
} catch (_) {}
let fxRaf = 0, fxT0 = 0;
const fxColour = () => { const lc = $("#vLightColor").value; return transmit(fxBase(lc === "custom" ? $("#vLightRGB").value : lc), backingRGB(backingVal())); };
const matColour = () => { const m = $("#vMatColor").value; return materialRGB(m === "custom" ? $("#vMatRGB").value : m); };
try {
  const mc = localStorage.lithMat, mr = localStorage.lithMatRGB;
  if (mc && [...$("#vMatColor").options].some(o => o.value === mc)) $("#vMatColor").value = mc;
  if (/^#[0-9a-f]{6}$/i.test(mr || "")) $("#vMatRGB").value = mr;
} catch (_) {}
$("#vMatRGB").hidden = $("#vMatColor").value !== "custom";
const saveMat = () => { try { localStorage.lithMat = $("#vMatColor").value; localStorage.lithMatRGB = $("#vMatRGB").value; } catch (_) {} };
$("#vMatColor").onchange = () => { $("#vMatRGB").hidden = $("#vMatColor").value !== "custom"; saveMat(); syncFx(); };
$("#vMatRGB").oninput = () => { saveMat(); syncFx(); };
function fxTick(now) {
  fxRaf = 0;
  if (!S.lightOn || document.hidden || !viewer || $("#vLightFx").value === "steady") return;
  viewer.setTint(transmit(effectRGB($("#vLightFx").value, fxColour(), (now - fxT0) / 1000, +$("#vLightSpeed").value), matColour()));
  fxRaf = requestAnimationFrame(fxTick);
}
function syncFx() {
  const fx = $("#vLightFx").value;
  $("#vLightSpeedBox").hidden = fx === "steady";
  if (fx !== "strobe") $("#vStrobeWarn").hidden = true;
  if (fxRaf) { cancelAnimationFrame(fxRaf); fxRaf = 0; }
  if (S.lightOn && viewer && !document.hidden && fx !== "steady") { fxT0 = performance.now(); fxRaf = requestAnimationFrame(fxTick); }
  else if (S.lightOn && viewer) viewer.setTint(transmit(fxColour(), matColour()));
}
$("#vLightFx").onchange = e => {
  const fx = e.target.value;
  try {
    localStorage.lithFx = fx; if (reduceMotion()) localStorage.lithFxOptIn = fx === "steady" ? "0" : "1";
    if (fx === "strobe" && localStorage.lithStrobeWarned !== "1") { $("#vStrobeWarn").hidden = false; localStorage.lithStrobeWarned = "1"; }
  } catch (_) { if (fx === "strobe") $("#vStrobeWarn").hidden = false; }
  syncFx();
};
$("#vLightSpeed").oninput = e => { try { localStorage.lithFxSpeed = e.target.value; } catch (_) {} };
document.addEventListener("visibilitychange", syncFx);
$("#vLightSpeedBox").hidden = $("#vLightFx").value === "steady";

/* ---------- history ---------- */
function renderHistory() {
  $("#histCount").textContent = `${S.history.length} / ${S.max}`;
  const cards = S.history.slice().reverse().map(b => `
    <li class="hcard ${S.current?.id === b.id ? "cur" : ""}" data-id="${b.id}">
      <button type="button" class="thumbbtn" data-open="${b.id}" aria-label="Open ${esc(b.title)}"><img src="${b.thumb}" alt=""></button>
      <div class="meta"><b>${esc(b.title)}</b><span>${MODE_LABEL[b.mode]}${b.ai ? ' · <span class="ailbl">AI-made</span>' : ""}${b.visibility && b.visibility !== "private" ? " · " + b.visibility : " · <svg class=i aria-hidden=true focusable=false><use href=#i-lock></use></svg>"} · ${b.beginner ? "Beginner" : "Experienced"} · ${ago(b.created)}</span></div>
      <div class="row2"><button data-open="${b.id}">Open</button>
        <button data-send="${b.id}" title="Save this build or send it somewhere">Send…</button>
        <button data-fav="${b.id}" class="star ${b.favorite ? "on" : ""}" aria-pressed="${!!b.favorite}" aria-label="${b.favorite ? "Starred: kept until you delete it. Tap to un-star" : "Star to keep this build"}" title="${b.favorite ? "Starred - kept until you delete it" : "Star to keep it (builds are removed after " + (S.keepDays || 7) + " days)"}">${b.favorite ? '<svg class="i i-fill" aria-hidden=true focusable=false><use href=#i-star></use></svg>' : '<svg class=i aria-hidden=true focusable=false><use href=#i-star></use></svg>'}</button>
        <button data-del="${b.id}" aria-label="Delete this build"><svg class=i aria-hidden=true focusable=false><use href=#i-trash></use></svg></button></div></li>`);
  while (cards.length < Math.min(S.max, 5)) cards.push(`<li class="hslot">Empty slot</li>`);
  const note = $("#histNote"); if (note) note.textContent = `Builds are removed after ${S.keepDays || 7} days. Tap the star to keep one.`;
  $("#histList").innerHTML = cards.join("");
  document.dispatchEvent(new CustomEvent("zeim:history"));
}
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
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
  $("#fullMsg").innerHTML = allStar ? `All <b>${S.max}</b> of your builds are starred, and ZEIM never removes a starred build. Un-star or delete one to make room.` : `You can keep <b>${S.max} builds</b>. Delete one yourself, or let ZEIM remove the oldest one that isn't starred.`;
  $("#btnAutoDel").hidden = allStar;
  $("#fullList").innerHTML = S.history.map(b => `<div class="fl"><img src="${b.thumb}" alt=""><span><b>${b.favorite ? '<svg class="i i-fill" aria-hidden=true focusable=false><use href=#i-star></use></svg> ' : ""}${esc(b.title)}</b><br><small>${MODE_LABEL[b.mode]} · ${ago(b.created)}</small></span>${b.favorite ? `<button class="btn small" data-funstar="${b.id}">Un-star</button>` : ""}<button class="btn small danger" data-fdel="${b.id}">Delete</button></div>`).join("");
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
  const links = printInfo.slicers.map(s => `<a class="btn ${s.slicer === slicerDefault() ? "def" : ""}" href="${s.url}" title="${s.note || "Opens " + s.label}">Open in ${s.label}${s.slicer === slicerDefault() ? ' <svg class="i i-fill" aria-hidden=true focusable=false><use href=#i-star></use></svg><span class="sr-only">(your default)</span>' : ""}</a>`).join("") +
    (printInfo.slicer_links_disabled ? `<p class="muted small" style="grid-column:1/-1">${esc(printInfo.slicer_links_disabled)}</p>` : "");
  if (!isPhone()) {
    // desktop: Creality Print has no verified deep link, so it is a plain download (open the file from your Downloads folder)
    return `<a class="btn ${slicerDefault() === "creality" ? "def" : ""}" id="crDl" href="${dl}" download="ZEIM-build.3mf" title="Saves a 3MF. Open it in Creality Print."><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> Download 3MF for Creality Print${slicerDefault() === "creality" ? ' <svg class="i i-fill" aria-hidden=true focusable=false><use href=#i-star></use></svg><span class="sr-only">(your default)</span>' : ""}</a>` + links +
      `<a class="btn ghost" href="${dl}" download>…or download 3MF for another slicer</a>`;
  }
  const share = caps.share_ui && navigator.share && navigator.canShare && isSecureContext
    ? `<button type="button" class="btn" id="crShare" disabled><svg class=i aria-hidden=true focusable=false><use href=#i-upload></use></svg> Share… (choose Creality)</button>` : "";
  return `<div class="cre" style="grid-column:1/-1">
      <h5 style="margin:0 0 6px"><svg class="i i-fill" aria-hidden=true focusable=false><use href=#i-star></use></svg> Creality Cloud app <small class="help">(Creality K1 and other Creality printers)</small></h5>
      <div class="row"><a class="btn primary def" id="crDl" href="${dl}" download="ZEIM-build.3mf"><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> Download 3MF <svg class="i i-fill" aria-hidden=true focusable=false><use href=#i-star></use></svg><span class="sr-only">(your default)</span></a>${share}</div>
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
  if ($("#spoolOut")) $("#spoolOut").textContent = "";
  if ($("#printerHonest")) {
    const honesty = printInfo.printer_honesty || S.settings?.printer_honesty;
    const ver = printInfo.printer_verification || S.settings?.printer_verification || "Simulated";
    $("#printerHonest").textContent = honesty
      || (ver === "Live API"
           ? "Moonraker / OctoPrint: Live API (real HTTP). Not yet confirmed on Zach's Creality K1 hardware. Bambu / stubs stay Simulated."
           : ver + " until a real-hardware pass. Tested with a pretend printer only.");
  }
  $("#dlgPrint").showModal();
}
$("#btnPrint").onclick = () => openPrint(S.current);          // Studio's own build; Edit passes its project (they used to share S.current: QA-1)
const startNowOff = () => { $("#startNow").checked = false; };          // "Start print" is always a separate, unchecked choice
const TYPE_LABEL = { octoprint: "OctoPrint", moonraker: "Moonraker (Klipper)", bambu: "Bambu Lab LAN" };
function fillPrinterSel() {
  const ps = printInfo.printers;
  $("#printerSel").innerHTML = ps.length ? ps.map(p => `<option value="${p.id}">${esc(p.name)} (${esc(p.profile_label || TYPE_LABEL[p.type] || p.type)})</option>`).join("") : `<option value="">No printers configured — add one in Settings</option>`;
  $("#btnSend").disabled = !ps.length;
  if ($("#btnQueueAdd")) $("#btnQueueAdd").disabled = !ps.length;
  const live = $("#liveStatus");
  if (live) live.hidden = !ps.length;
  if (ps.length) refreshLiveStatus();
}
async function refreshLiveStatus() {
  const id = $("#printerSel")?.value; const out = $("#liveStatusText"); const cam = $("#camRow");
  if (!id || !out) return;
  out.textContent = "Checking printer…";
  try {
    const r = await api(`/api/printers/${id}/status`);
    const pct = r.progress_pct != null ? ` · ${Number(r.progress_pct).toFixed(1)}%` : "";
    const job = r.job_name ? ` · ${r.job_name}` : "";
    out.textContent = (r.ok ? `${r.state || "ok"}${pct}${job}` : (r.message || "Unavailable"))
      + (r.verification ? ` · ${r.verification}` : "");
    if (cam) {
      cam.hidden = false;
      const img = $("#camSnap");
      if (img) img.src = `/api/printers/${id}/camera?t=${Date.now()}`;
    }
  } catch (e) { out.textContent = e.message; }
}
$("#printerSel")?.addEventListener("change", () => refreshLiveStatus());
$("#btnRefreshStatus")?.addEventListener("click", () => refreshLiveStatus());
$("#btnCamRefresh")?.addEventListener("click", () => {
  const id = $("#printerSel")?.value; const img = $("#camSnap");
  if (id && img) img.src = `/api/printers/${id}/camera?t=${Date.now()}`;
});
async function controlSelected(action) {
  const id = $("#printerSel")?.value; if (!id) return;
  $("#liveStatusText").textContent = `Sending ${action}…`;
  try {
    const fd = new FormData(); fd.append("action", action);
    const r = await api(`/api/printers/${id}/control`, { method: "POST", body: fd });
    $("#liveStatusText").textContent = (r.ok ? "✔ " : "✖ ") + (r.message || action) + (r.verification ? ` · ${r.verification}` : "");
    refreshLiveStatus();
  } catch (e) { $("#liveStatusText").textContent = "✖ " + e.message; }
}
$("#btnPause")?.addEventListener("click", () => controlSelected("pause"));
$("#btnResume")?.addEventListener("click", () => controlSelected("resume"));
$("#btnCancel")?.addEventListener("click", () => {
  if (confirm("Stop this print on the printer? You cannot undo that from ZEIM.")) controlSelected("cancel");
});
$("#btnQueueAdd")?.addEventListener("click", async () => {
  const id = $("#printerSel")?.value; if (!id || !printId) return;
  const fd = new FormData(); fd.append("printer_id", id); fd.append("build_id", printId);
  fd.append("name", printLabel || printId); fd.append("start_on_send", $("#startNow").checked);
  try {
    const r = await api("/api/print-queue", { method: "POST", body: fd });
    $("#sendOut").textContent = r.ok ? "✔ Added to manual queue (start it from All printers)." : ("✖ " + (r.message || "failed"));
  } catch (e) { $("#sendOut").textContent = "✖ " + e.message; }
});
$("#btnOpenBoard")?.addEventListener("click", () => window.ZEIM_openPrinterBoard?.());

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
  try {
    const r = await api(`/api/send/${printId}`, { method: "POST", body: fd });
    $("#sendOut").textContent = (r.ok ? "✔ " : "✖ ") + (r.message || r.log || "failed") + (r.verification ? ` · ${r.verification}` : "");
    if ($("#spoolOut")) $("#spoolOut").textContent = r.spool?.message || (r.stage === "spool" ? (r.message || "") : "");
    if (r.ok) refreshLiveStatus();
  } catch (e) { $("#sendOut").textContent = "✖ " + e.message; }
};

/* ---------- settings ---------- */
async function openSettings() {
  S.settings = await api("/api/settings");
  $("#set_slicer").value = S.settings.default_slicer; $("#set_base").value = S.settings.public_base_url || "";
  const edit = !!S.settings.can_edit;
  $("#set_slicer").disabled = !edit; $("#set_base").disabled = !edit;
  if ($("#setLock")) $("#setLock").hidden = edit || !S.settings.printer_manage;
  renderPrinters(); await renderAccounts(); $("#dlgSettings").showModal();
}
function renderPrinters() {
  const types = S.settings.printer_types;
  const dc = !!S.settings.direct_control;
  const ver = S.settings.printer_verification || "Simulated";
  $("#printerList").innerHTML = S.settings.printers.map((p, i) => `<div class="printer" data-i="${i}">
    <div class="grid2">
      <div class="field"><label>Name</label><input data-f="name" value="${esc(p.name || "")}"></div>
      <div class="field"><label>Type</label><select data-f="type">${types.map(t => `<option value="${t.type}" ${t.type === p.type ? "selected" : ""}>${t.label}</option>`).join("")}</select></div>
      ${dc ? `<div class="field"><label>Address</label><input data-f="url" value="${esc(p.url || "")}" placeholder="http://printer.local:7125"></div>` : ""}
      <div class="field"><label>API key ${p.has_key ? "<em>(stored — leave blank to keep)</em>" : ""}</label><input data-f="api_key" type="password" placeholder="${p.has_key ? "••••••••" : ""}"></div>
      <div class="field"><label>Preset</label><select data-f="profile"><option value="">None (generic)</option>${(S.settings.printer_presets || []).map(x => `<option value="${x.id}" ${x.id === p.profile ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select></div>
      <div class="field"><label>Bed X mm</label><input data-f="bed_x" type="number" value="${p.bed_x || 250}"></div>
      <div class="field"><label>Bed Y mm</label><input data-f="bed_y" type="number" value="${p.bed_y || 210}"></div>
      <div class="field"><label>Serial <em>Bambu</em></label><input data-f="serial" value="${esc(p.serial || "")}" placeholder="01P…"></div>
      <div class="field"><label>Spool left (g)</label><input data-f="spool_remaining_g" type="number" step="1" value="${p.spool_remaining_g != null ? p.spool_remaining_g : ""}" placeholder="optional"></div>
    </div>
    <div class="row" style="flex-wrap:wrap;gap:10px;margin:.4rem 0">
      <label class="inl"><input type="checkbox" data-f="alert_done" ${p.alert_done ? "checked" : ""}> Alert when done</label>
      <label class="inl"><input type="checkbox" data-f="alert_failed" ${p.alert_failed ? "checked" : ""}> Alert on fail</label>
      <label class="inl"><input type="checkbox" data-f="watch_failures" ${p.watch_failures ? "checked" : ""}> Failure watch (pause only)</label>
      <label class="inl"><input type="checkbox" data-f="timelapse" ${p.timelapse ? "checked" : ""}> Timelapse folder</label>
    </div>
    <p class="help">${types.find(t => t.type === p.type)?.hint || ""}</p>
    ${(S.settings.printer_presets || []).find(x => x.id === p.profile) ? `<p class="help"><b>Experimental.</b> ${esc(S.settings.printer_presets.find(x => x.id === p.profile).hint)}</p>` : ""}
    ${dc
      ? `<p class="help">Direct control is on for this install. Addresses are checked against SSRF rules before every request. This printer path: <b>${esc((p.type === "moonraker" || p.type === "octoprint") ? "Live API" : (p.type === "bambu" ? "Simulated" : ver))}</b>${(p.type === "moonraker" || p.type === "octoprint") ? " (real HTTP; not yet Hardware-tested on Zach's K1)." : (p.type === "bambu" ? " — Bambu LAN not confirmed on real hardware; keep Open in Bambu Studio as fallback." : ".")}</p>`
      : `<p class="help">Direct control is off: slice, download the G-code and print from your printer's own app. (Arbitrary printer URLs can no longer be entered — they were an SSRF risk.)</p>`}
    <p class="help">${(S.settings.printer_honesty || "Moonraker / OctoPrint: Live API. Bambu / stubs: Simulated.")}</p>
    <button class="btn small" data-test="${i}" ${p.id ? "" : "disabled title='Save first, then test'"}>Test connection</button> <button class="btn small danger" data-rm="${i}">Remove</button>
    <p class="help" data-testout="${i}" role="status" aria-live="polite">${p.id ? "A test only asks the printer if it is there. It never starts a print." : "Save settings first, then you can test the connection."}</p></div>`).join("") || `<p class="help">No printers yet.</p>`;
}
function readPrinters() {
  const dc = !!S.settings.direct_control;
  return $$("#printerList .printer").map(el => {
    const p = { ...S.settings.printers[+el.dataset.i] };
    $$("[data-f]", el).forEach(i => {
      if (i.type === "checkbox") p[i.dataset.f] = i.checked;
      else p[i.dataset.f] = i.value;
    });
    if (!dc) delete p.url;                          /* production / direct control off: never send a URL */
    return p;
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
  const printers = readPrinters();
  try {
    if (S.settings?.can_edit) {
      const body = { default_slicer: $("#set_slicer").value, public_base_url: $("#set_base").value.trim(), printers };
      await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    } else if (S.settings?.printer_manage) {
      await api("/api/settings/printers", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ printers }) });
    } else {
      toast("Server settings can only be changed by the server admin.", "err");
      return;
    }
    toast("Settings saved", "ok"); $("#dlgSettings").close();
  } catch (e) { toast(e.message, "err"); }
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

export { S, api, toast, inlineMsg, clearInline, askConfirm, $, $$, esc, MODE_LABEL, ago, openPrint, printBuild, loadHistory, renderHistory, openFull, applyLevel, applyMode, isExpert, showBuild };

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
/* E: Send to… / Back from CAD reopens the Studio model (static/handoff.js) */
document.addEventListener("zeim:open-build", async e => { try { const r = await api("/api/builds/" + encodeURIComponent(e.detail)); if (S.current?.id) return; S.mode = r.mode; applyMode(); showBuild(r); } catch { } });

$("#btnOpenBoardFromSettings")?.addEventListener("click", () => window.ZEIM_openPrinterBoard?.());
