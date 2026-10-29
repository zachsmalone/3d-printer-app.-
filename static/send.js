/* The Send sheet (SEND-2..9, reports/design-ios-send.md): one place to save a build or hand it to another app.
   The SERVER decides what a person may do (/api/me -> send{...}, enforced again on every route); this file only draws what the
   server allows. Download is the product. Share/Email use the system share sheet and stay OFF until the device spike (SEND-0)
   passed (the server decides whether the share sheet is offered). No link is ever put in a share (no url field, no signed-link route). */
import { S, api, toast, $, $$, esc, openPrint, printBuild, isExpert } from "/static/app.js";

const FMTS = ["3mf", "stl", "obj"];
const MIMES = { "3mf": ["model/3mf", "application/octet-stream"], stl: ["model/stl", "application/octet-stream"], obj: ["model/obj", "application/octet-stream"] };
const BIG = 50 * 1024 * 1024;
const MODE_NAME = { lithophane: "Lithophane", relief: "Relief", popart: "Pop art", edit: "Edit", sculpt: "Sculpt" };
let lastCaps = null;
let X = null;                                   // the open sheet: bound to ONE build, never to "whatever is current later"

const mb = n => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
function saveFileName(b, fmt) {
  const stem = String(b?.file_name || "").replace(/[\\/:*?"<>|]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80);
  return (stem || "ZEIM-build") + "." + fmt;
}
const getFmt = () => { const f = localStorage.sendFmt; return FMTS.includes(f) ? f : "3mf"; };
const shareLabel = () => /iPad/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) ? "iPad" : "iPhone";

export async function openSend(b) {
  if (!b?.id) return toast("Build something first.", "err");
  if (S.building) return toast("Wait for your build to finish.", "err");
  let caps;
  try { caps = lastCaps = (await api("/api/me")).send || { download: true }; }
  catch (e) { if (navigator.onLine !== false || !lastCaps) return toast(e.message, "err"); caps = lastCaps; }   // offline: reuse what the server said last time (it still enforces everything)
  const adult = caps.role === "adult";
  X = { b, caps, adult, fmt: getFmt(), file: null, blob: null, seq: 0,
        label: `${b.title || "build"} (${b.beginner ? "Beginner" : "Experienced"}, ${MODE_NAME[b.mode] || b.mode || "Edit"})` };
  render();
  $("#dlgSendSheet").showModal();
  prepare();
}

function shareAllowed() {
  return !!(X.caps.share_ui && navigator.share && navigator.canShare && isSecureContext);
}

function render() {
  const { b, caps, adult } = X, fmt = X.fmt, sizes = b.sizes || {};
  const photo = b.kind !== "edit";
  $("#ssTitle").textContent = adult ? "Send or save your model" : "Save your model";
  const chooser = adult ? `<div class="fmt" role="radiogroup" aria-label="File type">${FMTS.map(f =>
    `<button type="button" role="radio" aria-checked="${f === fmt}" class="${f === fmt ? "on" : ""}" data-fmt="${f}">${f.toUpperCase()}${sizes[f] ? `<small>${mb(sizes[f])}</small>` : ""}</button>`).join("")}</div>
    <p class="help" id="ssFmtHint">${{ "3mf": "Best for most slicers. Smallest file.", stl: "A triangle mesh. Shapr3D opens it as a reference shape, not an editable solid.", obj: "For other 3D apps." }[fmt]}</p>` : "";
  const fileLine = !adult ? "" : !isExpert()
    ? `<div class="help">File: 3D print file (3MF)<details class="inl"><summary>Different file type?</summary>${chooser}</details></div>` : chooser;
  const save = [], other = [], print = [];
  const dlName = saveFileName(b, fmt);
  save.push(`<a class="btn primary sheet-row" id="ssSave" href="/files/${b.id}/model.${fmt}" download="${esc(dlName)}"><b>${adult ? "<svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> Save to this device" : "<svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> Download my model"}</b>
    <small>${b.file_name ? "Saves as " + esc(dlName) + "." : adult ? "Goes to your Files or Downloads." : "Saves a file on this device."}</small></a>`);
  if (b.original) save.push(`<a class="btn ghost sheet-row" href="${b.original}" download><b><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> Your original file</b><small>The file you opened, unchanged.</small></a>`);
  if (adult && shareAllowed()) {
    other.push(`<button type="button" class="btn sheet-row" id="ssShare" disabled><b><svg class=i aria-hidden=true focusable=false><use href=#i-upload></use></svg> Share… <span class="untested">untested</span></b><small>Opens the ${shareLabel()} share sheet, where you pick the app (Files, Mail and more). Not tried on a real iPhone or iPad yet.</small></button>`);
    other.push(`<button type="button" class="btn sheet-row" id="ssEmail" disabled><b><svg class=i aria-hidden=true focusable=false><use href=#i-mail></use></svg> Email it to myself <span class="untested">untested</span></b><small>Your Mail app sends it. ZEIM doesn't. Not tried on a real iPhone or iPad yet.</small></button>`);
    other.push(`<button type="button" class="btn sheet-row" id="ssShapr" disabled><b><svg class=i aria-hidden=true focusable=false><use href=#i-cube></use></svg> Share as STL for Shapr3D… <span class="untested">untested</span></b><small>Opens as a reference shape, not editable. When Shapr3D asks, choose <b>millimetres</b>. Pick Shapr3D on the next screen. Not tried with the real app yet.</small></button>`);
  }
  if (caps.printer_ui) print.push(`<button type="button" class="btn sheet-row" id="ssPrinter"><b><svg class=i aria-hidden=true focusable=false><use href=#i-printer></use></svg> Send to my printer</b><small>Opens the printer step in Print. Moonraker and OctoPrint are Live API, not Hardware-tested. Bambu stays Simulated. Test connection never starts a print.</small></button>`);
  const group = (title, items, id) => items.length ? `<h3 class="group" id="${id}">${title}</h3><ul class="rows" aria-labelledby="${id}">${items.map(h => `<li>${h}</li>`).join("")}</ul>` : "";
  const notes = [];
  if (caps.role !== "adult") notes.push("Sending to other apps isn't available for your account. You can download your build.");
  if (adult && !shareAllowed()) notes.push(!caps.share_ui ? "Want it in another app? Save it first, then open the Files app, press and hold the file, and tap Share."
    : !isSecureContext ? "Sharing to other apps needs a secure (https) address. Save it first, then open the Files app, press and hold the file, and tap Share."
    : "Want it in another app? Save it first, then open the Files app, press and hold the file, and tap Share.");
  if (photo) notes.push(adult ? "A lithophane or relief <b>is</b> the photo. Anyone who gets the file can see it. Don't send photos of other people without their OK."
                              : "A lithophane is your photo turned into a 3D shape. Anyone with the file can see the picture.");
  notes.push(adult ? "ZEIM sends nothing to other apps. The app you pick gets the file. Only send photos you have permission to use."
                   : "Only share photos and builds you made, or have permission to use.");
  if (adult) notes.push("If you delete this build in ZEIM, copies you already sent stay where they are.");
  const more = adult ? `<details class="more"><summary>More places</summary><p><a href="https://www.crealitycloud.com/" target="_blank" rel="noopener noreferrer">Creality Cloud ↗ (opens their website)</a><br>
    <small>This only opens the Creality Cloud website. You upload there yourself, and their rules apply. ZEIM does not connect to Creality, and we have not tested uploading a ZEIM file there yet.</small></p></details>` : "";
  $("#ssBody").innerHTML = `<p class="help">${adult ? "Choose a file type, then where to send it." : "Your build is a file. You can save it on this device."}</p>
    <p class="help"><b id="ssWhich">Sending: ${esc(X.label)}</b></p>
    ${fileLine}
    <p class="help" id="ssStatus" role="status" aria-live="polite"></p><p class="help bad" id="ssAlert" role="alert"></p>
    <div class="sheet-rows">${group("Save it", save, "ssG1")}${group("Send to another app", other, "ssG2")}${group("Print", print, "ssG3")}</div>${more}
    ${notes.filter(Boolean).map(n => `<p class="help">${n}</p>`).join("")}
    <div class="row end"><button type="button" class="btn" data-close-sheet>Close</button></div>`;
  $("#ssSave").focus();
}

/* Pre-fetch the real file with the cookie-checked download so share() can run straight from the click (no await in between). */
async function prepare() {
  const my = ++X.seq; if (!$("#ssShare")) return;
  const set = t => { if (X && my === X.seq && $("#ssStatus")) $("#ssStatus").textContent = t; };
  const size = (X.b.sizes || {})[X.fmt];
  X.file = null;
  if (size && size > BIG) return set(`This file is big (${mb(size)}). Sharing may fail. Save it instead, or pick 3MF, which is smaller.`);
  if (navigator.onLine === false) { $("#ssAlert").textContent = "You're offline. Connect to the internet to get your file."; return; }
  set("Getting your file ready…");
  try {
    const r = await fetch(`/files/${X.b.id}/model.${X.fmt}`, { credentials: "same-origin" });
    if (r.status === 404) { $("#ssAlert").textContent = "That build isn't here anymore."; return; }
    if (!r.ok) throw new Error("fetch");
    const blob = await r.blob(); if (!X || my !== X.seq) return;
    if (blob.size > BIG) return set(`This file is big (${mb(blob.size)}). Sharing may fail. Save it instead, or pick 3MF, which is smaller.`);
    let file = null;
    for (const t of MIMES[X.fmt]) {
      const f = new File([blob], `ZEIM-build.${X.fmt}`, { type: t });          // generic name: never the title
      let ok = false; try { ok = navigator.canShare({ files: [f] }); } catch { ok = false; }
      if (ok) { file = f; break; }
    }
    if (!file) { set(""); $$("#ssShare,#ssEmail,#ssShapr").forEach(e => e.remove()); return; }   // Share is a bonus; Save stays
    X.file = file; set("");
    $$("#ssShare,#ssEmail").forEach(e => e.disabled = false);
    if ($("#ssShapr")) $("#ssShapr").disabled = false;
  } catch { if (X && my === X.seq) $("#ssAlert").textContent = navigator.onLine === false ? "You're offline. Connect to the internet to get your file." : "That didn't work on this device. Save it instead."; }
}

async function doShare(file, button) {
  $("#ssAlert").textContent = "";
  try {
    await navigator.share({ files: [file], title: "My ZEIM build" });         // no url, no text link, ever
    $("#ssStatus").textContent = "Sent to the app you chose.";
  } catch (e) {
    if (e.name === "AbortError") { button.focus(); return; }
    if (e.name === "NotAllowedError") { $("#ssAlert").textContent = "Tap Share again."; button.focus(); return; }
    $("#ssAlert").textContent = "That didn't work on this device. Save it instead."; $("#ssSave").focus();
  }
}

document.addEventListener("click", async e => {
  const sheet = e.target.closest("#dlgSendSheet"); if (!sheet || !X) return;
  const t = e.target.closest("button,a"); if (!t) return;
  if (t.hasAttribute("data-close-sheet")) return $("#dlgSendSheet").close();
  if (t.dataset.fmt) { X.fmt = t.dataset.fmt; localStorage.sendFmt = X.fmt; render(); prepare(); $(`#ssBody [data-fmt="${X.fmt}"]`)?.focus(); return; }
  if (t.id === "ssSave") {
    e.preventDefault();
    const name = t.getAttribute("download") || ("ZEIM-build." + (X.fmt || "3mf"));
    const href = t.getAttribute("href");
    $("#ssAlert").textContent = "";
    $("#ssStatus").textContent = "Downloading…";
    try {
      const r = await fetch(href, { credentials: "same-origin" });
      if (!r.ok) { $("#ssAlert").textContent = "That file could not be saved."; $("#ssStatus").textContent = ""; return; }
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      $("#ssStatus").textContent = "Saved! Look in your Files or Downloads.";
    } catch {
      $("#ssAlert").textContent = "That file could not be saved.";
      $("#ssStatus").textContent = "";
    }
    return;
  }
  if (t.id === "ssShare" || t.id === "ssEmail") { if (X.file) doShare(X.file, t); return; }
  if (t.id === "ssShapr") {
    if (X.fmt !== "stl") { X.fmt = "stl"; localStorage.sendFmt = "stl"; render(); await prepare(); $("#ssAlert").textContent = "Now STL is chosen. Tap the Shapr3D button again."; return; }
    if (X.file) doShare(X.file, t); return;
  }
  if (t.id === "ssPrinter") { const b = X.b; $("#dlgSendSheet").close(); openPrint(b); return; }
});
$("#dlgSendSheet").addEventListener("close", () => { X = null; });

$("#btnSendSheet").onclick = () => openSend(S.current);
$("#printToSend").onclick = () => { const b = printBuild(); $("#dlgPrint").close(); openSend(b); };
$("#histList").addEventListener("click", async e => {
  const t = e.target.closest("[data-send]"); if (!t) return;
  openSend(S.history.find(x => x.id === t.dataset.send));
});
document.addEventListener("zeim:send-build", e => { if (e.detail) openSend(e.detail); });
