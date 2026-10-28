/* "Send to…": one hand-off between sections, the same everywhere.
   Studio/Lithophane → three buttons (Save work · Send to Slicer/TorchC0 · Send to CAD); Slicer → CAD · TorchC0, TorchC0 → CAD · Slicer (CAD → … lives in cad.js).
   The same mesh travels (orientation and size kept), units go with it, work is saved first, and a "Back to …" chip
   gives a one-tap way back. Only the slicer that matches the printer type (FDM / Resin) is offered.
   Kept models: Studio remembers the build it sent (sessionStorage zeim.studio.return) so Back from CAD reopens it; TorchC0 keeps
   its file in this browser (IndexedDB) so leaving and coming back, or a reload, does not lose it. */
import { S, api, toast, $, esc } from "/static/app.js";
import { isPublishUrl } from "/static/workspace-controls.js";

const NAMES = { lithophane: "Studio", slicer: "FDM Slicer", torchc0: "TorchC0", cad: "CAD" };
const DESC = { cad: "Design and edit it with exact sizes", slicer: "Slice it for your filament printer", torchc0: "Hollow, support and prepare it for resin" };
const ICON = `<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-send"/></svg>`;
const kind = () => document.body.dataset.printKind === "resin" ? "resin" : "fdm";
const FD = o => { const fd = new FormData(); Object.entries(o).forEach(([k, v]) => fd.append(k, v)); return fd; };
const ss = { get: k => { try { return sessionStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { sessionStorage.setItem(k, v); } catch { } }, del: k => { try { sessionStorage.removeItem(k); } catch { } } };
const beginner = () => document.body.dataset.level !== "expert";

export function targetsFor(src, k = kind()) {
  return ["cad", "slicer", "torchc0"].filter(t => t !== src && !(t === "slicer" && k === "resin") && !(t === "torchc0" && k === "fdm"));
}
function sourceNow() { const v = document.body.dataset.view; return v === "slicer" || v === "torchc0" ? v : "lithophane"; }

/* ---- TorchC0 keeps its file (IndexedDB, this browser only) ---- */
const IDB = "zeim-handoff", ST = "files", MAXB = 80 * 1048576;
function idb() { return new Promise((ok, no) => { const r = indexedDB.open(IDB, 1); r.onupgradeneeded = () => r.result.createObjectStore(ST); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); }); }
async function idbDo(mode, fn) { const db = await idb(); return new Promise((ok, no) => { const tx = db.transaction(ST, mode), r = fn(tx.objectStore(ST)); tx.oncomplete = () => { ok(r?.result); db.close(); }; tx.onerror = () => { no(tx.error); db.close(); }; }); }
export const keepTorchFile = f => f && f.size <= MAXB ? idbDo("readwrite", s => s.put({ name: f.name, type: f.type, blob: f, t: Date.now() }, "torchc0")).catch(() => { }) : Promise.resolve();
const keptTorchFile = () => idbDo("readonly", s => s.get("torchc0")).catch(() => null);

function torchInput(f) {
  const inp = $("#rzFile"); if (!inp || !f) return false;
  const dt = new DataTransfer(); dt.items.add(f); inp.files = dt.files; inp.dispatchEvent(new Event("change")); return true;
}
let pendingTorch = null;
document.addEventListener("zeim:torchc0-file", e => { pendingTorch = e.detail; if (torchInput(e.detail)) pendingTorch = null; keepTorchFile(e.detail); });
document.addEventListener("zeim:torchc0-forget", () => { idbDo("readwrite", s => s.delete("torchc0")).catch(() => { }); });
document.addEventListener("zeim:torchc0-ready", async () => {      // the TorchC0 panel was just built
  const inp = $("#rzFile"); if (!inp) return;
  inp.addEventListener("change", () => { if (inp.files[0]) keepTorchFile(inp.files[0]); });
  if (pendingTorch) { torchInput(pendingTorch); pendingTorch = null; return; }
  if (inp.files.length) return;
  const k = await keptTorchFile(); if (!k?.blob || inp.files.length) return;
  torchInput(new File([k.blob], k.name || "model.stl", { type: k.type || "model/stl" }));
  const st = $("#rzFileStatus"); if (st) st.textContent += " (kept from before)";
});

/* ---- the model of a section, as an edit-project id (CAD and the Slicer share these) ---- */
async function editIdFrom(src) {
  if (src === "slicer") { const id = window.__zeimEdit?.p?.id || ss.get("zeim.edit.last"); if (id) return id; throw new Error("Open a model in the Slicer first."); }
  if (src === "lithophane") {
    if (!S.current?.id) throw new Error("Make a model first, then send it.");
    return (await api("/api/edit/new", { method: "POST", body: FD({ from_build: S.current.id, beginner: beginner() }) })).id;
  }
  if (src === "torchc0") {
    const f = await torchFile(); if (!f) throw new Error("Choose a model in TorchC0 first.");
    return (await api("/api/edit/new", { method: "POST", body: FD({ file: f, units: "mm", beginner: beginner() }) })).id;
  }
  throw new Error("Nothing to send.");
}
async function blobOf(url) { const r = await fetch(url, { credentials: "same-origin" }); if (!r.ok) throw new Error("Couldn't fetch the model. Try again."); return r.blob(); }
async function torchFile() {
  const url = document.body.dataset.torchStl;                       // the prepared result, if there is one
  if (url) return new File([await blobOf(url)], "torchc0.stl", { type: "model/stl" });
  return $("#rzFile")?.files?.[0] || null;
}
export async function fileFromEdit(id) {
  const p = await api("/api/edit/" + encodeURIComponent(id));
  return new File([await blobOf(p.downloads.stl)], ((p.title || "model").replace(/[^\w.-]+/g, "_").slice(0, 40) || "model") + ".stl", { type: "model/stl" });
}

function remember(src) {
  let prev = null;
  try { prev = JSON.parse(ss.get("zeim.back") || "null"); } catch { prev = null; }
  const marker = { label: NAMES[src], hash: src, t: Date.now() };
  const studio = prev && prev.from === "mystudio" ? { label: prev.label, hash: prev.hash, url: prev.url, from: prev.from, t: prev.t }
    : (prev && prev.studio && prev.studio.from === "mystudio" ? prev.studio : null);
  if (studio) marker.studio = studio;
  ss.set("zeim.back", JSON.stringify(marker));
  if (src === "lithophane" && S.current?.id) ss.set("zeim.studio.return", S.current.id);   // reopened once when you come back
}
const units = () => { try { return localStorage.getItem("zeim.cad.units") || localStorage.getItem("eunit") || "mm"; } catch { return "mm"; } };

async function sendToShowcase(src) {
  try {
    document.dispatchEvent(new CustomEvent("zeim:save-now"));
    let build;
    if (src === "lithophane") {
      if (!S.current?.id) throw new Error("Make a model first, then send it.");
      const named = ($("#designName")?.value || "").trim();
      build = { id: S.current.id, title: named || S.current.title, ai: S.current.ai, mode: S.current.mode, base: S.current.base };
    } else if (src === "slicer") {
      const id = window.__zeimEdit?.p?.id || ss.get("zeim.edit.last");
      if (!id) throw new Error("Open a model in the Slicer first.");
      build = { id, title: window.__zeimEdit?.p?.title || "Slicer model" };
    } else if (src === "torchc0") {
      build = { id: await editIdFrom("torchc0"), title: "Resin model" };
    } else throw new Error("Nothing to send.");
    if (typeof window.zeimOpenShowcase === "function") { window.zeimOpenShowcase(build); return true; }
    location.href = "/?publish=" + encodeURIComponent(build.id);
    return true;
  } catch (e) { toast(e.message, "err"); return false; }
}

export async function sendTo(target, src = sourceNow()) {
  if (!targetsFor(src).includes(target)) { toast(`${NAMES[target]} doesn't match your printer type. Change it with My printer at the top.`); return false; }
  document.dispatchEvent(new CustomEvent("zeim:save-now"));                    // nothing is lost
  const root = document.documentElement; root.classList.add("handing");
  try {
    if (src === "lithophane" && target === "torchc0" && S.current?.downloads?.stl) {
      const f = new File([await blobOf(S.current.downloads.stl)], "studio.stl", { type: "model/stl" });
      remember(src); location.hash = "torchc0";
      document.dispatchEvent(new CustomEvent("zeim:torchc0-file", { detail: f }));
      return true;
    }
    const id = await editIdFrom(src);
    remember(src);
    if (target === "cad") {
      try { localStorage.setItem("zeim.cad.units", units()); } catch { }
      location.href = `/static/cad.html?bid=${encodeURIComponent(id)}&from=${encodeURIComponent(NAMES[src])}&back=${encodeURIComponent("/#" + src)}`;
      return true;
    }
    if (target === "slicer") { location.hash = "slicer"; document.dispatchEvent(new CustomEvent("zeim:open-edit", { detail: id })); return true; }
    if (target === "torchc0") { const f = await fileFromEdit(id); location.hash = "torchc0"; document.dispatchEvent(new CustomEvent("zeim:torchc0-file", { detail: f })); return true; }
  } catch (e) { toast(e.message, "err"); return false; }
  finally { setTimeout(() => root.classList.remove("handing"), 220); }
}

/* ---- the menu ---- */
function menu(src, anchor) {
  let d = $("#dlgSendTo");
  if (!d) { d = document.createElement("dialog"); d.id = "dlgSendTo"; d.setAttribute("aria-labelledby", "sendToH"); document.body.append(d); }
  const ts = targetsFor(src), other = kind() === "resin" ? "FDM Slicer" : "TorchC0";
  d.innerHTML = `<div class="dlg"><div class="dh"><h3 id="sendToH">Send to…</h3><button type="button" class="x" data-close aria-label="Close"><svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-x"/></svg></button></div>
    <div class="body"><p class="help">The same model goes over with its size, units and orientation. Your work here is saved first.</p>
    <ul class="sendlist">${ts.map(t => `<li><button type="button" class="btn sendto" data-to="${t}"><b>${NAMES[t]}</b><small>${DESC[t]}</small></button></li>`).join("")}
    <li><button type="button" class="btn sendto" data-to="showcase"><b>Showcase</b><small>Send this model to Showcase. Free to share. ZEIM doesn't take a cut.</small></button></li></ul>
    <p class="help" id="sendToKind">Printer type: ${kind() === "resin" ? "Resin" : "FDM"}. ${esc(other)} is hidden; change it with My printer at the top.</p></div></div>`;
  d.querySelector("[data-close]").onclick = () => d.close();
  d.querySelectorAll("[data-to]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.setAttribute("aria-busy", "true");
    let ok = false;
    try {
      if (b.dataset.to === "showcase") ok = await sendToShowcase(src);
      else ok = await sendTo(b.dataset.to, src);
    } finally { b.disabled = false; b.removeAttribute("aria-busy"); }
    if (ok && d.open) d.close();
    if (!ok) anchor?.focus();
  });
  d.addEventListener("close", () => anchor?.focus(), { once: true });
  d.showModal(); d.querySelector("[data-to]")?.focus();
}

/* ---- visible triggers: a real button in each section's action row (no dependence on the floating toolbar) ---- */
function addBtn(id, after, src, cls = "btn") {
  if (!after || $("#" + id)) return;
  const b = document.createElement("button"); b.type = "button"; b.className = cls + " sendtobtn"; b.id = id; b.setAttribute("aria-haspopup", "dialog");
  b.innerHTML = `${ICON} Send to…`; b.onclick = () => menu(src, b); after.after(b);
}
/* Studio/Lithophane: three side-by-side buttons after generate (Save work | Send to Slicer/TorchC0 | Send to CAD).
   Nozzle / multi-head controls stay out of this section — those live only in the FDM Slicer. */
function wireStudioHandoff() {
  const save = $("#btnSaveWork"), slicer = $("#btnSendSlicer"), cad = $("#btnSendCad"), lab = $("#btnSendSlicerL");
  if (!save || !slicer || !cad) return;
  const paint = () => {
    const resin = kind() === "resin";
    slicer.dataset.to = resin ? "torchc0" : "slicer";
    if (lab) lab.textContent = resin ? "Send to TorchC0" : "Send to Slicer";
    slicer.title = resin
      ? "Save first, then open this model in TorchC0 for resin"
      : "Save first, then open this model in the FDM Slicer";
    slicer.hidden = !targetsFor("lithophane").includes(slicer.dataset.to);
    cad.hidden = !targetsFor("lithophane").includes("cad");
  };
  save.onclick = () => {
    const ok = window.zeimSave ? !!window.zeimSave.saveNow() : (document.dispatchEvent(new CustomEvent("zeim:save-now")), true);
    const why = window.zeimSave && window.zeimSave.lastResult ? window.zeimSave.lastResult() : "";
    toast(ok ? "Draft saved in this browser." : (why === "failed" ? "Could not store the draft in this browser." : "Nothing new to save yet."), ok ? undefined : "err");
  };
  const go = async (btn, target) => {
    if (btn.disabled) return;
    btn.disabled = true; btn.setAttribute("aria-busy", "true");
    try { await sendTo(target, "lithophane"); } finally { btn.disabled = false; btn.removeAttribute("aria-busy"); }
  };
  slicer.onclick = () => go(slicer, slicer.dataset.to || "slicer");
  cad.onclick = () => go(cad, "cad");
  paint();
  new MutationObserver(paint).observe(document.body, { attributes: true, attributeFilter: ["data-print-kind"] });
}
wireStudioHandoff();
addBtn("editSendTo", $("#editSend"), "slicer");
{ const ph = $("#viewTorch .pagehead"); if (ph && !$("#torchSendTo")) { const s = document.createElement("span"); ph.append(s); addBtn("torchSendTo", s, "torchc0"); s.remove(); } }

/* Phone layouts can fold a section's panels away (the Slicer's result panel starts minimised), which hid its Send to…
   button. A small floating "Send to…" stands in whenever the section has a model but its own button is not on screen.
   Studio uses the three handoff buttons instead of a Send to… menu. */
const SRC_BTN = { lithophane: "#btnSendSlicer", slicer: "#editSendTo", torchc0: "#torchSendTo" };
const hasModel = v => v === "lithophane" ? !!S.current?.id : v === "slicer" ? !!window.__zeimEdit?.p?.id : v === "torchc0" ? !!($("#rzFile")?.files?.length || document.body.dataset.torchStl) : false;
let fab = null;
function syncFab() {
  const v = document.body.dataset.view, inline = $(SRC_BTN[v] || "#none");
  const need = !!inline && hasModel(v) && !(inline.offsetParent && inline.getClientRects().length);
  if (!need) { if (fab) fab.hidden = true; return; }
  if (!fab) { fab = document.createElement("button"); fab.type = "button"; fab.id = "sendToFab"; fab.className = "btn primary sendfab"; fab.setAttribute("aria-haspopup", "dialog");
    fab.innerHTML = `${ICON} Send to…`; fab.onclick = () => menu(sourceNow(), fab); document.body.append(fab); }
  fab.hidden = false;
}
const ro = new ResizeObserver(syncFab);
Object.values(SRC_BTN).forEach(sel => { const b = $(sel); if (b) ro.observe(b); });
new MutationObserver(syncFab).observe(document.body, { attributes: true, attributeFilter: ["data-view", "data-torch-stl"] });
["zeim:edit-shown", "zeim:torchc0-ready", "zeim:torchc0-file"].forEach(ev => document.addEventListener(ev, () => setTimeout(syncFab, 50)));
document.addEventListener("change", e => { if (e.target.id === "rzFile") syncFab(); });
addEventListener("resize", syncFab); setInterval(syncFab, 1500);   // cheap: catches models opened by any route

/* Print dialog with Resin chosen: "Open in TorchC0" carries the model (Studio or Slicer) */
export function openInTorch() {
  $("#dlgPrint")?.close();
  const src = document.body.dataset.view === "slicer" ? "slicer" : "lithophane";
  const has = src === "slicer" ? (window.__zeimEdit?.p?.id || ss.get("zeim.edit.last")) : S.current?.id;
  if (!has) { location.hash = "torchc0"; return Promise.resolve(false); }
  return sendTo("torchc0", src);
}

/* ---- arrival from CAD: /?resin=<id>#torchc0 ---- */
{
  const rid = new URLSearchParams(location.search).get("resin");
  if (rid && /^[0-9a-f]{12}$/.test(rid)) {
    history.replaceState(null, "", location.pathname + "#torchc0");
    fileFromEdit(rid).then(f => document.dispatchEvent(new CustomEvent("zeim:torchc0-file", { detail: f })), e => toast(e.message, "err"));
  }
}

/* ---- Studio keeps its model: coming back after Send to… (Back chip, browser Back, a full page load from CAD) reopens it once ---- */
function restoreStudio() {
  const id = ss.get("zeim.studio.return");
  if (!id || document.body.dataset.view !== "lithophane") return;
  ss.del("zeim.studio.return");
  if (!/^[0-9a-f]{12}$/.test(id) || S.current?.id) return;
  document.dispatchEvent(new CustomEvent("zeim:open-build", { detail: id }));
}

/* ---- one-tap way back ---- */
function backChip() {
  let info = null; try { info = JSON.parse(ss.get("zeim.back") || "null"); } catch { }
  let c = $("#backChip");
  const here = document.body.dataset.view;
  if (!info || Date.now() - (info.t || 0) > 6 * 3600e3 || info.hash === here || !here) { if (c) c.hidden = true; return; }
  if (!c) {
    c = document.createElement("a"); c.id = "backChip"; c.className = "backchip"; document.body.append(c);
    c.addEventListener("click", ev => {
      const href = c.getAttribute("href");
      const go = () => {
        let cur = null;
        try { cur = JSON.parse(ss.get("zeim.back") || "null"); } catch { cur = null; }
        if (cur && cur.studio && cur.studio.from === "mystudio") ss.set("zeim.back", JSON.stringify(cur.studio));
        else ss.del("zeim.back");
        if (href && !isPublishUrl(href)) location.href = href;
      };
      ev.preventDefault();
      if (window.zeimSave && typeof window.zeimSave.leave === "function") window.zeimSave.leave(go);
      else { document.dispatchEvent(new CustomEvent("zeim:save-now")); go(); }
    });
  }
  if (info.from === "mystudio") { c.hidden = true; return; }
  const url = info.url && info.url.startsWith("/") && !info.url.startsWith("//") && !isPublishUrl(info.url) ? info.url : "#" + info.hash;
  if (isPublishUrl(url)) { c.hidden = true; return; }
  c.href = url; c.hidden = false;
  c.innerHTML = `<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M15 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg> Back to ${esc(info.label || "")}`;
}
const onView = () => { backChip(); restoreStudio(); };
new MutationObserver(onView).observe(document.body, { attributes: true, attributeFilter: ["data-view"] });
setTimeout(onView, 0);
addEventListener("pageshow", () => document.documentElement.classList.remove("handing"));

window.zeimHandoff = { sendTo, targetsFor, openInTorch, keepTorchFile, syncFab };
