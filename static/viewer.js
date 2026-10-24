import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";
import { backlitColors, lightRGB } from "/static/lithlight.js";
const SOLID_PART = /^(stand|base|lid|frame|post|rail)/;   // non-lithophane parts: shown solid, never glowing

const b64 = (s, T) => { const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new T(u.buffer); };

export class Viewer {
  constructor(el) {
    this.el = el;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    el.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
    this.camera.up.set(0, 0, 1);               // Z is "up" (print axis)
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x334055, 1.1));
    const d = new THREE.DirectionalLight(0xffffff, 2.0); d.position.set(-1, -1.5, 2); this.scene.add(d);
    const d2 = new THREE.DirectionalLight(0x88aaff, 0.6); d2.position.set(2, 1, 1); this.scene.add(d2);
    this.group = new THREE.Group(); this.scene.add(this.group);
    this.wire = false;
    this._controlsFrozen = false;   // plate drag: skip controls.update so orbit damping can't move the camera mid-drag
    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    const loop = () => { requestAnimationFrame(loop); if (!this._controlsFrozen) this.controls.update(); this.renderer.render(this.scene, this.camera); };
    loop();
  }
  /* Freeze orbit/pan/zoom (and kill in-flight damping) while the plate editor drags an object on the bed. */
  freezeControls() { this._controlsFrozen = true; this.controls.enabled = false; }
  unfreezeControls() { this._controlsFrozen = false; this.controls.enabled = true; }
  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  load(preview, mode, opts = {}) {
    this.group.clear();
    for (const b of preview.bodies) {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(b64(b.positions, Float32Array), 3));
      g.setIndex(new THREE.BufferAttribute(b64(b.indices, Uint32Array), 1));
      const gg = opts.flat ? g.toNonIndexed() : g;
      gg.computeVertexNormals();
      const color = b.color || (mode === "lithophane" ? "#f2ead8" : "#8fb0e0");
      const m = new THREE.MeshStandardMaterial({ color, roughness: 0.65, metalness: 0.05, flatShading: false, wireframe: this.wire });
      const mesh = new THREE.Mesh(gg, m); mesh.userData.object = b.object ?? null; mesh.userData.name = b.name || ""; this.group.add(mesh);
    }
    this.backlit = false; this.scene.background = null;
    if (!opts.keepCamera) this.reset();
  }
  reset() {
    const box = new THREE.Box3().setFromObject(this.group);
    if (box.isEmpty()) return;
    const c = box.getCenter(new THREE.Vector3()), s = box.getSize(new THREE.Vector3());
    const r = Math.max(s.x, s.y) * 0.9 + s.z;
    this.camera.position.set(c.x, c.y - r * 1.1, c.z + r * 0.9);
    this.camera.far = r * 20; this.camera.updateProjectionMatrix();
    this.controls.target.copy(c); this.controls.update();
  }
  /* Turn left / right buttons (a keyboard- and touch-friendly alternative to dragging): spin the camera round the model's centre (Z is up here). */
  turn(deg) {
    const t = this.controls.target, v = this.camera.position.clone().sub(t), a = deg * Math.PI / 180, c = Math.cos(a), sn = Math.sin(a);
    this.camera.position.set(t.x + v.x * c - v.y * sn, t.y + v.x * sn + v.y * c, t.z + v.z); this.controls.update();
  }
  /* "Light on": the lithophane as if lit from behind (per-vertex colour from wall thickness, unlit material on a dark backdrop). */
  setBacklight(on, shape = "rect", light = "warm") {
    this.backlit = on;
    this.scene.background = on ? new THREE.Color(0x0b0d12) : null;
    let box = null;
    if (on && shape === "memorybox") { const b = new THREE.Box3().setFromObject(this.group); box = { lo: b.min.toArray(), hi: b.max.toArray() }; }
    for (const m of this.group.children) {
      if (!m.userData.lit) m.userData.lit = m.material;
      if (m.material !== m.userData.lit) m.material.dispose();          // drop the previous backlit material (colour change / off)
      if (!on || SOLID_PART.test(m.userData.name || "")) { m.material = m.userData.lit; m.material.wireframe = this.wire; continue; }   // stands / bases / lids stay opaque
      const pos = m.geometry.getAttribute("position");
      m.geometry.setAttribute("color", new THREE.BufferAttribute(backlitColors(pos.array, shape, "white", undefined, undefined, box), 3));   // shade once
      m.material = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, wireframe: this.wire });
      m.material.color.setRGB(...lightRGB(light));                                   // light colour = material tint (effects change it in place)
    }
  }
  /* LED effects: retint the backlit materials in place each frame (no new materials, no geometry upload) */
  setTint(rgb) { if (!this.backlit) return; for (const m of this.group.children) if (m.material !== m.userData.lit) m.material.color.setRGB(rgb[0], rgb[1], rgb[2]); }
  toggleWire() { this.wire = !this.wire; this.group.children.forEach(m => { m.material.wireframe = this.wire; if (m.userData.lit) m.userData.lit.wireframe = this.wire; }); }

  /* Colour problem faces (print check): highlights = {faces:[{face,category}], colors:{overhang:[r,g,b], thin:[..], ok:[..]}} */
  setProblemHighlights(highlights) {
    this.clearProblemHighlights();
    if (!highlights || !highlights.faces || !highlights.faces.length) return;
    const colors = highlights.colors || {};
    const colOf = (c) => {
      const rgb = colors[c] || (c === "thin" ? [1, 0.2, 0.35] : c === "overhang" ? [1, 0.55, 0.1] : [0.56, 0.69, 0.88]);
      return rgb;
    };
    const map = new Map();
    for (const f of highlights.faces) map.set(f.face | 0, f.category);
    for (const mesh of this.group.children) {
      if (!mesh.isMesh) continue;
      const geom = mesh.geometry;
      const idx = geom.getIndex();
      const pos = geom.getAttribute("position");
      if (!pos) continue;
      // Build per-vertex colours from face categories (non-indexed or indexed)
      const nVert = pos.count;
      const cols = new Float32Array(nVert * 3);
      const ok = colOf("ok");
      for (let i = 0; i < nVert; i++) { cols[i*3]=ok[0]; cols[i*3+1]=ok[1]; cols[i*3+2]=ok[2]; }
      const paintFace = (fi, a, b, c) => {
        const cat = map.get(fi); if (!cat || cat === "ok") return;
        const rgb = colOf(cat);
        for (const vi of [a, b, c]) { cols[vi*3]=rgb[0]; cols[vi*3+1]=rgb[1]; cols[vi*3+2]=rgb[2]; }
      };
      if (idx) {
        const nFaces = (idx.count / 3) | 0;
        for (let fi = 0; fi < nFaces; fi++) paintFace(fi, idx.getX(fi*3), idx.getX(fi*3+1), idx.getX(fi*3+2));
      } else {
        const nFaces = (nVert / 3) | 0;
        for (let fi = 0; fi < nFaces; fi++) paintFace(fi, fi*3, fi*3+1, fi*3+2);
      }
      geom.setAttribute("color", new THREE.BufferAttribute(cols, 3));
      if (!mesh.userData._problemMatBackup) mesh.userData._problemMatBackup = mesh.material;
      mesh.material = new THREE.MeshStandardMaterial({
        vertexColors: true, roughness: 0.65, metalness: 0.05, wireframe: this.wire, side: THREE.DoubleSide
      });
      mesh.userData._problemColored = true;
    }
    // Thin-point markers
    const pts = highlights.thin_points || [];
    if (pts.length && !this._thinGroup) {
      this._thinGroup = new THREE.Group(); this.scene.add(this._thinGroup);
    }
    if (this._thinGroup) {
      while (this._thinGroup.children.length) {
        const c = this._thinGroup.children.pop();
        c.geometry?.dispose(); c.material?.dispose();
      }
      for (const p of pts) {
        if (!p.at) continue;
        const s = new THREE.Mesh(
          new THREE.SphereGeometry(0.6, 10, 8),
          new THREE.MeshBasicMaterial({ color: 0xff3366, depthTest: false })
        );
        s.position.set(p.at[0], p.at[1], p.at[2]); s.renderOrder = 10;
        this._thinGroup.add(s);
      }
    }
  }
  clearProblemHighlights() {
    for (const mesh of this.group.children) {
      if (!mesh.userData._problemColored) continue;
      if (mesh.material && mesh.material !== mesh.userData._problemMatBackup) mesh.material.dispose();
      if (mesh.userData._problemMatBackup) mesh.material = mesh.userData._problemMatBackup;
      mesh.geometry.deleteAttribute("color");
      mesh.userData._problemColored = false;
    }
    if (this._thinGroup) {
      while (this._thinGroup.children.length) {
        const c = this._thinGroup.children.pop();
        c.geometry?.dispose(); c.material?.dispose();
      }
    }
  }
}

