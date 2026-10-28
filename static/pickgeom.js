/* Edge and face picking math for the CAD workspace.
   Clipping, the camera near plane, and occlusion are decided here so a test can run
   without WebGL. Points are [x, y, z]. Clip points are {x, y, z, w}. */

const EPS = 1e-8;

function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
function scale(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function len(a) { return Math.hypot(a[0], a[1], a[2]); }

/* Keep the part of a segment where the signed distance is >= 0.
   da/db are the distances of the endpoints. Returns null when the whole segment is cut away. */
export function clipHalfSpace(a, b, da, db) {
  if (da >= -EPS && db >= -EPS) return { a: a.slice(), b: b.slice() };
  if (da < -EPS && db < -EPS) return null;
  const t = da / (da - db);
  const p = [0, 1, 2].map(i => a[i] + (b[i] - a[i]) * t);
  if (da >= -EPS) return { a: a.slice(), b: p };
  return { a: p, b: b.slice() };
}

/* Clip a segment in clip space to w >= minW (in front of the camera).
   A point behind the camera has w <= 0; dividing by it flips the point onto the screen. */
export function clipByW(a, b, minW = 1e-4) {
  const aw = a.w, bw = b.w;
  if (aw >= minW && bw >= minW) return [a, b];
  if (aw < minW && bw < minW) return null;
  const t = (minW - aw) / (bw - aw);
  const p = {
    x: a.x + (b.x - a.x) * t,
    y: a.y + (b.y - a.y) * t,
    z: a.z + (b.z - a.z) * t,
    w: minW,
  };
  return aw >= minW ? [a, p] : [p, b];
}

export function screenOf(c, width, height) {
  const inv = 1 / c.w;
  return [(c.x * inv + 1) * 0.5 * width, (1 - c.y * inv) * 0.5 * height];
}

export function screenDist(ax, ay, bx, by, mx, my) {
  const dx = bx - ax, dy = by - ay;
  const L = dx * dx + dy * dy || 1;
  let t = ((mx - ax) * dx + (my - ay) * dy) / L;
  if (t < 0) t = 0;
  else if (t > 1) t = 1;
  const x = ax + dx * t, y = ay + dy * t;
  return { d: Math.hypot(x - mx, y - my), t };
}

/* An edge point farther from the camera than the surface under the pointer is hidden. */
export function inFrontOfHit(edgeCamDist, hitCamDist, rel = 0.01) {
  if (hitCamDist == null || !Number.isFinite(hitCamDist)) return true;
  const slack = Math.max(0.5, Math.abs(rel) * hitCamDist);
  return edgeCamDist <= hitCamDist + slack;
}

function near3(p, x, y, z, tol2) {
  const dx = p[0] - x, dy = p[1] - y, dz = p[2] - z;
  return dx * dx + dy * dy + dz * dz <= tol2;
}

/* flat is xyzxyz pairs. Either endpoint order matches. */
export function edgeMatches(a, b, flat, tol) {
  const tol2 = tol * tol;
  for (let i = 0; i + 5 < flat.length; i += 6) {
    const Aok = near3(a, flat[i], flat[i + 1], flat[i + 2], tol2);
    const Bok = near3(b, flat[i + 3], flat[i + 4], flat[i + 5], tol2);
    const Aflip = near3(b, flat[i], flat[i + 1], flat[i + 2], tol2);
    const Bflip = near3(a, flat[i + 3], flat[i + 4], flat[i + 5], tol2);
    if ((Aok && Bok) || (Aflip && Bflip)) return true;
  }
  return false;
}

/* Distance from p to triangle abc. */
export function distPointTri(p, a, b, c) {
  const ab = sub(b, a), ac = sub(c, a), ap = sub(p, a);
  const d1 = dot(ab, ap), d2 = dot(ac, ap);
  if (d1 <= 0 && d2 <= 0) return len(sub(p, a));
  const bp = sub(p, b);
  const d3 = dot(ab, bp), d4 = dot(ac, bp);
  if (d3 >= 0 && d4 <= d3) return len(sub(p, b));
  const vc = d1 * d4 - d3 * d2;
  if (vc <= 0 && d1 >= 0 && d3 <= 0) {
    const v = d1 / (d1 - d3);
    return len(sub(p, add(a, scale(ab, v))));
  }
  const cp = sub(p, c);
  const d5 = dot(ab, cp), d6 = dot(ac, cp);
  if (d6 >= 0 && d5 <= d6) return len(sub(p, c));
  const vb = d5 * d2 - d1 * d6;
  if (vb <= 0 && d2 >= 0 && d6 <= 0) {
    const w = d2 / (d2 - d6);
    return len(sub(p, add(a, scale(ac, w))));
  }
  const va = d3 * d6 - d5 * d4;
  if (va <= 0 && (d4 - d3) >= 0 && (d5 - d6) >= 0) {
    const w = (d4 - d3) / ((d4 - d3) + (d5 - d6));
    return len(sub(p, add(b, scale(sub(c, b), w))));
  }
  const denom = va + vb + vc || 1;
  const v = vb / denom, w = vc / denom;
  return len(sub(p, add(a, add(scale(ab, v), scale(ac, w)))));
}

/* flat is xyzxyzxyz triangles (the non-indexed mesh). */
export function distPointTris(p, flat) {
  let best = Infinity;
  for (let i = 0; i + 8 < flat.length; i += 9) {
    const d = distPointTri(
      p,
      [flat[i], flat[i + 1], flat[i + 2]],
      [flat[i + 3], flat[i + 4], flat[i + 5]],
      [flat[i + 6], flat[i + 7], flat[i + 8]],
    );
    if (d < best) best = d;
  }
  return best;
}

/* Join collinear pieces of one straight edge. A corner (not parallel) stops the run.
   flat is xyzxyz pairs, the same buffer the workspace draws. */
export function chainStraight(a, b, flat, tol = 0.05) {
  const segs = [];
  for (let i = 0; i + 5 < (flat ? flat.length : 0); i += 6) {
    segs.push([[flat[i], flat[i + 1], flat[i + 2]], [flat[i + 3], flat[i + 4], flat[i + 5]]]);
  }
  const near = (p, q) => {
    const d = p[0] - q[0], e = p[1] - q[1], f = p[2] - q[2];
    return d * d + e * e + f * f <= tol * tol;
  };
  const dirOf = (p, q) => {
    const d = [q[0] - p[0], q[1] - p[1], q[2] - p[2]];
    const L = Math.hypot(d[0], d[1], d[2]) || 1;
    return [d[0] / L, d[1] / L, d[2] / L];
  };
  const parallel = (u, v) => Math.abs(u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) > 0.999;
  let start = [a[0], a[1], a[2]], end = [b[0], b[1], b[2]];
  const axis = dirOf(start, end);
  const along = (p, q) => (q[0] - p[0]) * axis[0] + (q[1] - p[1]) * axis[1] + (q[2] - p[2]) * axis[2];
  const used = new Set();
  let grew = true;
  while (grew) {
    grew = false;
    for (let i = 0; i < segs.length; i++) {
      if (used.has(i)) continue;
      const [p, q] = segs[i];
      if (!parallel(dirOf(p, q), axis)) continue;
      const pEnd = near(p, end), qEnd = near(q, end), pStart = near(p, start), qStart = near(q, start);
      if ((pEnd || qEnd) && !(pStart && qStart)) {
        const nxt = pEnd ? q : p;
        if (along(end, nxt) <= tol) { used.add(i); continue; }
        end = [nxt[0], nxt[1], nxt[2]];
        used.add(i);
        grew = true;
      } else if (pStart || qStart) {
        const nxt = pStart ? q : p;
        if (along(start, nxt) >= -tol) { used.add(i); continue; }
        start = [nxt[0], nxt[1], nxt[2]];
        used.add(i);
        grew = true;
      }
    }
  }
  return { a: start, b: end };
}

/* samples: {p, px, py, behind}. The nearest sample within maxPx, or null. */
export function closestSample(px, py, samples, maxPx) {
  let best = null, bd = maxPx;
  for (const s of samples || []) {
    if (!s || s.behind) continue;
    const d = Math.hypot(s.px - px, s.py - py);
    if (d < bd) { bd = d; best = s.p; }
  }
  return best;
}

/* Drop edges, a face, or a body that the current meshes no longer contain.
   bodies: [{ index, visible, edges: number[], tris: number[] }]. */
export function reconcileSelection(sel, bodies, tol) {
  const list = bodies || [];
  const byId = (id) => list.find(b => b.index === id);
  const kept = [];
  let droppedEdge = false;
  for (const e of sel.edges || []) {
    const b = byId(e.body);
    if (!b || b.visible === false || !edgeMatches(e.a, e.b, b.edges || [], tol)) droppedEdge = true;
    else kept.push(e);
  }
  let face = sel.face || null;
  let droppedFace = false;
  if (face) {
    const b = byId(sel.body);
    const near = !!(b && b.visible !== false && distPointTris(face, b.tris || []) <= tol);
    if (!near) { face = null; droppedFace = true; }
  }
  let body = sel.body;
  let droppedBody = false;
  if (typeof body === "number" && body >= 0) {
    const b = byId(body);
    if (!b || b.visible === false) { body = -1; droppedBody = true; }
  }
  if (droppedBody) {
    if (kept.length) droppedEdge = true;
    if (face) droppedFace = true;
    return { edges: [], face: null, body: -1, droppedEdge, droppedFace, droppedBody };
  }
  return { edges: kept, face, body, droppedEdge, droppedFace, droppedBody };
}
