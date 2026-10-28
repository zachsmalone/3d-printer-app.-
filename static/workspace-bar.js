/* Exit, Done, New build, and Return to Projects on Lithophane, the Slicer, TorchC0, and 2D→3D.
   Save uses the same leave / saveNow path as CAD. None of these actions publish to Showcase. */
import { S, askConfirm, toast } from "/static/app.js";
import { exitTarget, takeExit, LIBRARY_URL } from "/static/studio-library.js";
import { leavePlan, newBuildPlan, isPublishUrl } from "/static/workspace-controls.js";

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
    if (done) done.hidden = !sectionHasWork(section);
  });
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
    if (plan.url === LIBRARY_URL || String(plan.url).indexOf("#account/studio") >= 0) takeExit(sessionStorage);
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
      ? "This browser could not store the workspace draft. Start a new build anyway? A project already on your account stays in Projects. This does not send it to Showcase."
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

function onControl(ev) {
  const el = ev.target.closest && ev.target.closest("[data-ws-act]");
  if (!el) return;
  const action = el.getAttribute("data-ws-act");
  const host = el.closest("[data-ws]");
  const section = el.getAttribute("data-ws") || (host && host.getAttribute("data-ws")) || "";
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

document.addEventListener("click", onControl);
["zeim:build", "zeim:edit-loaded", "zeim:edit-shown", "zeim:new-build", "zeim:torchc0-ready"].forEach(name => {
  document.addEventListener(name, paintWorkspaceBars);
});
window.addEventListener("hashchange", paintWorkspaceBars);
new MutationObserver(paintWorkspaceBars).observe(document.body, { attributes: true, attributeFilter: ["data-view", "data-torch-stl"] });
paintWorkspaceBars();
