import test from "node:test";
import assert from "node:assert/strict";
import {
  clipHalfSpace, clipByW, screenOf, screenDist, inFrontOfHit, edgeMatches, distPointTri, chainStraight, closestSample, reconcileSelection,
} from "../../static/pickgeom.js";

test("a section cut drops the hidden side and keeps the visible part of a crossing edge", () => {
  const gone = clipHalfSpace([0, 0, -2], [0, 0, -1], -2, -1);
  assert.equal(gone, null);
  const kept = clipHalfSpace([0, 0, -2], [0, 0, 2], -2, 2);
  assert.ok(kept);
  assert.equal(kept.a[2], 0);
  assert.equal(kept.b[2], 2);
  const whole = clipHalfSpace([0, 0, 1], [1, 0, 1], 1, 1);
  assert.deepEqual(whole.a, [0, 0, 1]);
});

test("an edge behind the camera is not projected onto the screen", () => {
  const behind = clipByW({ x: 1, y: 0, z: 1, w: -0.4 }, { x: -1, y: 0, z: 1, w: -0.2 }, 1e-4);
  assert.equal(behind, null);
  const cross = clipByW({ x: -1, y: 0, z: 0, w: -1 }, { x: 1, y: 0, z: 0, w: 1 }, 1e-4);
  assert.ok(cross);
  assert.ok(cross[0].w >= 1e-4 - 1e-9 && cross[1].w >= 1e-4 - 1e-9);
  const [sx, sy] = screenOf({ x: 0, y: 0, z: 0, w: 1 }, 200, 100);
  assert.equal(sx, 100);
  assert.equal(sy, 50);
});

test("screen distance and occlusion", () => {
  const on = screenDist(0, 0, 10, 0, 4, 0);
  assert.ok(on.d < 1e-9);
  assert.equal(inFrontOfHit(10, 12, 0.01), true);
  assert.equal(inFrontOfHit(30, 10, 0.01), false);
  assert.equal(inFrontOfHit(10, null, 0.01), true);
});

test("a straight edge split into pieces is one length, and a corner stops it", () => {
  const flat = [
    0, 0, 0, 10, 0, 0,
    10, 0, 0, 20, 0, 0,
    20, 0, 0, 20, 10, 0,
  ];
  const run = chainStraight([0, 0, 0], [10, 0, 0], flat);
  assert.deepEqual(run.a, [0, 0, 0]);
  assert.deepEqual(run.b, [20, 0, 0]);
  const corner = chainStraight([10, 0, 0], [20, 0, 0], flat);
  assert.deepEqual(corner.a, [0, 0, 0]);
  assert.deepEqual(corner.b, [20, 0, 0]);
  const turn = chainStraight([20, 0, 0], [20, 10, 0], flat);
  assert.deepEqual(turn.a, [20, 0, 0]);
  assert.deepEqual(turn.b, [20, 10, 0]);
  const hit = closestSample(10, 10, [
    { p: [0, 0, 0], px: 0, py: 0, behind: false },
    { p: [1, 0, 0], px: 12, py: 9, behind: false },
    { p: [2, 0, 0], px: 4, py: 4, behind: true },
  ], 8);
  assert.deepEqual(hit, [1, 0, 0]);
  assert.equal(closestSample(0, 0, [{ p: [1, 1, 1], px: 40, py: 40, behind: false }], 8), null);
});

test("a lost edge or face is dropped and a real one stays", () => {
  const bodies = [{
    index: 0,
    visible: true,
    edges: [0, 0, 0, 10, 0, 0],
    tris: [0, 0, 0, 10, 0, 0, 0, 10, 0],
  }];
  const kept = reconcileSelection({
    body: 0,
    edges: [{ a: [0, 0, 0], b: [10, 0, 0], body: 0 }],
    face: [2, 2, 0],
  }, bodies, 0.5);
  assert.equal(kept.droppedEdge, false);
  assert.equal(kept.droppedFace, false);
  assert.equal(kept.edges.length, 1);
  assert.ok(distPointTri([2, 2, 0], [0, 0, 0], [10, 0, 0], [0, 10, 0]) < 1e-6);

  const lost = reconcileSelection({
    body: 0,
    edges: [{ a: [0, 0, 5], b: [10, 0, 5], body: 0 }],
    face: [2, 2, 8],
  }, bodies, 0.5);
  assert.equal(lost.droppedEdge, true);
  assert.equal(lost.droppedFace, true);
  assert.equal(lost.edges.length, 0);
  assert.equal(lost.face, null);

  const hidden = reconcileSelection({
    body: 0,
    edges: [{ a: [0, 0, 0], b: [10, 0, 0], body: 0 }],
    face: [2, 2, 0],
  }, [{ ...bodies[0], visible: false }], 0.5);
  assert.equal(hidden.droppedBody, true);
  assert.equal(hidden.body, -1);
  assert.equal(hidden.edges.length, 0);
  assert.equal(edgeMatches([10, 0, 0], [0, 0, 0], bodies[0].edges, 0.2), true);
});
