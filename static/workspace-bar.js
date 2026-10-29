/* Exit, Done, New build, and Return to Account on Lithophane, the Slicer, TorchC0, and 2D→3D.
   Save uses the same leave / saveNow path as CAD. None of these actions publish to Showcase. */
import { S, api, askConfirm, esc, toast } from "/static/app.js";
import { exitTarget, takeExit, LIBRARY_URL } from "/static/studio-library.js";
import { fdmDonePlan, fdmLeavePlan, leavePlan, newBuildPlan, isPublishUrl } from "/static/workspace-controls.js";
import { mountSlicerPrinter, prefLabel } from "/static/printer.js";

function fromStudio() {
  return exitTarget(sessionStorage) === LIBRARY_URL;
}

function sectionHasWork(section) {
  if (section === "lithophane") return !!(S.current && S.current.id);
  if (section === "slicer") {
    const result = document.getElementById("editResult");
    return !!(result && !result.hidden);
  }
  if (section === "torchc0") return !!document.body.dataset.torchStl;
  if (section === "ai3d") {
    const result = document.getElementById("a3Res");
    return !!(result && !result.hidden);
  }
  return false;
}

function unstored(section) {
  if (section === "lithophane") {
    const built = !!(S.current && S.current.id);
    const photo = !!S.file && !built;
    const mb = document.getElementById("mbFiles");
    const box = !!(mb && mb.files && mb.files.length) && !built;
    return photo || box;
  }
  if (section === "torchc0") {
    const inp = document.getElementById("rzFile");
    const hasFile = !!(inp && inp.files && inp.files.length);
    return hasFile || !!document.body.dataset.torchStl;
  }
  if (section === "ai3d") {
    const img = document.getElementById("a3Img");
    const result = document.getElementById("a3Res");
    const title = document.getElementById("a3Title");
    const showing = !!(result && !result.hidden);
    const photo = !!(img && !img.hidden) && !showing;
    const named = !!(title && title.value.trim()) && !showing;
    return photo || named;
  }
  return false;
}

function busy(section) {
  if (section === "lithophane" && S.building) return "Wait for your model to finish.";
  if (section === "slicer") {
    const el = document.getElementById("editBusy");
    if (el && !el.hidden) return "Wait for the slicer to finish.";
  }
  if (section === "torchc0") {
    const go = document.getElementById("rzGo");
    if (go && go.getAttribute("aria-busy") === "true") return "Wait for TorchC0 to finish.";
  }
  return "";
}

function paintWorkspaceBars() {
  const back = fromStudio();
  document.querySelectorAll(".wsbar [data-ws-act='return-studio']").forEach(el => { el.hidden = !back; });
  document.querySelectorAll(".wsbar").forEach(bar => {
    const section = bar.getAttribute("data-ws");
    const done = bar.querySelector("[data-ws-act='done']");
    if (!done) return;
    /* FDM Done stays on the header. It opens destinations. It does not mean the bed has a model. */
    if (section === "slicer") done.hidden = false;
    else done.hidden = !sectionHasWork(section);
  });
}

function slicerModel() {
  return !!(window.__zeimEdit && window.__zeimEdit.p && window.__zeimEdit.p.id);
}

function paintDevice() {
  const nameEl = document.getElementById("bedPrinterName");
  const stateEl = document.getElementById("bedPrinterState");
  const fromPanel = document.getElementById("spPrinter");
  let name = "";
  try { name = (fromPanel && fromPanel.textContent.trim()) || prefLabel() || ""; } catch { name = ""; }
  if (nameEl) nameEl.textContent = name || "No printer saved";
  const liveBox = document.getElementById("liveStatus");
  const liveText = document.getElementById("liveStatusText");
  const live = liveBox && !liveBox.hidden && liveText && liveText.textContent.trim();
  const state = live || "Not connected";
  if (stateEl) stateEl.textContent = state;
  const read = document.getElementById("deviceReadout");
  if (read) read.textContent = (name || "No printer saved") + " · " + state;
  const mat = document.getElementById("spMat");
  document.querySelectorAll("#bedTools [data-mat]").forEach(btn => {
    const on = mat && btn.getAttribute("data-mat") === mat.value;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (document.body.dataset.view === "slicer") mountSlicerPrinter();
}

function saveThen(done) {
  if (window.zeimSave && typeof window.zeimSave.leave === "function") window.zeimSave.leave(done);
  else {
    document.dispatchEvent(new CustomEvent("zeim:save-now"));
    done();
  }
}

let slicerLeaveOpen = false;

function confirmSlicerLeave(nextUrl) {
  if (slicerLeaveOpen) return;
  const ask = fdmLeavePlan({ confirmed: false, nextUrl: nextUrl || "" });
  if (!ask.ask || ask.publish || isPublishUrl(ask.url)) return;
  slicerLeaveOpen = true;
  askConfirm({
    title: "Leave the FDM Slicer?",
    message: "Save this work, then clear the bed? A model already on Account stays there. This does not send it to Showcase.",
    okLabel: "Save and clear",
    danger: false,
  }).then(yes => {
    slicerLeaveOpen = false;
    if (!yes) return;
    const plan = fdmLeavePlan({ confirmed: true, nextUrl: nextUrl || "" });
    if (plan.publish || isPublishUrl(plan.url)) return;
    saveThen(() => {
      if (plan.clear) document.dispatchEvent(new CustomEvent("zeim:new-build", { detail: { section: "slicer", publish: false } }));
      if (plan.navigate && plan.url) navigate(plan.url);
      paintWorkspaceBars();
    });
  });
}

function openFdmDone() {
  const plan = fdmDonePlan();
  if (plan.publish || plan.navigate || plan.clear || !plan.sheet) return;
  const dlg = document.getElementById("fdmDone");
  if (dlg && typeof dlg.showModal === "function") dlg.showModal();
}

function runFdmDone(dest) {
  const dlg = document.getElementById("fdmDone");
  if (dlg && dlg.open) dlg.close();
  const has = slicerModel();
  switch (dest) {
    case "close":
      return;
    case "cad":
      if (!has) { toast("Open a model first, then send it to CAD.", "err"); return; }
      if (window.zeimSave && typeof window.zeimSave.saveNow === "function") window.zeimSave.saveNow();
      document.getElementById("editOpenCad")?.click();
      return;
    case "device":
      if (!has) { toast("Open a model first, then save the file.", "err"); return; }
      document.getElementById("editSend")?.click();
      return;
    case "account": {
      if (window.zeimSave && typeof window.zeimSave.saveNow === "function") window.zeimSave.saveNow();
      const where = window.zeimSave && typeof window.zeimSave.where === "function" ? window.zeimSave.where() : null;
      toast(where
        ? "This model stays in saved work on Account. Slicer settings are stored for this sign-in in this browser."
        : "Saved in this browser. Sign in on Account to keep it with your saved work.");
      return;
    }
    case "showcase":
      /* The existing result button opens the Showcase form. Nothing is published here. */
      document.getElementById("editPublish")?.click();
      return;
    default: {
      const unknown = dest;
      return unknown;
    }
  }
}

const VIEW_ALIAS = {
  "": "showcase",
  edit: "slicer",
  fdm: "slicer",
  create: "lithophane",
  projects: "account",
  studio: "account",
  resin: "torchc0",
  "2d3d": "ai3d",
};

function viewOfHash(href) {
  const head = String(href || "").replace(/^#/, "").split("/")[0].split("?")[0];
  return VIEW_ALIAS[head] || head || "showcase";
}

function onSlicerNav(ev) {
  if (document.body.dataset.view !== "slicer") return;
  if (ev.target.closest && ev.target.closest("#fdmDone, #fdmImport, #dlgConfirm")) return;
  const navBtn = ev.target.closest && ev.target.closest("#mainNav button[data-view]");
  const link = ev.target.closest && ev.target.closest("a[href]");
  let next = "";
  if (navBtn) next = "#" + navBtn.getAttribute("data-view");
  else if (link) {
    const href = link.getAttribute("href") || "";
    if (!href.startsWith("#")) return;
    if (viewOfHash(href) === "slicer") return;
    next = href;
  } else return;
  if (!next || viewOfHash(next) === "slicer") return;
  ev.preventDefault();
  ev.stopPropagation();
  confirmSlicerLeave(next.startsWith("#") ? next : "#" + next);
}

async function openFdmImport() {
  const dlg = document.getElementById("fdmImport");
  const list = document.getElementById("fdmImportList");
  if (!dlg || !list) return;
  list.innerHTML = "<li>Loading saved work…</li>";
  if (typeof dlg.showModal === "function") dlg.showModal();
  try {
    const r = await api("/api/builds");
    const builds = (r && r.builds) || [];
    if (!builds.length) {
      list.innerHTML = "<li>No saved work on this account yet.</li>";
      return;
    }
    list.innerHTML = builds.slice().reverse().map(b => {
      const id = String(b.id || "");
      if (!/^[0-9a-f]{12}$/.test(id)) return "";
      const title = esc(b.title || "Untitled");
      const kind = b.kind === "edit" ? "Edited model" : esc(b.mode || "Saved");
      return `<li><button type="button" data-import-id="${id}" data-import-kind="${b.kind === "edit" ? "edit" : "photo"}">${title}<small>${kind}</small></button></li>`;
    }).join("") || "<li>No saved work on this account yet.</li>";
  } catch (e) {
    list.innerHTML = `<li>${esc(e && e.message ? e.message : "Could not load saved work. Sign in on Account if this list stays empty.")}</li>`;
  }
}

function takeImport(btn) {
  const id = btn.getAttribute("data-import-id") || "";
  if (!/^[0-9a-f]{12}$/.test(id)) return;
  const dlg = document.getElementById("fdmImport");
  if (dlg && dlg.open) dlg.close();
  if (btn.getAttribute("data-import-kind") === "edit") {
    document.dispatchEvent(new CustomEvent("zeim:open-edit", { detail: id }));
    return;
  }
  document.dispatchEvent(new CustomEvent("zeim:edit-from-build", { detail: id }));
}

function navigate(url) {
  if (!url || isPublishUrl(url)) return false;
  const hashAt = url.indexOf("#");
  if (hashAt >= 0) {
    location.hash = url.slice(hashAt);
    return true;
  }
  if (url.startsWith("/") && !url.startsWith("//")) {
    location.href = url;
    return true;
  }
  return false;
}

function finishLeave(plan) {
  if (plan.publish || isPublishUrl(plan.url)) return;
  if (plan.navigate && plan.url) {
    const leaveUrl = String(plan.url || "");
    if (leaveUrl === LIBRARY_URL || leaveUrl.indexOf("#account") >= 0 || leaveUrl.indexOf("#projects") >= 0 || leaveUrl.indexOf("#studio") >= 0) takeExit(sessionStorage);
    navigate(plan.url);
  } else if (window.zeimSave && typeof window.zeimSave.lastResult === "function") {
    const why = window.zeimSave.lastResult();
    if (why === "saved") toast("Draft saved in this browser.");
    else if (why === "failed") toast("Could not store the draft in this browser.", "err");
  }
  paintWorkspaceBars();
}

function runLeave(plan) {
  const go = () => finishLeave(plan);
  if (window.zeimSave && typeof window.zeimSave.leave === "function") window.zeimSave.leave(go);
  else {
    document.dispatchEvent(new CustomEvent("zeim:save-now"));
    go();
  }
}

function clearSection(section) {
  document.dispatchEvent(new CustomEvent("zeim:new-build", { detail: { section, publish: false } }));
  paintWorkspaceBars();
}

export function guardNewBuild(section) {
  const wait = busy(section);
  if (wait) { toast(wait, "err"); return; }
  const dirty = !!(window.zeimSave && typeof window.zeimSave.isDirty === "function" && window.zeimSave.isDirty());
  let saveOk = !dirty;
  if (dirty && window.zeimSave && typeof window.zeimSave.saveNow === "function") {
    window.zeimSave.saveNow();
    saveOk = !window.zeimSave.isDirty();
  }
  const local = unstored(section);
  const plan = newBuildPlan({ dirty, saveOk, unstored: local, confirmed: false });
  if (plan.publish || plan.navigate || isPublishUrl(plan.url)) return;
  if (plan.ask) {
    const message = plan.reason === "unsaved"
      ? "This browser could not store the workspace draft. Start a new build anyway? A project already saved stays on Account. This does not send it to Showcase."
      : "This screen has work that is not a saved project yet. Start a new build anyway? This does not send it to Showcase.";
    askConfirm({ title: "New build", message, okLabel: "New build anyway", danger: true }).then(yes => {
      if (!yes) return;
      const again = newBuildPlan({ dirty, saveOk, unstored: local, confirmed: true });
      if (again.clear && !again.publish && !again.navigate) clearSection(section);
    });
    return;
  }
  if (plan.clear) clearSection(section);
}

function pinCategory(id, label) {
  const pin = document.getElementById("bedPin");
  const cats = document.getElementById("bedCats");
  const tools = document.getElementById("bedTools");
  if (!pin || !cats || !tools) return;
  tools.querySelectorAll("[data-for]").forEach(row => { row.hidden = row.getAttribute("data-for") !== id; });
  pin.hidden = false;
  pin.textContent = label;
  pin.dataset.cat = id;
  cats.hidden = true;
  tools.hidden = false;
  tools.scrollLeft = 0;
}

function unpinCategory() {
  const pin = document.getElementById("bedPin");
  const cats = document.getElementById("bedCats");
  const tools = document.getElementById("bedTools");
  if (!pin || !cats || !tools) return;
  pin.hidden = true;
  pin.textContent = "";
  delete pin.dataset.cat;
  tools.hidden = true;
  cats.hidden = false;
}

function onBedCat(ev) {
  const pin = ev.target.closest && ev.target.closest("#bedPin");
  if (pin) {
    ev.preventDefault();
    ev.stopPropagation();
    unpinCategory();
    return;
  }
  const cat = ev.target.closest && ev.target.closest("#bedCats [data-bed-cat]");
  if (!cat) return;
  ev.preventDefault();
  ev.stopPropagation();
  pinCategory(cat.getAttribute("data-bed-cat"), cat.getAttribute("data-bed-label") || cat.textContent.trim());
}

function onFdmAct(ev) {
  const preview = ev.target.closest && ev.target.closest("[data-bed-act=preview]");
  if (preview && preview.closest("#viewEdit")) {
    ev.preventDefault();
    const gc = document.getElementById("gcPrev");
    if (!gc) { toast("Slice first. Preview shows the layers after Slice finishes."); return; }
    const sheet = document.getElementById("processSheet");
    if (sheet) sheet.hidden = false;
    gc.scrollIntoView?.({ block: "nearest" });
    return;
  }
  const send = ev.target.closest && ev.target.closest("[data-bed-act=send-print]");
  if (send && send.closest("#viewEdit")) {
    ev.preventDefault();
    if (!slicerModel()) { toast("Open a model first, then send it to a printer.", "err"); return; }
    document.getElementById("editPrint")?.click();
    return;
  }
  const imp = ev.target.closest && ev.target.closest("#slicerBar [data-bed-act=import]");
  if (imp && !imp.hasAttribute("data-bed-cat")) {
    ev.preventDefault();
    openFdmImport();
    return;
  }
  const matBtn = ev.target.closest && ev.target.closest("#bedTools [data-mat]");
  if (matBtn) {
    ev.preventDefault();
    const sel = document.getElementById("spMat");
    if (!sel) { toast("Open a model first, then pick a filament.", "err"); return; }
    sel.value = matBtn.getAttribute("data-mat");
    sel.dispatchEvent(new Event("change"));
    paintDevice();
    return;
  }
  const jump = ev.target.closest && ev.target.closest("#bedTools [data-bed-click]");
  if (jump) {
    ev.preventDefault();
    document.getElementById(jump.getAttribute("data-bed-click"))?.click();
    return;
  }
  const look = ev.target.closest && ev.target.closest("#bedTools [data-look]");
  if (look) {
    ev.preventDefault();
    document.querySelector("#editViewer [data-look='" + look.getAttribute("data-look") + "']")?.click();
  }
}

function onControl(ev) {
  const doneDest = ev.target.closest && ev.target.closest("[data-fdm-done]");
  if (doneDest) {
    ev.preventDefault();
    runFdmDone(doneDest.getAttribute("data-fdm-done") || "close");
    return;
  }
  const imported = ev.target.closest && ev.target.closest("#fdmImportList [data-import-id]");
  if (imported) {
    ev.preventDefault();
    takeImport(imported);
    return;
  }
  const el = ev.target.closest && ev.target.closest("[data-ws-act]");
  if (!el) return;
  const action = el.getAttribute("data-ws-act");
  const host = el.closest("[data-ws]");
  const section = el.getAttribute("data-ws") || (host && host.getAttribute("data-ws")) || "";
  if (section === "slicer" && action === "exit") {
    ev.preventDefault();
    confirmSlicerLeave("");
    return;
  }
  if (section === "slicer" && action === "done") {
    ev.preventDefault();
    openFdmDone();
    return;
  }
  if (action === "new-build") {
    ev.preventDefault();
    guardNewBuild(section);
    return;
  }
  if (action !== "exit" && action !== "done" && action !== "return-studio") return;
  ev.preventDefault();
  const plan = leavePlan(action, { fromStudio: fromStudio(), libraryUrl: LIBRARY_URL });
  if (plan.publish || isPublishUrl(plan.url)) return;
  if (action === "done" && !plan.navigate) {
    if (window.zeimSave && typeof window.zeimSave.isDirty === "function" && window.zeimSave.isDirty() && typeof window.zeimSave.saveNow === "function") window.zeimSave.saveNow();
    const why = window.zeimSave && typeof window.zeimSave.lastResult === "function" ? window.zeimSave.lastResult() : "";
    if (why === "failed" || (window.zeimSave && window.zeimSave.isDirty && window.zeimSave.isDirty())) toast("Could not store the draft in this browser.", "err");
    else if (why === "saved") toast("Draft saved in this browser.");
    else toast("Nothing new to save yet.");
    paintWorkspaceBars();
    return;
  }
  runLeave(plan);
}

document.addEventListener("click", onBedCat, true);
document.addEventListener("click", onSlicerNav, true);
document.addEventListener("click", onFdmAct);
document.addEventListener("click", onControl);
document.getElementById("fdmImportClose")?.addEventListener("click", () => document.getElementById("fdmImport")?.close());
["zeim:build", "zeim:edit-loaded", "zeim:edit-shown", "zeim:new-build", "zeim:torchc0-ready", "zeim:printer", "zeim:fdm-device"].forEach(name => {
  document.addEventListener(name, () => { paintWorkspaceBars(); paintDevice(); });
});
document.addEventListener("zeim:fdm-note", e => { if (e.detail) toast(String(e.detail)); });
function placeFdmSheet() {
  const head = document.querySelector("#viewEdit > .bed-head");
  if (!head) return;
  const top = Math.ceil(head.getBoundingClientRect().bottom + 8);
  document.documentElement.style.setProperty("--fdm-head-bottom", top + "px");
}

function paintChrome() { paintWorkspaceBars(); paintDevice(); placeFdmSheet(); }
window.addEventListener("hashchange", paintChrome);
window.addEventListener("resize", placeFdmSheet);
new MutationObserver(paintChrome).observe(document.body, { attributes: true, attributeFilter: ["data-view", "data-torch-stl"] });
const slicePanel = document.getElementById("slicePanel");
if (slicePanel) new MutationObserver(paintDevice).observe(slicePanel, { childList: true, subtree: true, characterData: true });
paintChrome();
