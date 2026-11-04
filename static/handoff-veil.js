/* Hand-off veil: while a model travels to another section, cover that section's viewport with one opaque panel
   showing a real percentage (bytes streamed, then parse/render stages). The section underneath switches at once
   but is never seen empty: the veil fades out (120 ms, none with reduced motion) only when the model is drawn.
   Progress comes in as fractions of the current band: veil.band(lo, hi) then veil.frac(0..1) or the
   "zeim:handoff-progress" event (detail = 0..1) from edit.js / torchc0.js. */
let el = null, lo = 0, hi = 100, pct = 0, guard = 0, done = null;
const reduce = () => { try { return matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; } };
function node() {
  if (el) return el;
  el = document.createElement("div"); el.id = "handoffVeil"; el.className = "handoff-veil"; el.hidden = true;
  el.setAttribute("role", "status"); el.setAttribute("aria-live", "polite");
  el.innerHTML = `<div class="hv-box"><p class="hv-label"></p><div class="hv-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"><i></i></div><p class="hv-pct">0%</p><p class="hv-stage help"></p></div>`;
  document.body.append(el); return el;
}
function paint(v) {
  pct = Math.max(pct, Math.min(100, Math.round(v)));      // never goes backwards
  if (!el) return;
  el.dataset.pct = String(pct);
  el.querySelector(".hv-bar i").style.width = pct + "%";
  el.querySelector(".hv-bar").setAttribute("aria-valuenow", String(pct));
  el.querySelector(".hv-pct").textContent = pct + "%";
}
export function open(label, until) {
  const v = node(); clearTimeout(guard); done?.(); pct = 0; lo = 0; hi = 100;
  const top = document.querySelector("header.topbar")?.getBoundingClientRect().bottom || 0;
  v.style.top = Math.max(0, Math.round(top)) + "px";
  v.querySelector(".hv-label").textContent = label;
  v.querySelector(".hv-stage").textContent = "";
  v.classList.remove("out"); v.hidden = false; paint(0);
  const onP = e => frac(+e.detail || 0);
  const evs = until || [];
  const fin = () => close();
  document.addEventListener("zeim:handoff-progress", onP);
  evs.forEach(n => document.addEventListener(n, fin));
  done = () => { document.removeEventListener("zeim:handoff-progress", onP); evs.forEach(n => document.removeEventListener(n, fin)); done = null; };
  guard = setTimeout(close, 180000);                        // never leave the page covered
}
export const band = (a, b, stage) => { lo = a; hi = b; paint(a); if (el && stage) el.querySelector(".hv-stage").textContent = stage; };
export const frac = f => paint(lo + (hi - lo) * Math.max(0, Math.min(1, f)));
export const isOpen = () => !!el && !el.hidden;
export function close() {
  if (!el || el.hidden) return;
  clearTimeout(guard); done?.(); paint(100);
  const v = el;
  // wait one frame so the model's first frame is on screen, then fade
  requestAnimationFrame(() => {
    if (reduce()) { v.hidden = true; return; }
    v.classList.add("out"); setTimeout(() => { if (v.classList.contains("out")) { v.hidden = true; v.classList.remove("out"); } }, 130);
  });
}
/* Streamed fetch: real byte progress when the server sends Content-Length. */
export async function fetchBytes(url, opt, onFrac) {
  const r = await fetch(url, { credentials: "same-origin", ...(opt || {}) });
  const total = +r.headers.get("Content-Length") || 0;
  if (!r.body || !total || !onFrac) return { r, buf: await r.arrayBuffer() };
  const rd = r.body.getReader(), parts = []; let got = 0;
  for (; ;) { const { done: d, value } = await rd.read(); if (d) break; parts.push(value); got += value.byteLength; onFrac(got / total); }
  const buf = new Uint8Array(got); let o = 0; for (const p of parts) { buf.set(p, o); o += p.byteLength; }
  return { r, buf: buf.buffer };
}
export const progress = f => document.dispatchEvent(new CustomEvent("zeim:handoff-progress", { detail: f }));
/* POST a form with real upload + download progress (fetch can't report upload bytes). Resolves {ok, status, headers, buf}. */
export function postForm(url, fd, onFrac) {
  return new Promise((ok, no) => {
    const x = new XMLHttpRequest(); x.open("POST", url); x.withCredentials = true; x.responseType = "arraybuffer";
    x.upload.onprogress = e => { if (e.lengthComputable) onFrac?.(0.6 * e.loaded / e.total); };
    x.onprogress = e => { if (e.lengthComputable) onFrac?.(0.6 + 0.3 * e.loaded / e.total); };
    x.onload = () => ok({ ok: x.status >= 200 && x.status < 300, status: x.status, headers: { get: k => x.getResponseHeader(k) }, buf: x.response });
    x.onerror = () => no(new Error("network error")); x.send(fd);
  });
}
