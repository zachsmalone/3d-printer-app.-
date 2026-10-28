/* ZEIM CAD — phone compact layout (original code).
   Phones: one-row header with a "…" menu, the tool rail and the quick cluster float over a full-size view
   (drag by the grip, snap to an edge, remembered per orientation, never over each other / the view cube / open panels),
   and History/Items is a bottom sheet (peek 48px → half → full; a right-hand drawer in landscape). */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var PHONE = matchMedia("(max-width:820px), (max-height:500px) and (pointer:coarse)");
  var main = $(".cw-main"), stage = $("#cwStage"), side = $("#cwSide"), rail = $("#cwRail"), bl = $(".cw-bl");
  if (!main || !stage || !side || !rail || !bl) return;
  var land = function () { return innerWidth > innerHeight; };
  var store = { get: function (k) { try { return JSON.parse(localStorage.getItem(k)); } catch (e) { return null; } },
                set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };

  /* ---------- safe-area probe (env() is only readable through CSS) */
  var probe = document.createElement("div"); probe.className = "cw-safe"; probe.setAttribute("aria-hidden", "true"); document.body.append(probe);
  function safe() { var c = getComputedStyle(probe); return { t: parseFloat(c.paddingTop) || 0, r: parseFloat(c.paddingRight) || 0, b: parseFloat(c.paddingBottom) || 0, l: parseFloat(c.paddingLeft) || 0 }; }

  /* ---------- "…" menu: proxies for the items the phone header hides */
  var more = $("#cwMore"), menu = $("#cwMoreMenu"), unitsHome = $("#cwOpenMenu"), units = $(".cw-units"), unitsHelp = $(".cw-units-help");
  var ITEMS = [["#cwImport", "Import STL, OBJ or 3MF…"], ["#cwFromBuild", "From my builds…"], ["a[href='/static/cad.html']", "New blank design"], null,
    ["#cwDlStl", "Download STL"], ["#cwDl3mf", "Download 3MF"], ["#cwSaveCopy", "Save as a new version (copy)"], ["#cwToSlicer", "Open in Slicer & plate editor"], null,
    ["#cwGrid", function (t) { return "Grid: " + t.textContent.trim(); }], ["#cwSnap", function (t) { return t.textContent.trim(); }],
    ["#cwHints", function (t) { return t.textContent.trim(); }], ["#cwSearch", "Search tools"], ["#cwLearn", "Lessons"], null,
    ["#zwsCust-cad", "Customise workspace…"], ["#themeToggle", function (t) { return t.getAttribute("aria-pressed") === "true" ? "Light mode" : "Dark mode"; }], ["#lookBtn", "Look & colour palette…"]];
  function fillMenu() {
    menu.innerHTML = "";
    if (units) { menu.append(units); if (unitsHelp) menu.append(unitsHelp); }
    ITEMS.forEach(function (it) {
      if (!it) { menu.append(document.createElement("hr")); return; }
      var t = $(it[0]); if (!t) return;
      var a = document.createElement("button"); a.type = "button"; a.setAttribute("role", "menuitem"); a.className = "cw-mi";
      a.textContent = typeof it[1] === "function" ? it[1](t) : it[1];
      var p = t.getAttribute("aria-pressed"); if (p && it[0] !== "#themeToggle") a.setAttribute("aria-checked", p);
      a.onclick = function (e) { e.stopPropagation(); close(); t.click(); };
      menu.append(a);
    });
  }
  function close() { menu.hidden = true; more.setAttribute("aria-expanded", "false"); }
  if (more && menu) {
    more.onclick = function (e) { e.stopPropagation(); if (menu.hidden) { fillMenu(); menu.hidden = false; more.setAttribute("aria-expanded", "true"); var f = menu.querySelector(".cw-mi"); if (f) f.focus(); } else close(); };
    document.addEventListener("click", function (e) { if (!e.target.closest("#cwMoreMenu")) close(); });
    menu.addEventListener("click", function (e) { e.stopPropagation(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !menu.hidden) { close(); more.focus(); } });
  }
  function homeUnits() { if (units && unitsHome && units.parentElement !== unitsHome) { unitsHome.prepend(unitsHelp || units); unitsHome.prepend(units); } }

  /* ---------- every panel floats over the full-size view (wslayout.js) */
  var fit = $("#cwHome"), chips = $(".cw-chips"), tool = $("#cwTool");
  function stageInset() { var m = main.getBoundingClientRect(), r = stage.getBoundingClientRect(); return { l: r.left - m.left, t: r.top - m.top, r: m.right - r.right, b: m.bottom - r.bottom }; }
  function phone() { return PHONE.matches; }
  var ws = window.ZWS && ZWS.create({ id: "cad", root: main, btnClass: "cw-btn zws-cw",
    customise: $(".cw-top"), inset: function () { return PHONE.matches ? stageInset() : { l: 0, t: 0, r: 0, b: 0 }; },
    obstacles: ["#cwStage .cw-cubewrap", "#cwSectionBar", "#cwStage > .cw-lesson", "#cwStage > .cw-hint", "#cwEmpty", ".cw-warn", ".cw-modepop", ".cw-phone #cwSide", ".cw-phone #cwSide[data-sheet=peek] > #cwLesson", ".cw-phone #cwSide > .cw-msg:not(:empty)"],
    watch: ["#cwSectionBar", "#cwHint", "#cwLesson", "#cwSide", "#cwEmpty"],
    panels: [
      { id: "tools", el: rail, label: "Tools", core: true, dock: true, def: function () { return { edge: "left", t: 0 }; }, resize: false, bare: true },
      { id: "tool", el: tool, core: true, dock: true, label: "Tool options", def: function () { return phone() ? { edge: "bottom", t: 0 } : { edge: "left", t: 0.2 }; } },
      { id: "quick", el: bl, label: "Quick buttons", dock: true, def: function () { return { edge: "bottom", t: 0 }; }, resize: false, bare: true },
      { id: "view", el: chips, label: "Grid & snap", dock: true, lead: true, def: function () { return { edge: "right", t: 0.46, hidden: phone() }; }, resize: false, bare: true },
      { id: "side", el: side, label: "History & items", dock: true, def: function () { return { edge: "right", t: 1 }; }, skip: function () { return PHONE.matches; } }
    ] });
  function layout() { if (ws) ws.layout(); }

  /* ---------- bottom sheet (right drawer in landscape) */
  var tabsRow = $(".cw-tabs", side), sheetBtn = $("#cwSheetBtn"), SNAP = ["peek", "half", "full"];
  function sheet(s) {
    if (!s) return side.dataset.sheet || "peek";
    side.dataset.sheet = s; side.style.removeProperty("--drag");
    if (sheetBtn) { sheetBtn.setAttribute("aria-expanded", s !== "peek"); sheetBtn.setAttribute("aria-label", s === "full" ? "Close History and Items" : "Show more of History and Items"); }
    layout();
  }
  if (sheetBtn) sheetBtn.addEventListener("click", function (e) { e.stopPropagation(); if (sheetBtn._drag) { sheetBtn._drag = false; return; } sheet(SNAP[(SNAP.indexOf(sheet()) + 1) % 3]); });
  ["#tabHist", "#tabItems"].forEach(function (s) { var b = $(s); if (b) b.addEventListener("click", function () { if (PHONE.matches && sheet() === "peek") sheet("half"); }); });
  if (tabsRow) {
    var sd = null;
    tabsRow.addEventListener("pointerdown", function (e) {
      if (!PHONE.matches) return; var r = side.getBoundingClientRect();
      sd = { x: e.clientX, y: e.clientY, size: land() ? r.width : r.height, moved: false, id: e.pointerId };
    });
    tabsRow.addEventListener("pointermove", function (e) {
      if (!sd) return; var d = land() ? sd.x - e.clientX : sd.y - e.clientY;
      if (!sd.moved && Math.abs(d) < 8) return;
      if (!sd.moved) { sd.moved = true; try { tabsRow.setPointerCapture(sd.id); } catch (er) {} side.classList.add("drag"); }
      var max = land() ? main.clientWidth : main.clientHeight;
      side.style.setProperty("--drag", Math.max(48, Math.min(max, sd.size + d)) + "px");
    });
    function sEnd(e) {
      if (!sd) return; var moved = sd.moved; sd = null; side.classList.remove("drag");
      if (!moved) { var tb = e && e.type === "pointerup" && e.target.closest && e.target.closest("[role=tab]");   // a tap on a tab in peek opens the sheet
        if (tb && sheet() === "peek") { tb.click(); if (sheet() === "peek") sheet("half"); } return; }
      var r = side.getBoundingClientRect(), max = land() ? main.clientWidth : main.clientHeight, v = (land() ? r.width : r.height) / max;
      sheet(v < 0.25 ? "peek" : v < 0.75 ? "half" : "full");
      if (sheetBtn) sheetBtn._drag = true; setTimeout(function () { if (sheetBtn) sheetBtn._drag = false; }, 50);
      var k = function (ev) { ev.stopPropagation(); ev.preventDefault(); }; tabsRow.addEventListener("click", k, true);
      setTimeout(function () { tabsRow.removeEventListener("click", k, true); }, 60);   // touch drags usually fire no click
    }
    tabsRow.addEventListener("pointerup", sEnd); tabsRow.addEventListener("pointercancel", sEnd);
  }
  var lesson = $("#cwLesson");
  var toolEl = $("#cwTool");
  // (a lesson card needs no open sheet: at peek it floats just above the tabs, see cad.css)
  // a tool opening on a phone wants the room: fold the sheet back to peek (the lesson card stays in view above the tabs)
  if (toolEl) new MutationObserver(function () { if (PHONE.matches && !toolEl.hidden && sheet() !== "peek") sheet("peek"); }).observe(toolEl, { attributes: true, attributeFilter: ["hidden"] });

  /* ---------- mode switch */
  function apply() {
    var on = PHONE.matches; document.body.classList.toggle("cw-phone", on);
    if (on) { if (fit && fit.parentElement !== bl) { fit._home = fit.parentElement; bl.prepend(fit); } if (!side.dataset.sheet) sheet("peek"); }
    else { if (fit && fit._home && fit.parentElement !== fit._home) fit._home.insertBefore(fit, fit._home.children[2] || null); homeUnits(); close(); }
    layout();
  }
  /* keyboard open / browser bars: size the page to what is actually visible */
  var vv = window.visualViewport;
  function vvFit() { if (vv && PHONE.matches) document.body.style.setProperty("--vvh", Math.round(vv.height) + "px"); else document.body.style.removeProperty("--vvh"); layout(); }
  if (vv) vv.addEventListener("resize", vvFit);
  PHONE.addEventListener ? PHONE.addEventListener("change", apply) : PHONE.addListener(apply);
  apply(); vvFit();
  window.zeimCadLayout = { layout: layout, sheet: sheet };
})();
