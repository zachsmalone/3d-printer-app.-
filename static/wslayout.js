/* ZEIM workspace layout (original code). The 3D view is the full background of a workspace; every panel and
   toolbar floats over it. Each one can be dragged anywhere, docked to any side, resized, minimised to a chip or
   hidden, per workspace, saved per user (local for guests; positions per orientation). "Customise workspace" lists
   every panel with a checkbox and has "Reset layout". Core panels (Undo, the tool menu, Export/Print) can't be hidden,
   and the Customise button itself is never inside a panel, so it stays reachable. Layout code only runs on
   change (drop / resize / rotate / keyboard), and a drag only moves the panel with a transform. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var EDGES = ["left", "bottom", "right", "top"], M = 8, SNAP = 48;
  var user = "guest", WS = {};
  try { fetch("/api/me", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (me) {
    var u = me && (me.user && (me.user.id || me.user.username) || me.id || me.username);
    if (u && String(u) !== user) { user = String(u); Object.keys(WS).forEach(function (k) { WS[k].load(); WS[k].layout(); }); } }).catch(function () {}); } catch (e) {}
  var land = function () { return innerWidth > innerHeight; };
  function rd(k) { try { return JSON.parse(localStorage.getItem(k)) || null; } catch (e) { return null; } }
  function wr(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function rel(el, b) { var a = el.getBoundingClientRect(); return { x: a.left - b.left, y: a.top - b.top, w: a.width, h: a.height }; }
  function hit(a, b) { return a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1; }
  var probe;
  function safe() {
    if (!probe) { probe = document.createElement("div"); probe.className = "zws-safe"; probe.setAttribute("aria-hidden", "true"); document.body.append(probe); }
    var c = getComputedStyle(probe); return { t: parseFloat(c.paddingTop) || 0, r: parseFloat(c.paddingRight) || 0, b: parseFloat(c.paddingBottom) || 0, l: parseFloat(c.paddingLeft) || 0 };
  }
  var ICON = { grip: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="7" r="1.4"/><circle cx="15" cy="7" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="17" r="1.4"/><circle cx="15" cy="17" r="1.4"/></svg>',
    min: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12"/></svg>', hide: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' };

  /* opts: {id, root, active()?, obstacles:[sel], panels:[{id, el, label, core, def:{edge,t}|{x,y}, resize, bare}], customise: element to append the button to} */
  function create(o) {
    var root = o.root, P = [], state = {}, on = false;
    var K = function () { return "zeim.ws." + user + "." + (o.key ? o.key() : o.id); };
    var KP = function () { return K() + "." + (land() ? "land" : "port"); };
    function load() { var a = rd(K()) || {}, b = rd(KP()) || {}; P.forEach(function (p) { state[p.id] = Object.assign({}, p.def, b[p.id] || {}, { hidden: !p.core && !!(a[p.id] ? a[p.id].hidden : p.def.hidden), min: !!(a[p.id] ? a[p.id].min : p.def.min) }); }); }
    function save() {
      var a = {}, b = {};
      P.forEach(function (p) { var s = state[p.id]; a[p.id] = { hidden: !!s.hidden, min: !!s.min }; b[p.id] = { edge: s.edge || null, t: s.t, x: s.x, y: s.y, w: s.w, h: s.h }; });
      wr(K(), a); wr(KP(), b);
    }
    function wrap(p) {
      var w = document.createElement("section"); w.className = "zws-p" + (p.bare ? " bare" : ""); w.id = "zws-" + p.id; w.dataset.panel = p.id; w.setAttribute("aria-label", p.label);
      w.innerHTML = '<div class="zws-head"><button type="button" class="zws-grip" aria-label="Move ' + p.label + ': drag it anywhere or to a side; Enter sends it to the next side">' + ICON.grip + '</button>' +
        '<button type="button" class="zws-chip" aria-label="' + p.label + ' (minimised): tap to open" title="' + p.label + '">' + p.label + '</button>' +
        '<span class="zws-t">' + p.label + '</span><button type="button" class="zws-min" aria-label="Minimise ' + p.label + '" title="Minimise">' + ICON.min + '</button>' +
        (p.core ? "" : '<button type="button" class="zws-hide" aria-label="Hide ' + p.label + ' (bring it back from Customise workspace)" title="Hide">' + ICON.hide + '</button>') + "</div>" +
        '<div class="zws-body"></div>' + (p.resize === false ? "" : '<div class="zws-rs" aria-hidden="true"></div>');
      p.w = w; p.body = w.querySelector(".zws-body"); p.home = p.el.parentElement; p.next = p.el.nextSibling;
      var g = w.querySelector(".zws-grip"), drag = null;
      g.addEventListener("pointerdown", function (e) { e.preventDefault(); e.stopPropagation(); try { g.setPointerCapture(e.pointerId); } catch (er) {} drag = { x: e.clientX, y: e.clientY, moved: false }; });
      g.addEventListener("pointermove", function (e) { if (!drag) return; var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 6) return; drag.moved = true; w.classList.add("drag"); w.style.transform = "translate(" + dx + "px," + dy + "px)"; });
      function end(e) {
        if (!drag) return; var moved = drag.moved; drag = null; if (!moved) return; p.justDragged = true;
        var rr = root.getBoundingClientRect(), r = w.getBoundingClientRect(); w.style.transform = ""; w.classList.remove("drag");
        var bx = lastBox || { x: 0, y: 0, w: rr.width, h: rr.height }, px = e.clientX - rr.left, py = e.clientY - rr.top;
        var d = { left: px - bx.x, right: bx.x + bx.w - px, top: py - bx.y, bottom: bx.y + bx.h - py };
        var edge = Object.keys(d).sort(function (a, b) { return d[a] - d[b]; })[0], s = state[p.id];
        if (d[edge] < SNAP) { s.edge = edge; var vert = edge === "left" || edge === "right"; s.t = Math.max(0, Math.min(1, vert ? (py - bx.y) / bx.h : (px - bx.x) / bx.w)); }
        else { s.edge = null; s.x = Math.max(0, (r.left - rr.left) / rr.width); s.y = Math.max(0, (r.top - rr.top) / rr.height); }
        save(); layout();
      }
      g.addEventListener("pointerup", end); g.addEventListener("pointercancel", end);
      g.addEventListener("click", function () { if (p.justDragged) { p.justDragged = false; return; } var s = state[p.id]; s.edge = EDGES[(EDGES.indexOf(s.edge || "top") + 1) % 4]; s.t = s.t || 0; save(); layout(); g.focus(); });
      w.querySelector(".zws-min").onclick = function () { state[p.id].min = true; save(); layout(); w.querySelector(".zws-chip").focus(); };
      w.querySelector(".zws-chip").onclick = function () { if (p.justDragged) { p.justDragged = false; return; } p.pri = Date.now(); state[p.id].min = false; save(); layout(); };
      var hb = w.querySelector(".zws-hide"); if (hb) hb.onclick = function () { setHidden(p.id, true); };
      var rs = w.querySelector(".zws-rs");
      if (rs) { var rz = null;
        rs.addEventListener("pointerdown", function (e) { e.preventDefault(); e.stopPropagation(); rs.setPointerCapture(e.pointerId); var r = w.getBoundingClientRect(); rz = { x: e.clientX, y: e.clientY, w: r.width, h: r.height }; });
        rs.addEventListener("pointermove", function (e) { if (!rz) return; w.style.width = Math.max(120, rz.w + e.clientX - rz.x) + "px"; w.style.maxHeight = w.style.height = Math.max(64, rz.h + e.clientY - rz.y) + "px"; });
        var re = function () { if (!rz) return; rz = null; var r = w.getBoundingClientRect(), s = state[p.id]; s.w = Math.round(r.width); s.h = Math.round(r.height); save(); layout(); };
        rs.addEventListener("pointerup", re); rs.addEventListener("pointercancel", re); }
    }
    function rekey() { load(); layout(); }
    function setHidden(id, h) { var p = P.find(function (x) { return x.id === id; }); if (!p || p.core && h) return false; state[id].hidden = !!h; if (!h) { state[id].min = false; p.pri = Date.now(); } save(); layout(); return true; }
    function home(p) { if (p.el.parentElement === p.body) { p.home.insertBefore(p.el, p.next && p.next.parentNode === p.home ? p.next : null); p.w.remove(); } }
    function mount() { var fa = document.activeElement; P.forEach(function (p) { if (p.skip && p.skip()) return home(p); if (p.el.parentElement !== p.body) { p.body.append(p.el); root.append(p.w); } }); if (!on) root.classList.add("zws"); on = true; refocus(fa); }
    function unmount() { var fa = document.activeElement; P.forEach(function (p) { if (p.el.parentElement === p.body) { p.home.insertBefore(p.el, p.next && p.next.parentNode === p.home ? p.next : null); p.w.remove(); } }); root.classList.remove("zws"); on = false; refocus(fa); }
    function refocus(fa) { if (fa && fa !== document.body && fa.isConnected && document.activeElement !== fa) try { fa.focus({ preventScroll: true }); } catch (e) {} }   // moving a node drops focus: keep it
    function obstacles(rr) {
      var out = []; (o.obstacles || []).forEach(function (s) { document.querySelectorAll(s).forEach(function (el) {
        if (el.hidden || !el.getClientRects().length || el.closest(".zws-p")) return; var r = rel(el, rr); if (r.w && r.h) out.push({ x: r.x - 4, y: r.y - 4, w: r.w + 8, h: r.h + 8 }); }); });
      return out;
    }
    function place(p, s, box, obs) {
      var w = p.w, vert = s.edge === "left" || s.edge === "right";
      w.classList.toggle("v", !!s.edge && vert); w.classList.toggle("h", !!s.edge && !vert); w.dataset.edge = s.edge || "free"; w.classList.toggle("free", !s.edge);
      w.style.left = w.style.top = "0px"; w.style.width = s.w && !s.min ? Math.min(s.w, box.w) + "px" : ""; w.style.height = "";
      w.style.maxWidth = box.w + "px"; w.style.maxHeight = (s.h && !s.min ? Math.min(s.h, box.h) : box.h) + "px";
      var r0 = w.getBoundingClientRect(), W = Math.min(r0.width, box.w), H = Math.min(r0.height, box.h);
      function cands(edge, t, W, H) {
        var out = [], L = edge ? (edge === "left" || edge === "right" ? box.h - H : box.w - W) : 0, p0 = Math.round(Math.max(0, Math.min(1, t || 0)) * Math.max(0, L));
        if (!edge) { var x0 = box.x + Math.min(box.w - W, Math.max(0, (s.x || 0) * (box.w + 2 * M))), y0 = box.y + Math.min(box.h - H, Math.max(0, (s.y || 0) * (box.h + 2 * M)));
          for (var d = 0; d < Math.max(box.w, box.h); d += 8) [[0, d], [d, 0], [0, -d], [-d, 0]].forEach(function (k) { var x = x0 + k[0], y = y0 + k[1]; if (x >= box.x && y >= box.y && x + W <= box.x + box.w + .5 && y + H <= box.y + box.h + .5) out.push({ x: x, y: y, w: W, h: H }); });
          return out; }
        for (var dd = 0; dd <= L; dd += 4) [p0 - dd, p0 + dd].forEach(function (q) { if (q < 0 || q > L) return;
          out.push(edge === "left" ? { x: box.x, y: box.y + q, w: W, h: H } : edge === "right" ? { x: box.x + box.w - W, y: box.y + q, w: W, h: H } : edge === "top" ? { x: box.x + q, y: box.y, w: W, h: H } : { x: box.x + q, y: box.y + box.h - H, w: W, h: H }); });
        return out;
      }
      var order = [s.edge].concat(EDGES.filter(function (e) { return e !== s.edge; })), shrink = [1, .75, .55, .4];
      function fit(e, k, first) {
        var v = e === "left" || e === "right", Wk = W, Hk = H;
        if (!first && e) { w.classList.toggle("v", v); w.classList.toggle("h", !v); w.dataset.edge = e; var r1 = w.getBoundingClientRect(); Wk = Math.min(r1.width, box.w); Hk = Math.min(r1.height, box.h); }
        // a toolbar only gets shorter along its length; a panel shrinks both ways (its body scrolls)
        if (!e || v || !p.bare) Hk = Math.max(Math.min(Hk, 96), Hk * shrink[k]);
        if (e && (!v || !p.bare)) Wk = Math.max(Math.min(Wk, 120), Wk * shrink[k]);
        var c = cands(e, first ? s.t : 0, Wk, Hk).find(function (r) { return !obs.some(function (b) { return hit(r, b); }); });
        if (c) { w.style.left = c.x + "px"; w.style.top = c.y + "px"; if (Hk < H || e && v) w.style.maxHeight = Hk + "px"; if (Wk < W || e && !v) w.style.maxWidth = Wk + "px"; }
        return c;
      }
      for (var i = 0; i < order.length; i++) { for (var k = 0; k < shrink.length; k++) { var c = fit(order[i], k, !i); if (c) return c; if (!order[i]) break; } }
      if (!s.min) {   // still no room: show it as a chip for now (not saved), tap opens it (a core panel too, rather than lying on top of the panel just opened)
        w.classList.add("min", "auto-min"); w.classList.toggle("v", !!s.edge && vert); w.classList.toggle("h", !!s.edge && !vert); w.dataset.edge = s.edge || "free"; w.style.maxWidth = box.w + "px"; w.style.maxHeight = box.h + "px"; W = Math.min(w.getBoundingClientRect().width, box.w); H = Math.min(w.getBoundingClientRect().height, box.h);
        for (var j = 0; j < order.length; j++) { var c2 = fit(order[j], 0, !j); if (c2) return c2; }
        var c3 = cands("", 0, W, H).find(function (r) { return !obs.some(function (b) { return hit(r, b); }); });   // anywhere free
        if (c3) { w.classList.add("free"); w.style.left = c3.x + "px"; w.style.top = c3.y + "px"; return c3; }
        if (p.core) { w.classList.remove("min", "auto-min", "free"); w.style.maxWidth = w.style.maxHeight = ""; var r0 = w.getBoundingClientRect(); W = Math.min(r0.width, box.w); H = Math.min(r0.height, box.h); }   // a core panel never steps aside
        else { w.classList.add("auto-off"); return { x: 0, y: 0, w: 0, h: 0 }; }   // truly no room (a big tool panel is open): step aside until there is
      }
      w.classList.toggle("v", !!s.edge && vert); w.classList.toggle("h", !!s.edge && !vert); w.dataset.edge = s.edge || "free";   // undo the trial edges' classes
      var f = cands(s.edge, s.t, W, H)[0] || { x: box.x, y: box.y, w: W, h: H }; w.style.left = f.x + "px"; w.style.top = f.y + "px"; w.dataset.crowded = "1"; return f;
    }
    var queued = false, lastBox = null, api_watch = null;
    function layout() { if (queued) return; queued = true; Promise.resolve().then(function () { queued = false; doLayout(); }); }   // before the next paint: no frame with a panel on top of another
    function doLayout() {
      var want = !o.active || o.active(); if (want) mount(); else if (on) unmount(); if (!on) return;
      if (o.before) o.before(); if (api_watch) api_watch();
      var rr = root.getBoundingClientRect(), sa = safe(), vv = window.visualViewport;
      var bottom = vv ? Math.min(rr.height, vv.height + vv.offsetTop - rr.top) : rr.height;   // keyboard open: stay above it
      var box = { x: M + sa.l, y: M + Math.max(0, sa.t - rr.top), w: rr.width - 2 * M - sa.l - sa.r, h: Math.max(120, bottom - 2 * M - Math.max(0, sa.t - rr.top) - (rr.bottom >= innerHeight - 1 ? sa.b : 0)) };
      if (o.inset) { var ins = o.inset(); box.x += ins.l || 0; box.y += ins.t || 0; box.w -= (ins.l || 0) + (ins.r || 0); box.h -= (ins.t || 0) + (ins.b || 0); }
      lastBox = box; var obs = obstacles(rr);
      P.slice().sort(function (a, b) { return (b.pri || 0) - (a.pri || 0) || (b.core ? 1 : 0) - (a.core ? 1 : 0); }).forEach(function (p) {
        if (p.skip && p.skip()) return;
        var s = state[p.id]; p.w.hidden = !!s.hidden || p.el.hidden; p.w.classList.toggle("min", !!s.min); p.w.classList.remove("auto-min", "auto-off"); p.w.dataset.crowded = "";
        if (p.w.hidden) return; obs.push(pad(place(p, s, box, obs)));
      });
      root.dispatchEvent(new CustomEvent("zws:layout"));
    }
    function pad(r) { return { x: r.x - 3, y: r.y - 3, w: r.w + 6, h: r.h + 6 }; }
    function reset() { wr(K(), null); wr(KP(), null); wr(K() + "." + (land() ? "port" : "land"), null); P.forEach(function (p) { if (p.w) { p.w.style.width = p.w.style.height = ""; } }); load(); layout(); }

    /* Customise workspace */
    var dlg = document.createElement("dialog"); dlg.className = "zws-dlg"; dlg.id = "zwsDlg-" + o.id; dlg.setAttribute("aria-label", "Customise workspace");
    function fillDlg() {
      dlg.innerHTML = '<form method="dialog"><h2>Customise workspace' + (o.title ? ": " + (typeof o.title === "function" ? o.title() : o.title) : "") + '</h2><p class="help">Show or hide each panel here. Drag a panel by its grip to move it or dock it to any side.</p><ul class="zws-list">' +
        P.map(function (p) { return '<li><label><input type="checkbox" data-zws="' + p.id + '"' + (state[p.id].hidden ? "" : " checked") + (p.core ? " disabled" : "") + "> " + p.label + (p.core ? ' <small>(always shown)</small>' : "") + "</label></li>"; }).join("") +
        '</ul><div class="zws-row"><button type="button" class="btn" data-zws-reset>Reset layout</button><button class="btn primary" value="ok">Done</button></div></form>';
      dlg.querySelectorAll("input[data-zws]").forEach(function (c) { c.onchange = function () { setHidden(c.dataset.zws, !c.checked); }; });
      dlg.querySelector("[data-zws-reset]").onclick = function () { reset(); fillDlg(); };
    }
    document.body.append(dlg);
    var btn = document.createElement("button"); btn.type = "button"; btn.className = (o.btnClass || "btn small") + " zws-cust"; btn.id = "zwsCust-" + o.id;
    btn.setAttribute("aria-haspopup", "dialog"); btn.title = "Customise workspace: show, hide, move panels; reset layout"; btn.setAttribute("aria-label", "Customise workspace");
    btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg><span class="lbl">Customise</span>';
    btn.onclick = function () { open(); };
    function open() { fillDlg(); dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", ""); }
    if (o.customise) o.customise.append(btn);
    if (o.title) dlg.dataset.title = o.title;
    (o.panels || []).forEach(function (p) { if (p.el) { P.push(p); wrap(p); } });
    load();
    var ro = new ResizeObserver(layout); ro.observe(root); P.forEach(function (p) { ro.observe(p.el); new MutationObserver(function () { var h = !!state[p.id].hidden || p.el.hidden; if (p.w.hidden !== h) p.w.hidden = h; layout(); }).observe(p.el, { attributes: true, attributeFilter: ["hidden"] }); });
    addEventListener("resize", layout); addEventListener("orientationchange", function () { load(); setTimeout(layout, 150); });
    matchMedia("(orientation: landscape)").addEventListener("change", function () { load(); layout(); });
    if (window.visualViewport) visualViewport.addEventListener("resize", layout);
    /* an obstacle (e.g. the "Making your model" overlay) showing pushes panels aside; it going away must bring them
       back, so watch each obstacle too (the selector's :not(...) part is dropped so a hidden one is still found) */
    var watched = [];
    function watchObstacles() { (o.obstacles || []).forEach(function (s) { document.querySelectorAll(s.replace(/:not\([^)]*\)/g, "")).forEach(function (el) {
      if (watched.indexOf(el) >= 0) return; watched.push(el); new MutationObserver(layout).observe(el, { attributes: true, attributeFilter: ["hidden", "class", "style"] }); }); }); }
    watchObstacles(); api_watch = watchObstacles;
    (o.watch || []).forEach(function (s) { var el = $(s); if (el) new MutationObserver(layout).observe(el, { attributes: true, attributeFilter: ["hidden", "class", "style", "data-sheet"], childList: !!o.watchChildren }); });
    layout();
    var api = { id: o.id, layout: layout, reset: reset, open: open, setHidden: setHidden, state: function () { return JSON.parse(JSON.stringify(state)); }, load: load, rekey: rekey, button: btn, panels: P };
    WS[o.id] = api; return api;
  }
  window.ZWS = { create: create, all: WS };
})();
