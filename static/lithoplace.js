/* Lithophane image placement: move / zoom / rotate the photo inside the chosen shape.
   Mirrors app/core/litho_shapes.place_image: scale 1 = fill (centre crop, today's default), x/y = offset of the photo
   centre as a fraction of the shape box (+x right, +y down), rotation = degrees clockwise. Wrap shapes (globe / cup /
   night-light) slide round the wrap horizontally (no seam gap). */
const WRAP = ["globe", "cup", "nightlight"];
const LIM = { x: [-1, 1], y: [-1, 1], scale: [0.1, 8] };
const clamp = (v, [a, b]) => Math.min(b, Math.max(a, v));

function heart(n = 400) {
  const p = []; let m = 0;
  for (let i = 0; i < n; i++) {
    const t = i / n * 2 * Math.PI, x = 16 * Math.sin(t) ** 3 / 17,
      y = (13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t) + 2.5) / 17 * 1.15;
    p.push([x, y]); m = Math.max(m, Math.abs(x), Math.abs(y));
  }
  return p.map(([x, y]) => [x / m, y / m]);
}
function outline(shape) {                     // -1..1 box, y up
  if (shape === "heart") return heart();
  if (shape === "star") return Array.from({ length: 10 }, (_, i) => { const a = i * Math.PI / 5 + Math.PI / 2, r = i % 2 ? 0.45 : 1; return [r * Math.cos(a), r * Math.sin(a)]; });
  if (shape === "circle") return Array.from({ length: 120 }, (_, i) => [Math.cos(i * Math.PI / 60), Math.sin(i * Math.PI / 60)]);
  if (shape === "hexagon") return Array.from({ length: 6 }, (_, i) => { const a = i * Math.PI / 3 + Math.PI / 6; return [Math.cos(a), Math.sin(a)]; });
  if (shape === "diamond") return Array.from({ length: 4 }, (_, i) => { const a = i * Math.PI / 2 + Math.PI / 2; return [Math.cos(a), Math.sin(a)]; });
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]];
}

export function mountPlace(root, { shape, aspect, onChange }) {
  root.innerHTML = `
  <p class="help" id="lpHelp">Drag the photo to move it inside the shape. Pinch or scroll to zoom. Keyboard: arrow keys move, + and − zoom, [ and ] rotate.</p>
  <canvas id="lpCanvas" tabindex="0" role="img" aria-roledescription="image placement editor" aria-describedby="lpHelp lpSay"
    style="width:100%;max-width:420px;touch-action:none;cursor:grab;border-radius:8px;display:block"></canvas>
  <p class="help" id="lpSay" aria-live="polite"></p>
  <div class="field"><label for="lpZoom">Zoom <em id="lpZoomV">100%</em></label><input type="range" id="lpZoom" min="10" max="800" step="1" value="100"></div>
  <div class="field"><label for="lpRot">Rotate <em id="lpRotV">0°</em></label><input type="range" id="lpRot" min="-180" max="180" step="1" value="0"></div>
  <div class="row" role="group" aria-label="Placement shortcuts">
    <button type="button" class="btn ghost" id="lpRotL" aria-label="Rotate 90 degrees left"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"/></svg> 90°</button>
    <button type="button" class="btn ghost" id="lpRotR" aria-label="Rotate 90 degrees right">⟳ 90°</button>
    <button type="button" class="btn ghost" id="lpFit" aria-label="Fit: show the whole photo inside the shape">Fit</button>
    <button type="button" class="btn ghost" id="lpFill" aria-label="Fill: cover the whole shape">Fill</button>
    <button type="button" class="btn ghost" id="lpReset" aria-label="Reset placement">Reset</button>
  </div>`;
  const q = s => root.querySelector(s), cv = q("#lpCanvas"), ctx = cv.getContext("2d");
  const P = { x: 0, y: 0, scale: 1, rotation: 0 }; let img = null;
  const box = () => { const a = aspect(); const W = 400, H = Math.round(W / a); return [W, H]; };
  const norm = r => ((r % 360) + 540) % 360 - 180;       // slider range
  function say() {
    q("#lpZoomV").textContent = Math.round(P.scale * 100) + "%"; q("#lpRotV").textContent = Math.round(P.rotation) + "°";
    q("#lpZoom").value = Math.round(P.scale * 100); q("#lpRot").value = Math.round(norm(P.rotation));
    const t = `Photo moved ${Math.round(P.x * 100)}% across, ${Math.round(P.y * 100)}% down, zoom ${Math.round(P.scale * 100)}%, rotated ${Math.round(P.rotation)}°.`;
    cv.setAttribute("aria-label", `${shape()} placement editor. ${t}`); q("#lpSay").textContent = t;
  }
  function draw() {
    const [W, H] = box(); const pad = 20, dpr = window.devicePixelRatio || 1;
    cv.width = (W + 2 * pad) * dpr; cv.height = (H + 2 * pad) * dpr; cv.style.aspectRatio = `${W + 2 * pad} / ${H + 2 * pad}`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W + 2 * pad, H + 2 * pad);
    if (img) {
      const base = Math.max(W / img.width, H / img.height) * P.scale, wrap = WRAP.includes(shape());
      for (const k of wrap ? [-1, 0, 1] : [0]) {
        ctx.save(); ctx.translate(pad + W / 2 + (P.x + k) * W, pad + H / 2 + P.y * H); ctx.rotate(P.rotation * Math.PI / 180);
        ctx.drawImage(img, -img.width * base / 2, -img.height * base / 2, img.width * base, img.height * base); ctx.restore();
      }
    }
    // dim everything outside the shape, then draw the outline
    const pts = WRAP.includes(shape()) ? [[-1, -1], [1, -1], [1, 1], [-1, 1]] : outline(shape());
    ctx.beginPath(); ctx.rect(0, 0, W + 2 * pad, H + 2 * pad);
    pts.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](pad + (x + 1) / 2 * W, pad + (1 - y) / 2 * H)); ctx.closePath();
    ctx.fillStyle = "rgba(20,20,30,.6)"; ctx.fill("evenodd");
    ctx.beginPath(); pts.forEach(([x, y], i) => ctx[i ? "lineTo" : "moveTo"](pad + (x + 1) / 2 * W, pad + (1 - y) / 2 * H)); ctx.closePath();
    ctx.lineWidth = 3; ctx.strokeStyle = "#ff3b7f"; ctx.setLineDash([]); ctx.stroke();
    if (WRAP.includes(shape())) { ctx.fillStyle = "#fff"; ctx.font = "12px sans-serif"; ctx.fillText("← wraps all the way round →", pad + 4, pad + H + 14); }
  }
  let raf = 0;
  function set(o, quiet) {
    Object.assign(P, o);
    P.x = clamp(P.x, LIM.x); P.y = clamp(P.y, LIM.y); P.scale = clamp(P.scale, LIM.scale);
    if (WRAP.includes(shape())) P.x = ((P.x + 1.5) % 1 + 1) % 1 - 0.5;   // round the wrap: -0.5..0.5 covers it
    if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); });
    say(); if (!quiet) onChange && onChange(get());
  }
  const get = () => ({ ...P, rotation: ((P.rotation % 360) + 360) % 360 });
  const fitScale = () => {
    if (!img) return 1; const [W, H] = box(), r = P.rotation * Math.PI / 180;
    const iw = Math.abs(img.width * Math.cos(r)) + Math.abs(img.height * Math.sin(r)), ih = Math.abs(img.width * Math.sin(r)) + Math.abs(img.height * Math.cos(r));
    return Math.min(W / iw, H / ih) / Math.max(W / img.width, H / img.height);
  };
  // pointer: drag + pinch (iPhone), wheel zoom
  const pts = new Map(); let last = null;
  const pinch = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
  cv.addEventListener("pointerdown", e => { cv.setPointerCapture(e.pointerId); pts.set(e.pointerId, { x: e.clientX, y: e.clientY }); last = pts.size === 2 ? pinch() : null; cv.style.cursor = "grabbing"; });
  cv.addEventListener("pointermove", e => {
    const p = pts.get(e.pointerId); if (!p) return; const [W, H] = box(), k = cv.clientWidth / (W + 40);
    if (pts.size === 1) set({ x: P.x + (e.clientX - p.x) / k / W, y: P.y + (e.clientY - p.y) / k / H });
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2) { const d = pinch(); if (last) set({ scale: P.scale * d / last }); last = d; }
  });
  const up = e => { pts.delete(e.pointerId); last = null; cv.style.cursor = "grab"; };
  cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
  cv.addEventListener("wheel", e => { e.preventDefault(); set({ scale: P.scale * Math.exp(-e.deltaY * 0.0015) }); }, { passive: false });
  cv.addEventListener("keydown", e => {
    const st = e.shiftKey ? 0.1 : 0.02, m = { ArrowLeft: { x: P.x - st }, ArrowRight: { x: P.x + st }, ArrowUp: { y: P.y - st }, ArrowDown: { y: P.y + st },
      "+": { scale: P.scale * 1.1 }, "=": { scale: P.scale * 1.1 }, "-": { scale: P.scale / 1.1 }, _: { scale: P.scale / 1.1 },
      "[": { rotation: P.rotation - (e.shiftKey ? 90 : 5) }, "]": { rotation: P.rotation + (e.shiftKey ? 90 : 5) }, "0": { x: 0, y: 0, scale: 1, rotation: 0 } }[e.key];
    if (m) { e.preventDefault(); set(m); }
  });
  q("#lpZoom").oninput = e => set({ scale: e.target.value / 100 });
  q("#lpRot").oninput = e => set({ rotation: +e.target.value });
  q("#lpRotL").onclick = () => set({ rotation: P.rotation - 90 });
  q("#lpRotR").onclick = () => set({ rotation: P.rotation + 90 });
  q("#lpFit").onclick = () => set({ x: 0, y: 0, scale: fitScale() });
  q("#lpFill").onclick = () => set({ x: 0, y: 0, scale: 1 });
  q("#lpReset").onclick = () => set({ x: 0, y: 0, scale: 1, rotation: 0 });
  say(); draw();
  return {
    get, set, redraw: () => set({}, true),
    isDefault: () => P.x === 0 && P.y === 0 && P.scale === 1 && ((P.rotation % 360) + 360) % 360 === 0,
    setImage(url) { if (!url) { img = null; draw(); return; } const i = new Image(); i.onload = () => { img = i; set({ x: 0, y: 0, scale: 1, rotation: 0 }, true); }; i.src = url; },
  };
}
