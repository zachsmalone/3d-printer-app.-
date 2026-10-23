/* First-visit 18+ confirmation for every visitor (not just sign-up). Classic synchronous script so the page is covered
   before anything else paints. Yes -> remembered in this browser (localStorage) and, when signed in, on the account.
   No -> a polite exit screen; nothing at all is stored (no answer, no birthdate, no personal data).
   Test-only: <html data-agegate="off"> (server setting PHOTO3D_AGE_GATE=0) skips it. */
(function () {
  var KEY = "zeim.adult", root = document.documentElement, gate = document.getElementById("ageGate");
  if (!gate) return;
  var ok = false;
  try { ok = localStorage.getItem(KEY) === "yes"; } catch (e) { }
  function open() { try { mo && mo.disconnect(); } catch (e) { } gate.remove(); root.classList.remove("gated"); }
  if (ok || root.getAttribute("data-agegate") === "off") { open(); return; }
  root.classList.add("gated");
  function inertRest(on) {
    for (var c = document.body.firstElementChild; c; c = c.nextElementSibling) if (c !== gate && c.tagName !== "SCRIPT") { if (on) c.setAttribute("inert", ""); else c.removeAttribute("inert"); }
  }
  var mo; inertRest(true);
  addEventListener("DOMContentLoaded", function () { if (gate.isConnected) inertRest(true); });
  try {   // things added to <body> later (floating buttons, dialogs) stay behind the gate too
    mo = new MutationObserver(function () { if (gate.isConnected) inertRest(true); else mo.disconnect(); });
    mo.observe(document.body || root, { childList: true, subtree: !document.body });
  } catch (e) { }
  var yes = document.getElementById("ageYes"), no = document.getElementById("ageNo");
  setTimeout(function () { try { yes.focus(); } catch (e) { } }, 0);
  yes.addEventListener("click", function () {
    try { localStorage.setItem(KEY, "yes"); } catch (e) { }
    try { fetch("/api/me/adult", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ adult: true }) }).catch(function () { }); } catch (e) { }
    inertRest(false); open();
    var main = document.querySelector("main:not([hidden])"); if (main) { main.setAttribute("tabindex", "-1"); main.focus({ preventScroll: true }); }
  });
  no.addEventListener("click", function () {
    document.getElementById("ageAsk").hidden = true;
    var bye = document.getElementById("ageBye"); bye.hidden = false; bye.focus();
  });
  gate.addEventListener("keydown", function (e) {   // keep focus inside the dialog
    if (e.key !== "Tab") return;
    var f = [].filter.call(gate.querySelectorAll("button"), function (b) { return b.offsetParent; });
    if (!f.length) { e.preventDefault(); return; }
    var i = f.indexOf(document.activeElement);
    if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); } else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus(); }
  });
  // Signed-in adult on a new device: the account already said yes.
  try { fetch("/api/me/adult").then(function (r) { return r.json(); }).then(function (j) { if (j && j.signed_up && j.confirmed && gate.isConnected && !document.getElementById("ageAsk").hidden) { try { localStorage.setItem(KEY, "yes"); } catch (e) { } inertRest(false); open(); } }).catch(function () { }); } catch (e) { }
})();
