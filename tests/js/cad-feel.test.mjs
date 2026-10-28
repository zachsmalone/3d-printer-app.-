import test from "node:test";
import assert from "node:assert/strict";
import {
  FEEL_MS, pickChoice, edgeKey, curvePaint, bodyGlow,
  constraintBlock, constraintSummary, filletBlock, faceOffsetBlock,
  extrudeBlock, revolveBlock, measureBlock, anchorClear, barRect,
} from "../../static/cad-feel.js";

test("hover follows the same pick a tap will keep", () => {
  const edge = true, hit = true;
  assert.equal(pickChoice({ tool: null, measure: false, edge, hit, onEdge: false }).kind, "face");
  assert.equal(pickChoice({ tool: null, measure: false, edge, hit, onEdge: true }).kind, "edge");
  assert.equal(pickChoice({ tool: null, measure: false, edge: false, hit: false, onEdge: false }).kind, "none");
  assert.equal(pickChoice({ tool: null, measure: true, edge, hit, onEdge: false }).kind, "face");
  assert.equal(pickChoice({ tool: null, measure: true, edge, hit, onEdge: true }).kind, "edge");
  assert.equal(pickChoice({ tool: "fillet", edge: false, hit, onEdge: false }).kind, "none");
  assert.equal(pickChoice({ tool: "fillet", edge, hit, onEdge: false }).kind, "edge");
  assert.equal(pickChoice({ tool: "faceoffset", edge, hit, onEdge: true }).kind, "face");
  assert.equal(pickChoice({ tool: "sculpt", edge, hit, onEdge: true }).kind, "none");
  assert.equal(pickChoice({ tool: "extrude", edge, hit, onEdge: true }).kind, "region");
  assert.equal(FEEL_MS, 180);
});

test("press, hover, and selected stay distinct", () => {
  assert.equal(curvePaint("a", { hover: "a", press: null, selected: false }), "hover");
  assert.equal(curvePaint("a", { hover: "a", press: "a", selected: true }), "press");
  assert.equal(curvePaint("a", { hover: "b", press: null, selected: true }), "selected");
  assert.equal(curvePaint("a", { hover: null, press: null, selected: false, construction: true }), "cons");
  assert.equal(edgeKey([0, 0, 0], [1, 0, 0]), edgeKey([1, 0, 0], [0, 0, 0]));
  assert.deepEqual(bodyGlow(1, { selected: 0, hover: 1, press: -1 }), { color: 0x7eb6ff, intensity: 0.22 });
  assert.equal(bodyGlow(0, { selected: 0, hover: 0, press: 0 }).intensity, 0.55);
  assert.equal(bodyGlow(0, { selected: 0, hover: 1, press: -1 }).intensity, 0.42);
  assert.equal(bodyGlow(-1, { selected: -1, hover: -1, press: -1 }), null);
});

test("hard-surface tools say why they cannot run", () => {
  assert.equal(filletBlock({ bodies: 0, radius: 1 }), "Make a solid first.");
  assert.equal(filletBlock({ bodies: 1, radius: 0 }), "Type a size greater than 0.");
  assert.equal(filletBlock({ bodies: 1, radius: Number.NaN }), "Type a size greater than 0.");
  assert.equal(filletBlock({ bodies: 1, radius: 1.5 }), "");
  assert.equal(faceOffsetBlock({ hasFace: false, distance: 2 }), "Tap a flat face first.");
  assert.equal(faceOffsetBlock({ hasFace: true, distance: 0 }), "Type a distance other than 0.");
  assert.equal(faceOffsetBlock({ hasFace: true, distance: -2 }), "");
  assert.equal(extrudeBlock({ pending: false }), "");
  assert.equal(extrudeBlock({ pending: true, regionsKnown: false, regionCount: 0, distance: 10 }), "Checking the sketch.");
  assert.equal(extrudeBlock({ pending: true, regionsKnown: true, regionCount: 0, distance: 10 }), "This sketch has no closed shape.");
  assert.equal(extrudeBlock({ pending: true, regionsKnown: true, regionCount: 1, distance: 0 }), "Type a distance other than 0.");
  assert.equal(extrudeBlock({ pending: true, failed: true, regionsKnown: false, regionCount: 0, distance: 10 }), "The sketch could not be read.");
  assert.equal(revolveBlock({ pending: true, regionsKnown: true, regionCount: 1, angle: 0 }), "Type an angle other than 0.");
  assert.equal(revolveBlock({ pending: true, regionsKnown: true, regionCount: 1, angle: 90 }), "");
  assert.equal(measureBlock({ bodies: 0 }), "Make a solid first.");
  assert.equal(measureBlock({ bodies: 2 }), "");
});

test("constraint reasons match the selection", () => {
  const line = { type: "line" }, circle = { type: "circle" };
  assert.equal(constraintBlock("parallel", []), "Select curves first.");
  assert.equal(constraintBlock("parallel", [line]), "Select exactly two curves.");
  assert.equal(constraintBlock("parallel", [line, line]), "");
  assert.equal(constraintBlock("horizontal", [circle]), "Select a line first.");
  assert.equal(constraintBlock("horizontal", [line]), "");
  assert.equal(constraintBlock("lock", [circle]), "");
  assert.match(constraintSummary([]), /Select curves first/);
  assert.equal(constraintSummary([line, circle]), "");
  assert.match(constraintSummary([line, line, line]), /exactly two/);
});

test("a context bar stays inside the stage and off the mid-right dock", () => {
  const bounds = { w: 800, h: 600 };
  const bar = { w: 280, h: 48, gap: 18 };
  const dock = { left: 700, top: 80, right: 790, bottom: 360 };
  const placed = anchorClear({ x: 740, y: 200, behind: false }, bar, bounds, [dock]);
  const rect = barRect(placed, bar);
  assert.equal(placed.hidden, false);
  assert.ok(rect.right <= dock.left + 0.5 || rect.left >= dock.right - 0.5 || rect.bottom <= dock.top + 0.5 || rect.top >= dock.bottom - 0.5);
  assert.ok(rect.left >= -0.5 && rect.top >= -0.5 && rect.right <= bounds.w + 0.5 && rect.bottom <= bounds.h + 0.5);

  const underHeader = anchorClear({ x: 80, y: 20, behind: false }, bar, bounds, []);
  assert.ok(barRect(underHeader, bar).top >= -0.5);

  assert.equal(anchorClear({ x: 40, y: 40, behind: true }, bar, bounds, []).hidden, true);
});
