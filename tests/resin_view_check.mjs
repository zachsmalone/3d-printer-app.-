/* Cache and pick grid for resin support taps. node tests/resin_view_check.mjs [triangles] */
import { createMeshCache, buildGrid, raycastGrid, legacyTapBytes, parseBinaryStl } from "../static/resin-view.js";

function assert(cond, msg) {
  if (!cond) {
    console.error(msg);
    process.exit(1);
  }
}

function stlTriangle() {
  const buf = new ArrayBuffer(84 + 50);
  const dv = new DataView(buf);
  dv.setUint32(80, 1, true);
  const verts = [0, 0, 0, 2, 0, 0, 0, 2, 0];
  verts.forEach((v, i) => dv.setFloat32(84 + 12 + i * 4, v, true));
  return buf;
}

const one = parseBinaryStl(stlTriangle());
assert(one.triangles === 1, "one triangle");
assert(Math.abs(one.positions[3] - 2) < 1e-6, "vertex kept");

const cache = createMeshCache();
const buf = stlTriangle();
const first = cache.use(buf);
const second = cache.use(buf);
assert(first.built === true && second.built === false, "second use must not rebuild");
assert(first.positions === second.positions, "position buffer is reused");
assert(cache.builds === 1, "one build");
const other = cache.use(stlTriangle());
assert(other.built === true && cache.builds === 2, "a new file builds again");

const positions = new Float32Array([
  -1, -1, 0, 1, -1, 0, 0, 1, 0,
]);
const grid = buildGrid(positions, 4);
const hit = raycastGrid(grid, [0, 0, 5], [0, 0, -1]);
assert(hit && Math.abs(hit.point[2]) < 1e-4, "ray hits the triangle");
assert(Math.abs(hit.point[0]) < 0.3 && Math.abs(hit.point[1]) < 0.3, "hit is near the centre");
const miss = raycastGrid(grid, [5, 5, 5], [0, 0, -1]);
assert(miss === null, "ray past the triangle misses");
const behind = raycastGrid(grid, [0, 0, -2], [0, 0, -1]);
assert(behind === null, "ray pointing away misses");

const sheetN = 400;
const sheet = new Float32Array(sheetN * 9);
for (let i = 0; i < sheetN; i++) {
  const x = (i % 20) * 0.5, y = Math.floor(i / 20) * 0.5, o = i * 9;
  sheet[o] = x; sheet[o + 1] = y; sheet[o + 2] = 0;
  sheet[o + 3] = x + 0.5; sheet[o + 4] = y; sheet[o + 5] = 0;
  sheet[o + 6] = x; sheet[o + 7] = y + 0.5; sheet[o + 8] = 0;
}
const sheetGrid = buildGrid(sheet);
const sheetHit = raycastGrid(sheetGrid, [1.1, 1.1, 3], [0, 0, -1]);
assert(sheetHit && Math.abs(sheetHit.point[2]) < 1e-3, "sheet ray hits z=0");
assert(Math.abs(sheetHit.point[0] - 1.1) < 0.05 && Math.abs(sheetHit.point[1] - 1.1) < 0.05, "sheet hit stays on the ray");

const tris = Math.max(1, Number(process.argv[2] || 20000));
const big = new Float32Array(tris * 9);
for (let i = 0; i < tris; i++) {
  const x = (i % 1000) * 0.2, y = Math.floor(i / 1000) * 0.2, o = i * 9;
  big[o] = x; big[o + 1] = y; big[o + 2] = 0;
  big[o + 3] = x + 0.2; big[o + 4] = y; big[o + 5] = 0;
  big[o + 6] = x; big[o + 7] = y + 0.2; big[o + 8] = 0;
}
const legacy = legacyTapBytes(big, 5);
const heapAfterLegacy = process.memoryUsage().heapUsed;
const tGrid = performance.now();
const bigGrid = buildGrid(big);
const gridMs = performance.now() - tGrid;
const tRays = performance.now();
let hits = 0;
for (let i = 0; i < 8; i++) {
  const x = 2.05 + i * 0.2, y = 0.05;
  const h = raycastGrid(bigGrid, [x, y, 8], [0, 0, -1]);
  if (h && Math.abs(h.point[2]) < 1e-2 && Math.abs(h.point[0] - x) < 0.05) hits += 1;
}
const rayMs = performance.now() - tRays;
const heapAfterReuse = process.memoryUsage().heapUsed;
process.stdout.write(JSON.stringify({
  triangles: tris,
  legacy_taps: 5,
  legacy_ms: Math.round(legacy.ms * 10) / 10,
  legacy_bytes: legacy.bytes,
  grid_ms: Math.round(gridMs * 10) / 10,
  eight_rays_ms: Math.round(rayMs * 10) / 10,
  rays_hit: hits,
  heap_after_legacy_bytes: heapAfterLegacy,
  heap_after_reuse_bytes: heapAfterReuse,
}));
if (hits < 8) {
  console.error("large sheet missed a ray");
  process.exit(1);
}
