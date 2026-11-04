// ONB10: after the first file someone saves, one quiet note - shown once on this device, never again.
// Star tip always; a challenge link only if the server lists an open challenge right now.
(() => {
  const KEY = "zeim.onb10.shown";
  let armed = false;
  try { if (localStorage.getItem(KEY)) return; } catch { return; }
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  async function show() {
    try { if (localStorage.getItem(KEY)) return; localStorage.setItem(KEY, String(Date.now())); } catch { return; }
    let ch = null;
    try {
      const r = await fetch("/api/challenges", { credentials: "same-origin" });
      if (r.ok) ch = ((await r.json()).challenges || []).find(c => c.status === "open") || null;
    } catch {}
    const box = document.createElement("aside");
    box.className = "onb10"; box.setAttribute("role", "status"); box.setAttribute("aria-label", "A small tip");
    box.innerHTML = `<p><b>Saved.</b> Tip: tap the <svg class="i" aria-hidden=true focusable=false><use href=#i-star></use></svg> star next to a build in <i>My builds</i> to keep it. Unstarred builds are removed after a while.</p>` +
      (ch ? `<p>The open challenge right now is <b>${esc(ch.title)}</b>. It's prize-free, if you'd like to join.</p>` : "") +
      `<div class="row">${ch ? `<button type="button" class="btn small" id="onb10Ch">See the challenge</button>` : ""}<button type="button" class="btn small" id="onb10X">OK</button></div>`;
    document.body.append(box);
    const close = () => box.remove();
    box.querySelector("#onb10X").onclick = close;
    const b = box.querySelector("#onb10Ch");
    if (b) b.onclick = () => { close(); if (typeof window.zeimOpenChallenge === "function") window.zeimOpenChallenge(ch.id); };
  }
  document.addEventListener("click", e => {
    const a = e.target && e.target.closest && e.target.closest("a[download]");
    if (!a || armed) return;
    armed = true; setTimeout(show, 1200);
  }, true);
})();
