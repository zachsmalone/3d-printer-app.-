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

if (typeof document !== "undefined") {
  if (!ls.get(K_SEEN)) ls.set(K_SEEN, String(Date.now()));
  document.addEventListener("click", e => {
    const a = e.target && e.target.closest ? e.target.closest("a[download]") : null;
    if (isPrintDownload(a)) firstPrint();
  }, true);
}
