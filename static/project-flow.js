/* One project across Design → Check & Repair → Prepare → Slice & Export.
   Saved work is on Account (#account). #projects and #studio open that page.
   A photo design and its slicer copy are different records. The copy is remembered
   for this browser tab (zeim.flow) so the next stage does not import the photo again.
   A repaired file that is not a project yet is remembered the same way: one slicer
   project per repair id. Resin layer files are made in the printer's own slicer.
   TorchC0 only prepares. */
import { LIBRARY_HASH } from "./studio-library.js";
export const FLOW_KEY = "zeim.flow";
export const STAGES = [
  { id: "design", label: "Design" },
  { id: "repair", label: "Check & Repair" },
  { id: "prepare", label: "Prepare" },
  { id: "slice", label: "Slice & Export" },
];
const ID = /^[0-9a-f]{12}$/;
const REPAIR_ID = /^[0-9a-f]{16}$/;
const MAX_COPIES = 8;

const valid = id => ID.test(id || "");
const validRepair = id => REPAIR_ID.test(id || "");

export function stageFor(view, tool) {
  const t = tool || "";
  if (view === "lithophane" || view === "cad") return "design";
  if (view === "torchc0") return "prepare";
  if (view === "smartfix" || view === "repair") return "repair";
  if (view === "slicer") {
    if (t === "repair" || t === "simplify") return "repair";
    if (t === "smartorient" || t === "orient" || t === "hollow" || t === "cut") return "prepare";
    return "slice";
  }
  return "";
}

export function flowVisible(view) {
  return stageFor(view, "") !== "" || view === "slicer";
}

function blankFlow() {
  return { copies: {}, repairs: {} };
}

export function readFlow(storage) {
  const out = blankFlow();
  try {
    const raw = storage && storage.getItem(FLOW_KEY);
    const j = raw ? JSON.parse(raw) : {};
    if (j && typeof j.copies === "object" && j.copies) out.copies = Object.assign({}, j.copies);
    if (j && typeof j.repairs === "object" && j.repairs) out.repairs = Object.assign({}, j.repairs);
  } catch { return blankFlow(); }
  return out;
}

function writeFlow(storage, flow) {
  try { storage.setItem(FLOW_KEY, JSON.stringify({ copies: flow.copies, repairs: flow.repairs })); }
  catch { /* the stage still opens; the next visit may copy again */ }
}

function trimMap(map, keepKey, validKey) {
  const keys = Object.keys(map).filter(k => k !== keepKey);
  const next = {};
  for (const k of keys) if (validKey(k) && valid(map[k])) next[k] = map[k];
  const ordered = Object.keys(next);
  while (ordered.length >= MAX_COPIES) delete next[ordered.shift()];
  return next;
}

export function rememberCopy(storage, photoId, editId) {
  if (!storage || !valid(photoId) || !valid(editId)) return readFlow(storage);
  const cur = readFlow(storage);
  const copies = trimMap(cur.copies, photoId, valid);
  copies[photoId] = editId;
  const flow = { copies, repairs: cur.repairs };
  writeFlow(storage, flow);
  return flow;
}

export function rememberRepair(storage, repairId, editId) {
  if (!storage || !validRepair(repairId) || !valid(editId)) return readFlow(storage);
  const cur = readFlow(storage);
  const repairs = trimMap(cur.repairs, repairId, validRepair);
  repairs[repairId] = editId;
  const flow = { copies: cur.copies, repairs };
  writeFlow(storage, flow);
  return flow;
}

export function forgetCopy(storage, editId) {
  if (!storage || !valid(editId)) return readFlow(storage);
  const cur = readFlow(storage);
  let changed = false;
  for (const k of Object.keys(cur.copies)) {
    if (cur.copies[k] === editId) { delete cur.copies[k]; changed = true; }
  }
  for (const k of Object.keys(cur.repairs)) {
    if (cur.repairs[k] === editId) { delete cur.repairs[k]; changed = true; }
  }
  if (changed) writeFlow(storage, cur);
  return cur;
}

export function reuseCopy(flow, photoId) {
  const id = flow && flow.copies ? flow.copies[photoId] : "";
  return valid(photoId) && valid(id) ? id : "";
}

export function reuseRepair(flow, repairId) {
  const id = flow && flow.repairs ? flow.repairs[repairId] : "";
  return validRepair(repairId) && valid(id) ? id : "";
}

export function slicerUrlForNewProject(id) {
  return valid(id) ? "/?edit=" + id + "#slicer" : "";
}

function meshOf(ctx) {
  const editId = valid(ctx.editId) ? ctx.editId : "";
  const copyId = valid(ctx.copyId) ? ctx.copyId : "";
  if (ctx.view === "lithophane") return copyId;
  if (ctx.view === "slicer" || ctx.view === "cad" || ctx.view === "repair") return editId;
  return editId || copyId;
}

function repairPageNote(ctx) {
  if (valid(ctx.editId)) return "Check & Repair uses the project kept for this repair. Slice & Export opens that project in the FDM Slicer.";
  return "This page repairs a file that is not a project yet. Open in the FDM Slicer starts a new project from the repaired file. The file you uploaded stays as it was.";
}

function sameNote(stage) {
  if (stage === "repair") return "Check & Repair uses this project.";
  if (stage === "prepare") return "Prepare places this project on the bed.";
  if (stage === "slice") return "Slice & Export uses this project.";
  return "This project continues here.";
}

function copyNote(stage) {
  const head = "This slicer project is a copy of the photo design. The photo design stays on Account.";
  if (stage === "repair") return head + " Check & Repair uses that copy.";
  if (stage === "prepare") return head + " Prepare places that copy on the bed.";
  return head + " Slice & Export uses that copy.";
}

function willCopyNote(stage) {
  if (stage === "repair") return "Check & Repair opens a slicer copy of this photo design. The photo design stays on Account.";
  if (stage === "prepare") return "Prepare opens a slicer copy of this photo design and places it on the bed. The photo design stays on Account.";
  return "Slice & Export opens a slicer copy of this photo design. The photo design stays on Account.";
}

function meshNote(stage, ctx, meshId) {
  if (valid(ctx.photoId) && ctx.copyId === meshId) return copyNote(stage);
  return sameNote(stage);
}

function slicerPlan(stage, ctx, tool) {
  const photoId = valid(ctx.photoId) ? ctx.photoId : "";
  const meshId = meshOf(ctx);
  const hash = tool ? "#slicer/" + tool : "#slicer";
  if (meshId) {
    const here = ctx.view === "slicer" && (ctx.tool || "") === tool && ctx.editId === meshId;
    return { stage, stay: here, hash, open: "edit", id: meshId, note: meshNote(stage, ctx, meshId) };
  }
  if (photoId) {
    return { stage, stay: false, hash, open: "send", target: "slicer", src: "lithophane", tool, derived: true, note: willCopyNote(stage) };
  }
  return { stage, stay: false, hash: LIBRARY_HASH, open: "", note: "Open a saved project on Account, then continue." };
}

function torchPlan(ctx, note, editId) {
  if (ctx.view === "torchc0" && !editId) return { stay: true, open: "", note };
  if (editId) {
    const src = ctx.view === "lithophane" ? "lithophane" : (ctx.view === "cad" ? "cad" : "slicer");
    return { stay: false, open: "send", target: "torchc0", src, editId, note };
  }
  if (valid(ctx.photoId)) return { stay: false, open: "send", target: "torchc0", src: "lithophane", note };
  return { stay: false, hash: "#torchc0", open: "", note };
}

export function planHop(stage, ctx) {
  const c = ctx || {};
  const kind = c.kind === "resin" ? "resin" : "fdm";
  const photoId = valid(c.photoId) ? c.photoId : "";
  const view = c.view || "";
  if (stage === "design") {
    if (view === "lithophane" && photoId) {
      return { stage, stay: true, hash: "#lithophane", open: "build", id: photoId, note: "Design is this photo model." };
    }
    if (photoId && c.copyId === c.editId && valid(c.editId) && view === "slicer") {
      return { stage, stay: false, hash: "#lithophane", open: "build", id: photoId, note: "Design is the photo model. This slicer project is a copy of it." };
    }
    const meshId = meshOf(c);
    if (meshId) {
      return {
        stage,
        stay: view === "cad",
        url: view === "cad" ? "" : "/static/cad.html?bid=" + meshId,
        open: "",
        note: "Design opens this project in CAD.",
      };
    }
    return { stage, stay: view === "cad", hash: "#cad", open: "", note: "Design starts in CAD, or from a photo in Lithophane." };
  }
  if (stage === "repair" && c.view === "repair") return { stage, stay: true, open: "", note: repairPageNote(c) };
  if (stage === "repair") return Object.assign({ stage }, slicerPlan("repair", c, "repair"));
  if (stage === "prepare" && kind === "fdm") return Object.assign({ stage }, slicerPlan("prepare", c, "smartorient"));
  if (stage === "prepare" && kind === "resin") {
    const meshId = meshOf(c);
    const note = meshId && photoId && meshId === c.copyId
      ? "Prepare copies the slicer copy of this photo design into TorchC0. The photo design stays on Account. The layer file is made in your resin printer's slicer."
      : (meshId
        ? "Prepare copies this project's mesh into TorchC0. This project stays as it is. The layer file is made in your resin printer's slicer."
        : "Prepare copies this photo model into TorchC0. The photo design stays on Account. The layer file is made in your resin printer's slicer.");
    return Object.assign({ stage }, torchPlan(c, note, c.view === "torchc0" ? "" : meshId));
  }
  if (stage === "slice" && kind === "fdm") return Object.assign({ stage }, slicerPlan("slice", c, ""));
  if (stage === "slice" && kind === "resin") {
    const meshId = meshOf(c);
    const note = "Slice & Export for resin is the layer file in your resin printer's slicer. TorchC0 prepares the model. Export that file, then open it in the printer's slicer.";
    if (c.view === "torchc0") return { stage, stay: false, open: "focus", focus: "#rzExport", note };
    return Object.assign({ stage }, torchPlan(c, note, meshId));
  }
  return { stage, stay: true, open: "", note: "Open a saved project on Account." };
}

export function flowNote(ctx) {
  const stage = stageFor(ctx && ctx.view, ctx && ctx.tool);
  if (!stage) return "";
  return planHop(stage, ctx).note || "";
}

export function bindFlow(getCtx, go) {
  const root = document.getElementById("projectFlow");
  if (!root) return function () {};
  const list = root.querySelector("ol");
  const note = root.querySelector("[data-flow-note]");
  function paint() {
    const ctx = (typeof getCtx === "function" ? getCtx() : {}) || {};
    const stage = stageFor(ctx.view, ctx.tool);
    const show = flowVisible(ctx.view);
    root.hidden = !show;
    if (!show || !list) return;
    list.innerHTML = STAGES.map(s => {
      const on = s.id === stage;
      return `<li class="${on ? "cur" : ""}"><button type="button" data-stage="${s.id}"${on ? ' aria-current="step"' : ""}>${s.label}</button></li>`;
    }).join("");
    if (note) note.textContent = flowNote(ctx);
  }
  if (list) list.addEventListener("click", e => {
    const b = e.target.closest("[data-stage]");
    if (!b || typeof go !== "function") return;
    const plan = planHop(b.dataset.stage, (getCtx() || {}));
    if (!plan || plan.stay) return;
    Promise.resolve(go(plan)).catch(() => {});
  });
  addEventListener("hashchange", () => setTimeout(paint, 0));
  ["zeim:build", "zeim:edit-loaded", "zeim:flow", "zeim:torchc0-shown", "zeim:torchc0-file"].forEach(name => {
    document.addEventListener(name, paint);
  });
  if (document.body) new MutationObserver(paint).observe(document.body, { attributes: true, attributeFilter: ["data-view", "data-print-kind"] });
  paint();
  return paint;
}
