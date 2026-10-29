/* Batch 3: one project across Design, Check & Repair, Prepare, Slice & Export. */
import test from "node:test";
import assert from "node:assert/strict";
import {
  stageFor, planHop, readFlow, rememberCopy, reuseCopy, forgetCopy, rememberRepair, reuseRepair, slicerUrlForNewProject, flowNote,
  leaveBedUrl,
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
  assert.match(fresh.note, /Account/);

  const again = planHop("slice", { view: "lithophane", photoId: PHOTO, copyId: EDIT, kind: "fdm" });
  assert.equal(again.open, "edit");
  assert.equal(again.id, EDIT);
  assert.equal(again.derived, undefined);
  assert.match(again.note, /copy of the photo design/);
  assert.match(again.note, /Account/);
});

test("an open slicer project stays that project through repair, prepare, and slice", () => {
  const ctx = { view: "slicer", editId: EDIT, kind: "fdm", tool: "" };
  for (const [stage, hash] of [["repair", "#slicer/repair"], ["prepare", "#slicer/smartorient"], ["slice", "#slicer"]]) {
    const plan = planHop(stage, ctx);
    assert.equal(plan.id, EDIT);
    assert.equal(plan.hash, hash);
    assert.equal(plan.derived, undefined);
    assert.doesNotMatch(plan.note, /copy/);
    if (stage === "slice") {
      assert.equal(plan.open, "slice");
      assert.equal(plan.slice, true);
      assert.equal(plan.stay, false);
    } else {
      assert.equal(plan.open, "edit");
    }
  }
  const fromPrepare = planHop("slice", { ...ctx, tool: "smartorient" });
  assert.equal(fromPrepare.stay, false);
  assert.equal(fromPrepare.slice, true);
  assert.equal(fromPrepare.hash, "#slicer");
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

test("with no project, the next stage opens Account", () => {
  const plan = planHop("repair", { view: "slicer", kind: "fdm" });
  assert.equal(plan.hash, "#account");
  assert.match(plan.note, /Account/);
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

const REPAIR = "abcdabcdabcdabcd";

test("the repair page stays on Check & Repair, and a kept project is the same id", () => {
  assert.equal(stageFor("repair", ""), "repair");
  const fresh = planHop("repair", { view: "repair", kind: "fdm" });
  assert.equal(fresh.stay, true);
  assert.match(fresh.note, /new project from the repaired file/);
  assert.doesNotMatch(fresh.note, /same one/);
  const kept = planHop("repair", { view: "repair", editId: EDIT, kind: "fdm" });
  assert.equal(kept.stay, true);
  assert.match(kept.note, /project kept for this repair/);
  assert.doesNotMatch(kept.note, /new project/);
  const slice = planHop("slice", { view: "repair", editId: EDIT, kind: "fdm" });
  assert.equal(slice.open, "edit");
  assert.equal(slice.id, EDIT);
  assert.equal(slice.hash, "#slicer");
  assert.doesNotMatch(slice.note, /copy/);
  const prepare = planHop("prepare", { view: "repair", editId: EDIT, kind: "fdm" });
  assert.equal(prepare.id, EDIT);
  assert.equal(prepare.hash, "#slicer/smartorient");
  const design = planHop("design", { view: "repair", editId: EDIT, kind: "fdm" });
  assert.equal(design.url, "/static/cad.html?bid=" + EDIT);
  const none = planHop("slice", { view: "repair", kind: "fdm" });
  assert.equal(none.hash, "#account");
});

test("reload keeps the open bed, and leaving drops the restore link", () => {
  const mid = "/?edit=bbbbbbbbbbbb#slicer/smartorient";
  assert.equal(new URL(mid, "http://zeim.local").searchParams.get("edit"), "bbbbbbbbbbbb");
  assert.match(mid, /#slicer\/smartorient/);
  const left = leaveBedUrl(mid);
  assert.equal(left, "/#slicer");
  assert.equal(new URL(left, "http://zeim.local").searchParams.get("edit"), null);
  assert.equal(leaveBedUrl("/static/cad.html?bid=bbbbbbbbbbbb&from=TorchC0"), "/static/cad.html?from=TorchC0");
  assert.equal(leaveBedUrl("/?resin=bbbbbbbbbbbb#torchc0"), "/#torchc0");
  assert.equal(leaveBedUrl("/#slicer"), "/#slicer");
});

test("a repair hand-off is remembered beside photo copies and dropped with that project", () => {
  const storage = mem();
  rememberCopy(storage, PHOTO, EDIT);
  assert.equal(reuseRepair(readFlow(storage), REPAIR), "");
  rememberRepair(storage, REPAIR, EDIT);
  assert.equal(reuseCopy(readFlow(storage), PHOTO), EDIT);
  assert.equal(reuseRepair(readFlow(storage), REPAIR), EDIT);
  rememberRepair(storage, "short", EDIT);
  assert.equal(readFlow(storage).repairs[REPAIR], EDIT);
  for (let i = 0; i < 10; i++) {
    rememberRepair(storage, "e" + String(i).padStart(15, "0"), "f" + String(i).padStart(11, "0"));
  }
  const repairs = readFlow(storage).repairs;
  assert.equal(Object.keys(repairs).length, 8);
  assert.equal(repairs[REPAIR], undefined);
  assert.equal(reuseCopy(readFlow(storage), PHOTO), EDIT);
  const gone = Object.values(repairs)[0];
  forgetCopy(storage, gone);
  assert.equal(Object.values(readFlow(storage).repairs).includes(gone), false);
  assert.equal(reuseCopy(readFlow(storage), PHOTO), EDIT);
});
