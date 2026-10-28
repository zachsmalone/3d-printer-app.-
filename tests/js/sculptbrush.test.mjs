import test from "node:test";
import assert from "node:assert/strict";
import { applyPrepared, prepareStroke, sculptIdle } from "../../static/sculptbrush.js";

function plate() {
  const positions = [
    0, 0, 1, 3, 0, 1, 0, 3, 1,
    0, 0, 0, 3, 0, 0, 0, 3, 0,
  ];
  const faces = [0, 1, 2, 3, 5, 4];
  return prepareStroke(positions, faces);
}

function at(prep, params) {
  return applyPrepared(prep, params);
}

test("draw and carve move only the facing side by the server falloff", () => {
  const draw = at(plate(), { brush: "draw", radius: 4, strength: 1, points: [[0, 0, 1]], normal: [0, 0, 1] });
  assert.equal(draw.kept, true);
  assert.ok(Math.abs(draw.positions[2] - 1.6) < 1e-9);
  const w = (1 - (3 / 4) ** 2) ** 2;
  assert.ok(Math.abs(draw.positions[5] - (1 + w * 0.15 * 4)) < 1e-9);
  assert.equal(draw.positions[11], 0);
  assert.equal(draw.positions[14], 0);
  const carve = at(plate(), { brush: "carve", radius: 4, strength: 1, points: [[0, 0, 1]], normal: [0, 0, 1] });
  assert.ok(Math.abs(carve.positions[2] - 0.4) < 1e-9);
  assert.equal(carve.positions[11], 0);
});

test("grab, pinch, flatten, and smooth use the server weights", () => {
  const grab = at(plate(), { brush: "grab", radius: 4, strength: 0.2, points: [[0, 0, 1]], normal: [0, 0, 1], delta: [0, 0, 2] });
  assert.ok(Math.abs(grab.positions[2] - 3) < 1e-9);
  const moved = at(plate(), { brush: "pinch", radius: 5, strength: 1, points: [[0, 0, 1]], normal: [0, 0, 1] });
  const w = (1 - (3 / 5) ** 2) ** 2 * 0.3;
  assert.ok(Math.abs(moved.positions[3] - (3 + (0 - 3) * w)) < 1e-9);
  assert.equal(moved.positions[5], 1);
  const flatPrep = prepareStroke([0, 0, 2, 1, 0, 1, 0, 1, 1], [0, 1, 2]);
  const flat = at(flatPrep, { brush: "flatten", radius: 5, strength: 1, points: [[0, 0, 2]], normal: [0, 0, 1] });
  assert.ok(Math.abs(flat.positions[2] - 4 / 3) < 1e-9);
  const smooth = at(flatPrep, { brush: "smooth", radius: 5, strength: 1, points: [[0, 0, 2]], normal: [0, 0, 1] });
  assert.ok(Math.abs(smooth.positions[2] - 1) < 1e-9);
});

test("mirror across the model centre moves the other side and leaves a far vertex", () => {
  const positions = [
    2, 0, 1, 4, 0, 1, 2, 2, 1,
    -2, 0, 1, -4, 0, 1, -2, 2, 1,
  ];
  const faces = [0, 1, 2, 3, 5, 4];
  const prep = prepareStroke(positions, faces);
  const off = at(prep, { brush: "draw", radius: 1.5, strength: 1, points: [[2, 0, 1]], normal: [0, 0, 1], symmetry: false });
  assert.ok(Math.abs(off.positions[2] - 1.225) < 1e-9);
  assert.equal(off.positions[11], 1);
  const on = at(prep, { brush: "draw", radius: 1.5, strength: 1, points: [[2, 0, 1]], normal: [0, 0, 1], symmetry: true });
  assert.ok(Math.abs(on.positions[2] - 1.225) < 1e-9);
  assert.ok(Math.abs(on.positions[11] - 1.225) < 1e-9);
  assert.equal(on.positions[5], 1);
});

test("a back-only dab, a zero strength, and a fold are not kept", () => {
  const back = at(plate(), { brush: "draw", radius: 0.5, strength: 1, points: [[0, 0, 0]], normal: [0, 0, 1] });
  assert.equal(back.kept, false);
  assert.match(back.reason, /back of a thin wall/);
  assert.equal(back.positions[2], 1);
  const zero = at(plate(), { brush: "draw", radius: 4, strength: 0, points: [[0, 0, 1]], normal: [0, 0, 1] });
  assert.equal(zero.kept, false);
  assert.match(zero.reason, /Strength is 0/);
  assert.equal(zero.positions[2], 1);
  const fold = at(plate(), { brush: "grab", radius: 2.5, strength: 1, points: [[0, 0, 1]], normal: [0, 0, 1], delta: [10, 10, 0] });
  assert.equal(fold.kept, false);
  assert.match(fold.reason, /folded/);
  assert.equal(fold.positions[2], 1);
  assert.equal(fold.positions[11], 0);
});

test("the idle line names the brush and does not pretend grab uses the slider", () => {
  assert.match(sculptIdle("draw", 5, 0.5, false, true), /Draw · 5 mm · 50%/);
  assert.match(sculptIdle("grab", 5, 0.5, true, true), /mirror on/);
  assert.match(sculptIdle("grab", 5, 0.5, false, true), /slider is not used/);
  assert.equal(sculptIdle("draw", 5, 0.5, false, false), "Make a solid first.");
});
