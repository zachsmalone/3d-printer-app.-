/* Select mode: trace round the part of the photo you want (finger or mouse). The outline snaps to the
   subject's edges; only that part becomes the relief / pop-art / bust model, and for a lithophane the rest turns
   plain (glows white) or flat (solid, no picture). Tools: Trace, Add, Subtract, Undo, Clear, Invert,
   Soft edge, Use whole photo. One finger draws; two fingers pinch-zoom and pan. The page never scrolls
   while drawing. The selection is sent with the build (app.js formData -> "select") and kept in the
   saved build's params, so re-opening, rebuilding and Send-to keep it. Warnings never block. */
const $ = s => document.querySelector(s);
const WORK = 384;                                   // long side of the mask raster (sent to the server)
const MODES = ["lithophane", "relief", "popart", "bust"];
const st = { img: null, w: 0, h: 0, paths: [], invert: false, soft: 0, outside: "plain", snap: true, tool: "new",
             undo: [], mask: null, rough: null, open: false, use: false, mode: "lithophane", rgb: null, zoom: 1, panX: 0, panY: 0 };
window.zeimSelectState = st;                       // for tests / debugging

/* ---------------- DOM ---------------- */
const host = document.createElement("div");
host.className = "selm"; host.id = "selectMode"; host.hidden = true;
host.innerHTML = `
<div class="selm-bar"><button type="button" class="btn selm-open" id="selOpen" aria-expanded="false" aria-controls="selPanel">Choose part of the photo</button>
<span class="selm-state" id="selState" role="status" aria-live="polite">Using the whole photo.</span></div>
<div class="selm-panel" id="selPanel" hidden>
  <p class="help selm-say" id="selSay">Draw round what you want to keep. Use one finger or the mouse. Pinch with two fingers to zoom.</p>
  <div class="selm-tools" role="toolbar" aria-label="Selection tools">
    <button type="button" class="selm-t" data-tool="new" aria-pressed="true">Trace</button>
    <button type="button" class="selm-t" data-tool="add" aria-pressed="false">＋ Add</button>
    <button type="button" class="selm-t" data-tool="sub" aria-pressed="false">− Subtract</button>
    <button type="button" class="selm-t" id="selUndo" disabled>↶ Undo</button>
    <button type="button" class="selm-t" id="selClear" disabled>Clear</button>
    <button type="button" class="selm-t" id="selInvert" aria-pressed="false">Invert</button>
  </div>
  <div class="selm-stage" id="selStage"><div class="selm-zoom" id="selZoom"><canvas id="selCanvas" aria-label="Your photo. Draw round the part to keep."></canvas></div>
    <button type="button" class="selm-t selm-fit" id="selFit" hidden>Fit</button></div>
  <div class="selm-row"><label for="selSoft">Soft edge</label><input type="range" id="selSoft" min="0" max="20" step="1" value="0"><output id="selSoftOut">Off</output></div>
  <div class="selm-row"><label class="inl"><input type="checkbox" id="selSnap" checked> Snap to edges</label></div>
  <fieldset class="selm-row selm-out" id="selOutside"><legend>Outside the selection (lithophane)</legend>
    <label class="inl"><input type="radio" name="selOut" value="plain" checked> Plain: glows white</label>
    <label class="inl"><input type="radio" name="selOut" value="flat"> Flat: solid, no picture</label></fieldset>
  <p class="help selm-warn" id="selWarn" hidden></p>
  <div class="selm-go"><button type="button" class="btn primary" id="selUse" disabled>Make it from my selection</button>
    <button type="button" class="btn" id="selWhole">Use whole photo</button></div>
</div>`;
function mount() {
  const after = $("#photoChosen");
  if (after && !host.isConnected) after.after(host);
}
mount();
const cv = host.querySelector("#selCanvas"), ctx = cv.getContext("2d");
const stage = host.querySelector("#selStage"), zoomEl = host.querySelector("#selZoom");

/* ---------------- state helpers ---------------- */
const snapshot = () => JSON.stringify({ paths: st.paths, invert: st.invert });
function push() { st.undo.push(snapshot()); if (st.undo.length > 60) st.undo.shift(); }
function setTool(t) { st.tool = t; host.querySelectorAll("[data-tool]").forEach(b => b.setAttribute("aria-pressed", b.dataset.tool === t)); }
function say(t) { host.querySelector("#selSay").textContent = t; }
function status() {
  const has = st.use && st.mask && st.paths.length;
  host.querySelector("#selState").textContent = has ? `Using your selection (${Math.round(st.area * 100)}% of the photo).` : "Using the whole photo.";
  host.querySelector("#selUndo").disabled = !st.undo.length;
  host.querySelector("#selClear").disabled = !st.paths.length && !st.invert;
  host.querySelector("#selInvert").setAttribute("aria-pressed", st.invert);
  host.querySelector("#selUse").disabled = !st.paths.length;
  host.querySelector("#selOutside").hidden = st.mode !== "lithophane";
}
function warn(t) { const w = host.querySelector("#selWarn"); w.hidden = !t; w.textContent = t || ""; }

/* ---------------- image ---------------- */
function loadImage(src) {
  const im = new Image();
  im.onload = () => {
    st.img = im; const s = WORK / Math.max(im.naturalWidth, im.naturalHeight);
    st.w = Math.max(4, Math.round(im.naturalWidth * Math.min(1, s))); st.h = Math.max(4, Math.round(im.naturalHeight * Math.min(1, s)));
    const c = document.createElement("canvas"); c.width = st.w; c.height = st.h;
    const x = c.getContext("2d", { willReadFrequently: true }); x.drawImage(im, 0, 0, st.w, st.h);
    st.rgb = x.getImageData(0, 0, st.w, st.h).data;
    recompute(); draw();
  };
  im.src = src;
}

/* ---------------- mask: rasterise + edge snap ---------------- */
function rasterRough() {
  const c = document.createElement("canvas"); c.width = st.w; c.height = st.h;
  const x = c.getContext("2d");
  for (const p of st.paths) {
    if (p.op === "new") x.clearRect(0, 0, st.w, st.h);
    x.globalCompositeOperation = p.op === "sub" ? "destination-out" : "source-over";
    x.fillStyle = "#fff"; x.beginPath();
    p.pts.forEach(([u, v], i) => { const X = u * (st.w - 1), Y = v * (st.h - 1); i ? x.lineTo(X, Y) : x.moveTo(X, Y); });
    x.closePath(); x.fill();
  }
  const d = x.getImageData(0, 0, st.w, st.h).data, m = new Uint8Array(st.w * st.h);
  for (let i = 0; i < m.length; i++) m[i] = d[i * 4 + 3] > 127 ? 1 : 0;
  return m;
}
function chamfer(m, val) {        /* distance (px, 3-4 chamfer / 3) from each pixel with m==val to the nearest m!=val */
  const W = st.w, H = st.h, D = new Float32Array(W * H), INF = 1e9;
  for (let i = 0; i < D.length; i++) D[i] = m[i] === val ? INF : 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) { const i = y * W + x; if (!D[i]) continue; let v = D[i];
    if (x > 0) v = Math.min(v, D[i - 1] + 3); if (y > 0) { v = Math.min(v, D[i - W] + 3); if (x > 0) v = Math.min(v, D[i - W - 1] + 4); if (x < W - 1) v = Math.min(v, D[i - W + 1] + 4); } D[i] = v; }
  for (let y = H - 1; y >= 0; y--) for (let x = W - 1; x >= 0; x--) { const i = y * W + x; if (!D[i]) continue; let v = D[i];
    if (x < W - 1) v = Math.min(v, D[i + 1] + 3); if (y < H - 1) { v = Math.min(v, D[i + W] + 3); if (x < W - 1) v = Math.min(v, D[i + W + 1] + 4); if (x > 0) v = Math.min(v, D[i + W - 1] + 4); } D[i] = v; }
  for (let i = 0; i < D.length; i++) D[i] /= 3;
  return D;
}
function kmeans(idx, k = 4) {
  const rgb = st.rgb, n = idx.length, step = Math.max(1, Math.floor(n / 3000)), px = [];
  for (let i = 0; i < n; i += step) { const j = idx[i] * 4; px.push([rgb[j], rgb[j + 1], rgb[j + 2]]); }
  const c = []; for (let j = 0; j < k; j++) c.push([...px[Math.floor(j * (px.length - 1) / Math.max(1, k - 1))]]);
  for (let it = 0; it < 8; it++) {
    const sum = c.map(() => [0, 0, 0, 0]);
    for (const p of px) { let b = 0, bd = 1e18; for (let j = 0; j < k; j++) { const d = (p[0] - c[j][0]) ** 2 + (p[1] - c[j][1]) ** 2 + (p[2] - c[j][2]) ** 2; if (d < bd) { bd = d; b = j; } } const s = sum[b]; s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3]++; }
    sum.forEach((s, j) => { if (s[3]) c[j] = [s[0] / s[3], s[1] / s[3], s[2] / s[3]]; });
  }
  return c;
}
function snap(rough) {            /* GrabCut-style, simplified (same idea as app/core/selectmask.py:snap) */
  const W = st.w, H = st.h, N = W * H, band = Math.max(4, Math.round(0.06 * Math.max(W, H)));
  const dIn = chamfer(rough, 1), dOut = chamfer(rough, 0);
  const inIdx = [], outIdx = [];
  for (let i = 0; i < N; i++) { if (rough[i] && dIn[i] > band && dIn[i] <= band * 3) inIdx.push(i); else if (!rough[i] && dOut[i] > band && dOut[i] <= band * 3) outIdx.push(i); }
  if (inIdx.length < 20 || outIdx.length < 20) return rough;
  const cf = kmeans(inIdx), cb = kmeans(outIdx), rgb = st.rgb, out = new Uint8Array(N);
  const near = (cs, j) => { let b = 1e18; for (const c of cs) { const d = (rgb[j] - c[0]) ** 2 + (rgb[j + 1] - c[1]) ** 2 + (rgb[j + 2] - c[2]) ** 2; if (d < b) b = d; } return Math.sqrt(b); };
  for (let i = 0; i < N; i++) {
    if (rough[i] && dIn[i] > band) { out[i] = 1; continue; }
    if (!rough[i] && dOut[i] > band) continue;
    const df = near(cf, i * 4), db = near(cb, i * 4), prior = (rough[i] ? dIn[i] : -dOut[i]) / band;
    out[i] = (db - df) / (db + df + 1e-3) + 0.35 * prior > 0 ? 1 : 0;
  }
  for (let pass = 0; pass < 2; pass++) {          /* majority smoothing: no speckles, a clean edge */
    const o = out.slice();
    for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) { const i = y * W + x; let s = 0;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) s += o[i + dy * W + dx]; out[i] = s >= 5 ? 1 : 0; }
  }
  /* drop crumbs not joined to the sure-inside part */
  const seen = new Uint8Array(N), q = [];
  for (let i = 0; i < N; i++) if (out[i] && rough[i] && dIn[i] > band) { seen[i] = 1; q.push(i); }
  while (q.length) { const i = q.pop(), x = i % W; for (const j of [i - W, i + W, x > 0 ? i - 1 : -1, x < W - 1 ? i + 1 : -1]) if (j >= 0 && j < N && out[j] && !seen[j]) { seen[j] = 1; q.push(j); } }
  if (q.length === 0 && seen.some(v => v)) for (let i = 0; i < N; i++) out[i] = seen[i];
  return out;
}
function recompute() {
  if (!st.rgb) return;
  if (!st.paths.length) { st.mask = null; st.area = 1; status(); return; }
  let m = rasterRough();
  if (st.snap) m = snap(m);
  if (st.invert) for (let i = 0; i < m.length; i++) m[i] = 1 - m[i];
  let n = 0; for (const v of m) n += v;
  st.mask = m; st.area = n / m.length;
  warn(st.area < 0.002 ? "Nothing is selected yet, so the whole photo would be used. Draw round what you want to keep."
     : st.area < 0.02 ? "That's a very small part of the photo. It will work, but fine detail may not print." : "");
  status();
}

/* ---------------- drawing ---------------- */
function fitCanvas() {
  const W = Math.max(200, stage.clientWidth || 340), s = W / st.w;
  cv.width = st.w * 2; cv.height = st.h * 2; cv.style.width = W + "px"; cv.style.height = Math.round(st.h * s) + "px";
  stage.style.height = Math.round(st.h * s) + "px";
}
let live = null;                                 // the stroke being drawn (normalised points)
function draw() {
  if (!st.img) return;
  fitCanvas();
  const C = cv.width, R = cv.height;
  ctx.clearRect(0, 0, C, R); ctx.drawImage(st.img, 0, 0, C, R);
  if (st.mask) {
    const o = document.createElement("canvas"); o.width = st.w; o.height = st.h;
    const ox = o.getContext("2d"), id = ox.createImageData(st.w, st.h), litho = st.mode === "lithophane";
    const fill = litho ? (st.outside === "plain" ? [255, 255, 255, 235] : [20, 20, 20, 235]) : [40, 40, 48, 190];
    for (let i = 0; i < st.mask.length; i++) if (!st.mask[i]) { id.data.set(fill, i * 4); }
    ox.putImageData(id, 0, 0);
    ctx.save(); ctx.imageSmoothingEnabled = true;
    if (st.soft) ctx.filter = `blur(${(st.soft / 1000 * Math.max(C, R)).toFixed(1)}px)`;
    ctx.drawImage(o, 0, 0, C, R); ctx.restore();
    /* outline */
    const e = document.createElement("canvas"); e.width = st.w; e.height = st.h;
    const ex = e.getContext("2d"), ed = ex.createImageData(st.w, st.h), W = st.w, m = st.mask;
    for (let i = W; i < m.length - W; i++) if (m[i] && (!m[i - 1] || !m[i + 1] || !m[i - W] || !m[i + W])) ed.data.set([0, 220, 255, 255], i * 4);
    ex.putImageData(ed, 0, 0); ctx.drawImage(e, 0, 0, C, R);
  }
  if (live && live.length > 1) {
    ctx.save(); ctx.lineWidth = 4; ctx.lineJoin = "round"; ctx.strokeStyle = st.tool === "sub" ? "#ff4d6d" : "#ffd23f"; ctx.setLineDash([10, 6]);
    ctx.beginPath(); live.forEach(([u, v], i) => i ? ctx.lineTo(u * C, v * R) : ctx.moveTo(u * C, v * R)); ctx.stroke(); ctx.restore();
  }
}
const ptrs = new Map(); let pinch = null;
const norm = e => { const r = cv.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
function applyZoom() {
  st.zoom = Math.min(6, Math.max(1, st.zoom));
  if (st.zoom === 1) { st.panX = 0; st.panY = 0; }
  zoomEl.style.transform = `translate(${st.panX}px,${st.panY}px) scale(${st.zoom})`;
  host.querySelector("#selFit").hidden = st.zoom === 1;
}
cv.addEventListener("pointerdown", e => {
  e.preventDefault(); try { cv.setPointerCapture(e.pointerId); } catch (_) { /* not capturable: fine */ } ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (ptrs.size === 2) {                         /* second finger: zoom instead of draw */
    live = null; const [a, b] = [...ptrs.values()];
    pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), z: st.zoom, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, px: st.panX, py: st.panY }; draw(); return;
  }
  if (ptrs.size === 1) live = [norm(e)];
});
cv.addEventListener("pointermove", e => {
  if (!ptrs.has(e.pointerId)) return; e.preventDefault(); ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pinch && ptrs.size >= 2) { const [a, b] = [...ptrs.values()];
    st.zoom = pinch.z * Math.hypot(a.x - b.x, a.y - b.y) / Math.max(1, pinch.d);
    st.panX = pinch.px + (a.x + b.x) / 2 - pinch.cx; st.panY = pinch.py + (a.y + b.y) / 2 - pinch.cy; applyZoom(); return; }
  if (live) { const p = norm(e), q = live[live.length - 1]; if (Math.hypot(p[0] - q[0], p[1] - q[1]) > 0.003) { live.push(p); draw(); } }
});
function endPtr(e) {
  if (!ptrs.has(e.pointerId)) return; ptrs.delete(e.pointerId);
  if (pinch) { if (ptrs.size < 2) pinch = null; return; }
  if (!live) return;
  const pts = live; live = null;
  if (pts.length < 3) { draw(); say("That line was too short. Draw all the way round what you want to keep."); return; }
  push(); st.paths.push({ op: st.tool, pts: pts.map(([u, v]) => [+u.toFixed(4), +v.toFixed(4)]) });
  st.use = true; recompute(); draw();
  if (st.tool === "new") { setTool("add"); say("Done. Add more with ＋ Add, cut bits out with − Subtract, then press Make it."); }
}
["pointerup", "pointercancel"].forEach(t => cv.addEventListener(t, endPtr));
/* no page scroll / browser zoom while the finger is on the photo */
["touchstart", "touchmove"].forEach(t => cv.addEventListener(t, e => e.preventDefault(), { passive: false }));
stage.addEventListener("wheel", e => { if (!st.open) return; e.preventDefault(); st.zoom *= e.deltaY < 0 ? 1.15 : 1 / 1.15; applyZoom(); }, { passive: false });
host.querySelector("#selFit").onclick = () => { st.zoom = 1; applyZoom(); };

/* ---------------- controls ---------------- */
host.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
host.querySelector("#selUndo").onclick = () => { const s = st.undo.pop(); if (!s) return; Object.assign(st, JSON.parse(s)); if (!st.paths.length) setTool("new"); recompute(); draw(); };
host.querySelector("#selClear").onclick = () => { push(); st.paths = []; st.invert = false; setTool("new"); recompute(); draw(); say("Cleared. Draw round what you want to keep."); };
host.querySelector("#selInvert").onclick = () => { push(); st.invert = !st.invert; recompute(); draw(); };
const softIn = host.querySelector("#selSoft");
softIn.oninput = () => { st.soft = +softIn.value; host.querySelector("#selSoftOut").textContent = st.soft ? st.soft : "Off"; draw(); };
host.querySelector("#selSnap").onchange = e => { st.snap = e.target.checked; recompute(); draw(); };
host.querySelectorAll("input[name=selOut]").forEach(r => r.onchange = () => { st.outside = r.value; draw(); });
function openPanel(o) {
  st.open = o; host.querySelector("#selPanel").hidden = !o; host.querySelector("#selOpen").setAttribute("aria-expanded", o);
  host.querySelector("#selOpen").textContent = o ? "Hide selection tools" : "Choose part of the photo";
  if (o) { draw(); status(); }
}
host.querySelector("#selOpen").onclick = () => openPanel(!st.open);
const rebuild = () => { const b = $("#btnBuild"); if (b && !b.disabled) b.click(); };
host.querySelector("#selUse").onclick = () => {
  if (!st.paths.length) return;
  st.use = true; status();
  if (st.area < 0.002) say("Nothing is selected, so the whole photo will be used.");
  rebuild();
};
host.querySelector("#selWhole").onclick = () => { st.use = false; status(); openPanel(false); rebuild(); };

/* ---------------- what app.js sends ---------------- */
function maskPNG() {
  const c = document.createElement("canvas"); c.width = st.w; c.height = st.h;
  const x = c.getContext("2d"), id = x.createImageData(st.w, st.h);
  for (let i = 0; i < st.mask.length; i++) { const v = st.mask[i] ? 255 : 0; id.data[i * 4] = id.data[i * 4 + 1] = id.data[i * 4 + 2] = v; id.data[i * 4 + 3] = 255; }
  x.putImageData(id, 0, 0); return c.toDataURL("image/png");
}
window.zeimSelect = mode => {
  if (!MODES.includes(mode) || !st.use || !st.mask || !st.paths.length || st.area < 0.002) return "";
  return JSON.stringify({ v: 1, mask: maskPNG(), soft: st.soft, outside: st.outside, invert: st.invert, snap: st.snap, paths: st.paths });
};

/* ---------------- app events ---------------- */
document.addEventListener("zeim:file", e => {
  mount(); st.paths = []; st.undo = []; st.invert = false; st.mask = null; st.use = false; st.zoom = 1; applyZoom(); setTool("new");
  host.hidden = !MODES.includes(st.mode); status();
  const img = $("#dropPreview"); loadImage(img && img.src ? img.src : URL.createObjectURL(e.detail));
});
document.addEventListener("zeim:mode", e => {
  st.mode = e.detail; host.hidden = !MODES.includes(st.mode) || !st.img; status(); draw();
  if (st.mode === "bust") say("For a bust, draw round the head and shoulders. The rest becomes the clean pedestal cut.");
});
document.addEventListener("zeim:build", e => {        /* a saved build carries its selection: keep it for "make it again" */
  const s = e.detail?.params?.select; if (!s || !Array.isArray(s.paths)) return;
  st.paths = s.paths; st.invert = !!s.invert; st.soft = +s.soft || 0; st.outside = s.outside || "plain"; st.snap = s.snap !== false; st.use = true;
  softIn.value = st.soft; host.querySelector("#selSoftOut").textContent = st.soft || "Off"; host.querySelector("#selSnap").checked = st.snap;
  host.querySelectorAll("input[name=selOut]").forEach(r => r.checked = r.value === st.outside);
  if (st.paths.length) setTool("add");
  recompute(); draw();
});
const initMode = document.querySelector("#modeCards input:checked"); if (initMode) st.mode = initMode.value;
addEventListener("resize", () => { if (st.open) draw(); });
