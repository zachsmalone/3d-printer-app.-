/* Paint-on supports on the model that is already on screen.
   Left drag / one finger paints. Right drag orbits. Scroll or two fingers zoom.
   Green = need support (enforcer), red = never (blocker). Erase removes marks under the brush.
   The mesh material is not replaced. Marks are drawn on the surface itself, so they
   cannot float in the air or spill past the silhouette. The slicer still builds a
   vertical column at the hit, which is a different shape from this patch. */
import * as THREE from "three";

let strokes = [];
let kind = "enforce";
let brushR = 4;
let tipR = 1.2;
let thickness = 2.5;
let filamentSlot = "same";
let armed = false;
let painting = false;
let viewer = null;
let getProjectId = () => null;
let onStale = () => {};
const MAX = 200;
const $ = (s, el = document) => el.querySelector(s);
const savedButtons = { mouse: null, touch: null };

export function getStrokes() { return strokes.filter(s => s.kind === "enforce" || s.kind === "block").map(s => ({ ...s })); }
export function clearStrokes() { strokes = []; drawMarks(); saveSoon(); }

export function bindViewer(v) { viewer = v; listen(); drawMarks(); }
export function bindProject(fn) { getProjectId = fn; }

export function setStrokes(next, opts = {}) {
  strokes = (next || []).map(s => ({ ...s }));
  drawMarks();
  if (opts.stale) onStale();
  const n = $("#spPaintCount");
  if (n) n.textContent = countText();
}

function countText() {
  const need = strokes.filter(s => s.kind === "enforce").length;
  const never = strokes.filter(s => s.kind === "block").length;
  return strokes.length + " mark" + (strokes.length === 1 ? "" : "s")
    + (strokes.length ? ` · ${need} need / ${never} never` : "");
}

function arm(on) {
  armed = on;
  const btn = $("#spPaintArm");
  if (btn) btn.setAttribute("aria-pressed", on ? "true" : "false");
  const el = viewer && viewer.renderer && viewer.renderer.domElement;
  if (!el || !viewer.controls) return;
  if (!savedButtons.mouse) {
    savedButtons.mouse = { ...viewer.controls.mouseButtons };
    savedButtons.touch = { ...viewer.controls.touches };
  }
  if (on) {
    viewer.controls.mouseButtons.LEFT = -1;
    viewer.controls.mouseButtons.RIGHT = 0; // ROTATE, so orbit stays available
    viewer.controls.touches.ONE = -1;
    el.style.cursor = "crosshair";
  } else {
    Object.assign(viewer.controls.mouseButtons, savedButtons.mouse);
    Object.assign(viewer.controls.touches, savedButtons.touch);
    el.style.cursor = "";
    hideCursor();
  }
}

function modelMeshes() {
  if (!viewer) return [];
  return viewer.group.children.filter(o => o.isMesh && !o.userData.bed && !o.userData.paint);
}

export function raycastModel(v, ev) {
  const rect = v.renderer.domElement.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const ndc = new THREE.Vector2(
    ((ev.clientX - rect.left) / rect.width) * 2 - 1,
    -((ev.clientY - rect.top) / rect.height) * 2 + 1
  );
  const rc = new THREE.Raycaster();
  rc.setFromCamera(ndc, v.camera);
  const meshes = v.group.children.filter(o => o.isMesh && !o.userData.bed && !o.userData.paint);
  const hit = rc.intersectObjects(meshes, false)[0];
  if (!hit || !hit.object) return null;
  const local = hit.object.worldToLocal(hit.point.clone());
  const normal = hit.face ? hit.face.normal.clone().transformDirection(hit.object.matrixWorld).normalize() : new THREE.Vector3(0, 0, 1);
  return { local, normal, object: hit.object };
}

const STROKE_CAP = 64;

function clearLegacyDiscs() {
  const g = viewer && viewer.scene.getObjectByName("zeim-support-paint");
  if (!g) return;
  viewer.scene.remove(g);
  g.traverse(o => {
    if (o.geometry) o.geometry.dispose();
    if (o.material) o.material.dispose();
  });
}

function paintMaterial() {
  const data = new Float32Array(STROKE_CAP * 3 * 4);
  const tex = new THREE.DataTexture(data, STROKE_CAP, 3, THREE.RGBAFormat, THREE.FloatType);
  tex.magFilter = THREE.NearestFilter;
  tex.minFilter = THREE.NearestFilter;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.generateMipmaps = false;
  tex.flipY = false;
  if (THREE.NoColorSpace) tex.colorSpace = THREE.NoColorSpace;
  tex.needsUpdate = true;
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    depthTest: true,
    toneMapped: false,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
    uniforms: {
      strokeTex: { value: tex },
      cursor: { value: new THREE.Vector4(0, 0, 0, -1) },
      cursorN: { value: new THREE.Vector3(0, 0, 1) },
      cursorColor: { value: new THREE.Color(0x00e676) },
    },
    vertexShader: `
      varying vec3 vLocal;
      void main() {
        vLocal = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      varying vec3 vLocal;
      uniform sampler2D strokeTex;
      uniform vec4 cursor;
      uniform vec3 cursorN;
      uniform vec3 cursorColor;
      bool onFace(vec3 p, vec3 n, float r) {
        vec3 d = vLocal - p;
        float along = dot(d, n);
        vec3 planar = d - n * along;
        return abs(along) < 0.6 && dot(planar, planar) <= r * r;
      }
      void main() {
        vec3 col = vec3(0.0);
        float a = 0.0;
        for (int i = 0; i < ${STROKE_CAP}; i++) {
          float u = (float(i) + 0.5) / ${STROKE_CAP}.0;
          vec4 s = texture2D(strokeTex, vec2(u, 0.1667));
          if (s.w <= 0.0) continue;
          vec3 n = texture2D(strokeTex, vec2(u, 0.5)).xyz;
          if (onFace(s.xyz, n, s.w)) {
            col = texture2D(strokeTex, vec2(u, 0.8333)).rgb;
            a = 0.86;
          }
        }
        if (cursor.w > 0.0 && onFace(cursor.xyz, cursorN, cursor.w)) {
          vec3 d = vLocal - cursor.xyz;
          float along = dot(d, cursorN);
          float planar = length(d - cursorN * along);
          float band = max(0.35, cursor.w * 0.12);
          if (planar <= cursor.w && planar >= cursor.w - band) {
            col = cursorColor;
            a = 0.96;
          }
        }
        if (a < 0.02) discard;
        gl_FragColor = vec4(col, a);
      }
    `,
  });
  mat.userData.strokeData = data;
  mat.userData.strokeTex = tex;
  return mat;
}

function writeStrokes(mat, list) {
  const data = mat.userData.strokeData;
  data.fill(0);
  const slice = list.slice(-STROKE_CAP);
  slice.forEach((s, i) => {
    const o = i * 4;
    data[o] = s.x;
    data[o + 1] = s.y;
    data[o + 2] = s.z;
    data[o + 3] = Math.max(0.2, +s.r || 0);
    const nrm = (STROKE_CAP + i) * 4;
    const nx = +s.nx || 0, ny = +s.ny || 0, nz = s.nz == null ? 1 : +s.nz;
    const len = Math.hypot(nx, ny, nz) || 1;
    data[nrm] = nx / len;
    data[nrm + 1] = ny / len;
    data[nrm + 2] = nz / len;
    data[nrm + 3] = 1;
    const c = (STROKE_CAP * 2 + i) * 4;
    const col = s.kind === "block" ? [1, 0.0902, 0.2667] : [0, 0.902, 0.4627];
    data[c] = col[0];
    data[c + 1] = col[1];
    data[c + 2] = col[2];
    data[c + 3] = 1;
  });
  mat.userData.strokeTex.needsUpdate = true;
}

function ensureOverlays() {
  clearLegacyDiscs();
  modelMeshes().forEach((host, meshIndex) => {
    let ov = host.getObjectByName("zeim-paint-overlay");
    if (!ov) {
      ov = new THREE.Mesh(host.geometry, paintMaterial());
      ov.name = "zeim-paint-overlay";
      ov.userData.paint = true;
      ov.raycast = () => {};
      ov.renderOrder = 5;
      host.add(ov);
    }
    const mine = strokes.filter(s => (s.mesh || 0) === meshIndex && (s.kind === "enforce" || s.kind === "block"));
    writeStrokes(ov.material, mine);
  });
}

function hideCursor() {
  if (!viewer) return;
  modelMeshes().forEach(host => {
    const ov = host.getObjectByName("zeim-paint-overlay");
    if (ov) ov.material.uniforms.cursor.value.set(0, 0, 0, -1);
  });
}

function drawMarks() {
  if (!viewer) return;
  ensureOverlays();
  const n = $("#spPaintCount");
  if (n) n.textContent = countText();
}

function moveCursor(hit) {
  if (!viewer) return;
  ensureOverlays();
  const hex = kind === "block" ? 0xff1744 : kind === "erase" ? 0xffffff : 0x00e676;
  modelMeshes().forEach(host => {
    const ov = host.getObjectByName("zeim-paint-overlay");
    if (!ov) return;
    const u = ov.material.uniforms.cursor.value;
    if (!hit || !armed || hit.object !== host) {
      u.set(0, 0, 0, -1);
      return;
    }
    u.set(hit.local.x, hit.local.y, hit.local.z, Math.max(brushR, 0.8));
    ov.material.uniforms.cursorN.value.copy(hit.normal).normalize();
    ov.material.uniforms.cursorColor.value.setHex(hex);
  });
}

let saveTimer = 0;
function saveSoon() {
  const id = getProjectId && getProjectId();
  if (!id) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch("/api/edit/" + encodeURIComponent(id) + "/support-paint", {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strokes: getStrokes() }),
    }).catch(() => {});
  }, 300);
}

function paintAt(hit) {
  if (!hit) return;
  const p = hit.local, n = hit.normal;
  if (kind === "erase") {
    const before = strokes.length;
    strokes = strokes.filter(s => {
      const dx = s.x - p.x, dy = s.y - p.y, dz = s.z - p.z;
      return Math.hypot(dx, dy, dz) > brushR;
    });
    if (strokes.length !== before) { drawMarks(); saveSoon(); }
    return;
  }
  if (strokes.length >= MAX) return;
  const last = strokes[strokes.length - 1];
  if (last && last.kind === kind && Math.hypot(last.x - p.x, last.y - p.y, last.z - p.z) < brushR * 0.45) return;
  const meshes = modelMeshes();
  strokes.push({
    kind, x: +p.x.toFixed(3), y: +p.y.toFixed(3), z: +p.z.toFixed(3),
    nx: +n.x.toFixed(3), ny: +n.y.toFixed(3), nz: +n.z.toFixed(3),
    r: brushR, h: Math.max(4, brushR * 2), tip_r: tipR, thickness,
    filament_slot: filamentSlot, mesh: Math.max(0, meshes.indexOf(hit.object)),
  });
  drawMarks();
}

let listening = false;
function listen() {
  if (listening || !viewer) return;
  const el = viewer.renderer.domElement;
  el.addEventListener("pointerdown", e => {
    if (!armed || e.button !== 0) return;
    if (e.pointerType === "touch" && e.isPrimary === false) return;
    const hit = raycastModel(viewer, e);
    if (!hit) return;
    painting = true;
    el.setPointerCapture(e.pointerId);
    paintAt(hit);
    moveCursor(hit);
  });
  el.addEventListener("pointermove", e => {
    if (!armed) return;
    const hit = raycastModel(viewer, e);
    moveCursor(hit);
    if (painting) paintAt(hit);
  });
  const up = () => { if (painting) { painting = false; saveSoon(); } };
  el.addEventListener("pointerup", up);
  el.addEventListener("pointercancel", up);
  listening = true;
}

export function mountPaint(host) {
  if (host) {
    host.innerHTML = `<p class="help" id="spPaintNote">Paint tools stay on the model, including after this panel closes. The colour is a flat patch on the face. Slice builds a vertical column at that point (shaft and tip). The column is not cut to the face.</p>`;
  }
  const viewerEl = document.getElementById("editViewer");
  let dock = document.getElementById("spPaintDock");
  if (!dock) {
    dock = document.createElement("div");
    dock.id = "spPaintDock";
    dock.className = "sp-dock";
    (viewerEl || host || document.body).appendChild(dock);
  }
  dock.innerHTML = `
    <p class="help" id="spPaintLead">Drag on the surface while Paint is on. The colour stays on the model. Slice builds a vertical column here (shaft and tip below), not this flat patch, and that column is not cut to the face.</p>
    <div class="row">
      <div class="segmented" role="group" aria-label="Brush kind">
        <button type="button" id="spPaintNeed" aria-pressed="true">Need support</button>
        <button type="button" id="spPaintNever" aria-pressed="false">Never support</button>
        <button type="button" id="spPaintErase" aria-pressed="false">Erase</button>
      </div>
      <button type="button" class="btn small" id="spPaintArm" aria-pressed="false">Paint</button>
      <button type="button" class="btn small" id="spPaintClear">Clear</button>
    </div>
    <details class="spPaint" id="spPaintBox">
      <summary>Brush column</summary>
      <div class="grid2" style="margin-top:6px">
        <label class="inl">Brush radius <input type="range" id="spPaintR" min="1" max="12" step="0.5" value="4"> <span id="spPaintRlbl">4 mm</span></label>
        <label class="inl">Tip radius <input type="range" id="spPaintTip" min="0.4" max="6" step="0.2" value="1.2"> <span id="spPaintTiplbl">1.2 mm</span></label>
        <label class="inl">Shaft radius <input type="range" id="spPaintTh" min="1" max="10" step="0.5" value="2.5"> <span id="spPaintThlbl">2.5 mm</span></label>
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
      <p class="help">Brush radius is the patch you see. Tip and shaft are the column PrusaSlicer receives. The column stands upright through the mark and can extend past the silhouette.</p>
    </details>
    <p class="help" id="spPaintCount" aria-live="polite">0 marks</p>`;
  const setKind = k => {
    kind = k;
    $("#spPaintNeed").setAttribute("aria-pressed", k === "enforce" ? "true" : "false");
    $("#spPaintNever").setAttribute("aria-pressed", k === "block" ? "true" : "false");
    $("#spPaintErase").setAttribute("aria-pressed", k === "erase" ? "true" : "false");
    arm(true);
  };
  $("#spPaintNeed").onclick = () => setKind("enforce");
  $("#spPaintNever").onclick = () => setKind("block");
  $("#spPaintErase").onclick = () => setKind("erase");
  $("#spPaintArm").onclick = () => arm(!armed);
  $("#spPaintR").oninput = () => { brushR = +$("#spPaintR").value; $("#spPaintRlbl").textContent = brushR + " mm"; };
  $("#spPaintTip").oninput = () => { tipR = +$("#spPaintTip").value; $("#spPaintTiplbl").textContent = tipR + " mm"; };
  $("#spPaintTh").oninput = () => { thickness = +$("#spPaintTh").value; $("#spPaintThlbl").textContent = thickness + " mm"; };
  $("#spPaintSlot").onchange = () => { filamentSlot = $("#spPaintSlot").value; };
  $("#spPaintClear").onclick = () => clearStrokes();
  onStale = () => {
    const n = $("#spPaintCount");
    if (n) n.textContent = "Paint was cleared because the model changed. Paint the new shape.";
  };
  listen();
  drawMarks();
  arm(armed);
}
