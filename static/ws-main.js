/* ZEIM main-app workspaces (Studio, Lithophane, FDM Slicer, TorchC0) on the floating layout (wslayout.js, original code).
   Once a model is on screen, its 3D view becomes the full background of the workspace and every panel floats over it
   (drag / dock / resize / minimise / hide, "Customise workspace", "Reset layout"); before that the page reads as usual. */
(function boot() {
  "use strict";
  if (!window.ZWS) { var sc = document.createElement("script"); sc.src = "/static/wslayout.js"; sc.onload = boot; document.head.append(sc); return; }
  var $ = function (s) { return document.querySelector(s); };
  /* shown = not hidden itself and its workspace is the open one (it may sit in a minimised panel, so no layout check) */
  var vis = function (el) { var m = el && el.closest("main"); return !!el && !el.hidden && !!m && !m.hidden; };
  var PHONE = matchMedia("(max-width:820px), (max-height:500px) and (pointer:coarse)");
  /* the workspace fills what is left of the screen under the header */
  function fill(root) {
    return function () {
      var on = root.classList.contains("zws");
      if (on && !root._zwsOn && scrollY) scrollTo(0, 0);   // a workspace that just went full-screen starts at the top
      root._zwsOn = on;
      if (!on) { if (root.style.getPropertyValue("--zws-h")) root.style.removeProperty("--zws-h"); return; }
      var vv = window.visualViewport, vh = vv ? vv.height : innerHeight;
      var hdr = document.querySelector(".topbar"), top = hdr ? Math.max(0, hdr.getBoundingClientRect().bottom) : 0;
      var pb = parseFloat(getComputedStyle(document.body).paddingBottom) || 0;
      var v = Math.max(260, Math.round(vh - top - pb)) + "px";
      if (root.style.getPropertyValue("--zws-h") !== v) root.style.setProperty("--zws-h", v);   // only on a real change (no layout loop)
    };
  }
  function make(o) {
    var root = $(o.root); if (!root) return null;
    o.root = root; o.before = fill(root); o.btnClass = "btn small zws-cw";
    o.customise = root; o.obstacles = (o.obstacles || []).concat(["#" + root.id + " > .zws-cust"]);
    o.panels = o.panels.map(function (p) { p.el = typeof p.el === "string" ? $(p.el) : p.el; return p; }).filter(function (p) { return p.el; });
    var ws = ZWS.create(o);
    root.addEventListener("zws:layout", function () { document.body.classList.toggle("zws-on", !!document.querySelector("main.zws:not([hidden])")); });
    return ws;
  }
  var ph = PHONE.matches;
  /* Studio and Lithophane share a view: the lithophane light box tells them apart, and each keeps its own layout */
  var litho = function () { var b = $("#litLightBox"); return !!b && !b.hidden; };
  var studio = make({ id: "studio", key: function () { return litho() ? "litho" : "studio"; }, title: function () { return litho() ? "Lithophane" : "Studio"; },
    root: "#viewCreate", active: function () { return vis($("#result")); },
    watch: ["#result", "#litLightBox", "#viewCreate"], obstacles: ["#busy:not([hidden])"],
    panels: [
      { id: "result", el: "#result", label: "Export & print", core: true, def: ph ? { edge: "bottom", t: 0.5, h: Math.round(innerHeight * 0.42) } : { edge: "right", t: 0.3 } },
      { id: "view", el: "#vtools", label: "View & light", def: { edge: "top", t: 0 }, resize: false, bare: true },
      { id: "settings", el: "#viewCreate > aside.controls", label: "Photo & settings", def: { edge: "left", t: 0, min: ph } },
      { id: "history", el: "#viewCreate .stage > .history", label: "Recent builds", def: { edge: "right", t: 0, hidden: ph, min: !ph } }
    ] });
  var lastKey = null;
  if (studio) { var lb = $("#litLightBox"); if (lb) new MutationObserver(function () { var k = litho(); if (k !== lastKey) { lastKey = k; studio.rekey(); } }).observe(lb, { attributes: true, attributeFilter: ["hidden"] }); }
  make({ id: "slicer", title: "FDM Slicer", root: "#viewEdit", active: function () { return vis($("#editResult")); },
    watch: ["#editResult", "#viewEdit"], obstacles: ["#editBusy:not([hidden])", "#eMeasureOut:not([hidden])"],
    panels: [
      { id: "undo", el: "#editVtools", label: "Undo & view", core: true, def: { edge: "top", t: 0 }, resize: false, bare: true },
      { id: "tools", el: "#editSide", label: "Tools", core: true, def: { edge: "left", t: 0, min: ph } },
      { id: "result", el: "#editResult", label: "Slice, export & print", core: true, def: { edge: "right", t: 0, min: ph } }
    ] });
  /* TorchC0: the result view moves out of the results card to become the background */
  var tRoot = $("#viewTorch"), tOut = $("#torchOut");
  function torchView() { var v = $("#rzView"); if (v && tRoot && v.parentElement !== tRoot && tRoot.classList.contains("zws")) { v._home = v.parentElement; tRoot.prepend(v); v.classList.add("zws-bg"); }
    if (tRoot) tRoot.querySelectorAll(":scope > .zws-bg").forEach(function (o) { if (o !== v) o.remove(); });   // a re-run replaces the old view
    return v; }
  var torch = make({ id: "torchc0", title: "TorchC0", root: "#viewTorch", active: function () { return !!tRoot && !tRoot.hidden && !!$("#rzView"); },
    watch: ["#torchOut"], watchChildren: true,
    panels: [
      { id: "out", el: "#torchOut", label: "Result & downloads", core: true, def: { edge: "right", t: 0, min: ph } },
      { id: "settings", el: "#torchPanel", label: "Resin settings", def: { edge: "left", t: 0, min: ph } }
    ] });
  if (torch && tOut) new MutationObserver(function () { var v = $("#rzView"); if (v && v.parentElement === tOut) { torch.setHidden("out", false); requestAnimationFrame(torchView); } }).observe(tOut, { childList: true });
  if (tRoot) tRoot.addEventListener("zws:layout", torchView);
  window.zeimWorkspaces = ZWS.all;
})();
