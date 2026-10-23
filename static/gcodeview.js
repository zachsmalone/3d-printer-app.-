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
    <fieldset class="gclegend"><legend>Show</legend><div id="gcLegend">${GC_TYPES.map(([k, n, c]) =>
      `<label class="gcchip"><input type="checkbox" data-gct="${k}"${k === "travel" ? "" : " checked"}><span class="sw" style="background:${c}" aria-hidden="true"></span>${n}</label>`).join("")}</div></fieldset>
    <p class="help" id="gcNote"></p>
    <p class="help warn" id="gcWarn" hidden></p>
  </section>`;
}

/* url: G-code URL. est: {time, grams, mm} from the slice reply (optional). Returns a dispose() function. */
export function wireGcodePreview(url, est = {}) {
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
  }
  function addLayer(d) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(d.positions, 3));
    d.groups.forEach((g, i) => geo.addGroup(g.start, g.count, i));
    const ls = new THREE.LineSegments(geo, d.groups.map(g => mats[g.type]));
    ls.userData = { z: d.z, height: d.height, groups: d.groups }; ls.matrixAutoUpdate = false; ls.frustumCulled = false;
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
      streaming = false; clearTimeout(streamTimer); progWrap.hidden = true; frame(m.stats.bounds); rg.max = Math.max(1, layers.length); if (follow) show(layers.length);
      window.__gcDone = { layers: m.layers, ms: m.ms, bytes: m.bytes, segments: m.stats.extrudeSegments + m.stats.travelSegments };
      const t = est.time || m.meta.time || "", g = est.grams ?? m.meta.filamentG, mm = est.mm ?? m.meta.filamentMm ?? m.stats.filamentMm;
      $("#gcEst").textContent = [t && `⏱ ${t}`, g != null && `🧵 about ${g} g`, mm && `${(mm / 1000).toFixed(2)} m filament`].filter(Boolean).join(" · ");
      if (!m.layers) warn("No printed layers were found in this G-code.");
      worker.terminate();
    } else if (m.kind === "error") { progWrap.hidden = true; warn(`Preview unavailable: ${m.message}. The G-code download still works.`); worker.terminate(); }
  };
  worker.onerror = (e) => { progWrap.hidden = true; warn("Preview unavailable in this browser. The G-code download still works."); e.preventDefault?.(); };
  worker.postMessage({ url, touch: TOUCH });
  const stop = () => { clearInterval(timer); timer = null; const b = $("#gcPlay"); if (b) { b.textContent = "▶ Play"; b.setAttribute("aria-pressed", "false"); b.setAttribute("aria-label", "Play layers"); } };
  const user = (n) => { follow = n >= layers.length; show(n); };
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
