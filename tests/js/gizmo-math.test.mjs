/* Beads write the transform steps ZEIM already has. No second pipeline. */
import test from "node:test";
import assert from "node:assert/strict";
import {
  axisTravel, cadCommit, commitFor, dragAmount, handlesFor, handleName, keyAmount,
  layoutHandles, meshCommit, overlapsChrome, plateCommit, previewPlacement, readout,
  ringSamples, rotateAround, scaleFromTravel, snapFactor, snapMove, snapTurn, worldFromScreenAngle, worthCommit,
} from "../../static/gizmo-math.js";

const box = { min: [0, 0, 0], max: [20, 10, 30] };
const plate = { mode: "move", surface: "plate", center: [10, 5, 15], size: [20, 10, 30], box, body: null };

test("plate handles stay on the bed: move X/Y, turn Z, no lift", () => {
  assert.deepEqual(handlesFor("plate", "move"), ["x", "y"]);
  assert.deepEqual(handlesFor("plate", "rotate"), ["z"]);
  assert.deepEqual(handlesFor("plate", "scale"), ["x", "y", "z", "u"]);
  assert.equal(plateCommit("move", "z", 12, box, false), null);
  assert.equal(plateCommit("rotate", "x", 90, box, false), null);
  assert.equal(handleName("move", "x"), "Move along X");
  assert.equal(handleName("scale", "u"), "Resize all sides together");
});

test("plate move, turn, and scale use the plate transform step", () => {
  assert.deepEqual(plateCommit("move", "x", 5.4, box, false), { op: "plate", params: { action: "transform", dx: 5 } });
  assert.deepEqual(plateCommit("move", "y", -2, box, false), { op: "plate", params: { action: "transform", dy: -2 } });
  assert.equal(plateCommit("move", "x", 0.2, box, false), null);
  assert.deepEqual(plateCommit("move", "x", 0.2, box, true), { op: "plate", params: { action: "transform", dx: 0.2 } });
  assert.deepEqual(plateCommit("rotate", "z", 12, box, false), { op: "plate", params: { action: "transform", rz: 10 } });
  assert.deepEqual(plateCommit("scale", "u", 1.5, box, false), { op: "plate", params: { action: "transform", scale_pct: 150 } });
  assert.deepEqual(plateCommit("scale", "x", 2, box, false), { op: "plate", params: { action: "transform", size_mm: { x: 40 } } });
  assert.equal(plateCommit("scale", "z", 1, box, false), null);
});

test("a single model uses translate, rotate, and scale", () => {
  assert.deepEqual(meshCommit("move", "z", 4, false), { op: "translate", params: { dx: 0, dy: 0, dz: 4 } });
  assert.deepEqual(meshCommit("rotate", "y", 90, false), { op: "rotate", params: { rx: 0, ry: 90, rz: 0 } });
  const uniform = meshCommit("scale", "u", 1.25, false);
  assert.equal(uniform.op, "scale");
  assert.equal(uniform.params.pivot, "base");
  assert.equal(uniform.params.factor, 1.25);
  const axis = meshCommit("scale", "y", 1.5, false);
  assert.deepEqual(axis.params, { sx: 1, sy: 1.5, sz: 1, pivot: "base" });
});

test("CAD beads use body_transform and the body the panel already names", () => {
  assert.deepEqual(cadCommit("move", "x", 3, 1, false), { op: "body_transform", params: { body: 1, move: [3, 0, 0] } });
  assert.deepEqual(cadCommit("rotate", "z", 15, -1, false), { op: "body_transform", params: { body: -1, rotate: [0, 0, 15] } });
  assert.deepEqual(cadCommit("scale", "u", 2, 0, false).params.scale, [2, 2, 2]);
  assert.deepEqual(cadCommit("scale", "x", 1.5, 0, false).params.scale, [1.5, 1, 1]);
  assert.equal(cadCommit("move", "x", 1, NaN, false), null);
  assert.deepEqual(handlesFor("cad", "move"), ["x", "y", "z"]);
});

test("commitFor picks the surface's existing step", () => {
  assert.equal(commitFor({ ...plate, mode: "rotate" }, "z", 20, false).params.rz, 20);
  assert.equal(commitFor({ ...plate, surface: "mesh", mode: "move" }, "x", 8, false).op, "translate");
  assert.equal(commitFor({ ...plate, surface: "cad", mode: "move", body: 2 }, "y", 4, false).op, "body_transform");
  assert.equal(commitFor(null, "x", 5, false), null);
});

test("drag math snaps and keeps a scale drag as a factor", () => {
  const right = [1, 0, 0], up = [0, 0, 1];
  assert.equal(axisTravel([1, 0, 0], right, up, 10, 0, 2), 5);
  assert.equal(axisTravel([0, 0, 1], right, up, 10, 0, 2), 0);
  assert.equal(snapMove(1.6, false), 2);
  assert.equal(snapTurn(12, false), 10);
  assert.equal(snapFactor(1.006, false), 1.01);
  assert.equal(scaleFromTravel(20, 10), 1.5);
  const handle = { dir: [1, 0, 0], reach: 20, axis: "x" };
  const frame = { ...plate, mode: "scale" };
  assert.equal(dragAmount(frame, handle, 10, 0, { right, up, pxPerMm: 1 }, false, 0, 1), 1.5);
  assert.equal(worldFromScreenAngle(30, 15), 2);
  assert.equal(worldFromScreenAngle(10, 0), 0);
  assert.equal(worthCommit("move", 0.2, false), false);
  assert.equal(worthCommit("move", 0.2, true), true);
});

test("keyboard nudges are the same steps", () => {
  assert.equal(keyAmount("move", "ArrowRight", false, false), 1);
  assert.equal(keyAmount("move", "ArrowLeft", true, false), -10);
  assert.equal(keyAmount("rotate", "ArrowUp", false, true), 1);
  assert.equal(keyAmount("scale", "ArrowUp", false, false), 1.05);
  assert.equal(keyAmount("move", "Enter", false, false), null);
});

test("preview turns about the pivot and scale stays on that point", () => {
  const stay = previewPlacement([10, 0, 5], "rotate", "z", 90);
  assert.ok(Math.abs(stay.position[0] - 10) < 1e-6);
  assert.ok(Math.abs(stay.position[1] + 10) < 1e-6);
  const grown = previewPlacement([10, 0, 0], "scale", "u", 2);
  assert.deepEqual(grown.scale, [2, 2, 2]);
  assert.deepEqual(grown.position, [-10, 0, 0]);
  const slide = previewPlacement([0, 0, 0], "move", "y", -4);
  assert.deepEqual(slide.position, [0, -4, 0]);
  const spun = rotateAround([10, 0, 0], [0, 0, 0], [0, 0, 1], 90);
  assert.ok(Math.abs(spun[0]) < 1e-6 && Math.abs(spun[1] - 10) < 1e-6);
});

test("layout puts beads outside the box and a ring for turn", () => {
  const move = layoutHandles(plate);
  assert.deepEqual(move.map(h => h.axis), ["x", "y"]);
  assert.ok(move[0].at[0] > plate.center[0]);
  const turn = layoutHandles({ ...plate, mode: "rotate" });
  assert.equal(turn.length, 1);
  const ring = ringSamples(plate.center, [0, 0, 1], turn[0].reach, 8);
  assert.equal(ring.length, 8);
  assert.ok(Math.abs(ring[0][0] - turn[0].at[0]) < 1e-6);
});

test("readout is plain units and beads stay off chrome", () => {
  assert.equal(readout("plate", "move", "x", 12, box), "X  12 mm");
  assert.equal(readout("plate", "rotate", "z", 15, box), "Z  15°");
  assert.equal(readout("plate", "scale", "x", 2, box), "X  40 mm");
  assert.equal(readout("mesh", "scale", "u", 1.5, box), "All  150%");
  assert.equal(overlapsChrome(10, 10, [{ left: 0, top: 0, right: 40, bottom: 20, width: 40, height: 20 }], 0), true);
  assert.equal(overlapsChrome(100, 100, [{ left: 0, top: 0, right: 40, bottom: 20, width: 40, height: 20 }], 8), false);
  assert.equal(overlapsChrome(10, 10, [{ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }], 8), false);
});
