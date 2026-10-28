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
      var hdr = document.querySelector(".topbar");
      var flow = document.getElementById("projectFlow");
      var edge = (flow && !flow.hidden && flow.getBoundingClientRect().height > 0) ? flow : hdr;
      var top = edge ? Math.max(0, edge.getBoundingClientRect().bottom) : 0;
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
  function phone() { return PHONE.matches; }
  /* #create and #lithophane share #viewCreate and each keep a layout. #studio is Account → My Studio and does not show this view.
     The route is the identity. The light box only shows lithophane preview controls; opening it must not
     swap the saved layout. Recent builds (#recentBuilds) are listed in Account → My Studio. This panel follows that element's hidden flag.
     Defaults are read at layout time so a resize across the phone breakpoint is not stuck on the first paint. */
  function studioRoute() {
    var raw = (location.hash || "").replace(/^#/, "").split(/[/?]/)[0];
    return raw === "lithophane" ? "litho" : "studio";
  }
  var lastKey = studioRoute();
  var studio = make({ id: "studio", key: function () { return studioRoute(); }, title: function () { return studioRoute() === "litho" ? "Lithophane" : "Photo"; },
    root: "#viewCreate", active: function () { return vis($("#result")); },
    watch: ["#result", "#litLightBox", "#viewCreate"], obstacles: ["#busy:not([hidden])"],
    panels: [
      { id: "result", el: "#result", label: "Export & print", core: true, def: function () { return phone() ? { edge: "bottom", t: 0.5, h: Math.round(innerHeight * 0.42) } : { edge: "right", t: 0.3 }; } },
      { id: "view", el: "#vtools", label: "View & light", def: function () { return { edge: "top", t: 0 }; }, resize: false, bare: true },
      { id: "settings", el: "#viewCreate > aside.controls", label: "Photo & settings", def: function () { return { edge: "left", t: 0, min: phone() }; } },
      { id: "history", el: "#viewCreate .stage > .history", label: "Recent builds", def: function () { return { edge: "right", t: 0, hidden: phone(), min: !phone() }; } }
    ] });
  if (studio) window.addEventListener("hashchange", function () {
    var k = studioRoute(); if (k === lastKey) return; lastKey = k; studio.rekey();
  });
  make({ id: "slicer", title: "FDM Slicer", root: "#viewEdit", active: function () { return vis($("#editResult")); },
    watch: ["#editResult", "#viewEdit"], obstacles: ["#editBusy:not([hidden])", "#eMeasureOut:not([hidden])"],
    panels: [
      { id: "undo", el: "#editVtools", label: "Undo & view", core: true, def: function () { return { edge: "top", t: 0 }; }, resize: false, bare: true },
      { id: "tools", el: "#editSide", label: "Tools", core: true, def: function () { return { edge: "left", t: 0, min: phone() }; } },
      { id: "result", el: "#editResult", label: "Slice, export & print", core: true, def: function () { return { edge: "right", t: 0, min: phone() }; } }
    ] });
  /* TorchC0: the result view moves out of the results card to become the background */
  var tRoot = $("#viewTorch"), tOut = $("#torchOut");
  function torchView() { var v = $("#rzView"); if (v && tRoot && v.parentElement !== tRoot && tRoot.classList.contains("zws")) { v._home = v.parentElement; tRoot.prepend(v); v.classList.add("zws-bg"); }
    if (tRoot) tRoot.querySelectorAll(":scope > .zws-bg").forEach(function (o) { if (o !== v) o.remove(); });   // a re-run replaces the old view
    return v; }
  var torch = make({ id: "torchc0", title: "TorchC0", root: "#viewTorch", active: function () { return !!tRoot && !tRoot.hidden && !!$("#rzView"); },
    watch: ["#torchOut"], watchChildren: true,
    panels: [
      { id: "out", el: "#torchOut", label: "Result & downloads", core: true, def: function () { return { edge: "right", t: 0, min: phone() }; } },
      { id: "settings", el: "#torchPanel", label: "Resin settings", def: function () { return { edge: "left", t: 0, min: phone() }; } }
    ] });
  if (torch && tOut) new MutationObserver(function () { var v = $("#rzView"); if (v && v.parentElement === tOut) { torch.setHidden("out", false); requestAnimationFrame(torchView); } }).observe(tOut, { childList: true });
  if (tRoot) tRoot.addEventListener("zws:layout", torchView);
  window.zeimWorkspaces = ZWS.all;
})();
