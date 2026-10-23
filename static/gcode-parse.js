/* ZEIM G-code parser (written for ZEIM, MIT-compatible, no third-party code). Plain script: loaded by the
   Web Worker (importScripts) and by node tests (require). Streams: push(text) any number of times, then end().
   Handles G0/G1, G2/G3 arcs (I/J or R, split into short chords), G90/G91, M82/M83, G92, G20/G21,
   PrusaSlicer ;TYPE: comments (plus Cura/Orca names). A new layer starts on the first EXTRUDING move at a new Z,
   so z-hops and travel moves never count as layers. Output per layer: positions (Float32 x,y,z pairs) grouped by type. */
(function (root) {
  "use strict";
  const TYPES = ["outer", "inner", "infill", "solid", "support", "skirt", "other", "travel"];
  const TYPE_INDEX = Object.fromEntries(TYPES.map((t, i) => [t, i]));
  function typeOf(name) {
    const s = name.trim().toLowerCase();
    if (/external perimeter|overhang perimeter|wall-outer|outer wall/.test(s)) return "outer";
    if (/perimeter|wall-inner|inner wall|^wall/.test(s)) return "inner";
    if (/solid infill|top solid|bridge infill|gap fill|^skin|bottom surface|top surface|ironing/.test(s)) return "solid";
    if (/infill|^fill/.test(s)) return "infill";
    if (/support/.test(s)) return "support";
    if (/skirt|brim/.test(s)) return "skirt";
    return "other";
  }

  function utf8Len(s) { let n = 0; for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); n += c < 0x80 ? 1 : c < 0x800 ? 2 : (c >= 0xd800 && c < 0xdc00) ? (i++, 4) : 3; } return n; }
  class GcodeParser {
    constructor(opts = {}) {
      this.onLayer = opts.onLayer || (() => {});
      this.arcSegLen = opts.arcSegLen || 0.5;  // mm per chord
      // big files: join tiny consecutive pieces of the same line until they are at least minSegLen long (0 = keep all)
      this.minSegLen = opts.minSegLen || 0; this.pend = null;
      this.x = 0; this.y = 0; this.z = 0; this.e = 0;
      this.absXYZ = true; this.absE = true; this.unit = 1;
      this.type = "other"; this.rest = "";
      this.layer = null; this.layerCount = 0; this.lastLayerZ = null;
      this.stats = { lines: 0, moves: 0, extrudeSegments: 0, travelSegments: 0, filamentMm: 0, bounds: [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity] };
      this.meta = {};  // estimated time / filament read from slicer comments
      // code panel: byte + line offset of each layer's first line (the ;LAYER_CHANGE / Z lift before it when there is one)
      this.byte = 0; this.lineNo = 0; this.curByte = 0; this.curLine = 0; this.mark = null;
    }
    _newLayer(z) {
      this._flush();
      const at = this.mark || { byte: this.curByte, line: this.curLine }; this.mark = null;
      this.layer = { index: this.layerCount++, z, byte: at.byte, line: at.line, buf: TYPES.map(() => []), filamentMm: 0, height: this.lastLayerZ == null ? z : z - this.lastLayerZ };
      this.lastLayerZ = z;
    }
    _flush() {
      const L = this.layer; if (!L) return;
      this._emitPend();
      let total = 0; for (const b of L.buf) total += b.length;
      const pos = new Float32Array(total), groups = [];
      let o = 0;
      L.buf.forEach((b, i) => { if (!b.length) return; pos.set(b, o); groups.push({ type: TYPES[i], start: o / 3, count: b.length / 3 }); o += b.length; });
      this.onLayer({ index: L.index, z: Math.round(L.z * 1000) / 1000, height: Math.round(L.height * 1000) / 1000, filamentMm: L.filamentMm, byte: L.byte, line: L.line, positions: pos, groups });
      this.layer = null;
    }
    _emitPend() { const q = this.pend; if (q) { this.pend = null; this.layer.buf[TYPE_INDEX[q.k]].push(q.a, q.b, q.c, q.x, q.y, q.z); } }
    _seg(x0, y0, z0, x1, y1, z1, kind) {
      if (this.minSegLen && this.layer && kind !== "travel") {
        const q = this.pend;
        if (q && q.k === kind && q.x === x0 && q.y === y0 && q.z === z0 && Math.hypot(q.x - q.a, q.y - q.b) < this.minSegLen) {
          q.x = x1; q.y = y1; q.z = z1; this._bounds(x1, y1, z1); this.stats.extrudeSegments++; return;
        }
        this._emitPend(); this.pend = { k: kind, a: x0, b: y0, c: z0, x: x1, y: y1, z: z1 };
        this._bounds(x0, y0, z0); this._bounds(x1, y1, z1); this.stats.extrudeSegments++; return;
      }
      if (this.pend) this._emitPend();
      if (!this.layer) { if (kind === "travel") { this.stats.travelSegments++; return; } this._newLayer(z1); }  // travel before the first print line: no layer
      const b = this.layer.buf[TYPE_INDEX[kind]];
      b.push(x0, y0, z0, x1, y1, z1);
      if (kind !== "travel") { this._bounds(x0, y0, z0); this._bounds(x1, y1, z1); this.stats.extrudeSegments++; }
      else this.stats.travelSegments++;
    }
    _bounds(x, y, z) {
      const B = this.stats.bounds;
      if (x < B[0]) B[0] = x; if (y < B[1]) B[1] = y; if (z < B[2]) B[2] = z;
      if (x > B[3]) B[3] = x; if (y > B[4]) B[4] = y; if (z > B[5]) B[5] = z;
    }
    push(text) {
      const s = this.rest + text;
      let i = 0, n; const ascii = !/[^\x00-\x7f]/.test(text);   // fast path: byte length == char length
      if (ascii) while ((n = s.indexOf("\n", i)) !== -1) { this._line(s.slice(i, n)); this.byte += n - i + 1; this.lineNo++; i = n + 1; }
      else while ((n = s.indexOf("\n", i)) !== -1) { const raw = s.slice(i, n); this._line(raw); this._adv(raw, false); i = n + 1; }
      this.rest = s.slice(i);
    }
    _adv(raw, ascii) { this.byte += (ascii ? raw.length : utf8Len(raw)) + 1; this.lineNo++; }
    end() { if (this.rest) { this._line(this.rest); this._adv(this.rest, false); this.rest = ""; } this.stats.bytes = this.byte; this._flush(); return { layers: this.layerCount, stats: this.stats, meta: this.meta }; }
    _comment(c) {
      if (c.startsWith("TYPE:")) { this.type = typeOf(c.slice(5)); return; }
      if (c.startsWith("LAYER_CHANGE")) { this.mark = { byte: this.curByte, line: this.curLine }; return; }
      let m;
      if ((m = /^\s*estimated printing time \(normal mode\)\s*=\s*(.+)$/.exec(c))) this.meta.time = m[1].trim();
      else if ((m = /^\s*filament used \[g\]\s*=\s*([\d.]+)/.exec(c))) this.meta.filamentG = +m[1];
      else if ((m = /^\s*filament used \[mm\]\s*=\s*([\d.]+)/.exec(c))) this.meta.filamentMm = +m[1];
      else if ((m = /^TIME:(\d+)/.exec(c))) this.meta.seconds = +m[1];
    }
    _line(raw) {
      this.stats.lines++; this.curByte = this.byte; this.curLine = this.lineNo;
      let line = raw, sc = line.indexOf(";");
      if (sc !== -1) { this._comment(line.slice(sc + 1).trim()); line = line.slice(0, sc); }
      line = line.trim(); if (!line) return;
      // strip N line numbers and *checksums
      if (line[0] === "N" || line[0] === "n") line = line.replace(/^[Nn]\d+\s*/, "");
      const star = line.indexOf("*"); if (star !== -1) line = line.slice(0, star);
      const c0 = line[0] && line[0].toUpperCase();
      if (c0 !== "G" && c0 !== "M") return;
      let j = 1; while (j < line.length && line.charCodeAt(j) >= 48 && line.charCodeAt(j) <= 57) j++;
      if (line[j] === ".") { j++; while (j < line.length && line.charCodeAt(j) >= 48 && line.charCodeAt(j) <= 57) j++; }
      const code = c0 + (+line.slice(1, j));  // "G1", "G10", "G01"->"G1"; exact number, so G10/G11 never look like G1
      if (code === "M82") { this.absE = true; return; }
      if (code === "M83") { this.absE = false; return; }
      if (code === "G90") { this.absXYZ = true; this.absE = true; return; }   // Marlin: G90 also makes E absolute (M83 after it overrides)
      if (code === "G91") { this.absXYZ = false; this.absE = false; return; }
      if (code === "G20") { this.unit = 25.4; return; }
      if (code === "G21") { this.unit = 1; return; }
      if (code !== "G0" && code !== "G1" && code !== "G2" && code !== "G3" && code !== "G92") return;
      const w = {}; const re = /([A-Za-z])\s*([-+]?(?:\d+\.?\d*|\.\d+))/g; re.lastIndex = j; let m;
      while ((m = re.exec(line))) w[m[1].toUpperCase()] = +m[2];
      if (code === "G92") {
        if (w.E !== undefined) this.e = w.E;
        if (w.X !== undefined) this.x = w.X * this.unit; if (w.Y !== undefined) this.y = w.Y * this.unit; if (w.Z !== undefined) this.z = w.Z * this.unit;
        if (w.E === undefined && w.X === undefined && w.Y === undefined && w.Z === undefined) { this.e = 0; this.x = this.y = this.z = 0; }
        return;
      }
      this.stats.moves++;
      const u = this.unit;
      const nx = w.X === undefined ? this.x : (this.absXYZ ? w.X * u : this.x + w.X * u);
      const ny = w.Y === undefined ? this.y : (this.absXYZ ? w.Y * u : this.y + w.Y * u);
      const nz = w.Z === undefined ? this.z : (this.absXYZ ? w.Z * u : this.z + w.Z * u);
      let de = 0;
      if (w.E !== undefined) { if (this.absE) { de = w.E - this.e; this.e = w.E; } else { de = w.E; this.e += w.E; } }
      const moved = nx !== this.x || ny !== this.y;
      const extruding = de > 1e-9 && moved;
      if (extruding) {
        if (this.layer == null || Math.abs(nz - this.layer.z) > 1e-4) this._newLayer(nz);
        else if (this.mark && this.mark.hop) this.mark = null;   // that Z move was a hop inside the layer
        this.layer.filamentMm += de; this.stats.filamentMm += de;
      }
      else if (nz !== this.z && this.layer && this.mark == null) this.mark = { byte: this.curByte, line: this.curLine, hop: true };   // Z lift before the next layer
      const kind = extruding ? this.type : "travel";
      if (moved || nz !== this.z) {
        if (code === "G2" || code === "G3") this._arc(code === "G2", nx, ny, nz, w, kind);
        else if (moved) this._seg(this.x, this.y, this.z, nx, ny, nz, kind);
      }
      this.x = nx; this.y = ny; this.z = nz;
    }
    _arc(cw, nx, ny, nz, w, kind) {
      const x0 = this.x, y0 = this.y, z0 = this.z, u = this.unit;
      let cx, cy;
      if (w.I !== undefined || w.J !== undefined) { cx = x0 + (w.I || 0) * u; cy = y0 + (w.J || 0) * u; }
      else if (w.R !== undefined) {
        const r = w.R * u, dx = nx - x0, dy = ny - y0, d = Math.hypot(dx, dy);
        if (!d || Math.abs(r) < d / 2) { this._seg(x0, y0, z0, nx, ny, nz, kind); return; }
        const h = Math.sqrt(r * r - d * d / 4) * ((cw ? -1 : 1) * (r > 0 ? 1 : -1));
        cx = (x0 + nx) / 2 - h * dy / d; cy = (y0 + ny) / 2 + h * dx / d;
      } else { this._seg(x0, y0, z0, nx, ny, nz, kind); return; }
      const r = Math.hypot(x0 - cx, y0 - cy);
      let a0 = Math.atan2(y0 - cy, x0 - cx), a1 = Math.atan2(ny - cy, nx - cx);
      let sweep = a1 - a0;
      if (cw) { if (sweep >= -1e-9) sweep -= 2 * Math.PI; } else if (sweep <= 1e-9) sweep += 2 * Math.PI;
      const n = Math.max(2, Math.min(720, Math.ceil(Math.abs(sweep) * r / this.arcSegLen)));
      let px = x0, py = y0, pz = z0;
      for (let k = 1; k <= n; k++) {
        const t = k / n, a = a0 + sweep * t;
        const qx = k === n ? nx : cx + r * Math.cos(a), qy = k === n ? ny : cy + r * Math.sin(a), qz = z0 + (nz - z0) * t;
        this._seg(px, py, pz, qx, qy, qz, kind); px = qx; py = qy; pz = qz;
      }
    }
  }
  const api = { GcodeParser, TYPES, typeOf };
  if (typeof module === "object" && module.exports) module.exports = api; else root.ZeimGcode = api;
})(typeof self !== "undefined" ? self : this);
