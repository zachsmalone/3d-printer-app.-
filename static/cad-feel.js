/* Pointer and gate decisions for the CAD workspace.
   Hover, press, and the committed pick stay separate. Gates return a short reason
   or an empty string. The 180 ms ease matches the on-model beads. */

export const FEEL_MS = 180;

export const PAINT = {
  idle: 0xf2f5ff,
  cons: 0x8a93a8,
  hover: 0x7eb6ff,
  press: 0x003d99,
  selected: 0x0066ff,
};

const PAIRS = new Set(["parallel", "perpendicular", "equal", "tangent", "concentric", "coincident"]);

/* Direct select and Measure use the same edge test as a tap (onEdge).
   Fillet uses the edge pickEdge already accepted, and does not fall through onto a face.
   A face tool highlights the face the click will store. */
export function pickChoice(state) {
  const tool = state.tool || null;
  const edge = !!state.edge;
  const hit = !!state.hit;
  const onEdge = !!state.onEdge;
  if (tool === "sculpt" || tool === "merge") return { kind: "none" };
  if (tool === "extrude" || tool === "revolve") return { kind: "region" };
  if (!tool && state.measure) {
    if (edge && onEdge) return { kind: "edge" };
    if (hit) return { kind: "face" };
    return { kind: "none" };
  }
  if (!tool) {
    if (edge && onEdge) return { kind: "edge" };
    if (hit) return { kind: "face" };
    return { kind: "none" };
  }
  if (tool === "fillet") return edge ? { kind: "edge" } : { kind: "none" };
  if (hit) return { kind: "face" };
  return { kind: "none" };
}

export function edgeKey(a, b) {
  const r = (v) => [0, 1, 2].map(i => Math.round(Number(v[i]) * 1000) / 1000).join(",");
  const ka = r(a), kb = r(b);
  return ka < kb ? ka + "|" + kb : kb + "|" + ka;
}

export function curvePaint(id, state) {
  if (state.press != null && state.press === id) return "press";
  if (state.selected) return "selected";
  if (state.hover != null && state.hover === id) return "hover";
  return state.construction ? "cons" : "idle";
}

export function bodyGlow(index, state) {
  if (!(index >= 0)) return null;
  if (state.press === index) return { color: PAINT.press, intensity: 0.55 };
  if (state.selected === index) return { color: PAINT.selected, intensity: 0.42 };
  if (state.hover === index) return { color: PAINT.hover, intensity: 0.22 };
  return null;
}

export function constraintBlock(type, entities) {
  const list = entities || [];
  const n = list.length;
  if (!n) return "Select curves first.";
  if (PAIRS.has(type) && n !== 2) return "Select exactly two curves.";
  if (type === "horizontal" && !list.some(e => e && e.type === "line")) return "Select a line first.";
  return "";
}

export function constraintSummary(entities) {
  const list = entities || [];
  const n = list.length;
  if (!n) return "Select curves first.";
  const line = list.some(e => e && e.type === "line");
  if (n === 1) return line ? "One curve. Horizontal and Lock can run. Pairs need two." : "Lock can use this curve. Horizontal needs a line. Pairs need two.";
  if (n > 2) return "Pairs need exactly two. Horizontal and Lock can use this selection.";
  if (!line) return "Horizontal needs a line. The pair constraints can run.";
  return "";
}

export function filletBlock({ bodies, radius }) {
  if (!bodies) return "Make a solid first.";
  if (typeof radius !== "number" || !Number.isFinite(radius) || radius <= 0) return "Type a size greater than 0.";
  return "";
}

export function faceOffsetBlock({ hasFace, distance }) {
  if (!hasFace) return "Tap a flat face first.";
  if (typeof distance !== "number" || !Number.isFinite(distance) || distance === 0) return "Type a distance other than 0.";
  return "";
}

export function extrudeBlock(state) {
  if (!state.pending) return "";
  if (state.failed) return "The sketch could not be read.";
  if (!state.regionsKnown) return "Checking the sketch.";
  if (!state.regionCount) return "This sketch has no closed shape.";
  if (typeof state.distance !== "number" || !Number.isFinite(state.distance) || state.distance === 0) return "Type a distance other than 0.";
  return "";
}

export function revolveBlock(state) {
  if (!state.pending) return "";
  if (state.failed) return "The sketch could not be read.";
  if (!state.regionsKnown) return "Checking the sketch.";
  if (!state.regionCount) return "This sketch has no closed shape.";
  if (typeof state.angle !== "number" || !Number.isFinite(state.angle) || state.angle === 0) return "Type an angle other than 0.";
  return "";
}

export function measureBlock({ bodies }) {
  if (!bodies) return "Make a solid first.";
  return "";
}

/* Knuckles, links, and clearance are the values the solid step already accepts. */
export function jointBlock(state) {
  const kind = state.kind || "hinge";
  const clearance = state.clearance;
  if (typeof clearance !== "number" || !Number.isFinite(clearance) || clearance < 0.15 || clearance > 1) {
    return "Clearance must be between 0.15 and 1 mm.";
  }
  if (kind === "hinge" || kind === "snap_hinge") {
    const n = state.knuckles;
    if (typeof n !== "number" || !Number.isFinite(n) || n < 3 || n > 9 || Math.round(n) !== n || n % 2 === 0) {
      return "Knuckles must be 3, 5, 7, or 9.";
    }
  }
  if (kind === "chain") {
    const n = state.links;
    if (typeof n !== "number" || !Number.isFinite(n) || n < 2 || n > 30 || Math.round(n) !== n) {
      return "A chain needs 2 to 30 links.";
    }
  }
  return "";
}

export function boxesOverlap(a, b, pad = 0) {
  if (!a || !b) return false;
  for (let k = 0; k < 3; k++) {
    if (a.max[k] + pad < b.min[k] || b.max[k] + pad < a.min[k]) return false;
  }
  return true;
}

export function mergeFeel({ count, snap, overlaps }) {
  if (!count || count < 2) return "Pick at least two bodies. The first one stays put.";
  if (snap && snap !== "none") return "The others move to that side of the first and overlap 0.2 mm so they can fuse. A clearance gap is not closed.";
  if (!overlaps) return "These do not overlap. Fuse keeps them separate and leaves a tip. Snap a side, or move them so they touch.";
  return "Their boxes overlap. Fuse joins them only where the solids touch. A clearance gap stays open.";
}

/* Angle between face normals, and the distance between parallel planes. Same plane has no gap. */
export function facePair(n1, p1, n2, p2) {
  if (!n1 || !p1 || !n2 || !p2) return null;
  const dot = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2];
  const clamped = Math.max(-1, Math.min(1, dot));
  const angle = Math.acos(clamped) * 180 / Math.PI;
  const parallel = Math.abs(dot) >= Math.cos(3 * Math.PI / 180);
  const gap = Math.abs((p2[0] - p1[0]) * n1[0] + (p2[1] - p1[1]) * n1[1] + (p2[2] - p1[2]) * n1[2]);
  return { angle, parallel, gap: parallel && gap >= 0.05 ? gap : null };
}

export function measureLine(dist, delta, pair) {
  const fmt = (v) => (Math.round(Number(v) * 100) / 100).toString();
  const d = delta || [0, 0, 0];
  let text = `${fmt(dist)} mm  (ΔX ${fmt(Math.abs(d[0]))} · ΔY ${fmt(Math.abs(d[1]))} · ΔZ ${fmt(Math.abs(d[2]))})`;
  if (pair && Number.isFinite(pair.angle)) text += ` · faces ${fmt(pair.angle)}°`;
  if (pair && pair.gap != null) text += ` · ${fmt(pair.gap)} mm between faces`;
  return text;
}

export function barRect(anchor, bar) {
  const gap = bar.gap ?? 18;
  const w = bar.w, h = bar.h;
  return {
    left: anchor.x - w / 2,
    top: anchor.y - h - gap,
    right: anchor.x + w / 2,
    bottom: anchor.y - gap,
    width: w,
    height: h,
  };
}

function overlaps(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

/* Keep a context bar inside the stage and off docks. The anchor is the bar's bottom centre, matching the CSS shift. */
export function anchorClear(anchor, bar, bounds, obstacles) {
  if (!anchor || anchor.behind) return { x: 0, y: 0, hidden: true };
  const pads = (obstacles || []).filter(o => o && o.right > o.left && o.bottom > o.top);
  const outside = (r) => r.left < -0.5 || r.top < -0.5 || r.right > bounds.w + 0.5 || r.bottom > bounds.h + 0.5;
  const blocked = (r) => outside(r) || pads.some(o => overlaps(r, o));
  let x = anchor.x, y = anchor.y;
  const fit = () => {
    let r = barRect({ x, y }, bar);
    if (r.left < 0) x -= r.left;
    if (r.right > bounds.w) x -= r.right - bounds.w;
    if (r.top < 0) y -= r.top;
    if (r.bottom > bounds.h) y -= r.bottom - bounds.h;
    return barRect({ x, y }, bar);
  };
  let rect = fit();
  for (let pass = 0; pass < pads.length + 2; pass++) {
    const hit = pads.find(o => overlaps(rect, o));
    if (!hit && !outside(rect)) return { x, y, hidden: false };
    if (!hit) { rect = fit(); if (!outside(rect) && !pads.some(o => overlaps(rect, o))) return { x, y, hidden: false }; break; }
    const moves = [
      { x: x - (rect.right - hit.left) - 4, y },
      { x: x + (hit.right - rect.left) + 4, y },
      { x, y: y - (rect.bottom - hit.top) - 4 },
      { x, y: y + (hit.bottom - rect.top) + 4 },
    ];
    let best = null;
    for (const m of moves) {
      const trial = barRect(m, bar);
      if (blocked(trial)) continue;
      const cost = Math.hypot(m.x - anchor.x, m.y - anchor.y);
      if (!best || cost < best.cost) best = { x: m.x, y: m.y, cost };
    }
    if (!best) break;
    x = best.x; y = best.y; rect = barRect({ x, y }, bar);
  }
  rect = fit();
  return { x, y, hidden: false };
}
