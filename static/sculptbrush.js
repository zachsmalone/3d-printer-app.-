/* Live Sculpt preview. The displacement matches app/core/sculptws.py so the
   brush on screen is the stroke the server keeps: facing vertices only, the
   same falloff, a mirror across the model's centre, a 0.4 mm thin-wall hold,
   and a refusal when the stroke would fold or move the mesh outside the brush. */

export const BRUSHES = ["draw", "carve", "smooth", "inflate", "pinch", "flatten", "grab"];

const NAMES = {
  draw: "Draw", carve: "Carve", smooth: "Smooth", inflate: "Inflate",
  pinch: "Pinch", flatten: "Flatten", grab: "Grab",
};

export function brushTitle(id) {
  return NAMES[id] || "Draw";
}

export function sculptIdle(brush, radius, strength, sym, hasBody) {
  if (!hasBody) return "Make a solid first.";
  const name = brushTitle(brush);
  const mirror = sym ? " · mirror on" : "";
  if (brush === "grab") {
    return `${name} · ${radius} mm${mirror}. The centre follows your drag. The strength slider is not used.`;
  }
  return `${name} · ${radius} mm · ${Math.round(strength * 100)}%${mirror}. Drag the side you can see.`;
}

function centreX(positions) {
  let min = Infinity, max = -Infinity;
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i];
    if (x < min) min = x;
    if (x > max) max = x;
  }
  return Number.isFinite(min) ? (min + max) / 2 : 0;
}

function cornerAngle(ux, uy, uz, vx, vy, vz) {
  const lu = Math.hypot(ux, uy, uz), lv = Math.hypot(vx, vy, vz);
  if (lu < 1e-12 || lv < 1e-12) return 0;
  let d = (ux * vx + uy * vy + uz * vz) / (lu * lv);
  if (d > 1) d = 1;
  else if (d < -1) d = -1;
  return Math.acos(d);
}

function vertexNormals(pos, faces) {
  const n = pos.length / 3;
  const acc = new Float64Array(n * 3);
  for (let i = 0; i < faces.length; i += 3) {
    const a = faces[i], b = faces[i + 1], c = faces[i + 2];
    const ax = pos[a * 3], ay = pos[a * 3 + 1], az = pos[a * 3 + 2];
    const bx = pos[b * 3], by = pos[b * 3 + 1], bz = pos[b * 3 + 2];
    const cx = pos[c * 3], cy = pos[c * 3 + 1], cz = pos[c * 3 + 2];
    const abx = bx - ax, aby = by - ay, abz = bz - az;
    const acx = cx - ax, acy = cy - ay, acz = cz - az;
    let nx = aby * acz - abz * acy, ny = abz * acx - abx * acz, nz = abx * acy - aby * acx;
    const len = Math.hypot(nx, ny, nz);
    if (len < 1e-12) continue;
    nx /= len; ny /= len; nz /= len;
    const bax = ax - bx, bay = ay - by, baz = az - bz;
    const bcx = cx - bx, bcy = cy - by, bcz = cz - bz;
    const cax = ax - cx, cay = ay - cy, caz = az - cz;
    const cbx = bx - cx, cby = by - cy, cbz = bz - cz;
    const wa = cornerAngle(abx, aby, abz, acx, acy, acz);
    const wb = cornerAngle(bax, bay, baz, bcx, bcy, bcz);
    const wc = cornerAngle(cax, cay, caz, cbx, cby, cbz);
    acc[a * 3] += nx * wa; acc[a * 3 + 1] += ny * wa; acc[a * 3 + 2] += nz * wa;
    acc[b * 3] += nx * wb; acc[b * 3 + 1] += ny * wb; acc[b * 3 + 2] += nz * wb;
    acc[c * 3] += nx * wc; acc[c * 3 + 1] += ny * wc; acc[c * 3 + 2] += nz * wc;
  }
  for (let i = 0; i < n; i++) {
    const len = Math.hypot(acc[i * 3], acc[i * 3 + 1], acc[i * 3 + 2]);
    if (len < 1e-12) { acc[i * 3 + 2] = 1; continue; }
    acc[i * 3] /= len; acc[i * 3 + 1] /= len; acc[i * 3 + 2] /= len;
  }
  return acc;
}

function neighbors(n, faces) {
  const lists = Array.from({ length: n }, () => []);
  for (let i = 0; i < faces.length; i += 3) {
    const a = faces[i], b = faces[i + 1], c = faces[i + 2];
    lists[a].push(b, c);
    lists[b].push(a, c);
    lists[c].push(a, b);
  }
  return lists.map((row) => {
    const seen = new Set();
    const out = [];
    for (const j of row) if (!seen.has(j) && j !== undefined) { seen.add(j); out.push(j); }
    return out;
  });
}

function faceNormals(pos, faces) {
  const fn = new Float64Array(faces.length);
  for (let i = 0; i < faces.length; i += 3) {
    const a = faces[i], b = faces[i + 1], c = faces[i + 2];
    const abx = pos[b * 3] - pos[a * 3], aby = pos[b * 3 + 1] - pos[a * 3 + 1], abz = pos[b * 3 + 2] - pos[a * 3 + 2];
    const acx = pos[c * 3] - pos[a * 3], acy = pos[c * 3 + 1] - pos[a * 3 + 1], acz = pos[c * 3 + 2] - pos[a * 3 + 2];
    fn[i] = aby * acz - abz * acy;
    fn[i + 1] = abz * acx - abx * acz;
    fn[i + 2] = abx * acy - aby * acx;
  }
  return fn;
}

function foldedCount(v, faces, oldFn, touched) {
  let n = 0;
  for (let i = 0; i < faces.length; i += 3) {
    const a = faces[i], b = faces[i + 1], c = faces[i + 2];
    if (!touched[a] && !touched[b] && !touched[c]) continue;
    const abx = v[b * 3] - v[a * 3], aby = v[b * 3 + 1] - v[a * 3 + 1], abz = v[b * 3 + 2] - v[a * 3 + 2];
    const acx = v[c * 3] - v[a * 3], acy = v[c * 3 + 1] - v[a * 3 + 1], acz = v[c * 3 + 2] - v[a * 3 + 2];
    const nx = aby * acz - abz * acy, ny = abz * acx - abx * acz, nz = abx * acy - aby * acx;
    const area = Math.hypot(nx, ny, nz);
    if (area < 1e-12) { n++; continue; }
    if (nx * oldFn[i] + ny * oldFn[i + 1] + nz * oldFn[i + 2] < 0) n++;
  }
  return n;
}

function buildGrid(pos, ids, cell) {
  const map = new Map();
  for (const i of ids) {
    const k = Math.floor(pos[i * 3] / cell) + "," + Math.floor(pos[i * 3 + 1] / cell) + "," + Math.floor(pos[i * 3 + 2] / cell);
    let bucket = map.get(k);
    if (!bucket) map.set(k, bucket = []);
    bucket.push(i);
  }
  return map;
}

function nearest(pos, grid, cell, x, y, z, reach) {
  const r = Math.ceil(reach / cell);
  const ix = Math.floor(x / cell), iy = Math.floor(y / cell), iz = Math.floor(z / cell);
  let best = Infinity, bj = -1;
  for (let dx = -r; dx <= r; dx++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dz = -r; dz <= r; dz++) {
        const bucket = grid.get((ix + dx) + "," + (iy + dy) + "," + (iz + dz));
        if (!bucket) continue;
        for (const j of bucket) {
          const d = Math.hypot(x - pos[j * 3], y - pos[j * 3 + 1], z - pos[j * 3 + 2]);
          if (d < best) { best = d; bj = j; }
        }
      }
    }
  }
  return { dist: best, j: bj };
}

function clampThinWall(v, v0, vn, nStroke) {
  const minWall = 0.4, reach = 8, cell = 2;
  const n = v0.length / 3;
  const moved = [];
  for (let i = 0; i < n; i++) {
    const dx = v[i * 3] - v0[i * 3], dy = v[i * 3 + 1] - v0[i * 3 + 1], dz = v[i * 3 + 2] - v0[i * 3 + 2];
    if (dx * dx + dy * dy + dz * dz > 1e-16) moved.push(i);
  }
  if (!moved.length) return 0;
  const back = [];
  for (let i = 0; i < n; i++) {
    if (vn[i * 3] * nStroke[0] + vn[i * 3 + 1] * nStroke[1] + vn[i * 3 + 2] * nStroke[2] < -0.2) back.push(i);
  }
  if (!back.length) return 0;
  const grid = buildGrid(v0, back, cell);
  let held = 0;
  for (const i of moved) {
    const x = v0[i * 3], y = v0[i * 3 + 1], z = v0[i * 3 + 2];
    const hit = nearest(v0, grid, cell, x, y, z, reach);
    if (hit.j < 0 || hit.dist >= reach || hit.dist + 1e-9 < minWall) continue;
    const qx = v0[hit.j * 3], qy = v0[hit.j * 3 + 1], qz = v0[hit.j * 3 + 2];
    const px = v[i * 3], py = v[i * 3 + 1], pz = v[i * 3 + 2];
    if (Math.hypot(px - qx, py - qy, pz - qz) >= minWall) continue;
    const dx = px - x, dy = py - y, dz = pz - z;
    const a = dx * dx + dy * dy + dz * dz;
    const bx = x - qx, by = y - qy, bz = z - qz;
    const b = 2 * (bx * dx + by * dy + bz * dz);
    const c = bx * bx + by * by + bz * bz - minWall * minWall;
    const disc = b * b - 4 * a * c;
    let s = 0;
    if (a > 1e-12 && disc >= 0) {
      const root = Math.sqrt(disc);
      const s1 = (-b - root) / (2 * a), s2 = (-b + root) / (2 * a);
      const ok1 = s1 >= 0 && s1 <= 1, ok2 = s2 >= 0 && s2 <= 1;
      if (ok1 && ok2) s = Math.min(s1, s2);
      else if (ok1) s = s1;
      else if (ok2) s = s2;
    }
    v[i * 3] = x + s * dx;
    v[i * 3 + 1] = y + s * dy;
    v[i * 3 + 2] = z + s * dz;
    held++;
  }
  return held;
}

function partnerOf(v0, cx) {
  const n = v0.length / 3;
  const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < 3; k++) {
      const p = v0[i * 3 + k];
      if (p < lo[k]) lo[k] = p;
      if (p > hi[k]) hi[k] = p;
    }
  }
  const span = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]);
  const tol = Math.max(1e-6, 1e-4 * (span || 1));
  const cell = tol;
  const map = new Map();
  const key = (x, y, z) => Math.round(x / cell) + "," + Math.round(y / cell) + "," + Math.round(z / cell);
  for (let i = 0; i < n; i++) map.set(key(v0[i * 3], v0[i * 3 + 1], v0[i * 3 + 2]), i);
  const j = new Int32Array(n);
  j.fill(-1);
  for (let i = 0; i < n; i++) {
    const mx = 2 * cx - v0[i * 3], y = v0[i * 3 + 1], z = v0[i * 3 + 2];
    const ix = Math.round(mx / cell), iy = Math.round(y / cell), iz = Math.round(z / cell);
    let found = -1, best = tol;
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dz = -1; dz <= 1; dz++) {
          const hit = map.get((ix + dx) + "," + (iy + dy) + "," + (iz + dz));
          if (hit == null) continue;
          const d = Math.hypot(mx - v0[hit * 3], y - v0[hit * 3 + 1], z - v0[hit * 3 + 2]);
          if (d <= best) { best = d; found = hit; }
        }
      }
    }
    j[i] = found;
  }
  return j;
}

function outsideMoved(v, v0, dabs, radius, sym, cx) {
  const margin = radius + Math.max(0.5, 0.02 * radius);
  const n = v0.length / 3;
  const near = (x, y, z) => {
    for (const c of dabs) if (Math.hypot(x - c[0], y - c[1], z - c[2]) <= margin + 1e-4) return true;
    return false;
  };
  for (let i = 0; i < n; i++) {
    const x = v0[i * 3], y = v0[i * 3 + 1], z = v0[i * 3 + 2];
    let inside = near(x, y, z);
    if (!inside && sym) inside = near(2 * cx - x, y, z);
    if (inside) continue;
    if (Math.hypot(v[i * 3] - x, v[i * 3 + 1] - y, v[i * 3 + 2] - z) > 1e-5) return true;
  }
  return false;
}

function dabIndices(v, c, r, vn, nStroke) {
  const idx = [];
  const r2 = r * r;
  for (let i = 0; i < v.length / 3; i++) {
    const dx = v[i * 3] - c[0], dy = v[i * 3 + 1] - c[1], dz = v[i * 3 + 2] - c[2];
    if (dx * dx + dy * dy + dz * dz >= r2) continue;
    if (vn[i * 3] * nStroke[0] + vn[i * 3 + 1] * nStroke[1] + vn[i * 3 + 2] * nStroke[2] <= 0.2) continue;
    idx.push(i);
  }
  return idx;
}

function runBrush(v0, faces, nbr, baseN, brush, dabs, nStroke, radius, strength, grab) {
  const v = new Float64Array(v0);
  const touched = new Uint8Array(v0.length / 3);
  const use = brush === "grab" ? dabs.slice(0, 1) : dabs;
  for (const c of use) {
    let vn = baseN;
    if (brush === "inflate") vn = vertexNormals(v, faces);
    const idx = dabIndices(v, c, radius, baseN, nStroke);
    if (!idx.length) continue;
    const upd = [];
    let flatN = nStroke, flatC = null;
    if (brush === "flatten") {
      let sx = 0, sy = 0, sz = 0;
      for (const i of idx) { sx += v[i * 3]; sy += v[i * 3 + 1]; sz += v[i * 3 + 2]; }
      flatC = [sx / idx.length, sy / idx.length, sz / idx.length];
    }
    for (const i of idx) {
      touched[i] = 1;
      const dx = v[i * 3] - c[0], dy = v[i * 3 + 1] - c[1], dz = v[i * 3 + 2] - c[2];
      const d = Math.hypot(dx, dy, dz);
      const w = (1 - (d / radius) ** 2) ** 2 * strength;
      if (brush === "draw" || brush === "carve") {
        const mag = w * 0.15 * radius * (brush === "draw" ? 1 : -1);
        upd.push([i, nStroke[0] * mag, nStroke[1] * mag, nStroke[2] * mag]);
      } else if (brush === "inflate") {
        const mag = w * 0.15 * radius;
        upd.push([i, vn[i * 3] * mag, vn[i * 3 + 1] * mag, vn[i * 3 + 2] * mag]);
      } else if (brush === "smooth") {
        const nb = nbr[i];
        let sx = 0, sy = 0, sz = 0;
        for (const j of nb) { sx += v[j * 3]; sy += v[j * 3 + 1]; sz += v[j * 3 + 2]; }
        const deg = nb.length || 1;
        upd.push([i, (sx / deg - v[i * 3]) * w, (sy / deg - v[i * 3 + 1]) * w, (sz / deg - v[i * 3 + 2]) * w]);
      } else if (brush === "pinch") {
        let tx = c[0] - v[i * 3], ty = c[1] - v[i * 3 + 1], tz = c[2] - v[i * 3 + 2];
        const along = tx * nStroke[0] + ty * nStroke[1] + tz * nStroke[2];
        tx -= along * nStroke[0]; ty -= along * nStroke[1]; tz -= along * nStroke[2];
        const mag = w * 0.3;
        upd.push([i, tx * mag, ty * mag, tz * mag]);
      } else if (brush === "flatten") {
        const px = v[i * 3] - flatC[0], py = v[i * 3 + 1] - flatC[1], pz = v[i * 3 + 2] - flatC[2];
        const along = (px * flatN[0] + py * flatN[1] + pz * flatN[2]) * w;
        upd.push([i, -flatN[0] * along, -flatN[1] * along, -flatN[2] * along]);
      } else if (brush === "grab") {
        const mag = w / Math.max(strength, 1e-9);
        upd.push([i, grab[0] * mag, grab[1] * mag, grab[2] * mag]);
      }
    }
    for (const [i, x, y, z] of upd) {
      v[i * 3] += x; v[i * 3 + 1] += y; v[i * 3 + 2] += z;
    }
  }
  const delta = new Float64Array(v.length);
  for (let i = 0; i < v.length; i++) delta[i] = v[i] - v0[i];
  return { delta, touched };
}

function mirrorDelta(delta, v0, cx) {
  const n = v0.length / 3;
  const out = new Float64Array(delta.length);
  const partners = partnerOf(v0, cx);
  for (let i = 0; i < n; i++) {
    const j = partners[i];
    if (j >= 0) {
      out[i * 3] = -delta[j * 3];
      out[i * 3 + 1] = delta[j * 3 + 1];
      out[i * 3 + 2] = delta[j * 3 + 2];
    }
  }
  return out;
}

function unchanged(prep, reason, extra) {
  return { positions: new Float64Array(prep.positions), kept: reason ? false : true, moved: 0, clamped: 0, reason, ...extra };
}

export function prepareStroke(positions, faces) {
  const pos = positions instanceof Float64Array ? new Float64Array(positions) : Float64Array.from(positions);
  const fa = faces instanceof Uint32Array ? faces : Uint32Array.from(faces);
  const n = pos.length / 3;
  return { positions: pos, faces: fa, n, nbr: neighbors(n, fa), normals: vertexNormals(pos, fa), cx: centreX(pos) };
}

export function applyPrepared(prep, params) {
  const brush = params.brush;
  const radius = Number(params.radius);
  const strength = brush === "grab" ? 1 : Number(params.strength);
  const points = params.points || [];
  const normal = params.normal || [0, 0, 1];
  const nlen = Math.hypot(normal[0], normal[1], normal[2]);
  if (!(nlen > 1e-9)) return unchanged(prep, "normal can't be zero.");
  const nStroke = [normal[0] / nlen, normal[1] / nlen, normal[2] / nlen];
  const grab = params.delta || [0, 0, 0];
  if (!points.length) return unchanged(prep, "", { kept: true });
  const dabs = points.map((p) => [p[0], p[1], p[2]]);
  const first = runBrush(prep.positions, prep.faces, prep.nbr, prep.normals, brush, dabs, nStroke, radius, strength, grab);
  let delta = first.delta;
  const cx = Number.isFinite(params.symX) ? params.symX : prep.cx;
  if (params.symmetry) {
    const mir = dabs.map((p) => [2 * cx - p[0], p[1], p[2]]);
    const nM = [-nStroke[0], nStroke[1], nStroke[2]];
    const gM = [-grab[0], grab[1], grab[2]];
    const second = runBrush(prep.positions, prep.faces, prep.nbr, prep.normals, brush, mir, nM, radius, strength, gM);
    const reflected = mirrorDelta(first.delta, prep.positions, cx);
    const partners = partnerOf(prep.positions, cx);
    for (let i = 0; i < prep.n; i++) {
      if (partners[i] >= 0) {
        second.delta[i * 3] = reflected[i * 3];
        second.delta[i * 3 + 1] = reflected[i * 3 + 1];
        second.delta[i * 3 + 2] = reflected[i * 3 + 2];
      }
    }
    for (let i = 0; i < delta.length; i++) delta[i] += second.delta[i];
    for (let i = 0; i < first.touched.length; i++) first.touched[i] = first.touched[i] || second.touched[i];
  }
  const v0 = prep.positions;
  const v = new Float64Array(v0.length);
  for (let i = 0; i < v.length; i++) v[i] = v0[i] + delta[i];
  const clamped = clampThinWall(v, v0, prep.normals, nStroke);
  if (outsideMoved(v, v0, dabs, radius, !!params.symmetry, cx)) {
    return unchanged(prep, "the stroke would change dimensions outside the brush — refused; the model was left unchanged.");
  }
  const folded = foldedCount(v, prep.faces, faceNormals(v0, prep.faces), first.touched);
  if (folded) {
    return unchanged(prep, `the sculpt stroke folded ${folded} face(s) — refused; the model was left unchanged. Lower the strength or the brush size and try again.`);
  }
  let moved = 0;
  for (let i = 0; i < prep.n; i++) {
    if (Math.hypot(v[i * 3] - v0[i * 3], v[i * 3 + 1] - v0[i * 3 + 1], v[i * 3 + 2] - v0[i * 3 + 2]) > 1e-8) moved++;
  }
  if (!moved) {
    if (strength <= 1e-9) return unchanged(prep, "Strength is 0, so the stroke changed nothing. The model was left unchanged.");
    if (clamped) return unchanged(prep, "The stroke was held so the wall stayed at least 0.4 mm, and nothing else moved. The model was left unchanged.");
    let inRadius = false, facing = false;
    for (let i = 0; i < prep.n; i++) {
      let close = false;
      for (const c of dabs) if (Math.hypot(v0[i * 3] - c[0], v0[i * 3 + 1] - c[1], v0[i * 3 + 2] - c[2]) <= radius) close = true;
      if (!close) continue;
      inRadius = true;
      const dot = prep.normals[i * 3] * nStroke[0] + prep.normals[i * 3 + 1] * nStroke[1] + prep.normals[i * 3 + 2] * nStroke[2];
      if (dot > 0.2) facing = true;
    }
    if (inRadius && !facing) {
      return unchanged(prep, "the brush only reached the back of the surface, so nothing was changed. Turn the model and sculpt the side you can see. The back of a thin wall stays put.");
    }
    if (inRadius) return unchanged(prep, brushTitle(brush) + " stroke was too light to move the surface. Nothing changed.", { kept: true });
    return unchanged(prep, brushTitle(brush) + " stroke was outside the model. Nothing changed.", { kept: true });
  }
  return { positions: v, kept: true, moved, clamped, reason: "" };
}
