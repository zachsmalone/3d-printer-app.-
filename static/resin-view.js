/* One parsed STL and a grid for support taps.
   Placing a mark must not copy the triangle buffer again. The grid is built once. */

export function parseBinaryStl(buf) {
  const dv = new DataView(buf);
  if (buf.byteLength < 84) throw new Error("not a binary STL");
  const n = dv.getUint32(80, true);
  if (84 + n * 50 > buf.byteLength) throw new Error("not a binary STL");
  const positions = new Float32Array(n * 9);
  for (let i = 0; i < n; i++) {
    const base = 84 + i * 50 + 12;
    const o = i * 9;
    for (let k = 0; k < 9; k++) positions[o + k] = dv.getFloat32(base + k * 4, true);
  }
  return { triangles: n, positions };
}

/* Same buffer object means the mesh is already on the GPU. A new file is a new buffer. */
export function createMeshCache() {
  let key = null;
  let positions = null;
  let triangles = 0;
  let builds = 0;
  return {
    get builds() { return builds; },
    get positions() { return positions; },
    get triangles() { return triangles; },
    use(buf) {
      if (buf && buf === key && positions) return { positions, triangles, built: false };
      const parsed = parseBinaryStl(buf);
      key = buf;
      positions = parsed.positions;
      triangles = parsed.triangles;
      builds += 1;
      return { positions, triangles, built: true };
    },
  };
}

function hitTriangle(ox, oy, oz, dx, dy, dz, ax, ay, az, bx, by, bz, cx, cy, cz) {
  const e1x = bx - ax, e1y = by - ay, e1z = bz - az;
  const e2x = cx - ax, e2y = cy - ay, e2z = cz - az;
  const px = dy * e2z - dz * e2y;
  const py = dz * e2x - dx * e2z;
  const pz = dx * e2y - dy * e2x;
  const det = e1x * px + e1y * py + e1z * pz;
  if (det > -1e-8 && det < 1e-8) return null;
  const inv = 1 / det;
  const tx = ox - ax, ty = oy - ay, tz = oz - az;
  const u = (tx * px + ty * py + tz * pz) * inv;
  if (u < 0 || u > 1) return null;
  const qx = ty * e1z - tz * e1y;
  const qy = tz * e1x - tx * e1z;
  const qz = tx * e1y - ty * e1x;
  const v = (dx * qx + dy * qy + dz * qz) * inv;
  if (v < 0 || u + v > 1) return null;
  const t = (e2x * qx + e2y * qy + e2z * qz) * inv;
  if (t < 1e-5) return null;
  return {
    t,
    nx: e1y * e2z - e1z * e2y,
    ny: e1z * e2x - e1x * e2z,
    nz: e1x * e2y - e1y * e2x,
  };
}

export function buildGrid(positions, divisions) {
  const n = positions.length / 9;
  const cellsAcross = divisions || (n < 2000 ? 8 : n < 100000 ? 24 : 48);
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i], y = positions[i + 1], z = positions[i + 2];
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }
  const sx = Math.max(maxX - minX, 1e-6);
  const sy = Math.max(maxY - minY, 1e-6);
  const sz = Math.max(maxZ - minZ, 1e-6);
  const cells = new Map();
  const large = [];
  const span = cellsAcross;
  for (let tri = 0; tri < n; tri++) {
    const o = tri * 9;
    let x0 = Infinity, y0 = Infinity, z0 = Infinity;
    let x1 = -Infinity, y1 = -Infinity, z1 = -Infinity;
    for (let k = 0; k < 3; k++) {
      const x = positions[o + k * 3], y = positions[o + k * 3 + 1], z = positions[o + k * 3 + 2];
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
      if (z < z0) z0 = z;
      if (z > z1) z1 = z;
    }
    const ix0 = Math.max(0, Math.min(span - 1, Math.floor((x0 - minX) / sx * span)));
    const iy0 = Math.max(0, Math.min(span - 1, Math.floor((y0 - minY) / sy * span)));
    const iz0 = Math.max(0, Math.min(span - 1, Math.floor((z0 - minZ) / sz * span)));
    const ix1 = Math.max(0, Math.min(span - 1, Math.floor((x1 - minX) / sx * span)));
    const iy1 = Math.max(0, Math.min(span - 1, Math.floor((y1 - minY) / sy * span)));
    const iz1 = Math.max(0, Math.min(span - 1, Math.floor((z1 - minZ) / sz * span)));
    const count = (ix1 - ix0 + 1) * (iy1 - iy0 + 1) * (iz1 - iz0 + 1);
    if (count > 8) { large.push(tri); continue; }
    for (let ix = ix0; ix <= ix1; ix++) {
      for (let iy = iy0; iy <= iy1; iy++) {
        for (let iz = iz0; iz <= iz1; iz++) {
          const key = (ix * span + iy) * span + iz;
          let bucket = cells.get(key);
          if (!bucket) { bucket = []; cells.set(key, bucket); }
          bucket.push(tri);
        }
      }
    }
  }
  return {
    positions, divisions: span, minX, minY, minZ, sx, sy, sz, cells, large,
    triangles: n, seen: new Uint32Array(n), stamp: 1,
  };
}

function consider(grid, tri, ox, oy, oz, dx, dy, dz, best) {
  if (grid.seen[tri] === grid.stamp) return best;
  grid.seen[tri] = grid.stamp;
  const o = tri * 9;
  const p = grid.positions;
  const h = hitTriangle(ox, oy, oz, dx, dy, dz,
    p[o], p[o + 1], p[o + 2], p[o + 3], p[o + 4], p[o + 5], p[o + 6], p[o + 7], p[o + 8]);
  if (h && h.t < best.t) return h;
  return best;
}

/* Closest hit of a ray against the grid. `direction` does not need to be a unit vector. */
export function raycastGrid(grid, origin, direction) {
  const ox = origin[0], oy = origin[1], oz = origin[2];
  let dx = direction[0], dy = direction[1], dz = direction[2];
  const len = Math.hypot(dx, dy, dz) || 1;
  dx /= len; dy /= len; dz /= len;
  grid.stamp += 1;
  if (grid.stamp === 0xffffffff) {
    grid.seen.fill(0);
    grid.stamp = 1;
  }
  let best = { t: Infinity };
  for (let i = 0; i < grid.large.length; i++) best = consider(grid, grid.large[i], ox, oy, oz, dx, dy, dz, best);
  const { divisions, minX, minY, minZ, sx, sy, sz } = grid;
  const maxX = minX + sx, maxY = minY + sy, maxZ = minZ + sz;
  let t0 = 0, t1 = Infinity;
  const slabs = [[ox, dx, minX, maxX], [oy, dy, minY, maxY], [oz, dz, minZ, maxZ]];
  for (let a = 0; a < 3; a++) {
    const [o, d, lo, hi] = slabs[a];
    if (Math.abs(d) < 1e-12) {
      if (o < lo || o > hi) return finish(best, ox, oy, oz, dx, dy, dz);
      continue;
    }
    let ta = (lo - o) / d, tb = (hi - o) / d;
    if (ta > tb) { const s = ta; ta = tb; tb = s; }
    if (ta > t0) t0 = ta;
    if (tb < t1) t1 = tb;
    if (t0 > t1) return finish(best, ox, oy, oz, dx, dy, dz);
  }
  if (t1 < 0) return finish(best, ox, oy, oz, dx, dy, dz);
  const tEnter = Math.max(t0, 0);
  const px = ox + dx * (tEnter + 1e-8);
  const py = oy + dy * (tEnter + 1e-8);
  const pz = oz + dz * (tEnter + 1e-8);
  let ix = Math.max(0, Math.min(divisions - 1, Math.floor((px - minX) / sx * divisions)));
  let iy = Math.max(0, Math.min(divisions - 1, Math.floor((py - minY) / sy * divisions)));
  let iz = Math.max(0, Math.min(divisions - 1, Math.floor((pz - minZ) / sz * divisions)));
  const stepX = dx > 0 ? 1 : dx < 0 ? -1 : 0;
  const stepY = dy > 0 ? 1 : dy < 0 ? -1 : 0;
  const stepZ = dz > 0 ? 1 : dz < 0 ? -1 : 0;
  const cellX = sx / divisions, cellY = sy / divisions, cellZ = sz / divisions;
  const tDeltaX = stepX === 0 ? Infinity : Math.abs(cellX / dx);
  const tDeltaY = stepY === 0 ? Infinity : Math.abs(cellY / dy);
  const tDeltaZ = stepZ === 0 ? Infinity : Math.abs(cellZ / dz);
  const plane = (i, step, min, size, origin, dir) => {
    if (step === 0) return Infinity;
    const boundary = min + (step > 0 ? i + 1 : i) * size;
    return (boundary - origin) / dir;
  };
  let tMaxX = plane(ix, stepX, minX, cellX, ox, dx);
  let tMaxY = plane(iy, stepY, minY, cellY, oy, dy);
  let tMaxZ = plane(iz, stepZ, minZ, cellZ, oz, dz);
  const limit = divisions * 3 + 2;
  for (let step = 0; step < limit; step++) {
    const key = (ix * divisions + iy) * divisions + iz;
    const bucket = grid.cells.get(key);
    if (bucket) {
      for (let b = 0; b < bucket.length; b++) best = consider(grid, bucket[b], ox, oy, oz, dx, dy, dz, best);
    }
    const exit = Math.min(tMaxX, tMaxY, tMaxZ);
    if (best.t <= exit) break;
    if (exit === Infinity || exit > t1 + 1e-6) break;
    if (tMaxX <= tMaxY && tMaxX <= tMaxZ) { ix += stepX; tMaxX += tDeltaX; }
    else if (tMaxY <= tMaxZ) { iy += stepY; tMaxY += tDeltaY; }
    else { iz += stepZ; tMaxZ += tDeltaZ; }
    if (ix < 0 || iy < 0 || iz < 0 || ix >= divisions || iy >= divisions || iz >= divisions) break;
  }
  return finish(best, ox, oy, oz, dx, dy, dz);
}

function finish(best, ox, oy, oz, dx, dy, dz) {
  if (!best || !(best.t < Infinity)) return null;
  const nl = Math.hypot(best.nx, best.ny, best.nz) || 1;
  return {
    t: best.t,
    point: [ox + dx * best.t, oy + dy * best.t, oz + dz * best.t],
    normal: [best.nx / nl, best.ny / nl, best.nz / nl],
  };
}

/* What one old tap allocated: a fresh copy of the positions and a fresh normal buffer. */
export function legacyTapBytes(positions, taps) {
  const held = [];
  const t0 = performance.now();
  for (let i = 0; i < taps; i++) {
    const copy = new Float32Array(positions.length);
    copy.set(positions);
    held.push(copy, new Float32Array(positions.length));
  }
  return { ms: performance.now() - t0, arrays: held.length, bytes: held.length * positions.byteLength };
}
