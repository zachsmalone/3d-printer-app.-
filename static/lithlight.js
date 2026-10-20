/* Backlit lithophane "Light on" preview — browser twin of app/core/litho_light.py (keep in step).
   Preview estimate: I = exp(-k * t), t = wall thickness in mm (thin = bright, thick = dark). No three.js here, so node can test it. */
export const K_PER_MM = 0.9;
export const LIGHTS = { warm: [1.0, 0.72, 0.42], cool: [0.74, 0.85, 1.0], white: [1.0, 1.0, 1.0], sunlight: [0.97, 0.98, 1.0] };  // sunlight ~6000 K daylight
/* a named light, or a custom "#rrggbb" bulb colour -> [r,g,b] 0..1 (unknown -> white) */
export function lightRGB(light) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(light || ""));
  if (m) { const n = parseInt(m[1], 16); return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]; }
  return LIGHTS[light] || LIGHTS.white;
}
export const brightness = (t, k = K_PER_MM) => Math.exp(-k * Math.max(0, t));

export function wallThickness(pos, shape = "rect") {          // pos: flat Float32Array x,y,z,...
  const n = pos.length / 3, lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity], t = new Float32Array(n);
  for (let i = 0; i < n; i++) for (let a = 0; a < 3; a++) { const x = pos[3 * i + a]; if (x < lo[a]) lo[a] = x; if (x > hi[a]) hi[a] = x; }
  if (shape === "nightlight" || shape === "cup") {
    const cx = (lo[0] + hi[0]) / 2, cy = (lo[1] + hi[1]) / 2, h = hi[2] - lo[2]; let rin = Infinity, rall = Infinity;
    const r = i => Math.hypot(pos[3 * i] - cx, pos[3 * i + 1] - cy);
    for (let i = 0; i < n; i++) { const z = pos[3 * i + 2], ri = r(i); rall = Math.min(rall, ri); if (z > lo[2] + 0.2 * h && z < lo[2] + 0.8 * h) rin = Math.min(rin, ri); }
    if (!isFinite(rin)) rin = rall;
    for (let i = 0; i < n; i++) t[i] = Math.max(0, r(i) - rin);
  } else if (shape === "globe") {
    const R = (hi[0] - lo[0]) / 2, c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, hi[2] - R]; let rin = Infinity, rall = Infinity;
    const d = i => Math.hypot(pos[3 * i] - c[0], pos[3 * i + 1] - c[1], pos[3 * i + 2] - c[2]);
    for (let i = 0; i < n; i++) { const di = d(i); rall = Math.min(rall, di); if (pos[3 * i + 2] > c[2]) rin = Math.min(rin, di); }
    if (!isFinite(rin)) rin = rall;
    for (let i = 0; i < n; i++) t[i] = Math.max(0, d(i) - rin);
  } else for (let i = 0; i < n; i++) t[i] = pos[3 * i + 2] - lo[2];
  return t;
}

/* per-vertex RGB (Float32Array) for a light colour; shade is relative to the thinnest wall, gamma-lifted */
export function backlitColors(pos, shape, light = "warm", k = K_PER_MM, gamma = 0.6) {
  const t = wallThickness(pos, shape), L = lightRGB(light), out = new Float32Array(t.length * 3);
  let tmin = Infinity; for (const x of t) tmin = Math.min(tmin, x);
  const top = brightness(tmin, k) || 1;
  for (let i = 0; i < t.length; i++) { const s = Math.min(1, brightness(t[i], k) / top) ** gamma; out[3 * i] = L[0] * s; out[3 * i + 1] = L[1] * s; out[3 * i + 2] = L[2] * s; }
  return out;
}
