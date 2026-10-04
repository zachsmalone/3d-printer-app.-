/* Start-up watchdog. A classic (non-module) script so it still runs when one of the ES modules fails to load or throws.
   The page is wired by modules (app.js, community.js, edit.js); if one is missing, stale or broken, every button is dead and the
   page still LOOKS fine. So: if the app has not reported "started" in a few seconds, or a script fails first, say so out loud. */
(function () {
  var errors = (window.__zeimErrors = []);
  var shown = false;
  function started() { return window.__zeimStarted === true && window.__zeimEditStarted === true; }
  function show(why) {
    errors.push(why);
    if (shown || started() || !document.body) { if (!shown && !started()) addEventListener("DOMContentLoaded", function () { show("(late) " + why); }, { once: true }); return; }
    shown = true;
    var b = document.createElement("div");
    b.id = "bootError"; b.setAttribute("role", "alert");
    b.style.cssText = "position:fixed;left:0;right:0;top:0;z-index:99999;background:#7a1020;color:#fff;padding:14px 16px;font:16px/1.4 system-ui,sans-serif;text-align:center";
    b.appendChild(document.createTextNode("ZEIM didn't start properly, so the buttons won't work. "));
    var r = document.createElement("button");
    r.type = "button"; r.textContent = "Reload"; r.style.cssText = "margin-left:8px;min-height:44px;min-width:88px;font:inherit;border-radius:8px;border:0;padding:6px 14px";
    r.addEventListener("click", function () { location.reload(); });
    b.appendChild(r);
    var small = document.createElement("div");
    small.style.cssText = "font-size:13px;opacity:.85;margin-top:6px"; small.textContent = "If it keeps happening, tell the person who gave you this link.";
    b.appendChild(small);
    document.body.appendChild(b);
  }
  addEventListener("error", function (e) {
    var t = e.target;
    if (t && t !== window && t.tagName === "SCRIPT") return show("script failed to load: " + (t.src || ""));
    show("error: " + (e.message || "") + " @" + (e.filename || ""));
  }, true);
  addEventListener("unhandledrejection", function (e) { show("promise: " + ((e.reason && e.reason.message) || e.reason)); });
  setTimeout(function () { if (!started()) show("the app did not report started in 12 s"); }, 12000);
  // if it did start late, take the message away again
  var iv = setInterval(function () { if (started()) { clearInterval(iv); var b = document.getElementById("bootError"); if (b) b.remove(); } }, 500);
})();
