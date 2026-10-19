import * as THREE from "three";
import { OrbitControls } from "/static/vendor/OrbitControls.js";
import { backlitColors } from "/static/lithlight.js";

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
    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    const loop = () => { requestAnimationFrame(loop); this.controls.update(); this.renderer.render(this.scene, this.camera); };
    loop();
  }
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
      const mesh = new THREE.Mesh(gg, m); mesh.userData.object = b.object ?? null; this.group.add(mesh);
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
    for (const m of this.group.children) {
      if (!m.userData.lit) m.userData.lit = m.material;
      if (m.material !== m.userData.lit) m.material.dispose();          // drop the previous backlit material (colour change / off)
      if (!on) { m.material = m.userData.lit; m.material.wireframe = this.wire; continue; }
      const pos = m.geometry.getAttribute("position");
      m.geometry.setAttribute("color", new THREE.BufferAttribute(backlitColors(pos.array, shape, light), 3));
      m.material = new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide, wireframe: this.wire });
    }
  }
  toggleWire() { this.wire = !this.wire; this.group.children.forEach(m => { m.material.wireframe = this.wire; if (m.userData.lit) m.userData.lit.wireframe = this.wire; }); }
}
