/* Exit, Done, New build, and Return stay off Showcase. */
import test from "node:test";
import assert from "node:assert/strict";
import {
  LIBRARY_URL, SHOWCASE_BROWSE, isPublishUrl, leavePlan, newBuildPlan, plansNeverPublish,
} from "../../static/workspace-controls.js";

const studio = { fromStudio: true, libraryUrl: LIBRARY_URL };
const plain = { fromStudio: false, libraryUrl: LIBRARY_URL };

test("Exit from My Studio returns to the library and does not publish", () => {
  const plan = leavePlan("exit", studio);
  assert.equal(plan.navigate, true);
  assert.equal(plan.url, LIBRARY_URL);
  assert.equal(plan.clear, false);
  assert.equal(plan.publish, false);
  assert.equal(plan.save, true);
  assert.equal(isPublishUrl(plan.url), false);
});

test("Exit from anywhere else opens the Showcase list, not a publish", () => {
  const plan = leavePlan("exit", plain);
  assert.equal(plan.url, SHOWCASE_BROWSE);
  assert.equal(plan.url.includes("publish"), false);
  assert.equal(isPublishUrl(plan.url), false);
  assert.equal(isPublishUrl("/?publish=abc"), true);
  assert.equal(isPublishUrl("/?edit=abc#slicer"), false);
});

test("Done returns to My Studio only when the project was opened from there", () => {
  const home = leavePlan("done", studio);
  assert.equal(home.navigate, true);
  assert.equal(home.url, LIBRARY_URL);
  assert.equal(home.clear, false);
  assert.equal(home.publish, false);
  const stay = leavePlan("done", plain);
  assert.equal(stay.navigate, false);
  assert.equal(stay.url, null);
  assert.equal(stay.clear, false);
  assert.equal(stay.publish, false);
});

test("Return to My Studio is not a publish and does not clear the screen", () => {
  const plan = leavePlan("return-studio", studio);
  assert.equal(plan.navigate, true);
  assert.equal(plan.url, LIBRARY_URL);
  assert.equal(plan.clear, false);
  assert.equal(plan.publish, false);
  assert.equal(plansNeverPublish("return-studio", plain), true);
});

test("New build asks before dropping unsaved or unstored work and never publishes", () => {
  const failed = newBuildPlan({ dirty: true, saveOk: false, unstored: false, confirmed: false });
  assert.equal(failed.clear, false);
  assert.equal(failed.ask, true);
  assert.equal(failed.reason, "unsaved");
  assert.equal(failed.publish, false);
  assert.equal(failed.navigate, false);

  const saved = newBuildPlan({ dirty: true, saveOk: true, unstored: false, confirmed: false });
  assert.equal(saved.clear, true);
  assert.equal(saved.ask, false);
  assert.equal(saved.publish, false);

  const photo = newBuildPlan({ dirty: false, saveOk: true, unstored: true, confirmed: false });
  assert.equal(photo.clear, false);
  assert.equal(photo.ask, true);
  assert.equal(photo.reason, "unstored");

  const anyway = newBuildPlan({ dirty: true, saveOk: false, unstored: true, confirmed: true });
  assert.equal(anyway.clear, true);
  assert.equal(anyway.ask, false);
  assert.equal(anyway.publish, false);

  const empty = newBuildPlan({ dirty: false, saveOk: true, unstored: false, confirmed: false });
  assert.equal(empty.clear, true);
  assert.equal(empty.publish, false);
  assert.equal(plansNeverPublish("new-build", { dirty: true, saveOk: false, unstored: true, confirmed: false }), true);
});

test("an unknown action does not navigate or publish", () => {
  const plan = leavePlan("showcase", plain);
  assert.equal(plan.navigate, false);
  assert.equal(plan.publish, false);
  assert.equal(plan.url, null);
  assert.equal(plansNeverPublish("showcase", plain), false);
});
