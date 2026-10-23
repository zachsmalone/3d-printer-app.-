/* Web Worker: stream a G-code file (URL via fetch, or a File/Blob in 4 MB slices), parse it with gcode-parse.js,
   post finished layers in batches (buffers transferred, not copied) and progress. Never blocks the page. */
importScripts("/static/gcode-parse.js");
let cancelled = false;
self.onmessage = async (ev) => {
  const msg = ev.data || {};
  if (msg.cancel) { cancelled = true; return; }
  cancelled = false;
  const t0 = performance.now();
  let batch = [], transfer = [], lastPost = 0, done = 0, total = 0;
  const post = (force) => {
    const now = performance.now();
    if (!force && now - lastPost < 120 && batch.length < 400) return;
    self.postMessage({ kind: "layers", layers: batch, done, total }, transfer);
    batch = []; transfer = []; lastPost = now;
  };
  // size budget (GPU memory on phones): files over 20 MB join pieces shorter than 0.3 mm (0.6 mm on touch / over 120 MB)
  const big = (n) => n > 120e6 || (msg.touch && n > 20e6) ? 0.6 : n > 20e6 ? 0.3 : 0;
  const opts = { onLayer: (L) => { batch.push(L); transfer.push(L.positions.buffer); } };
  let p = null; const mk = (n) => { const m = big(n); p = new self.ZeimGcode.GcodeParser({ ...opts, minSegLen: m, arcSegLen: m ? 1 : 0.5 }); self.postMessage({ kind: "info", simplified: m }); };
  try {
    const dec = new TextDecoder();
    if (msg.url) {
      const r = await fetch(msg.url, { credentials: "same-origin" });
      if (!r.ok) throw new Error("Could not load the G-code (" + r.status + ")");
      total = +r.headers.get("content-length") || 0; mk(total);
      const rd = r.body.getReader();
      for (;;) {
        const { value, done: fin } = await rd.read();
        if (cancelled) { rd.cancel(); return; }
        if (fin) break;
        done += value.byteLength; p.push(dec.decode(value, { stream: true })); post(false);
      }
    } else if (msg.blob) {
      total = msg.blob.size; mk(total); const step = 4 << 20;
      for (let o = 0; o < total; o += step) {
        if (cancelled) return;
        const buf = await msg.blob.slice(o, o + step).arrayBuffer();
        done = Math.min(total, o + step); p.push(dec.decode(buf, { stream: true })); post(false);
      }
    } else if (typeof msg.text === "string") { total = done = msg.text.length; mk(total); p.push(msg.text); }
    p.push(dec.decode());
    const res = p.end(); post(true);
    self.postMessage({ kind: "done", layers: res.layers, stats: res.stats, meta: res.meta, ms: Math.round(performance.now() - t0), bytes: done });
  } catch (e) { self.postMessage({ kind: "error", message: String(e && e.message || e) }); }
};
