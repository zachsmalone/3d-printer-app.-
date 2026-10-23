/* 3D G-code preview (three.js, MIT). The G-code is parsed in a Web Worker (static/gcode-worker.js) while it streams in;
   each layer becomes ONE merged LineSegments geometry with a group per line type. Render on demand only (no RAF loop),
   DPR capped at 1.5 on touch. Layer slider (bottom .. shown layer), Play, per-type toggles (travel off by default). */
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";
import { esc, $ } from "/static/app.js";

export const GC_TYPES = [
  ["outer", "Outer wall", "#ff8a3d"], ["inner", "Inner wall", "#ffd166"], ["infill", "Infill", "#b48cff"],
  ["solid", "Solid / top infill", "#ef476f"], ["support", "Support", "#2ec4a6"], ["skirt", "Skirt / brim", "#4cc9f0"],
  ["other", "Other", "#9aa5b8"], ["travel", "Travel", "#5a6b8c"]];
const TOUCH = matchMedia("(pointer: coarse)").matches || navigator.maxTouchPoints > 0 && matchMedia("(hover: none)").matches;

export function gcodePreviewHTML() {
  return `<section class="gcprev" id="gcPrev" aria-labelledby="gcH"><h4 id="gcH">G-code preview</h4>
    <div class="gcprog" id="gcProgWrap"><label for="gcProg" id="gcProgLbl">Reading the G-code…</label><progress id="gcProg" max="100" value="0"></progress></div>
    <div class="gcstage" id="gcStage" role="img" aria-label="3D preview of the sliced G-code. Drag to turn, pinch or scroll to zoom."></div>
    <div class="gcrow">
      <button type="button" class="btn" id="gcPrevL" aria-label="Previous layer">◀</button>
      <label for="gcRange" class="sr-only">Layer shown</label>
      <input type="range" id="gcRange" min="1" max="1" value="1" step="1" aria-valuetext="Layer 1">
      <button type="button" class="btn" id="gcNextL" aria-label="Next layer">▶</button>
      <button type="button" class="btn" id="gcPlay" aria-pressed="false" aria-label="Play layers">▶ Play</button>
    </div>
    <p class="gcinfo" id="gcInfo" aria-live="polite"></p>
    <p class="gcinfo" id="gcEst"></p>
    <style>
      .gcx-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}
      .gcx-row input,.gcx-row select{min-height:44px;min-width:0;font-size:1rem}
      .gcx-row input[type=number]{width:6.5em}
      .gcticks{position:relative;height:8px;margin:0 52px}
      .gcticks i{position:absolute;top:0;width:3px;height:8px;background:#ffb020;border-radius:2px}
      .gcx-box{border:1px solid var(--line,#33405c);border-radius:10px;padding:6px 10px;margin:8px 0;min-width:0}
      .gcx-box summary{min-height:44px;display:flex;align-items:center;cursor:pointer;font-weight:600}
      .gcx-list{list-style:none;margin:4px 0;padding:0}
      .gcx-list li{display:flex;gap:6px;align-items:center;min-width:0}
      .gcx-list li>span{flex:1;min-width:0;overflow-wrap:anywhere}
      .gcmk{text-align:left;flex:1;min-width:0;white-space:normal;overflow-wrap:anywhere}
      .gccode{position:relative;height:260px;overflow:auto;background:#0d1420;border-radius:8px;font:12px/18px ui-monospace,Menlo,Consolas,monospace;color:#cfd8e6;contain:strict}
      .gccode>div{position:absolute;left:0;right:0;white-space:pre;padding:0 6px;height:18px;overflow:hidden;text-overflow:ellipsis}
      .gccode>div b{display:inline-block;min-width:4.5em;color:#6b7a96;font-weight:400}
      .gccode>div.hl{background:#3a2f12}
      @media (max-width:600px){.gccode{height:200px}}
    </style>
    <div class="gcticks" id="gcTicks" aria-hidden="true"></div>
    <div class="gcx-row" role="group" aria-label="Jump to a layer or height">
      <label for="gcJumpV">Jump to</label><input type="number" id="gcJumpV" inputmode="decimal" min="0" step="any" placeholder="e.g. 12.4">
      <label for="gcJumpU" class="sr-only">Jump by</label><select id="gcJumpU"><option value="z">mm height</option><option value="layer">layer #</option></select>
      <button type="button" class="btn" id="gcJumpGo">Go</button>
    </div>
    <p class="help" id="gcJumpMsg" aria-live="polite"></p>
    <section class="gcx-box" id="gcMarks" hidden aria-labelledby="gcMarksH"><div class="gcx-row"><strong id="gcMarksH" style="flex:1">Possible trouble spots</strong>
      <button type="button" class="btn" id="gcMarksX" aria-label="Hide trouble spots"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
      <p class="help">Likely trouble spots from ZEIM's checks, not a diagnosis. Tap one to see that layer and its code.</p>
      <ul class="gcx-list" id="gcMarkList"></ul></section>
    <details class="gcx-box" id="gcCodeBox"><summary id="gcCodeSum">G-code for this layer</summary>
      <div class="gccode" id="gcCode" tabindex="0" role="region" aria-label="G-code lines of the shown layer"><div id="gcCodeSp" style="position:static;height:0"></div></div>
      <p class="help" id="gcCodeMsg"></p></details>
    <details class="gcx-box" id="gcPauseBox"><summary>Pause at a layer (filament change)</summary>
      <div class="gcx-row"><button type="button" class="btn" id="gcPauseAdd">⏸ Pause at this layer</button></div>
      <div class="gcx-row"><label for="gcPauseCmd">Command</label><select id="gcPauseCmd"></select></div>
      <p class="help" id="gcPauseNote"></p>
      <ul class="gcx-list" id="gcPauseList"></ul>
      <a class="btn primary" id="gcPauseDl" hidden download="zeim-model-with-pauses.gcode">⬇ G-code with pauses</a>
      <p class="help">A new file. The normal G-code download above is unchanged.</p></details>
    <fieldset class="gclegend"><legend>Show</legend><div id="gcLegend">${GC_TYPES.map(([k, n, c]) =>
      `<label class="gcchip"><input type="checkbox" data-gct="${k}"${k === "travel" ? "" : " checked"}><span class="sw" style="background:${c}" aria-hidden="true"></span>${n}</label>`).join("")}</div></fieldset>
    <p class="help" id="gcNote"></p>
    <p class="help warn" id="gcWarn" hidden></p>
  </section>`;
}

/* url: G-code URL. est: {time, grams, mm} from the slice reply (optional). Returns a dispose() function. */
export function wireGcodePreview(url, est = {}, extra = {}) {
  const root = $("#gcPrev"); if (!root) return () => {};
  const stage = $("#gcStage"), rg = $("#gcRange"), info = $("#gcInfo"), prog = $("#gcProg"), progWrap = $("#gcProgWrap");
  const warn = (t) => { const w = $("#gcWarn"); w.hidden = false; w.textContent = t; };   // warnings never block
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: !TOUCH, alpha: true, powerPreference: TOUCH ? "low-power" : "default" }); }
  catch (e) { warn("3D preview needs WebGL, which this browser has turned off. The G-code download still works."); progWrap.hidden = true; return () => {}; }
  renderer.setPixelRatio(Math.min(devicePixelRatio, TOUCH ? 1.5 : 2));
  stage.appendChild(renderer.domElement);
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
  camera.up.set(0, 0, 1); camera.position.set(100, -160, 140);
  const controls = new OrbitControls(camera, renderer.domElement);
  const group = new THREE.Group(); scene.add(group);
  const mats = {}, matsTop = {};
  for (const [k, , c] of GC_TYPES) {
    const col = new THREE.Color(c);
    mats[k] = new THREE.LineBasicMaterial({ color: col.clone().lerp(new THREE.Color(0x1b2233), 0.35), visible: k !== "travel" });
    matsTop[k] = new THREE.LineBasicMaterial({ color: col, visible: k !== "travel" });
  }
  const layers = []; let cur = 0, follow = true, timer = null, pending = false, framed = false, disposed = false;
  window.__gcFrames = 0;
  const T = window.__gcT = { render: 0, maxRender: 0, msg: 0, maxMsg: 0 };   // timings for tests / perf checks
  const render = () => { pending = false; if (disposed) return; const t = performance.now(); renderer.render(scene, camera); const dt = performance.now() - t; T.render += dt; T.maxRender = Math.max(T.maxRender, dt); window.__gcFrames++; window.__gcLines = renderer.info.render.lines; };
  let streaming = true, lastStreamDraw = 0, streamTimer = null;
  const invalidate = () => { if (!pending) { pending = true; requestAnimationFrame(render); } };
  // while the file streams in, redraw at most once a second (each draw grows with the model); user input still draws at once
  const invalidateStream = () => {
    const wait = 1000 - (performance.now() - lastStreamDraw);
    if (wait <= 0) { lastStreamDraw = performance.now(); invalidate(); }
    else if (!streamTimer) streamTimer = setTimeout(() => { streamTimer = null; lastStreamDraw = performance.now(); invalidate(); }, wait);
  };
  controls.addEventListener("change", invalidate);
  const resize = () => { const w = stage.clientWidth, h = stage.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); invalidate(); };
  const ro = new ResizeObserver(resize); ro.observe(stage); resize();
  const matFor = (i) => (i === cur - 1 ? matsTop : mats);
  const matList = (L, set) => L.userData.groups.map(g => set[g.type]);
  function show(n, fromStream) {
    n = Math.max(1, Math.min(layers.length, n | 0)); const old = cur; cur = n;
    for (let i = 0; i < layers.length; i++) layers[i].visible = i < n;
    if (old && layers[old - 1]) layers[old - 1].material = matList(layers[old - 1], mats);
    if (layers[n - 1]) layers[n - 1].material = matList(layers[n - 1], matsTop);
    rg.value = n; const L = layers[n - 1];
    const txt = L ? `Layer ${n} of ${layers.length} · Z ${L.userData.z.toFixed(2)} mm · ${L.userData.height.toFixed(2)} mm tall` : "";
    info.textContent = txt; rg.setAttribute("aria-valuetext", L ? `Layer ${n} of ${layers.length}, height ${L.userData.z.toFixed(2)} mm` : "");
    if (fromStream && streaming) invalidateStream(); else invalidate();
    if (!fromStream || !streaming) codeSoon(); else if (pauseUI) pauseUI();
  }
  function addLayer(d) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(d.positions, 3));
    d.groups.forEach((g, i) => geo.addGroup(g.start, g.count, i));
    const ls = new THREE.LineSegments(geo, d.groups.map(g => mats[g.type]));
    ls.userData = { z: d.z, height: d.height, groups: d.groups, byte: d.byte, line: d.line }; ls.matrixAutoUpdate = false; ls.frustumCulled = false;
    group.add(ls); layers.push(ls);
  }
  function frame(b) {
    if (!(b[3] > b[0])) return;
    const c = new THREE.Vector3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2), r = Math.max(b[3] - b[0], b[4] - b[1], b[5] - b[2], 10);
    controls.target.copy(c); camera.position.set(c.x + r * 0.9, c.y - r * 1.5, c.z + r * 1.2); camera.near = r / 100; camera.far = r * 50; camera.updateProjectionMatrix(); controls.update(); framed = true;
  }
  const bounds = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  const worker = new Worker("/static/gcode-worker.js");
  worker.onmessage = (ev) => {
    const m = ev.data; if (disposed) return; const t0 = performance.now();
    try { onMsg(m); } finally { const dt = performance.now() - t0; T.msg += dt; T.maxMsg = Math.max(T.maxMsg, dt); }
  };
  const onMsg = (m) => {
    if (m.kind === "info") { if (m.simplified) $("#gcNote").textContent = `Large file: lines shorter than ${m.simplified} mm are joined in this preview so it stays smooth. The G-code itself is unchanged.`; return; }
    if (m.kind === "layers") {
      for (const d of m.layers) {
        addLayer(d);
        for (let i = 0; i < d.positions.length && !framed && layers.length < 4; i += 3) {   // rough bounds from the first layers
          bounds[0] = Math.min(bounds[0], d.positions[i]); bounds[1] = Math.min(bounds[1], d.positions[i + 1]);
          bounds[3] = Math.max(bounds[3], d.positions[i]); bounds[4] = Math.max(bounds[4], d.positions[i + 1]);
        }
      }
      if (!framed && layers.length >= 3) frame([bounds[0], bounds[1], 0, bounds[3], bounds[4], 20]);
      rg.max = Math.max(1, layers.length);
      if (m.total) { prog.value = Math.round(100 * m.done / m.total); $("#gcProgLbl").textContent = `Reading the G-code… ${prog.value}% (${layers.length} layers)`; }
      if (follow) show(layers.length, true); else show(cur, true);
    } else if (m.kind === "done") {
      streaming = false; clearTimeout(streamTimer); fileBytes = m.stats.bytes || m.bytes; marksUI(); progWrap.hidden = true; frame(m.stats.bounds); rg.max = Math.max(1, layers.length); if (follow) show(layers.length);
      window.__gcDone = { layers: m.layers, ms: m.ms, bytes: m.bytes, segments: m.stats.extrudeSegments + m.stats.travelSegments };
      const t = est.time || m.meta.time || "", g = est.grams ?? m.meta.filamentG, mm = est.mm ?? m.meta.filamentMm ?? m.stats.filamentMm;
      $("#gcEst").textContent = [t && `${t}`, g != null && `about ${g} g`, mm && `${(mm / 1000).toFixed(2)} m filament`].filter(Boolean).join(" · ");
      if (!m.layers) warn("No printed layers were found in this G-code.");
      worker.terminate();
    } else if (m.kind === "error") { progWrap.hidden = true; warn(`Preview unavailable: ${m.message}. The G-code download still works.`); worker.terminate(); }
  };
  worker.onerror = (e) => { progWrap.hidden = true; warn("Preview unavailable in this browser. The G-code download still works."); e.preventDefault?.(); };
  worker.postMessage({ url, touch: TOUCH });
  const stop = () => { clearInterval(timer); timer = null; const b = $("#gcPlay"); if (b) { b.textContent = "▶ Play"; b.setAttribute("aria-pressed", "false"); b.setAttribute("aria-label", "Play layers"); } };
  const user = (n) => { follow = n >= layers.length; show(n); };
  // ---- code panel: the layer's lines are read lazily with an HTTP Range request (offsets come from the parser), and only
  // the rows in view are in the DOM (virtual list), so a 240 MB file costs the same as a cube.
  let fileBytes = 0, codeLines = [], codeFor = -1, lastFetch = 0, codeTimer = null; const cache = new Map();
  const codeEl = $("#gcCode"), codeSp = $("#gcCodeSp"), codeBox = $("#gcCodeBox"), RH = 18, CAP = 4 << 20;
  if (matchMedia("(min-width: 601px)").matches) codeBox.open = true;   // collapsed on phones
  const codeSoon = () => {   // throttled: at most ~3 reads a second while the slider moves or Play runs
    if (!codeBox.open) return; clearTimeout(codeTimer);
    const wait = Math.max(0, 300 - (performance.now() - lastFetch)); codeTimer = setTimeout(loadCode, wait);
  };
  async function loadCode() {
    const i = cur - 1, L = layers[i]; if (!L || L.userData.byte == null || disposed) return;
    const end = layers[i + 1] ? layers[i + 1].userData.byte : fileBytes; if (!end) return;
    if (codeFor === i) return; lastFetch = performance.now();
    let txt = cache.get(i), cut = false;
    if (txt == null) {
      const s0 = L.userData.byte, e0 = Math.min(end, s0 + CAP); cut = e0 < end;
      try {
        const r = await fetch(url, { headers: { Range: `bytes=${s0}-${e0 - 1}` }, credentials: "same-origin" });
        if (!r.ok) throw new Error(r.status);
        let b = await r.arrayBuffer(); if (r.status === 200) b = b.slice(s0, e0);   // server ignored Range
        txt = new TextDecoder().decode(b); cache.set(i, txt); if (cache.size > 8) cache.delete(cache.keys().next().value);
      } catch { $("#gcCodeMsg").textContent = "Couldn't read this layer's G-code."; return; }
      if (cur - 1 !== i) return codeSoon();
    }
    codeFor = i; codeLines = txt.split("\n"); if (codeLines[codeLines.length - 1] === "") codeLines.pop();
    let hl = codeLines.findIndex(t => /^\s*G[0123]\b[^;]*E/.test(t)); window.__gcCodeHL = hl;
    $("#gcCodeSum").textContent = `G-code for layer ${i + 1}: lines ${L.userData.line + 1}–${L.userData.line + codeLines.length}`;
    $("#gcCodeMsg").textContent = cut ? "Very big layer: showing the first 4 MB of it." : "Highlighted: the first printing move of this layer.";
    codeSp.style.height = codeLines.length * RH + "px"; codeEl.dataset.hl = hl; codeEl.scrollTop = Math.max(0, (hl - 2) * RH); drawCode();
    window.__gcCode = { layer: i + 1, line: L.userData.line + 1, first: codeLines[0], count: codeLines.length };
  }
  function drawCode() {
    const top = codeEl.scrollTop, h = codeEl.clientHeight || 260, a = Math.max(0, Math.floor(top / RH) - 5), b = Math.min(codeLines.length, Math.ceil((top + h) / RH) + 5);
    const hl = +codeEl.dataset.hl, base = (layers[codeFor]?.userData.line || 0) + 1;
    codeEl.querySelectorAll(".r").forEach(e => e.remove());
    const frag = document.createDocumentFragment();
    for (let k = a; k < b; k++) { const d = document.createElement("div"); d.className = "r" + (k === hl ? " hl" : ""); d.style.top = k * RH + "px"; const n = document.createElement("b"); n.textContent = base + k; d.append(n, codeLines[k]); frag.appendChild(d); }
    codeEl.appendChild(frag);
  }
  codeEl.addEventListener("scroll", () => requestAnimationFrame(drawCode), { passive: true });
  codeBox.addEventListener("toggle", () => { if (codeBox.open) { codeFor = -1; codeSoon(); } });
  // ---- jump to a layer or a height (where a real print failed)
  const layerAtZ = (z) => { let k = layers.findIndex(L => L.userData.z >= z - 1e-3); return k < 0 ? layers.length : k + 1; };
  const go = (n, why) => { stop(); user(n); $("#gcJumpMsg").textContent = why || ""; codeBox.open = true; codeFor = -1; codeSoon(); };
  $("#gcJumpGo").onclick = () => {
    const v = parseFloat($("#gcJumpV").value); if (!(v >= 0) || !layers.length) { $("#gcJumpMsg").textContent = "Enter a number first."; return; }
    if ($("#gcJumpU").value === "layer") go(Math.round(v), `Layer ${Math.max(1, Math.min(layers.length, Math.round(v)))}.`);
    else { const n = layerAtZ(v); go(n, `${v} mm is printed in layer ${n} (Z ${layers[n - 1].userData.z.toFixed(2)} mm).`); }
  };
  $("#gcJumpV").addEventListener("keydown", e => { if (e.key === "Enter") $("#gcJumpGo").click(); });
  // ---- problem markers (heights from ZEIM's checks; the model sits on the bed so model height ~ print Z)
  const marks = (extra.markers || []).slice(0, 20); let marksHidden = false;
  function marksUI() {
    if (!marks.length || marksHidden) return;
    $("#gcMarks").hidden = false;
    $("#gcMarkList").innerHTML = marks.map((m, k) => `<li>${m.z == null ? `<span>⚠ ${esc(m.text)}</span>` :
      `<button type="button" class="btn gcmk" data-mk="${k}">⚠ ${m.z.toFixed(1)} mm · layer ${layerAtZ(m.z)}: ${esc(m.text)}</button>`}</li>`).join("");
    const N = Math.max(1, layers.length);
    $("#gcTicks").innerHTML = marks.filter(m => m.z != null).map(m => `<i style="left:${(100 * (layerAtZ(m.z) - 1) / Math.max(1, N - 1)).toFixed(2)}%"></i>`).join("");
    $("#gcMarkList").querySelectorAll("[data-mk]").forEach(b => b.onclick = () => { const m = marks[+b.dataset.mk], n = layerAtZ(m.z); go(n, `Layer ${n}: ${m.text}`); });
  }
  $("#gcMarksX").onclick = () => { marksHidden = true; $("#gcMarks").hidden = true; $("#gcTicks").innerHTML = ""; };
  // ---- pause at this layer: a NEW download with the firmware's pause command; the original link never changes
  const fw = extra.firmware || {}, pauses = new Set(), cmdSel = $("#gcPauseCmd");
  cmdSel.innerHTML = (fw.command ? "" : `<option value="">Choose your printer's command…</option>`) +
    Object.entries(fw.commands || { M600: "M600", M601: "M601", M0: "M0", PAUSE: "PAUSE" }).map(([c, l]) => `<option value="${esc(c)}"${c === fw.command ? " selected" : ""}>${esc(l)}</option>`).join("");
  var pauseUI = function () {
    const cmd = cmdSel.value, list = [...pauses].sort((a, b) => a - b);
    $("#gcPauseNote").textContent = (fw.note || "") + (cmd ? ` Using ${cmd}.` : "");
    $("#gcPauseList").innerHTML = list.map(n => `<li><span>⏸ Layer ${n}${layers[n - 1] ? ` · Z ${layers[n - 1].userData.z.toFixed(2)} mm` : ""} · ${esc(cmd || "no command yet")}</span><button type="button" class="btn" data-rm="${n}" aria-label="Remove pause at layer ${n}"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button></li>`).join("");
    $("#gcPauseList").querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { pauses.delete(+b.dataset.rm); pauseUI(); });
    const dl = $("#gcPauseDl"), ok = list.length && cmd && extra.pausedUrl;
    dl.hidden = !ok; if (ok) { dl.href = `${extra.pausedUrl}?layers=${list.join(",")}&cmd=${encodeURIComponent(cmd)}`; dl.textContent = `⬇ G-code with ${list.length} pause${list.length > 1 ? "s" : ""} (${cmd})`; }
    $("#gcPauseAdd").textContent = `⏸ Pause at layer ${cur || 1}`;
  };
  cmdSel.onchange = pauseUI;
  $("#gcPauseAdd").onclick = () => { if (!cmdSel.value) { $("#gcPauseNote").textContent = "Pick the pause command your printer understands first."; cmdSel.focus(); return; } if (pauses.size < 50) pauses.add(cur || 1); pauseUI(); };
  pauseUI();
  rg.addEventListener("input", () => { stop(); user(+rg.value); });
  $("#gcPrevL").onclick = () => { stop(); user(cur - 1); };
  $("#gcNextL").onclick = () => { stop(); user(cur + 1); };
  $("#gcPlay").onclick = (e) => {
    if (timer) return stop();
    if (cur >= layers.length) show(1);
    e.currentTarget.textContent = "⏸ Pause"; e.currentTarget.setAttribute("aria-pressed", "true"); e.currentTarget.setAttribute("aria-label", "Pause");
    const step = Math.max(1, Math.round(layers.length / 150));
    timer = setInterval(() => { if (cur >= layers.length) { stop(); follow = true; return; } show(cur + step); }, 60);
  };
  root.querySelectorAll("[data-gct]").forEach(cb => cb.addEventListener("change", () => { mats[cb.dataset.gct].visible = matsTop[cb.dataset.gct].visible = cb.checked; invalidate(); }));
  return function dispose() {
    disposed = true; stop(); ro.disconnect(); try { worker.postMessage({ cancel: true }); worker.terminate(); } catch {}
    for (const L of layers) L.geometry.dispose();
    for (const k in mats) { mats[k].dispose(); matsTop[k].dispose(); }
    controls.dispose(); renderer.dispose(); renderer.domElement.remove();
  };
}
