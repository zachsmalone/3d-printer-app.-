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

export function wallThickness(pos, shape = "rect", box = null) {   // pos: flat Float32Array x,y,z,...; box {lo,hi}: whole-model bounds
  const n = pos.length / 3, lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity], t = new Float32Array(n);
  for (let i = 0; i < n; i++) for (let a = 0; a < 3; a++) { const x = pos[3 * i + a]; if (x < lo[a]) lo[a] = x; if (x > hi[a]) hi[a] = x; }
  if (shape === "memorybox") {                                   // square box, flat backs outward: depth in from the nearest side
    const L = box ? box.lo : lo, H = box ? box.hi : hi;
    for (let i = 0; i < n; i++) { const x = pos[3 * i], y = pos[3 * i + 1]; t[i] = Math.max(0, Math.min(x - L[0], H[0] - x, y - L[1], H[1] - y)); }
  } else if (shape === "nightlight" || shape === "cup") {
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
export function backlitColors(pos, shape, light = "warm", k = K_PER_MM, gamma = 0.6, box = null) {
  const t = wallThickness(pos, shape, box), L = lightRGB(light), out = new Float32Array(t.length * 3);
  let tmin = Infinity; for (const x of t) tmin = Math.min(tmin, x);
  const top = brightness(tmin, k) || 1;
  for (let i = 0; i < t.length; i++) { const s = Math.min(1, brightness(t[i], k) / top) ** gamma; out[3 * i] = L[0] * s; out[3 * i + 1] = L[1] * s; out[3 * i + 2] = L[2] * s; }
  return out;
}

/* LED-strip style effects. effectRGB(effect, base, tSec, speed) -> [r,g,b] 0..1 tint for this frame.
   speed 1 (slow) .. 10 (fast). Strobe is hard-capped at STROBE_MAX_HZ flashes/second (WCAG 2.3.1: no more than 3). */
export const EFFECTS = ["steady", "fade", "rainbow", "breathe", "strobe"];
export const STROBE_MAX_HZ = 3;
const sp = s => Math.min(10, Math.max(1, Number(s) || 5));
export function hsv(h, s = 1, v = 1) {                         // h in turns (0..1)
  h = ((h % 1) + 1) % 1; const f = k => { const x = (k + h * 6) % 6; return v - v * s * Math.max(0, Math.min(x, 4 - x, 1)); };
  return [f(5), f(3), f(1)];
}
export const strobeHz = speed => Math.min(STROBE_MAX_HZ, 0.5 + (sp(speed) - 1) * (2.5 / 9));
const FADE = [[1, 0, 0], [1, 0.5, 0], [0, 1, 0], [0, 0.6, 1], [0.6, 0, 1]];
export function effectRGB(effect, base, t, speed = 5) {
  const k = sp(speed);
  if (effect === "rainbow") return hsv(t / (22 - 2 * k));                         // one hue lap: 20 s (slow) .. 2 s (fast)
  if (effect === "fade") {                                                          // smooth cross-fade through a palette
    const p = t / (16 - 1.4 * k), i = Math.floor(p), w = 0.5 - 0.5 * Math.cos(Math.PI * (p - i));
    const a = FADE[((i % 5) + 5) % 5], b = FADE[(((i + 1) % 5) + 5) % 5];
    return a.map((x, j) => x + (b[j] - x) * w);
  }
  if (effect === "breathe") {                                                       // 6 s .. 1.5 s per breath, never fully dark
    const w = 0.5 - 0.5 * Math.cos(2 * Math.PI * t / (6.5 - 0.5 * k)), v = 0.15 + 0.85 * w;
    return base.map(x => x * v);
  }
  if (effect === "strobe") return ((t * strobeHz(k)) % 1) < 0.5 ? base.slice() : [0, 0, 0];
  return base.slice();
}
/* start-up effect: the remembered one, but Steady under prefers-reduced-motion unless the user opted in while it was set */
export function defaultEffect(saved, reduce, optedIn = false) {
  const e = EFFECTS.includes(saved) ? saved : "steady";
  return reduce && !optedIn ? "steady" : e;
}

/* filament / resin colour: transmitted light = light colour x material colour (per channel) */
export const MATERIALS = { white: [1, 1, 1], natural: [1.0, 0.94, 0.82], ivory: [1.0, 0.97, 0.88], grey: [0.62, 0.62, 0.62], red: [1.0, 0.35, 0.3], blue: [0.4, 0.6, 1.0] };
export const materialRGB = m => (MATERIALS[m] || (/^#?[0-9a-f]{6}$/i.test(String(m || "")) ? lightRGB(m) : MATERIALS.white));
export const transmit = (light, mat) => light.map((x, i) => x * mat[i]);
