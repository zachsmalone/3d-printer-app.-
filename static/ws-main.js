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
    o.customise = root; o.obstacles = (o.obstacles || []).concat(["#" + root.id + " > .zws-cust", "#" + root.id + " > .wsbar", "#" + root.id + " > .objdock:not([hidden])", "#" + root.id + " > .proc-sheet:not([hidden])"]);
    o.panels = o.panels.map(function (p) { p.el = typeof p.el === "string" ? $(p.el) : p.el; return p; }).filter(function (p) { return p.el; });
    var ws = ZWS.create(o);
    root.addEventListener("zws:layout", function () {
      document.body.classList.toggle("zws-on", !!document.querySelector("main.zws:not([hidden])"));
      syncSlicerDock();
    });
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
      { id: "result", el: "#result", label: "Export & print", core: true, dock: true, def: function () { return phone() ? { edge: "bottom", t: 0.5, h: Math.round(innerHeight * 0.42) } : { edge: "right", t: 0.3 }; } },
      { id: "view", el: "#vtools", label: "View & light", dock: true, lead: true, def: function () { return { edge: "right", t: 0.42 }; }, resize: false, bare: true },
      { id: "settings", el: "#viewCreate > aside.controls", label: "Photo & settings", dock: true, def: function () { return { edge: "left", t: 0, min: phone() }; } },
      { id: "history", el: "#viewCreate .stage > .history", label: "Recent builds", dock: true, def: function () { return { edge: "right", t: 0, hidden: phone(), min: !phone() }; } }
    ] });
  if (studio) window.addEventListener("hashchange", function () {
    var k = studioRoute(); if (k === lastKey) return; lastKey = k; studio.rekey();
  });
  make({ id: "slicer", title: "FDM Slicer", root: "#viewEdit", active: function () { return vis($("#editResult")); },
    watch: ["#editResult", "#viewEdit", "#processSheet", "#slicerDock"], obstacles: ["#editBusy:not([hidden])", "#eMeasureOut:not([hidden])"],
    panels: [
      { id: "undo", el: "#editVtools", label: "Undo & view", core: true, dock: true, lead: true, def: function () { return { edge: "right", t: 0.36 }; }, resize: false, bare: true },
      { id: "tools", el: "#editSide", label: "Tools", core: true, dock: true, def: function () { return { edge: "left", t: 0, min: phone() }; } },
      { id: "result", el: "#editResult", label: "Slice, export & print", core: true, dock: true, def: function () { return { edge: "right", t: 0, min: phone() }; } }
    ] });
  /* TorchC0: the result view moves out of the results card to become the background */
  var tRoot = $("#viewTorch"), tOut = $("#torchOut");
  function torchView() { var v = $("#rzView"); if (v && tRoot && v.parentElement !== tRoot && tRoot.classList.contains("zws")) { v._home = v.parentElement; tRoot.prepend(v); v.classList.add("zws-bg"); }
    if (tRoot) tRoot.querySelectorAll(":scope > .zws-bg").forEach(function (o) { if (o !== v) o.remove(); });   // a re-run replaces the old view
    return v; }
  var torch = make({ id: "torchc0", title: "TorchC0", root: "#viewTorch", active: function () { return !!tRoot && !tRoot.hidden && !!$("#rzView"); },
    watch: ["#torchOut"], watchChildren: true,
    panels: [
      { id: "out", el: "#torchOut", label: "Result & downloads", core: true, dock: true, def: function () { return { edge: "right", t: 0, min: phone() }; } },
      { id: "settings", el: "#torchPanel", label: "Resin settings", dock: true, def: function () { return { edge: "left", t: 0, min: phone() }; } }
    ] });
  if (torch && tOut) new MutationObserver(function () { var v = $("#rzView"); if (v && v.parentElement === tOut) { torch.setHidden("out", false); requestAnimationFrame(torchView); } }).observe(tOut, { childList: true });
  if (tRoot) tRoot.addEventListener("zws:layout", torchView);
  /* The plate dock follows the open model. Process is a half-height sheet; Close does not leave the workspace. */
  function syncSlicerDock() {
    var res = document.getElementById("editResult"), dock = document.getElementById("slicerDock");
    if (!dock || !res) return;
    var show = !res.hidden;
    if (dock.hidden !== !show) dock.hidden = !show;
    if (!show) { var sheet = document.getElementById("processSheet"); if (sheet) sheet.hidden = true; }
  }
  function setDockTab(which) {
    var dock = document.getElementById("slicerDock"); if (!dock) return;
    dock.querySelectorAll("[data-docktab]").forEach(function (b) { b.setAttribute("aria-selected", b.getAttribute("data-docktab") === which ? "true" : "false"); });
    var sheet = document.getElementById("processSheet");
    if (sheet) sheet.hidden = which !== "process";
  }
  function focusXform(kind) {
    var plate = document.getElementById("plateTool"); if (plate) plate.open = true;
    var sel = document.getElementById("plateSel");
    var map = { move: ["#pX", "[data-form=translate]"], rotate: ["#pRz", "[data-form=rotate]"], scale: ["#pPct", "[data-form=scale]"] };
    var pair = map[kind] || map.move;
    var field = sel && !sel.hidden ? document.querySelector(pair[0]) : null;
    var form = document.querySelector(pair[1]);
    if (field) { field.focus(); return; }
    if (form) { var det = form.closest("details"); if (det) det.open = true; var input = form.querySelector("input,button"); if (input) input.focus(); return; }
    var big = kind === "scale" ? document.querySelector("[data-big=scale]") : null;
    if (big) big.click();
  }
  document.addEventListener("click", function (e) {
    var go = e.target.closest && e.target.closest(".ws-go");
    if (go) {
      e.preventDefault();
      if (go.id === "slicerSlice") setDockTab("process");
      var target = document.getElementById(go.getAttribute("data-go") || "");
      if (target && !target.disabled) target.click();
      return;
    }
    var xform = e.target.closest && e.target.closest("#slicerDock [data-xform]");
    if (xform) {
      e.preventDefault();
      document.querySelectorAll("#slicerDock [data-xform]").forEach(function (b) { b.setAttribute("aria-pressed", b === xform ? "true" : "false"); });
      focusXform(xform.getAttribute("data-xform"));
      return;
    }
    var tab = e.target.closest && e.target.closest("#slicerDock [data-docktab]");
    if (tab) { e.preventDefault(); setDockTab(tab.getAttribute("data-docktab")); return; }
    if (e.target.closest && e.target.closest("#processClose")) {
      e.preventDefault();
      setDockTab("plate");
    }
  });
  window.zeimWorkspaces = ZWS.all;
})();
