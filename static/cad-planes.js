// Pure helpers for the CAD workspace (no THREE, so Node can test them):
// construction planes (offset / midplane) and the hints on/off preference.
const NAMED = { XY: [[0, 0, 0], [0, 0, 1], [1, 0, 0]], XZ: [[0, 0, 0], [0, -1, 0], [1, 0, 0]], YZ: [[0, 0, 0], [1, 0, 0], [0, 1, 0]] };
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = a => { const l = Math.hypot(...a); if (!(l > 1e-9)) throw new Error("Bad plane."); return a.map(c => c / l); };
const r5 = a => a.map(c => Math.round(c * 1e5) / 1e5 || 0);

/** {origin, normal, xdir} for "XY"/"XZ"/"YZ" or a plane dict. */
export function flat(pl) {
  if (typeof pl === "string") { const [o, n, x] = NAMED[pl] || []; if (!o) throw new Error("Unknown plane."); return { origin: o, normal: n, xdir: x }; }
  const n = norm(pl.normal);
  let x = pl.xdir && Math.abs(dot(norm(pl.xdir), n)) < 0.99 ? pl.xdir : (Math.abs(n[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0]);
  const k = dot(x, n); x = norm(x.map((c, i) => c - n[i] * k));
  return { origin: pl.origin.slice(0, 3), normal: n, xdir: x };
}
/** Base plane moved `d` mm along its normal. */
export function offsetPlane(base, d) {
  d = Number(d); if (!Number.isFinite(d) || Math.abs(d) > 1e5) throw new Error("Offset must be a number.");
  const b = flat(base);
  return { origin: r5(b.origin.map((c, i) => c + b.normal[i] * d)), normal: r5(b.normal), xdir: r5(b.xdir), construct: "offset" };
}
/** Plane halfway between two parallel planes (keeps the first one's normal). */
export function midPlane(a, b) {
  const A = flat(a), B = flat(b);
  if (Math.abs(dot(A.normal, B.normal)) < 0.999) throw new Error("Midplane needs two parallel planes or faces.");
  const gap = dot(B.origin.map((c, i) => c - A.origin[i]), A.normal);
  return { origin: r5(A.origin.map((c, i) => c + A.normal[i] * gap / 2)), normal: r5(A.normal), xdir: r5(A.xdir), construct: "midplane" };
}
export const parallel = (a, b) => { try { return Math.abs(dot(flat(a).normal, flat(b).normal)) >= 0.999; } catch { return false; } };

export const HINTS_KEY = "zeim.cad.hints";
export function hintsOn(store) { try { return store?.getItem(HINTS_KEY) !== "off"; } catch { return true; } }
export function setHintsOn(store, on) { try { store?.setItem(HINTS_KEY, on ? "on" : "off"); } catch { } return !!on; }
