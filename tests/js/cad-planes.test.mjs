import test from "node:test";
import assert from "node:assert/strict";
import { offsetPlane, midPlane, parallel, hintsOn, setHintsOn, HINTS_KEY } from "../../static/cad-planes.js";

test("offset from named plane and face", () => {
  assert.deepEqual(offsetPlane("XY", 10).origin, [0, 0, 10]);
  assert.equal(offsetPlane("XY", 10).construct, "offset");
  assert.deepEqual(offsetPlane({ origin: [1, 2, 3], normal: [0, 2, 0] }, -4).origin, [1, -2, 3]);
  assert.throws(() => offsetPlane("XY", "abc"));
});
test("midplane between parallel planes, rejects non-parallel", () => {
  const m = midPlane({ origin: [0, 0, 2], normal: [0, 0, 1] }, { origin: [5, 5, 10], normal: [0, 0, -1] });
  assert.deepEqual(m.origin, [0, 0, 6]); assert.equal(m.construct, "midplane");
  assert.deepEqual(midPlane("YZ", offsetPlane("YZ", 30)).origin, [15, 0, 0]);
  assert.throws(() => midPlane("XY", "XZ"));
  assert.equal(parallel("XY", "XZ"), false); assert.equal(parallel("XY", offsetPlane("XY", 3)), true);
});
test("hints preference persists and defaults on", () => {
  const m = new Map(); const st = { getItem: k => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
  assert.equal(hintsOn(st), true);
  setHintsOn(st, false); assert.equal(m.get(HINTS_KEY), "off"); assert.equal(hintsOn(st), false);
  setHintsOn(st, true); assert.equal(hintsOn(st), true);
  assert.equal(hintsOn({ getItem() { throw new Error("blocked"); } }), true);
});
