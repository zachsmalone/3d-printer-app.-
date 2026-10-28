/* On-model Move / Rotate / Scale math.
   Payloads use the fields ZEIM already stores: plate "transform", mesh translate / rotate / scale,
   and CAD body_transform. Nothing here applies a mesh. */

const AX = { x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] };

export function handlesFor(surface, mode) {
  if (surface === "plate") {
    if (mode === "move") return ["x", "y"];
    if (mode === "rotate") return ["z"];
    if (mode === "scale") return ["x", "y", "z", "u"];
  } else if (surface === "mesh" || surface === "cad") {
    if (mode === "move" || mode === "rotate") return ["x", "y", "z"];
    if (mode === "scale") return ["x", "y", "z", "u"];
  }
  return [];
}

export function handleName(mode, axis) {
  const name = axis === "u" ? "all sides" : String(axis || "").toUpperCase();
  if (mode === "move") return "Move along " + name;
  if (mode === "rotate") return "Turn about " + name;
  if (mode === "scale" && axis === "u") return "Resize all sides together";
  if (mode === "scale") return "Resize along " + name;
  return name;
}

export function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
export function cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
export function norm(a) {
  const l = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
}
export function ortho(axis) {
  const a = norm(axis);
  const helper = Math.abs(a[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0];
  return norm(cross(a, helper));
}

export function reachOf(size) {
  const m = Math.max(size[0] || 0, size[1] || 0, size[2] || 0, 1);
  return Math.max(16, m * 0.55);
}

export function layoutHandles(frame) {
  const center = frame.center, size = frame.size, reach0 = reachOf(size);
  return handlesFor(frame.surface, frame.mode).map(axis => {
    if (axis === "u") return { axis, at: center.slice(), dir: [0, 0, 1], reach: reach0 };
    const dir = AX[axis];
    if (frame.mode === "rotate") {
      const u = ortho(dir);
      return { axis, dir, reach: reach0, at: center.map((c, i) => c + u[i] * reach0) };
    }
    const half = (size["xyz".indexOf(axis)] || 0) / 2;
    const dist = Math.max(reach0, half + 14);
    return { axis, dir, reach: dist, at: center.map((c, i) => c + dir[i] * dist) };
  });
}

export function ringSamples(center, axis, radius, n = 40) {
  const u = ortho(axis), v = norm(cross(norm(axis), u)), pts = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2, c = Math.cos(a), s = Math.sin(a);
    pts.push(center.map((p, k) => p + radius * (c * u[k] + s * v[k])));
  }
  return pts;
}

/* Screen pixels (x right, y down) along a world axis, in millimetres. */
export function axisTravel(axis, right, up, dx, dy, pxPerMm) {
  const sx = dot(axis, right), sy = -dot(axis, up), len2 = sx * sx + sy * sy;
  if (len2 < 0.04 || !(pxPerMm > 0)) return 0;
  return (dx * sx + dy * sy) / (pxPerMm * len2);
}

export function scaleFromTravel(reach, travel) {
  const base = Math.max(Math.abs(reach) || 1, 1);
  return (base + travel) / base;
}

export function pointerAngle(cx, cy, x, y) { return Math.atan2(y - cy, x - cx) * 180 / Math.PI; }
export function signedAngleDelta(a0, a1) {
  let d = a1 - a0;
  while (d > 180) d -= 360;
  while (d < -180) d += 360;
  return d;
}
export function worldFromScreenAngle(screenDelta, screenPerWorldDeg) {
  if (!Number.isFinite(screenPerWorldDeg) || Math.abs(screenPerWorldDeg) < 0.05) return 0;
  return screenDelta / screenPerWorldDeg;
}

export function rotateAround(point, center, axis, deg) {
  const a = norm(axis), rad = deg * Math.PI / 180, c = Math.cos(rad), s = Math.sin(rad);
  const v = point.map((p, i) => p - center[i]);
  const d = dot(v, a), cr = cross(a, v);
  return v.map((x, i) => center[i] + x * c + cr[i] * s + a[i] * d * (1 - c));
}

export function snapMove(mm, free) {
  if (!Number.isFinite(mm)) return 0;
  return free ? Math.round(mm * 10) / 10 : Math.round(mm);
}
export function snapTurn(deg, free) {
  if (!Number.isFinite(deg)) return 0;
  return free ? Math.round(deg) : Math.round(deg / 5) * 5;
}
export function snapFactor(f, free) {
  if (!Number.isFinite(f)) return 1;
  const pct = free ? Math.round(f * 1000) / 10 : Math.round(f * 100);
  return Math.min(100, Math.max(0.01, pct / 100));
}
export function worthCommit(mode, amount, free) {
  if (mode === "move") return Math.abs(amount) >= (free ? 0.05 : 0.5);
  if (mode === "rotate") return Math.abs(amount) >= (free ? 0.5 : 0.5);
  if (mode === "scale") return Math.abs(amount - 1) >= 0.01;
  return false;
}

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const r1 = v => Math.round(v * 10) / 10;
const r4 = v => Math.round(v * 1e4) / 1e4;

export function plateCommit(mode, axis, raw, box, free) {
  if (!handlesFor("plate", mode).includes(axis) || !box) return null;
  if (mode === "move") {
    const mm = snapMove(raw, free);
    if (!worthCommit("move", mm, free)) return null;
    const params = { action: "transform" };
    params[axis === "x" ? "dx" : "dy"] = clamp(r4(mm), -1e5, 1e5);
    return { op: "plate", params };
  }
  if (mode === "rotate") {
    const deg = snapTurn(raw, free);
    if (!worthCommit("rotate", deg, free)) return null;
    return { op: "plate", params: { action: "transform", rz: clamp(r1(deg), -3600, 3600) } };
  }
  const factor = snapFactor(scaleAmount(raw), free);
  if (!worthCommit("scale", factor, free)) return null;
  if (axis === "u") return { op: "plate", params: { action: "transform", scale_pct: clamp(Math.round(factor * 100), 1, 10000) } };
  const i = "xyz".indexOf(axis), ext = box.max[i] - box.min[i];
  if (!(ext > 1e-6)) return null;
  const size = clamp(r1(ext * factor), 0.1, 5000);
  return { op: "plate", params: { action: "transform", size_mm: { [axis]: size } } };
}

export function meshCommit(mode, axis, raw, free) {
  if (!handlesFor("mesh", mode).includes(axis)) return null;
  if (mode === "move") {
    const mm = snapMove(raw, free);
    if (!worthCommit("move", mm, free)) return null;
    const params = { dx: 0, dy: 0, dz: 0 };
    params["d" + axis] = clamp(r4(mm), -1e5, 1e5);
    return { op: "translate", params };
  }
  if (mode === "rotate") {
    const deg = snapTurn(raw, free);
    if (!worthCommit("rotate", deg, free)) return null;
    const params = { rx: 0, ry: 0, rz: 0 };
    params["r" + axis] = clamp(r1(deg), -3600, 3600);
    return { op: "rotate", params };
  }
  const factor = snapFactor(scaleAmount(raw), free);
  if (!worthCommit("scale", factor, free)) return null;
  if (axis === "u") return { op: "scale", params: { factor: clamp(factor, 0.001, 1000), pivot: "base" } };
  const params = { sx: 1, sy: 1, sz: 1, pivot: "base" };
  params["s" + axis] = clamp(factor, 0.001, 1000);
  return { op: "scale", params };
}

export function cadCommit(mode, axis, raw, body, free) {
  if (!handlesFor("cad", mode).includes(axis)) return null;
  const id = Number(body);
  if (!Number.isFinite(id)) return null;
  if (mode === "move") {
    const mm = snapMove(raw, free);
    if (!worthCommit("move", mm, free)) return null;
    const move = [0, 0, 0];
    move["xyz".indexOf(axis)] = clamp(r4(mm), -1e5, 1e5);
    return { op: "body_transform", params: { body: id, move } };
  }
  if (mode === "rotate") {
    const deg = snapTurn(raw, free);
    if (!worthCommit("rotate", deg, free)) return null;
    const rotate = [0, 0, 0];
    rotate["xyz".indexOf(axis)] = clamp(r1(deg), -3600, 3600);
    return { op: "body_transform", params: { body: id, rotate } };
  }
  const factor = snapFactor(scaleAmount(raw), free);
  if (!worthCommit("scale", factor, free)) return null;
  const scale = axis === "u" ? [factor, factor, factor] : [1, 1, 1];
  if (axis !== "u") scale["xyz".indexOf(axis)] = clamp(factor, 0.001, 1000);
  return { op: "body_transform", params: { body: id, scale } };
}

function scaleAmount(raw) { return Number.isFinite(raw) ? raw : 1; }

export function commitFor(frame, axis, raw, free) {
  if (!frame) return null;
  if (frame.surface === "plate") return plateCommit(frame.mode, axis, raw, frame.box, free);
  if (frame.surface === "mesh") return meshCommit(frame.mode, axis, raw, free);
  if (frame.surface === "cad") return cadCommit(frame.mode, axis, raw, frame.body, free);
  return null;
}

/* Dragged amount before snap, from a pointer delta. Scale comes back as a factor. */
export function dragAmount(frame, handle, dx, dy, basis, free, screenAngleDelta, screenPerDeg) {
  if (!frame || !handle) return frame && frame.mode === "scale" ? 1 : 0;
  if (frame.mode === "rotate") {
    const deg = worldFromScreenAngle(screenAngleDelta, screenPerDeg);
    return snapTurn(deg, free);
  }
  const travel = axisTravel(handle.dir, basis.right, basis.up, dx, dy, basis.pxPerMm);
  if (frame.mode === "scale") return snapFactor(scaleFromTravel(handle.reach, travel), free);
  return snapMove(travel, free);
}

export function keyAmount(mode, key, shift, alt) {
  const dir = key === "ArrowRight" || key === "ArrowUp" ? 1 : key === "ArrowLeft" || key === "ArrowDown" ? -1 : 0;
  if (!dir) return null;
  if (mode === "move") return dir * (alt ? 0.1 : shift ? 10 : 1);
  if (mode === "rotate") return dir * (alt ? 1 : shift ? 15 : 5);
  const pct = alt ? 1 : shift ? 10 : 5;
  return dir > 0 ? 1 + pct / 100 : 1 / (1 + pct / 100);
}

export function readout(surface, mode, axis, amount, box) {
  const name = axis === "u" ? "All" : String(axis || "").toUpperCase();
  const n = v => (Math.round(v * 10) / 10).toString();
  if (mode === "move") return name + "  " + n(amount) + " mm";
  if (mode === "rotate") return name + "  " + n(amount) + "°";
  if (mode === "scale" && surface === "plate" && axis !== "u" && box) {
    const ext = box.max["xyz".indexOf(axis)] - box.min["xyz".indexOf(axis)];
    return name + "  " + n(ext * amount) + " mm";
  }
  if (mode === "scale") return name + "  " + Math.round(amount * 100) + "%";
  return "";
}

/* Object placement so world-space vertices rotate / scale about `pivot`.
   Three.js applies scale, then rotation, then translation. One axis at a time. */
export function previewPlacement(pivot, mode, axis, amount) {
  if (mode === "move") {
    const d = [0, 0, 0];
    if (axis === "x" || axis === "y" || axis === "z") d["xyz".indexOf(axis)] = amount || 0;
    return { position: d, rotation: [0, 0, 0], scale: [1, 1, 1] };
  }
  const s = [1, 1, 1], rot = [0, 0, 0];
  if (mode === "scale") {
    const f = amount || 1;
    if (axis === "u") s[0] = s[1] = s[2] = f;
    else if (axis === "x" || axis === "y" || axis === "z") s["xyz".indexOf(axis)] = f;
  } else if (mode === "rotate" && (axis === "x" || axis === "y" || axis === "z")) rot["xyz".indexOf(axis)] = amount || 0;
  const scaled = pivot.map((c, i) => c * s[i]);
  const spun = rotateAround(scaled, [0, 0, 0], [rot[0] ? 1 : 0, rot[1] ? 1 : 0, rot[2] ? 1 : 0], rot[0] || rot[1] || rot[2] || 0);
  return { position: pivot.map((c, i) => c - spun[i]), rotation: rot, scale: s };
}

export function overlapsChrome(x, y, rects, pad = 8) {
  return (rects || []).some(r => r && r.width > 0 && r.height > 0 && x >= r.left - pad && x <= r.right + pad && y >= r.top - pad && y <= r.bottom + pad);
}
