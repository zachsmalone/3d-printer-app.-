/* Paint-on supports: top-down brush on the bed. Green = need support (enforcer), red = never (blocker).
   Strokes go to POST /api/slice as support_paint JSON. Not a real-iPhone / K1 test. */
import { $ } from "/static/app.js";

const MAX = 200;
let strokes = [];
let kind = "enforce";
let brushR = 4;
let dragging = false;

export function getStrokes() { return strokes.slice(); }
export function clearStrokes() { strokes = []; if (mountPaint._redraw) mountPaint._redraw(); }

export function mountPaint(host) {
  if (!host) return;
  host.innerHTML = `
    <details class="spPaint" id="spPaintBox">
      <summary>Paint-on supports <small>(not K1-tested)</small></summary>
      <p class="help">Brush where supports must grow (green) or must never grow (red). ZEIM sends these as PrusaSlicer
        SupportEnforcer / SupportBlocker volumes. Approximate cylinders — not the same as painting on every triangle in PrusaSlicer.</p>
      <div class="row">
        <div class="segmented" role="group" aria-label="Brush kind">
          <button type="button" id="spPaintNeed" aria-pressed="true">Need support</button>
          <button type="button" id="spPaintNever" aria-pressed="false">Never support</button>
        </div>
        <label class="inl">Brush <input type="range" id="spPaintR" min="1" max="12" step="0.5" value="4"> <span id="spPaintRlbl">4 mm</span></label>
        <button type="button" class="btn small" id="spPaintClear">Clear</button>
      </div>
      <canvas id="spPaintCvs" width="280" height="280" aria-label="Top-down support paint"></canvas>
      <p class="help" id="spPaintCount" aria-live="polite">0 strokes</p>
    </details>`;
  const cvs = $("#spPaintCvs"), ctx = cvs.getContext("2d");
  const setKind = k => {
    kind = k;
    $("#spPaintNeed").setAttribute("aria-pressed", k === "enforce");
    $("#spPaintNever").setAttribute("aria-pressed", k === "block");
  };
  $("#spPaintNeed").onclick = () => setKind("enforce");
  $("#spPaintNever").onclick = () => setKind("block");
  $("#spPaintR").oninput = () => { brushR = +$("#spPaintR").value; $("#spPaintRlbl").textContent = brushR + " mm"; };
  $("#spPaintClear").onclick = () => clearStrokes();

  const bed = 220; // visual bed mm; strokes stored in mm matching this square
  const toMm = (cx, cy) => {
    const r = cvs.getBoundingClientRect();
    const x = ((cx - r.left) / r.width) * bed;
    const y = bed - ((cy - r.top) / r.height) * bed;
    return { x, y };
  };
  const add = (cx, cy) => {
    if (strokes.length >= MAX) return;
    const { x, y } = toMm(cx, cy);
    strokes.push({ kind, x: +x.toFixed(2), y: +y.toFixed(2), z: 0, r: brushR, h: 8 });
    redraw();
  };
  const redraw = () => {
    ctx.fillStyle = "#1a1a1a"; ctx.fillRect(0, 0, cvs.width, cvs.height);
    ctx.strokeStyle = "#444"; ctx.strokeRect(0.5, 0.5, cvs.width - 1, cvs.height - 1);
    for (const s of strokes) {
      const px = (s.x / bed) * cvs.width, py = cvs.height - (s.y / bed) * cvs.height;
      const pr = (s.r / bed) * cvs.width;
      ctx.beginPath(); ctx.arc(px, py, pr, 0, Math.PI * 2);
      ctx.fillStyle = s.kind === "enforce" ? "rgba(80,200,80,0.55)" : "rgba(220,80,80,0.55)";
      ctx.fill();
    }
    $("#spPaintCount").textContent = strokes.length + " stroke" + (strokes.length === 1 ? "" : "s")
      + (strokes.length ? ` · ${strokes.filter(s => s.kind === "enforce").length} need / ${strokes.filter(s => s.kind === "block").length} never` : "");
  };
  // expose for clearStrokes
  mountPaint._redraw = redraw;

  cvs.addEventListener("pointerdown", e => { dragging = true; cvs.setPointerCapture(e.pointerId); add(e.clientX, e.clientY); });
  cvs.addEventListener("pointermove", e => { if (dragging) add(e.clientX, e.clientY); });
  cvs.addEventListener("pointerup", () => { dragging = false; });
  cvs.addEventListener("pointercancel", () => { dragging = false; });
  redraw();
}

