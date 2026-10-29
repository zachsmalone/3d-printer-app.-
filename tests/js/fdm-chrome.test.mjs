/* FDM, CAD, and TorchC0 Back: empty leaves; dirty work offers four choices. Done does not publish. */
import test from "node:test";
import assert from "node:assert/strict";
import { BED_LEAVE, FDM_DONE, bedLeavePlan, fdmDonePlan, isPublishUrl } from "../../static/workspace-controls.js";

const fallback = "#showcase";

test("an empty bed leaves without a confirm, save, or clear", () => {
  for (const section of ["slicer", "cad", "torchc0"]) {
    const plan = bedLeavePlan({ section, dirty: false, nextUrl: "#account", fallbackUrl: fallback });
    assert.equal(plan.ask, false, section);
    assert.equal(plan.save, false, section);
    assert.equal(plan.clear, false, section);
    assert.equal(plan.reset, false, section);
    assert.equal(plan.navigate, true, section);
    assert.equal(plan.url, "#account", section);
    assert.equal(plan.publish, false, section);
  }
  const back = bedLeavePlan({ section: "slicer", dirty: false, nextUrl: "", fallbackUrl: fallback });
  assert.equal(back.ask, false);
  assert.equal(back.save, false);
  assert.equal(back.clear, false);
  assert.equal(back.url, fallback);
});

test("dirty work asks, then each choice does one thing and never publishes", () => {
  const ask = bedLeavePlan({ section: "slicer", dirty: true, nextUrl: "#cad", fallbackUrl: fallback });
  assert.equal(ask.ask, true);
  assert.equal(ask.save, false);
  assert.equal(ask.clear, false);
  assert.equal(ask.navigate, false);
  assert.deepEqual(ask.options, BED_LEAVE);
  assert.deepEqual(BED_LEAVE, ["stay", "save", "reset", "abandon"]);

  const stay = bedLeavePlan({ section: "torchc0", dirty: true, choice: "stay", nextUrl: "#cad", fallbackUrl: fallback });
  assert.equal(stay.ask, false);
  assert.equal(stay.save, false);
  assert.equal(stay.clear, false);
  assert.equal(stay.navigate, false);
  assert.equal(stay.url, null);

  const save = bedLeavePlan({ section: "slicer", dirty: true, choice: "save", nextUrl: "#cad", fallbackUrl: fallback });
  assert.equal(save.save, true);
  assert.equal(save.clear, true);
  assert.equal(save.reset, false);
  assert.equal(save.navigate, true);
  assert.equal(save.url, "#cad");
  assert.equal(save.publish, false);
  assert.equal(isPublishUrl(save.url), false);

  const backSave = bedLeavePlan({ section: "cad", dirty: true, choice: "save", nextUrl: "", fallbackUrl: "/" });
  assert.equal(backSave.save, true);
  assert.equal(backSave.clear, true);
  assert.equal(backSave.navigate, true);
  assert.equal(backSave.url, "/");

  const reset = bedLeavePlan({ section: "torchc0", dirty: true, choice: "reset", nextUrl: "#lithophane", fallbackUrl: fallback });
  assert.equal(reset.save, false);
  assert.equal(reset.clear, true);
  assert.equal(reset.reset, true);
  assert.equal(reset.navigate, false);
  assert.equal(reset.url, null);
  assert.equal(reset.publish, false);

  const abandon = bedLeavePlan({ section: "slicer", dirty: true, choice: "abandon", nextUrl: "", fallbackUrl: fallback });
  assert.equal(abandon.save, false);
  assert.equal(abandon.clear, true);
  assert.equal(abandon.reset, false);
  assert.equal(abandon.navigate, true);
  assert.equal(abandon.url, fallback);
  assert.equal(abandon.publish, false);
});

test("a publish url is dropped and an unknown section does nothing", () => {
  const bad = bedLeavePlan({ section: "slicer", dirty: true, choice: "save", nextUrl: "/?publish=1", fallbackUrl: fallback });
  assert.equal(bad.publish, false);
  assert.equal(bad.url, fallback);
  assert.equal(isPublishUrl(bad.url), false);
  const both = bedLeavePlan({ section: "cad", dirty: true, choice: "abandon", nextUrl: "/?publish=1", fallbackUrl: "/?publish=2" });
  assert.equal(both.navigate, false);
  assert.equal(both.url, null);
  const other = bedLeavePlan({ section: "lithophane", dirty: true, choice: "save", nextUrl: "#account" });
  assert.equal(other.navigate, false);
  assert.equal(other.save, false);
  assert.equal(other.clear, false);
});

test("FDM Done stays on the workspace and lists real destinations", () => {
  const plan = fdmDonePlan();
  assert.equal(plan.sheet, true);
  assert.equal(plan.navigate, false);
  assert.equal(plan.clear, false);
  assert.equal(plan.publish, false);
  assert.equal(plan.url, null);
  assert.deepEqual(plan.destinations, FDM_DONE);
  assert.deepEqual(FDM_DONE, ["cad", "device", "account", "showcase"]);
  assert.equal(plan.destinations.includes("slicer"), false);
});
