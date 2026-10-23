import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { GcodeParser, typeOf } = require("../../static/gcode-parse.js");
const MINI = readFileSync(new URL("../fixtures/gcode/mini.gcode", import.meta.url), "utf8");

function parse(text, chunk = 0) {
  const layers = []; const p = new GcodeParser({ onLayer: L => layers.push(L) });
  if (chunk) for (let i = 0; i < text.length; i += chunk) p.push(text.slice(i, i + chunk)); else p.push(text);
  const r = p.end(); return { ...r, layerCount: r.layers, layers };
}
const count = (L, t) => (L.groups.find(g => g.type === t) || { count: 0 }).count / 2;

test("layers: one per extruding Z, z-hop and retract-lift are not layers", () => {
  const { layers } = parse(MINI);
  assert.deepEqual(layers.map(l => l.z), [0.2, 0.4, 0.6]);
  assert.deepEqual(layers.map(l => l.index), [0, 1, 2]);
  assert.equal(layers[1].height, 0.2);
});
test("feature types from ;TYPE: comments", () => {
  const [l0, l1] = parse(MINI).layers;
  assert.equal(count(l0, "skirt"), 1); assert.equal(count(l0, "outer"), 1); assert.equal(count(l0, "inner"), 1);
  assert.equal(count(l0, "infill"), 1); assert.equal(count(l0, "solid"), 1);
  assert.equal(count(l1, "support"), 1);
  assert.ok(count(l0, "travel") >= 1, "travel moves recorded (hidden in UI by default)");
  assert.equal(typeOf("Top solid infill"), "solid"); assert.equal(typeOf("WALL-OUTER"), "outer"); assert.equal(typeOf("SUPPORT-INTERFACE"), "support");
  assert.equal(typeOf("Overhang perimeter"), "outer"); assert.equal(typeOf("Gap fill"), "solid"); assert.equal(typeOf("Wipe tower"), "other");
});
test("G2/G3 arcs are split into chords that stay on the circle", () => {
  const l1 = parse(MINI).layers[1];
  const g = l1.groups.find(x => x.type === "outer"); assert.ok(g.count / 2 > 20, "many chords");
  const P = l1.positions; let maxDev = 0, minY = 1e9, maxY = -1e9;
  for (let v = g.start; v < g.start + g.count; v++) {
    const x = P[v * 3], y = P[v * 3 + 1]; maxDev = Math.max(maxDev, Math.abs(Math.hypot(x - 11, y - 6) - 5)); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  assert.ok(maxDev < 1e-3, "on radius 5 around (11,6): " + maxDev);
  assert.ok(minY > 5.99 && maxY > 10.9, "CW from the left and CCW from the right both pass over the top: " + minY + " " + maxY);
});
test("R-form arcs pick the right centre (CW minor arc bulges up, CCW down)", () => {
  const ys = (code) => { const L = parse(`G1 Z0.2\nG1 X0 Y0\nG1 X0.001 Y0 E0.01\n${code} X10 Y0 R10 E1\n`).layers[0]; return [...L.positions].filter((_, i) => i % 3 === 1); };
  assert.ok(Math.max(...ys("G2")) > 1.3, "G2 R+ goes above");
  assert.ok(Math.min(...ys("G3")) < -1.3, "G3 R+ goes below");
});
test("absolute/relative E, G92, G91 relative XY, N/checksum stripped, G10/G11 ignored", () => {
  const { layers, stats } = parse(MINI);
  const l2 = layers[2];
  assert.equal(count(l2, "outer"), 3, "X7 extrudes, X8 (E down) is travel, G91 X+1 extrudes, N12 line extrudes -> 3");
  assert.equal(count(l2, "travel"), 1);
  const g = l2.groups.find(x => x.type === "outer"), e = (g.start + g.count) * 3;
  const last = [...l2.positions.slice(e - 3, e)].map(v => Math.round(v * 1000) / 1000);
  assert.deepEqual(last, [20, 20, 0.6]);
  assert.ok(Math.abs(stats.filamentMm - (0.5 * 4 + 0.1 + 0.2 + 2 + 0.3 + 0.1 + 0.5)) < 1e-6, String(stats.filamentMm));
});
test("slicer estimates read from comments", () => {
  const { meta } = parse(MINI);
  assert.equal(meta.time, "1m 2s"); assert.equal(meta.filamentMm, 12.34); assert.equal(meta.filamentG, 0.04);
});
test("chunked streaming (lines split across chunks) gives identical output", () => {
  const a = parse(MINI), b = parse(MINI, 7);
  assert.equal(a.layers.length, b.layers.length);
  a.layers.forEach((l, i) => assert.deepEqual([...l.positions], [...b.layers[i].positions]));
});
test("G0/G1 prefix does not match G10/G11/G100", () => {
  const { layers, stats } = parse("G1 Z0.2\nG1 X1 Y1 E1\nG10 X5\nG11 X9 E5\nG100 X3\nG01 X2 Y1 E1\n");
  assert.equal(layers.length, 1); assert.equal(stats.moves, 3);
});
test("mm/inch and Windows line endings", () => {
  const { layers } = parse("G20\r\nG1 Z0.01\r\nG1 X1 Y0 E0.1\r\n");
  assert.equal(layers.length, 1); assert.ok(Math.abs(layers[0].positions[3] - 25.4) < 1e-4); assert.ok(Math.abs(layers[0].z - 0.254) < 1e-3);
});
test("minSegLen joins tiny same-type pieces but keeps ends and types", () => {
  let g = "M83\nG1 Z0.2\nG1 X0 Y0\n;TYPE:Internal infill\n"; for (let i = 1; i <= 100; i++) g += `G1 X${i * 0.05} Y0 E0.01\n`;
  g += ";TYPE:Perimeter\nG1 X5 Y1 E0.1\n";
  const full = parse(g).layers[0];
  const layers = []; const p = new GcodeParser({ minSegLen: 0.5, onLayer: L => layers.push(L) }); p.push(g); p.end();
  const s = layers[0];
  assert.equal(count(full, "infill"), 100); assert.ok(count(s, "infill") <= 11, String(count(s, "infill")));
  assert.equal(count(s, "inner"), 1);
  const gi = s.groups.find(x => x.type === "infill"), e = (gi.start + gi.count) * 3;
  assert.ok(Math.abs(s.positions[e - 3] - 5) < 1e-5, "infill still ends at X5");
});
