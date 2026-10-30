/* Exit, Done, New build, and Return to Account on Lithophane, the Slicer, TorchC0, and 2D→3D.
   Save uses the same leave / saveNow path as CAD. None of these actions publish to Showcase. */
import { S, api, askConfirm, esc, toast, showPhotoBuild } from "/static/app.js";
import { askBedLeave, BED_LEAVE_MESSAGE } from "/static/bed-leave.js";
import { exitTarget, takeExit, LIBRARY_URL } from "/static/studio-library.js";
import { fdmDonePlan, bedLeavePlan, leavePlan, newBuildPlan, isPublishUrl } from "/static/workspace-controls.js";
import { leaveBedUrl } from "/static/project-flow.js";
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
  const lithoName = document.getElementById("lithoPrinterLabel");
  if (lithoName) lithoName.textContent = name || "No printer saved";
  const fdmName = document.getElementById("fdmPrinterLabel");
  if (fdmName) fdmName.textContent = name || "No printer saved";
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

let bedLeaveOpen = false;

function sectionSaveDirty(section) {
  return !!(window.zeimSave && typeof window.zeimSave.isSectionDirty === "function" && window.zeimSave.isSectionDirty(section));
}

function slicerDirty() {
  if (window.__zeimEdit && window.__zeimEdit.p) return true;
  const result = document.getElementById("editResult");
  if (result && !result.hidden) return true;
  const file = document.getElementById("editFile");
  if (file && file.files && file.files.length) return true;
  const busyEl = document.getElementById("editBusy");
  if (busyEl && !busyEl.hidden) return true;
  return sectionSaveDirty("slicer");
}

function torchDirty() {
  if (document.body.dataset.torchStl) return true;
  const inp = document.getElementById("rzFile");
  if (inp && inp.files && inp.files.length) return true;
  const out = document.getElementById("torchOut");
  if (out && out.classList.contains("rzResult")) return true;
  return sectionSaveDirty("torchc0");
}

function bedDirty(section) {
  if (section === "slicer") return slicerDirty();
  if (section === "torchc0") return torchDirty();
  return false;
}

function exitUrl() {
  return leavePlan("exit", { fromStudio: fromStudio(), libraryUrl: LIBRARY_URL }).url;
}

function forgetPersistedBed(section) {
  if (section === "slicer") {
    try { sessionStorage.removeItem("zeim.edit.last"); } catch { /* the address is still cleared */ }
  }
  if (section === "torchc0") document.dispatchEvent(new CustomEvent("zeim:torchc0-forget"));
  const next = leaveBedUrl(location.href);
  if (next !== location.pathname + location.search + location.hash) history.replaceState(null, "", next);
}

function applyBedLeave(plan) {
  if (!plan || plan.ask || plan.choice === "stay" || plan.publish || isPublishUrl(plan.url)) return;
  forgetPersistedBed(plan.section);
  const go = () => {
    if (plan.clear) clearSection(plan.section);
    if (plan.navigate && plan.url) finishLeave(plan);
    else paintWorkspaceBars();
  };
  if (plan.choice === "abandon" && window.zeimSave && typeof window.zeimSave.discard === "function") window.zeimSave.discard(plan.section);
  if (plan.save) saveThen(go);
  else go();
}

function startBedLeave(section, nextUrl) {
  const wait = busy(section);
  if (wait) { toast(wait, "err"); return; }
  const dirty = bedDirty(section);
  const fallbackUrl = exitUrl();
  if (!dirty) {
    applyBedLeave(bedLeavePlan({ section, dirty: false, nextUrl: nextUrl || "", fallbackUrl }));
    return;
  }
  if (bedLeaveOpen) return;
  bedLeaveOpen = true;
  const title = section === "torchc0" ? "Leave TorchC0?" : "Leave the FDM Slicer?";
  askBedLeave({ title, message: BED_LEAVE_MESSAGE }).then(choice => {
    bedLeaveOpen = false;
    applyBedLeave(bedLeavePlan({ section, dirty: true, choice, nextUrl: nextUrl || "", fallbackUrl }));
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

function onBedNav(ev) {
  const section = document.body.dataset.view;
  if (section !== "slicer" && section !== "torchc0") return;
  if (ev.target.closest && ev.target.closest("#fdmDone, #fdmImport, #dlgConfirm, #dlgBedLeave")) return;
  const navBtn = ev.target.closest && ev.target.closest("#mainNav button[data-view]");
  const link = ev.target.closest && ev.target.closest("a[href]");
  let next = "";
  if (navBtn) next = "#" + navBtn.getAttribute("data-view");
  else if (link) {
    const href = link.getAttribute("href") || "";
    if (!href.startsWith("#")) return;
    if (viewOfHash(href) === section) return;
    next = href;
  } else return;
  if (!next || viewOfHash(next) === section) return;
  const wait = busy(section);
  if (wait) {
    ev.preventDefault();
    ev.stopPropagation();
    toast(wait, "err");
    return;
  }
  if (!bedDirty(section)) return;
  ev.preventDefault();
  ev.stopPropagation();
  startBedLeave(section, next.startsWith("#") ? next : "#" + next);
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
  const title = document.getElementById("bedToolsTitle");
  if (!pin || !cats || !tools) return;
  tools.querySelectorAll("[data-for]").forEach(row => { row.hidden = row.getAttribute("data-for") !== id; });
  if (title) title.textContent = label || "Tool";
  pin.hidden = true;
  pin.textContent = label;
  pin.dataset.cat = id;
  cats.hidden = false;
  tools.hidden = false;
  tools.scrollLeft = 0;
  const root = document.getElementById("viewEdit");
  if (root) root.dataset.bedOpen = id;
  const sheet = { filament: "filament", process: "process", device: "device" }[id] || "plate";
  document.dispatchEvent(new CustomEvent("zeim:bed-sheet", { detail: sheet }));
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
  const root = document.getElementById("viewEdit");
  if (root) delete root.dataset.bedOpen;
  document.dispatchEvent(new CustomEvent("zeim:bed-sheet", { detail: "plate" }));
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
  const span = cat.id === "bedDevice" ? null : cat.querySelector("span");
  const label = (span && span.textContent.trim()) || cat.getAttribute("data-bed-label") || cat.textContent.trim();
  pinCategory(cat.getAttribute("data-bed-cat"), label);
}

function onFdmAct(ev) {
  const repair = ev.target.closest && ev.target.closest("[data-bed-act=repair]");
  if (repair && repair.closest("#viewEdit")) {
    ev.preventDefault();
    if (!slicerModel()) { toast("Open a model first, then Repair.", "err"); return; }
    const big = document.querySelector("#viewEdit [data-big=fix]");
    if (big) { big.click(); return; }
    const form = document.querySelector("#viewEdit form[data-form=repair]");
    const go = form && form.querySelector("button");
    if (go) { go.click(); return; }
    toast("Repair isn't available for this model.", "err");
    return;
  }
  const preview = ev.target.closest && ev.target.closest("[data-bed-act=preview]");
  if (preview && preview.closest("#viewEdit")) {
    ev.preventDefault();
    openWorkPreview("slicer");
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
  if ((section === "slicer" || section === "torchc0") && action === "exit") {
    ev.preventDefault();
    startBedLeave(section, "");
    return;
  }
  if (section === "slicer" && action === "done") {
    ev.preventDefault();
    openFdmDone();
    return;
  }
  if (section === "lithophane" && action === "done" && lithoHasModel()) {
    ev.preventDefault();
    openLithoDest();
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

function pinLitho(cat, label) {
  const root = document.getElementById("viewCreate");
  const pin = document.getElementById("lithoPin");
  const tools = document.getElementById("lithoTools");
  const cats = document.getElementById("lithoCats");
  const title = document.getElementById("lithoSheetTitle");
  const viewTitle = document.getElementById("lithoViewTitle");
  if (!root || !pin || !tools || !cats) return;
  if (cat === "collapse") {
    root.classList.toggle("wl-collapsed");
    return;
  }
  const viewLike = cat === "view" || cat === "rotate";
  root.dataset.lithoCat = cat;
  root.classList.toggle("litho-sheet", !viewLike);
  if (title) title.textContent = label || "Tool";
  if (viewTitle) viewTitle.textContent = label || "View";
  pin.hidden = true;
  pin.textContent = label;
  cats.hidden = false;
  tools.hidden = viewLike ? false : true;
  tools.querySelectorAll("[data-for]").forEach(el => { el.hidden = el.getAttribute("data-for") !== "view"; });
}

function unpinLitho() {
  const root = document.getElementById("viewCreate");
  const pin = document.getElementById("lithoPin");
  const tools = document.getElementById("lithoTools");
  const cats = document.getElementById("lithoCats");
  if (root) { delete root.dataset.lithoCat; root.classList.remove("litho-sheet"); }
  if (pin) { pin.hidden = true; pin.textContent = ""; }
  if (tools) tools.hidden = true;
  if (cats) cats.hidden = false;
}

function onLithoBar(ev) {
  const pin = ev.target.closest && ev.target.closest("#lithoPin");
  if (pin) { ev.preventDefault(); unpinLitho(); return; }
  const cat = ev.target.closest && ev.target.closest("#lithoCats [data-litho-cat], #lithoSettings [data-litho-cat]");
  if (cat) {
    ev.preventDefault();
    const span = cat.querySelector("span");
    pinLitho(cat.getAttribute("data-litho-cat"), (span && span.textContent.trim()) || cat.getAttribute("data-litho-label") || cat.textContent.trim());
    return;
  }
  const act = ev.target.closest && ev.target.closest("#lithoCats [data-litho-act]");
  if (act) {
    ev.preventDefault();
    const name = act.getAttribute("data-litho-act");
    if (name === "print") document.getElementById("btnPrint")?.click();
    else if (name === "preview") openWorkPreview("lithophane");
    return;
  }
  const jump = ev.target.closest && ev.target.closest("#lithoTools [data-litho-click]");
  if (jump) {
    ev.preventDefault();
    document.getElementById(jump.getAttribute("data-litho-click"))?.click();
    return;
  }
  const dest = ev.target.closest && ev.target.closest("[data-litho-dest]");
  if (dest) {
    ev.preventDefault();
    runLithoDest(dest.getAttribute("data-litho-dest") || "close");
  }
}

document.addEventListener("click", onLithoBar, true);
document.addEventListener("click", onBedCat, true);
document.addEventListener("click", onBedNav, true);
document.addEventListener("click", onFdmAct);
document.addEventListener("click", onControl);
document.getElementById("fdmImportClose")?.addEventListener("click", () => document.getElementById("fdmImport")?.close());
["zeim:build", "zeim:edit-loaded", "zeim:edit-shown", "zeim:new-build", "zeim:torchc0-ready", "zeim:printer", "zeim:fdm-device"].forEach(name => {
  document.addEventListener(name, () => { paintWorkspaceBars(); paintDevice(); paintWorkBars(); });
});
document.addEventListener("zeim:fdm-note", e => { if (e.detail) toast(String(e.detail)); });
document.addEventListener("change", ev => { if (ev.target && ev.target.id === "rzFile") paintWorkBars(); });
["editResult", "editBusy", "editEmpty"].forEach(id => {
  const el = document.getElementById(id);
  if (el) new MutationObserver(paintWorkBars).observe(el, { attributes: true, attributeFilter: ["hidden"] });
});
function placeFdmSheet() {
  const head = document.querySelector("#viewEdit > .bed-head");
  if (head) {
    const bottom = Math.ceil(head.getBoundingClientRect().bottom);
    document.documentElement.style.setProperty("--fdm-head-bottom", (bottom + 8) + "px");
    document.documentElement.style.setProperty("--wl-row-top", (bottom + 8) + "px");
    document.documentElement.style.setProperty("--wl-rail-top", (bottom + 56) + "px");
  }
  const litho = document.querySelector("#viewCreate.has-model > .wsbar");
  if (litho) {
    const bottom = Math.ceil(litho.getBoundingClientRect().bottom);
    document.documentElement.style.setProperty("--wl-litho-top", (bottom + 8) + "px");
  }
}

function bedHasModel() {
  if (window.__zeimEdit && window.__zeimEdit.p) return true;
  const result = document.getElementById("editResult");
  if (result && !result.hidden) return true;
  const busyEl = document.getElementById("editBusy");
  return !!(busyEl && !busyEl.hidden);
}

function torchHasModel() {
  if (document.body.dataset.torchStl) return true;
  const inp = document.getElementById("rzFile");
  if (inp && inp.files && inp.files.length) return true;
  const out = document.getElementById("torchOut");
  return !!(out && out.classList.contains("rzResult"));
}

function lithoHasModel() {
  return !!(S.current && S.current.id);
}

function paintWorkBars() {
  const edit = document.getElementById("viewEdit");
  if (edit) edit.classList.toggle("has-model", bedHasModel());
  const torch = document.getElementById("viewTorch");
  if (torch) torch.classList.toggle("has-model", torchHasModel());
  const litho = document.getElementById("viewCreate");
  if (litho) {
    const on = lithoHasModel();
    litho.classList.toggle("has-model", on);
    const exit = litho.querySelector("[data-ws-act=exit]");
    if (exit) {
      exit.textContent = on ? "Back" : "Exit";
      exit.setAttribute("aria-label", on ? "Back" : "Exit workspace");
    }
    if (!on) {
      delete litho.dataset.lithoCat;
      litho.classList.remove("litho-sheet");
      litho.classList.remove("wl-previewing");
    }
  }
  const editLitho = document.getElementById("fdmEditLitho");
  if (editLitho) editLitho.hidden = !lithoSourceId();
  paintWorkReadout();
}

function openLithoDest() {
  const dlg = document.getElementById("lithoDest");
  if (dlg && !dlg.open) dlg.showModal();
}

function runLithoDest(action) {
  const dlg = document.getElementById("lithoDest");
  if (dlg && dlg.open) dlg.close();
  if (action === "slicer") { document.getElementById("btnSendSlicer")?.click(); return; }
  if (action === "account") { document.getElementById("btnSaveWork")?.click(); return; }
  if (action === "showcase") { document.getElementById("btnPublish")?.click(); return; }
  if (action === "device") {
    const url = S.current && S.current.downloads && S.current.downloads.stl;
    if (!url) { toast("Make a model first.", "err"); return; }
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
  }
}

const PHOTO_MODES = new Set(["lithophane", "relief", "popart", "bust", "trace2d", "memorybox"]);

function lithoSourceId() {
  const p = window.__zeimEdit && window.__zeimEdit.p;
  if (!p) return "";
  const base = p.base || {};
  const origin = p.origin || base.origin || "";
  const mode = base.from_mode || base.photo_mode || p.mode || "";
  const id = String(base.from_build || "");
  if (!/^[0-9a-f]{12}$/.test(id)) return "";
  if (origin === "lithophane" || PHOTO_MODES.has(mode)) return id;
  return "";
}

function fmtMm(size) {
  if (!size || !size.length) return "";
  const parts = [];
  for (const v of size) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "";
    parts.push(String(Math.round(n * 10) / 10));
  }
  return parts.length ? parts.join(" × ") + " mm" : "";
}

function fmtBytes(n) {
  const b = Number(n);
  if (!Number.isFinite(b) || b < 0) return "";
  if (b < 1024) return Math.round(b) + " B";
  const kb = b / 1024;
  if (kb < 1024) return (Math.round(kb * 10) / 10) + " KB";
  return (Math.round((b / (1024 * 1024)) * 10) / 10) + " MB";
}

function modelCountLabel() {
  const p = window.__zeimEdit && window.__zeimEdit.p;
  if (!p) return "";
  const objs = p.plate && p.plate.objects;
  const total = objs && objs.length ? objs.length : 1;
  const pressed = [...document.querySelectorAll("#viewEdit .pselect[aria-pressed=true]")];
  if (pressed.length === 1) {
    const n = Number(pressed[0].getAttribute("data-psel"));
    const current = Number.isFinite(n) ? n + 1 : 1;
    return "Models " + current + "/" + total;
  }
  if (pressed.length > 1) return "Models " + pressed.length + "/" + total;
  if (total === 1) return "Models 1/1";
  return "Models " + total;
}

function photoCountLabel() {
  const imgs = [...document.querySelectorAll("#mbSides img")].filter(img => img.getAttribute("src"));
  let n = imgs.length;
  if (!n) {
    n = (S.file || (S.current && S.current.id)) ? 1 : 0;
    const extra = document.getElementById("collageExtra");
    if (extra && extra.files && extra.files.length) n += extra.files.length;
  }
  if (!n) return "";
  return "Photos " + n + "/" + n;
}

function workStats(which) {
  if (which === "lithophane") {
    const st = (S.current && S.current.stats) || {};
    const sizes = (S.current && S.current.sizes) || {};
    return {
      size: fmtMm(st.size_mm),
      triangles: Number.isFinite(Number(st.triangles)) ? Number(st.triangles).toLocaleString() : "",
      weight: "",
      stl: fmtBytes(sizes.stl),
      href: (S.current && S.current.downloads && S.current.downloads.stl) || "",
    };
  }
  const p = window.__zeimEdit && window.__zeimEdit.p;
  const a = (p && p.analysis) || {};
  const sizes = (p && p.sizes) || {};
  const host = document.getElementById("viewEdit");
  const grams = host && host.dataset.sliceGrams;
  const weight = grams != null && grams !== "" && Number.isFinite(Number(grams)) ? "about " + grams + " g" : "";
  const href = (host && host.dataset.sliceStl) || (p && p.id ? "/api/export/" + encodeURIComponent(p.id) + "/download?format=stl" : "");
  return {
    size: fmtMm(a.size_mm),
    triangles: Number.isFinite(Number(a.triangles)) ? Number(a.triangles).toLocaleString() : "",
    weight,
    stl: fmtBytes(sizes.stl),
    href,
  };
}

function statRow(stats) {
  const cell = (label, value) => `<span>${label}${value ? " <b>" + esc(value) + "</b>" : ""}</span>`;
  return cell("Size", stats.size) + cell("Triangles", stats.triangles) + cell("Weight", stats.weight) + cell("STL size", stats.stl);
}

function paintWorkReadout() {
  const slicer = workStats("slicer");
  const dims = document.getElementById("fdmDims");
  const count = document.getElementById("fdmCount");
  if (dims) dims.textContent = slicer.size;
  if (count) count.textContent = modelCountLabel();
  const litho = workStats("lithophane");
  const lDims = document.getElementById("lithoDims");
  const lCount = document.getElementById("lithoCount");
  if (lDims) lDims.textContent = litho.size;
  if (lCount) lCount.textContent = photoCountLabel();
  for (const [id, stats] of [["fdmPreviewStats", slicer], ["lithoPreviewStats", litho]]) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = statRow(stats);
  }
  for (const [id, href] of [["fdmDownloadStl", slicer.href], ["lithoDownloadStl", litho.href]]) {
    const a = document.getElementById(id);
    if (!a) continue;
    if (href) { a.href = href; a.hidden = false; }
    else { a.href = "#"; a.hidden = true; }
  }
}

function previewChips(which) {
  if (which === "lithophane") {
    return [
      ["vLeft", "Turn left"],
      ["vRight", "Turn right"],
      ["vReset", "Reset view"],
      ["vWire", "Wireframe"],
      ["vLight", "Light on"],
    ].map(([id, label]) => `<button type="button" data-wl-click="${id}">${label}</button>`).join("");
  }
  const looks = [["top", "Top"], ["front", "Front"], ["iso", "Iso"]];
  return `<button type="button" data-wl-click="eWire">Wireframe</button>` + looks.map(([id, label]) => `<button type="button" data-wl-look="${id}">${label}</button>`).join("");
}

function openWorkPreview(which) {
  const root = document.getElementById(which === "lithophane" ? "viewCreate" : "viewEdit");
  const panel = document.getElementById(which === "lithophane" ? "lithoPreview" : "fdmPreview");
  const chips = document.getElementById(which === "lithophane" ? "lithoPreviewChips" : "fdmPreviewChips");
  if (!root || !panel) return;
  root.classList.add("wl-previewing");
  panel.hidden = false;
  if (chips && !chips.childElementCount) chips.innerHTML = previewChips(which);
  paintWorkReadout();
}

function closeWorkPreview(which) {
  const root = document.getElementById(which === "lithophane" ? "viewCreate" : "viewEdit");
  const panel = document.getElementById(which === "lithophane" ? "lithoPreview" : "fdmPreview");
  if (root) root.classList.remove("wl-previewing");
  if (panel) panel.hidden = true;
  if (which === "slicer") {
    const sheet = document.getElementById("processSheet");
    if (sheet) sheet.hidden = true;
  }
}

async function openEditLitho() {
  const id = lithoSourceId();
  if (!id) return;
  location.hash = "lithophane";
  try {
    const r = await api("/api/builds/" + encodeURIComponent(id));
    showPhotoBuild(r);
  } catch (e) {
    toast((e && e.message) || "Could not open that lithophane.", "err");
  }
}

function hideBedTools() {
  const tools = document.getElementById("bedTools");
  const pin = document.getElementById("bedPin");
  const cats = document.getElementById("bedCats");
  if (tools) tools.hidden = true;
  if (pin) { pin.hidden = true; pin.textContent = ""; delete pin.dataset.cat; }
  if (cats) cats.hidden = false;
  const root = document.getElementById("viewEdit");
  if (root) delete root.dataset.bedOpen;
}

document.getElementById("bedToolsClose")?.addEventListener("click", ev => { ev.preventDefault(); unpinCategory(); });
document.getElementById("lithoSheetClose")?.addEventListener("click", ev => { ev.preventDefault(); unpinLitho(); });
document.getElementById("lithoViewClose")?.addEventListener("click", ev => { ev.preventDefault(); unpinLitho(); });
document.getElementById("lithoSlicerSwitch")?.addEventListener("click", () => document.getElementById("btnSendSlicer")?.click());
document.getElementById("lithoPrinterBtn")?.addEventListener("click", () => pinLitho("material", "Material"));
document.getElementById("lithoPlus")?.addEventListener("click", () => document.getElementById("sFile")?.click());
document.getElementById("fdmPlus")?.addEventListener("click", () => document.getElementById("editChooseModel")?.click());
document.getElementById("fdmPrinterBtn")?.addEventListener("click", () => document.getElementById("bedDevice")?.click());
document.getElementById("fdmSliceGo")?.addEventListener("click", () => document.getElementById("slicerSlice")?.click());
document.getElementById("fdmFilamentRow")?.addEventListener("click", () => document.getElementById("bedFilament")?.click());
document.getElementById("fdmProcessRow")?.addEventListener("click", () => document.querySelector("#slicerBar [data-bed-cat=process]")?.click());
document.getElementById("fdmEditLitho")?.addEventListener("click", () => { openEditLitho(); });
document.getElementById("lithoGenerate")?.addEventListener("click", () => {
  const go = document.getElementById("btnBuild");
  if (!go || go.disabled) {
    const hint = document.getElementById("buildHint");
    toast((hint && hint.textContent.trim()) || "Choose or take a photo to begin.", "err");
    return;
  }
  go.click();
});
document.getElementById("fdmBackPrepare")?.addEventListener("click", () => closeWorkPreview("slicer"));
document.getElementById("lithoBackPrepare")?.addEventListener("click", () => closeWorkPreview("lithophane"));
document.addEventListener("click", ev => {
  const jump = ev.target.closest && ev.target.closest("[data-wl-click]");
  if (jump) { ev.preventDefault(); document.getElementById(jump.getAttribute("data-wl-click"))?.click(); return; }
  const look = ev.target.closest && ev.target.closest("[data-wl-look]");
  if (look) { ev.preventDefault(); document.querySelector("#editViewer [data-look='" + look.getAttribute("data-wl-look") + "']")?.click(); }
});
document.addEventListener("zeim:bed-tools-close", hideBedTools);
document.addEventListener("zeim:build", paintWorkReadout);
document.addEventListener("zeim:edit-loaded", paintWorkReadout);

function paintChrome() { paintWorkspaceBars(); paintDevice(); placeFdmSheet(); paintWorkBars(); }
window.addEventListener("hashchange", paintChrome);
window.addEventListener("resize", placeFdmSheet);
new MutationObserver(paintChrome).observe(document.body, { attributes: true, attributeFilter: ["data-view", "data-torch-stl"] });
const slicePanel = document.getElementById("slicePanel");
if (slicePanel) new MutationObserver(paintDevice).observe(slicePanel, { childList: true, subtree: true, characterData: true });
paintChrome();
