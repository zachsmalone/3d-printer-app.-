/* Layer-by-layer preview of a sliced print: one layer at a time on a 2D canvas, the layers below drawn faint,
   colours by line kind (walls, infill, supports...). Data: GET /api/slice/<id>/layers (read from the G-code). */
import { api, esc, $ } from "/static/app.js";

const COLOURS = { outer: "#ff8a3d", inner: "#ffd166", infill: "#b48cff", solid: "#ef476f", support: "#2ec4a6", skirt: "#4cc9f0", other: "#9aa5b8" };

export function layerPreviewHTML() {
  return `<section class="layerprev" aria-labelledby="lpH"><h4 id="lpH">Layer-by-layer preview</h4>
    <button type="button" class="btn" id="lpOpen"><svg class=i aria-hidden=true focusable=false><use href=#i-search></use></svg> Show layer-by-layer preview</button>
    <div id="lpBox" hidden>
      <canvas id="lpCanvas" width="640" height="640" role="img" aria-label="Layer preview"></canvas>
      <div class="lprow">
        <button type="button" class="btn" id="lpPrev" aria-label="Previous layer">◀</button>
        <label for="lpRange" class="sr-only">Layer</label><input type="range" id="lpRange" min="1" max="1" value="1" step="1">
        <button type="button" class="btn" id="lpNext" aria-label="Next layer">▶</button>
        <button type="button" class="btn" id="lpPlay" aria-pressed="false">▶ Play</button>
      </div>
      <p id="lpInfo" class="lpinfo" aria-live="polite"></p>
      <label class="inl"><input type="checkbox" id="lpBelow" checked> Show the layers below (faint)</label>
      <ul class="lplegend" id="lpLegend"></ul>
      <p class="help" id="lpNote">Drawn from the G-code. Travel moves are not shown.</p>
    </div></section>`;
}

export function wireLayerPreview(url) {
  const open = $("#lpOpen"); if (!open) return;
  let D = null, cur = 0, timer = null;
  const cv = $("#lpCanvas"), rg = $("#lpRange"), info = $("#lpInfo");
  open.onclick = async () => {
    open.disabled = true; open.textContent = "Loading layers…";
    try { D = await api(url); } catch (e) { open.disabled = false; open.textContent = "Show layer-by-layer preview"; info.textContent = e.message; $("#lpBox").hidden = false; return; }
    open.hidden = true; $("#lpBox").hidden = false;
    rg.max = D.layers.length; rg.value = D.layers.length; cur = D.layers.length - 1;
    const used = new Set(D.layers.flatMap(l => l.paths.map(p => p.k)));
    $("#lpLegend").innerHTML = Object.entries(D.kinds).filter(([k]) => used.has(k)).map(([k, v]) =>
      `<li><span class="lpsw" style="background:${COLOURS[k] || COLOURS.other}" aria-hidden="true"></span>${esc(v)}</li>`).join("");
    if (D.thinned) $("#lpNote").textContent = "Drawn from the G-code (big print: some points thinned for speed). Travel moves are not shown.";
    draw(); rg.focus();
  };
  const go = i => { if (!D) return; cur = Math.max(0, Math.min(D.layers.length - 1, i)); rg.value = cur + 1; draw(); };
  rg.oninput = () => go(+rg.value - 1);
  $("#lpPrev").onclick = () => go(cur - 1);
  $("#lpNext").onclick = () => go(cur + 1);
  $("#lpBelow").onchange = () => draw();
  const stop = () => { clearInterval(timer); timer = null; $("#lpPlay").setAttribute("aria-pressed", "false"); $("#lpPlay").textContent = "▶ Play"; };
  $("#lpPlay").onclick = () => {
    if (timer) return stop();
    if (cur >= D.layers.length - 1) go(0);
    $("#lpPlay").setAttribute("aria-pressed", "true"); $("#lpPlay").textContent = "⏸ Pause";
    timer = setInterval(() => { if (!cv.isConnected || cur >= D.layers.length - 1) return stop(); go(cur + 1); }, 120);
  };
  function draw() {
    const L = D.layers, l = L[cur], ctx = cv.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2), css = cv.clientWidth || 320;
    if (cv.width !== Math.round(css * dpr)) { cv.width = cv.height = Math.round(css * dpr); }
    const W = cv.width, [x0, y0, x1, y1] = D.bounds, pad = 0.06 * W;
    const s = Math.min((W - 2 * pad) / Math.max(x1 - x0, 1), (W - 2 * pad) / Math.max(y1 - y0, 1));
    const ox = (W - (x1 - x0) * s) / 2, oy = (W - (y1 - y0) * s) / 2;
    const X = v => ox + (v - x0) * s, Y = v => W - (oy + (v - y0) * s);         // Y up, like looking down on the bed
    ctx.fillStyle = "#101826"; ctx.fillRect(0, 0, W, W);
    ctx.lineCap = ctx.lineJoin = "round";
    const stroke = (paths, colourOf, width) => {
      for (const p of paths) {
        const a = p.p; if (a.length < 4) continue;
        ctx.strokeStyle = colourOf(p.k); ctx.lineWidth = width; ctx.beginPath(); ctx.moveTo(X(a[0]), Y(a[1]));
        for (let i = 2; i < a.length; i += 2) ctx.lineTo(X(a[i]), Y(a[i + 1]));
        ctx.stroke();
      }
    };
    const lw = Math.max(1, 0.42 * s);
    if ($("#lpBelow").checked && cur > 0) {
      ctx.globalAlpha = 0.12;
      for (let i = Math.max(0, cur - 60); i < cur; i++) stroke(L[i].paths, () => "#c9d4e8", lw);
      ctx.globalAlpha = 1;
    }
    stroke(l.paths, k => COLOURS[k] || COLOURS.other, lw);
    const txt = `Layer ${cur + 1} of ${L.length} · height ${l.z.toFixed(2)} mm`;
    info.textContent = txt; cv.setAttribute("aria-label", "Layer preview. " + txt);
    rg.setAttribute("aria-valuetext", txt);
  }
}
