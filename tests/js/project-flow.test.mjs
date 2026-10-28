/* Batch 3: one project across Design, Check & Repair, Prepare, Slice & Export. */
import test from "node:test";
import assert from "node:assert/strict";
import {
  stageFor, planHop, readFlow, rememberCopy, reuseCopy, forgetCopy, slicerUrlForNewProject, flowNote,
} from "../../static/project-flow.js";

const PHOTO = "aaaaaaaaaaaa";
const EDIT = "bbbbbbbbbbbb";

function mem() {
  const m = new Map();
  return {
    get length() { return m.size; },
    key(i) { return [...m.keys()][i] ?? null; },
    getItem(k) { return m.has(k) ? m.get(k) : null; },
    setItem(k, v) { m.set(k, String(v)); },
    removeItem(k) { m.delete(k); },
  };
}

test("stage names follow the open workspace", () => {
  assert.equal(stageFor("lithophane", ""), "design");
  assert.equal(stageFor("cad", ""), "design");
  assert.equal(stageFor("smartfix", ""), "repair");
  assert.equal(stageFor("slicer", "repair"), "repair");
  assert.equal(stageFor("slicer", "smartorient"), "prepare");
  assert.equal(stageFor("slicer", ""), "slice");
  assert.equal(stageFor("torchc0", ""), "prepare");
  assert.equal(stageFor("showcase", ""), "");
  assert.equal(stageFor("account", ""), "");
});

test("a photo design makes one slicer copy, then later stages reuse it", () => {
  const fresh = planHop("repair", { view: "lithophane", photoId: PHOTO, kind: "fdm" });
  assert.equal(fresh.derived, true);
  assert.equal(fresh.open, "send");
  assert.equal(fresh.target, "slicer");
  assert.match(fresh.note, /slicer copy/);
  assert.match(fresh.note, /Projects/);

  const again = planHop("slice", { view: "lithophane", photoId: PHOTO, copyId: EDIT, kind: "fdm" });
  assert.equal(again.open, "edit");
  assert.equal(again.id, EDIT);
  assert.equal(again.derived, undefined);
  assert.match(again.note, /copy of the photo design/);
  assert.match(again.note, /Projects/);
});

test("an open slicer project stays that project through repair, prepare, and slice", () => {
  const ctx = { view: "slicer", editId: EDIT, kind: "fdm", tool: "" };
  for (const [stage, hash] of [["repair", "#slicer/repair"], ["prepare", "#slicer/smartorient"], ["slice", "#slicer"]]) {
    const plan = planHop(stage, ctx);
    assert.equal(plan.open, "edit");
    assert.equal(plan.id, EDIT);
    assert.equal(plan.hash, hash);
    assert.equal(plan.derived, undefined);
    assert.doesNotMatch(plan.note, /copy/);
  }
  assert.equal(planHop("slice", ctx).stay, true);
  assert.equal(planHop("repair", { ...ctx, tool: "repair", editId: EDIT }).stay, true);
});

test("design returns to the photo model only when this slicer project is its copy", () => {
  const back = planHop("design", { view: "slicer", photoId: PHOTO, editId: EDIT, copyId: EDIT, kind: "fdm" });
  assert.equal(back.open, "build");
  assert.equal(back.id, PHOTO);
  assert.equal(back.hash, "#lithophane");
  const other = planHop("design", { view: "slicer", photoId: PHOTO, editId: "cccccccccccc", copyId: EDIT, kind: "fdm" });
  assert.equal(other.url, "/static/cad.html?bid=cccccccccccc");
  const cad = planHop("repair", { view: "cad", editId: EDIT, kind: "fdm" });
  assert.equal(cad.open, "edit");
  assert.equal(cad.id, EDIT);
  assert.equal(cad.hash, "#slicer/repair");
  assert.equal(planHop("design", { view: "cad", editId: EDIT }).stay, true);
});

test("resin prepare names the TorchC0 copy, and slice points at the printer slicer", () => {
  const prep = planHop("prepare", { view: "lithophane", photoId: PHOTO, kind: "resin" });
  assert.equal(prep.target, "torchc0");
  assert.equal(prep.src, "lithophane");
  assert.match(prep.note, /resin printer's slicer/);
  const onCopy = planHop("prepare", { view: "lithophane", photoId: PHOTO, copyId: EDIT, kind: "resin" });
  assert.equal(onCopy.editId, EDIT);
  assert.match(onCopy.note, /slicer copy/);
  const slice = planHop("slice", { view: "torchc0", kind: "resin" });
  assert.equal(slice.open, "focus");
  assert.equal(slice.focus, "#rzExport");
  assert.match(slice.note, /resin printer's slicer/);
  assert.match(flowNote({ view: "torchc0", kind: "resin" }), /resin printer's slicer/);
});

test("with no project, the next stage opens Projects", () => {
  const plan = planHop("repair", { view: "slicer", kind: "fdm" });
  assert.equal(plan.hash, "#account/studio");
  assert.match(plan.note, /Projects/);
});

test("the slicer copy is remembered for this tab and dropped when that project is gone", () => {
  const storage = mem();
  assert.equal(reuseCopy(readFlow(storage), PHOTO), "");
  rememberCopy(storage, PHOTO, EDIT);
  assert.equal(reuseCopy(readFlow(storage), PHOTO), EDIT);
  for (let i = 0; i < 10; i++) {
    rememberCopy(storage, "c" + String(i).padStart(11, "0"), "d" + String(i).padStart(11, "0"));
  }
  const copies = readFlow(storage).copies;
  assert.equal(Object.keys(copies).length, 8);
  assert.equal(copies[PHOTO], undefined);
  const gone = Object.values(copies)[0];
  forgetCopy(storage, gone);
  assert.equal(Object.values(readFlow(storage).copies).includes(gone), false);
});

test("a repaired file opens as a new slicer project only with a real id", () => {
  assert.equal(slicerUrlForNewProject(EDIT), "/?edit=" + EDIT + "#slicer");
  assert.equal(slicerUrlForNewProject("nope"), "");
  assert.equal(slicerUrlForNewProject(""), "");
});
