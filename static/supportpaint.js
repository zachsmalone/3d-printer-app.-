/* Paint-on supports: top-down brush on the bed. Green = need support (enforcer), red = never (blocker).
   Edit upgrade 10: adjustable tip size, shaft thickness, attachment height, support filament slot. */
let strokes = [];
let kind = "enforce";
let brushR = 4;
let tipR = 1.2;
let thickness = 2.5;
let attachZ = 0;
let filamentSlot = "same";
let dragging = false;
const MAX = 200;
const $ = (s, el = document) => el.querySelector(s);

export function getStrokes() { return strokes.slice(); }
export function clearStrokes() { strokes = []; if (mountPaint._redraw) mountPaint._redraw(); }

export function mountPaint(host) {
  if (!host) return;
  host.innerHTML = `
    <details class="spPaint" id="spPaintBox" open>
      <summary>Paint-on supports <small>(adjustable · not K1-tested)</small></summary>
      <p class="help">Brush where supports must grow (green) or must never grow (red). Set tip size, shaft thickness,
        attachment height, and which filament slot prints the supports (same as the model, or another slot e.g. PVA).
        ZEIM sends these as PrusaSlicer SupportEnforcer / SupportBlocker volumes.</p>
      <div class="row">
        <div class="segmented" role="group" aria-label="Brush kind">
          <button type="button" id="spPaintNeed" aria-pressed="true">Need support</button>
          <button type="button" id="spPaintNever" aria-pressed="false">Never support</button>
        </div>
        <button type="button" class="btn small" id="spPaintClear">Clear</button>
      </div>
      <div class="grid2" style="margin-top:6px">
        <label class="inl">Brush Ø <input type="range" id="spPaintR" min="1" max="12" step="0.5" value="4"> <span id="spPaintRlbl">4 mm</span></label>
        <label class="inl">Tip Ø <input type="range" id="spPaintTip" min="0.4" max="6" step="0.2" value="1.2"> <span id="spPaintTiplbl">1.2 mm</span></label>
        <label class="inl">Shaft Ø <input type="range" id="spPaintTh" min="1" max="10" step="0.5" value="2.5"> <span id="spPaintThlbl">2.5 mm</span></label>
        <label class="inl">Attach Z <input type="range" id="spPaintZ" min="0" max="80" step="1" value="0"> <span id="spPaintZlbl">0 mm</span></label>
      </div>
      <div class="field" style="margin-top:6px">
        <label for="spPaintSlot">Support filament</label>
        <select id="spPaintSlot">
          <option value="same">Same as print</option>
          <option value="2">Slot 2</option>
          <option value="3">Slot 3</option>
          <option value="4">Slot 4</option>
          <option value="5">Slot 5</option>
          <option value="pva">PVA (dissolve)</option>
          <option value="hips">HIPS</option>
        </select>
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
  $("#spPaintTip").oninput = () => { tipR = +$("#spPaintTip").value; $("#spPaintTiplbl").textContent = tipR + " mm"; };
  $("#spPaintTh").oninput = () => { thickness = +$("#spPaintTh").value; $("#spPaintThlbl").textContent = thickness + " mm"; };
  $("#spPaintZ").oninput = () => { attachZ = +$("#spPaintZ").value; $("#spPaintZlbl").textContent = attachZ + " mm"; };
  $("#spPaintSlot").onchange = () => { filamentSlot = $("#spPaintSlot").value; };
  $("#spPaintClear").onclick = () => clearStrokes();

  const bed = 220;
  const toMm = (cx, cy) => {
    const r = cvs.getBoundingClientRect();
    const x = ((cx - r.left) / r.width) * bed;
    const y = bed - ((cy - r.top) / r.height) * bed;
    return { x, y };
  };
  const add = (cx, cy) => {
    if (strokes.length >= MAX) return;
    const { x, y } = toMm(cx, cy);
    strokes.push({
      kind, x: +x.toFixed(2), y: +y.toFixed(2), z: attachZ,
      r: brushR, h: Math.max(8, 12), tip_r: tipR, thickness,
      filament_slot: filamentSlot,
    });
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
      // tip indicator
      const tr = ((s.tip_r || tipR) / bed) * cvs.width;
      ctx.beginPath(); ctx.arc(px, py, tr, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255,255,255,0.5)"; ctx.stroke();
    }
    const slots = {};
    for (const s of strokes) { const k = s.filament_slot || "same"; slots[k] = (slots[k] || 0) + 1; }
    const slotNote = Object.keys(slots).length ? " · slots: " + Object.entries(slots).map(([k, n]) => k + "×" + n).join(", ") : "";
    $("#spPaintCount").textContent = strokes.length + " stroke" + (strokes.length === 1 ? "" : "s")
      + (strokes.length ? ` · ${strokes.filter(s => s.kind === "enforce").length} need / ${strokes.filter(s => s.kind === "block").length} never` : "")
      + slotNote;
  };
  mountPaint._redraw = redraw;

  cvs.addEventListener("pointerdown", e => { dragging = true; cvs.setPointerCapture(e.pointerId); add(e.clientX, e.clientY); });
  cvs.addEventListener("pointermove", e => { if (dragging) add(e.clientX, e.clientY); });
  cvs.addEventListener("pointerup", () => { dragging = false; });
  cvs.addEventListener("pointercancel", () => { dragging = false; });
  redraw();
}
