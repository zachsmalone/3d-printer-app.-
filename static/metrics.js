/* ONB1: time to first print, first-party and minimal. See app/api/metrics.py for exactly what is stored.
   This browser remembers when it first opened ZEIM (localStorage, never sent). On the first download of a print
   file it sends one coarse number of seconds since then, once. Off when Do Not Track / Global Privacy Control is on
   or when the person turns usage counts off (Your data panel). */
const K_SEEN = "zeim.firstSeen", K_SENT = "zeim.firstPrintSent", K_OFF = "zeim.metricsOff";
const ls = { get: k => { try { return localStorage.getItem(k); } catch { return null; } },
             set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
             del: k => { try { localStorage.removeItem(k); } catch {} } };

export function metricsOff() {
  return navigator.globalPrivacyControl === true || navigator.doNotTrack === "1" || window.doNotTrack === "1" || ls.get(K_OFF) === "1";
}
export function setMetricsOff(off) { off ? ls.set(K_OFF, "1") : ls.del(K_OFF); }

// a print file = a download link for 3MF / G-code / STL / ZIP of STLs
export function isPrintDownload(a) {
  if (!a || !a.hasAttribute || !a.hasAttribute("download")) return false;
  const n = ((a.getAttribute("download") || "") + " " + (a.getAttribute("href") || "")).toLowerCase();
  return /\.(3mf|gcode|bgcode|stl|zip)\b|\/download|3mf|gcode/.test(n);
}

export function firstPrint(now = Date.now()) {
  if (metricsOff() || ls.get(K_SENT)) return false;
  const seen = Number(ls.get(K_SEEN)) || now;
  ls.set(K_SENT, "1");
  try {
    fetch("/api/metrics", { method: "POST", keepalive: true, credentials: "omit",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event: "first_print", secs: Math.max(0, Math.round((now - seen) / 1000)) }) }).catch(() => {});
  } catch {}
  return true;
}

/* RET6: NPS pulse. After a print download that is not this browser's first, at most once every 90 days, a small
   card asks 0-10. Only the number is sent. Never shown when usage counts are off. */
const K_NPS = "zeim.npsAskedAt", NPS_GAP = 90 * 86400e3;
export function shouldAskNps(now = Date.now()) {
  return !metricsOff() && !!ls.get(K_SENT) && !(now - (Number(ls.get(K_NPS)) || 0) < NPS_GAP);
}
export function sendNps(score) {
  try { fetch("/api/metrics", { method: "POST", credentials: "omit", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event: "nps", score }) }).catch(() => {}); } catch {}
}
export function askNps() {
  if (!shouldAskNps() || document.getElementById("npsCard")) return;
  ls.set(K_NPS, String(Date.now()));          // asked, whether answered or dismissed
  const c = document.createElement("div");
  c.id = "npsCard"; c.className = "npscard"; c.setAttribute("role", "dialog"); c.setAttribute("aria-label", "Quick question");
  c.innerHTML = `<button class="x" type="button" aria-label="No thanks">\u00d7</button>
    <p>How likely are you to recommend ZEIM to a friend?</p>
    <div class="npsrow">${Array.from({ length: 11 }, (_, i) => `<button type="button" class="btn small" data-s="${i}">${i}</button>`).join("")}</div>
    <p class="help"><span>0 = not likely</span><span>10 = very likely</span></p>
    <p class="help">Only the number is sent. Turn this off under Me, Your data.</p>`;
  c.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.s != null) { sendNps(Number(b.dataset.s)); c.innerHTML = "<p>Thanks!</p>"; setTimeout(() => c.remove(), 1500); }
    else c.remove();
  });
  document.body.append(c);
}

if (typeof document !== "undefined") {
  if (!ls.get(K_SEEN)) ls.set(K_SEEN, String(Date.now()));
  document.addEventListener("click", e => {
    const a = e.target && e.target.closest ? e.target.closest("a[download]") : null;
    if (!isPrintDownload(a)) return;
    if (!firstPrint() && shouldAskNps()) setTimeout(askNps, 2500);
  }, true);
}
