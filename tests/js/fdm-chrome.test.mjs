/* FDM Back clears the bed after confirm. Done lists destinations and does not publish. */
import test from "node:test";
import assert from "node:assert/strict";
import { FDM_DONE, fdmDonePlan, fdmLeavePlan, isPublishUrl } from "../../static/workspace-controls.js";

test("FDM Back asks, then saves and clears without publishing", () => {
  const ask = fdmLeavePlan({ confirmed: false, nextUrl: "#account" });
  assert.equal(ask.ask, true);
  assert.equal(ask.clear, false);
  assert.equal(ask.navigate, false);
  assert.equal(ask.publish, false);
  assert.equal(ask.save, true);

  const stay = fdmLeavePlan({ confirmed: true, nextUrl: "" });
  assert.equal(stay.ask, false);
  assert.equal(stay.clear, true);
  assert.equal(stay.navigate, false);
  assert.equal(stay.url, null);
  assert.equal(stay.publish, false);

  const tab = fdmLeavePlan({ confirmed: true, nextUrl: "#cad" });
  assert.equal(tab.clear, true);
  assert.equal(tab.navigate, true);
  assert.equal(tab.url, "#cad");
  assert.equal(isPublishUrl(tab.url), false);
  assert.equal(tab.publish, false);
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
