/* ZEIM workspace layout (original code). The 3D view is the full background of a workspace; panels sit over
   it, docked to a side. A panel marked dock slides along its edge and cannot be left floating. Exit, Done,
   New build, Return to Account, and the primary action stay in a top strip that layout will not use, and a
   drag cannot move a panel into that strip. "Customise workspace" lists every panel with a checkbox and has
   "Reset layout". Core panels (Undo, the tool menu, Export/Print) can't be hidden. The Customise button
   sits in the top strip when that strip is there, and is never inside a panel, so it stays reachable.
   Layout code only runs on change (drop / resize / rotate / keyboard), and a drag only moves the panel
   with a transform.
   Open panels stay at their real size. Layout moves them off obstacles and off each other. It does not walk a
   ladder of smaller sizes, minimise, or hide a panel to make room. If a full-size slot does not exist, one
   shared height cap gives every open panel a usable band (the saved size is left alone). Reset drops every
   saved orientation and applies the defaults for the breakpoint on screen now. Creating a workspace again
   removes the previous listeners and observers. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var EDGES = ["left", "bottom", "right", "top"], M = 8, SNAP = 48;
  var PHONE_Q = "(max-width:820px), (max-height:500px) and (pointer:coarse)";
  var user = "guest", WS = {};
  try { fetch("/api/me", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (me) {
    var u = me && (me.user && (me.user.id || me.user.username) || me.id || me.username);
    if (u && String(u) !== user) { user = String(u); Object.keys(WS).forEach(function (k) { WS[k].load(); WS[k].layout(); }); } }).catch(function () {}); } catch (e) {}
  var land = function () { return innerWidth > innerHeight; };
  function rd(k) { try { return JSON.parse(localStorage.getItem(k)) || null; } catch (e) { return null; } }
  function wr(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function rel(el, b) { var a = el.getBoundingClientRect(); return { x: a.left - b.left, y: a.top - b.top, w: a.width, h: a.height }; }
  function hit(a, b) { return a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1; }
  function overlaps(r, obs) { for (var i = 0; i < obs.length; i++) if (hit(r, obs[i])) return true; return false; }
  function uniq(nums) {
    return nums.slice().sort(function (a, b) { return a - b; }).filter(function (n, i, a) { return !i || n - a[i - 1] > 0.5; });
  }
  /* Free rectangles inside box after subtracting obstacles. A gap keeps its full height where the
     same x-range stays clear, so a side panel is not cut down to a neighbour's shorter strip. */
  function freeRects(box, obs) {
    var ys = [box.y, box.y + box.h];
    obs.forEach(function (o) {
      var t = Math.max(box.y, o.y), b = Math.min(box.y + box.h, o.y + o.h);
      if (b - t > 0.5) { ys.push(t, b); }
    });
    ys = uniq(ys);
    var rows = [];
    for (var i = 0; i < ys.length - 1; i++) {
      var y1 = ys[i], y2 = ys[i + 1];
      if (y2 - y1 < 1) continue;
      var mid = (y1 + y2) / 2, spans = [];
      obs.forEach(function (o) {
        if (o.y < mid && o.y + o.h > mid) {
          var x1 = Math.max(box.x, o.x), x2 = Math.min(box.x + box.w, o.x + o.w);
          if (x2 - x1 > 0.5) spans.push([x1, x2]);
        }
      });
      spans.sort(function (a, b) { return a[0] - b[0]; });
      var merged = [], gaps = [], x = box.x;
      spans.forEach(function (sp) {
        if (!merged.length || sp[0] > merged[merged.length - 1][1] + 0.5) merged.push([sp[0], sp[1]]);
        else merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], sp[1]);
      });
      merged.forEach(function (sp) {
        if (sp[0] - x > 1) gaps.push([x, sp[0]]);
        if (sp[1] > x) x = sp[1];
      });
      if (box.x + box.w - x > 1) gaps.push([x, box.x + box.w]);
      rows.push({ y: y1, h: y2 - y1, gaps: gaps });
    }
    var out = [];
    rows.forEach(function (row, r) {
      row.gaps.forEach(function (g) {
        var h = row.h;
        for (var k = r + 1; k < rows.length; k++) {
          var still = rows[k].gaps.some(function (ng) { return ng[0] <= g[0] + 0.5 && ng[1] >= g[1] - 0.5; });
          if (!still) break;
          h += rows[k].h;
        }
        out.push({ x: g[0], y: row.y, w: g[1] - g[0], h: h });
      });
    });
    return out.filter(function (a, i) {
      return !out.some(function (b, j) {
        return j !== i && b.x <= a.x + 0.5 && b.y <= a.y + 0.5 && b.x + b.w + 0.5 >= a.x + a.w && b.y + b.h + 0.5 >= a.y + a.h && b.w * b.h > a.w * a.h + 1;
      });
    });
  }
  var probe;
  function safe() {
    if (!probe) { probe = document.createElement("div"); probe.className = "zws-safe"; probe.setAttribute("aria-hidden", "true"); document.body.append(probe); }
    var c = getComputedStyle(probe); return { t: parseFloat(c.paddingTop) || 0, r: parseFloat(c.paddingRight) || 0, b: parseFloat(c.paddingBottom) || 0, l: parseFloat(c.paddingLeft) || 0 };
  }
  var ICON = { grip: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="7" r="1.4"/><circle cx="15" cy="7" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="17" r="1.4"/><circle cx="15" cy="17" r="1.4"/></svg>',
    min: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12"/></svg>', hide: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' };

  /* opts: {id, root, active()?, obstacles:[sel], panels:[{id, el, label, core, def:{edge,t}|{x,y}|function, resize, bare}], customise: element to append the button to} */
  function create(o) {
    if (WS[o.id] && WS[o.id].destroy) WS[o.id].destroy();
    var root = o.root, P = [], state = {}, on = false, gesture = 0, epoch = 0, orientTimer = 0, laying = false, again = false;
    var drop = [], obsers = [];
    var K = function () { return "zeim.ws." + user + "." + (o.key ? o.key() : o.id); };
    var KP = function () { return K() + "." + (land() ? "land" : "port"); };
    function currentDef(p) {
      try { var d = typeof p.def === "function" ? p.def() : p.def; return d && typeof d === "object" ? d : {}; }
      catch (e) { return {}; }
    }
    function listen(target, type, fn, opt) {
      if (!target) return;
      if (target.addEventListener) {
        target.addEventListener(type, fn, opt);
        drop.push(function () { try { target.removeEventListener(type, fn, opt); } catch (e) {} });
      } else if (target.addListener && type === "change") {
        target.addListener(fn);
        drop.push(function () { try { target.removeListener(fn); } catch (e) {} });
      }
    }
    function track(ob) { obsers.push(ob); return ob; }
    function load() {
      var a = rd(K()) || {}, b = rd(KP()) || {};
      P.forEach(function (p) {
        var def = currentDef(p), saved = b[p.id] || {}, pos = {};
        ["edge", "t", "x", "y", "userSize"].forEach(function (k) { if (saved[k] !== undefined) pos[k] = saved[k]; });
        if (saved.userSize) { pos.w = saved.w; pos.h = saved.h; }
        state[p.id] = Object.assign({}, def, pos, {
          hidden: !p.core && !!(a[p.id] ? a[p.id].hidden : def.hidden),
          min: !!(a[p.id] ? a[p.id].min : def.min)
        });
      });
    }
    function save() {
      var a = {}, b = {};
      P.forEach(function (p) {
        var s = state[p.id], def = currentDef(p);
        a[p.id] = { hidden: !!s.hidden, min: !!s.min };
        b[p.id] = { edge: s.userSize ? null : (s.edge || null), t: s.t, x: s.x, y: s.y, userSize: !!s.userSize };
        if (s.userSize) { b[p.id].w = s.w; b[p.id].h = s.h; }
        else { if (def.w != null) b[p.id].w = def.w; if (def.h != null) b[p.id].h = def.h; }
      });
      wr(K(), a); wr(KP(), b);
    }
    function dockSize(p, s) {
      var def = currentDef(p);
      s.userSize = false; s.w = def.w; s.h = def.h;
    }
    function wrap(p) {
      var w = document.createElement("section"); w.className = "zws-p" + (p.bare ? " bare" : ""); w.id = "zws-" + p.id; w.dataset.panel = p.id; w.setAttribute("aria-label", p.label);
      w.innerHTML = '<div class="zws-head"><button type="button" class="zws-grip" aria-label="Move ' + p.label + ': drag it anywhere or to a side; Enter sends it to the next side">' + ICON.grip + '</button>' +
        '<button type="button" class="zws-chip" aria-label="' + p.label + ' (minimised): tap to open" title="' + p.label + '">' + p.label + '</button>' +
        '<span class="zws-t">' + p.label + '</span><button type="button" class="zws-min" aria-label="Minimise ' + p.label + '" title="Minimise">' + ICON.min + '</button>' +
        (p.core ? "" : '<button type="button" class="zws-hide" aria-label="Remove ' + p.label + ' (bring it back from Customise workspace)" title="Remove">' + ICON.hide + '</button>') + "</div>" +
        '<div class="zws-body"></div>' + (p.resize === false ? "" : '<div class="zws-rs" data-dir="se" aria-hidden="true"></div><div class="zws-edge" data-dir="e" aria-hidden="true"></div><div class="zws-edge" data-dir="s" aria-hidden="true"></div><div class="zws-edge" data-dir="w" aria-hidden="true"></div><div class="zws-edge" data-dir="n" aria-hidden="true"></div>');
      p.w = w; p.body = w.querySelector(".zws-body"); p.home = p.el.parentElement; p.next = p.el.nextSibling;
      var g = w.querySelector(".zws-grip"), drag = null;
      if (p.dock) g.setAttribute("aria-label", "Move " + p.label + ": drag along its edge. It stays off Exit. Enter sends it to the next side");
      g.addEventListener("pointerdown", function (e) { e.preventDefault(); e.stopPropagation(); try { g.setPointerCapture(e.pointerId); } catch (er) {} interacting = true; drag = { x: e.clientX, y: e.clientY, moved: false, g: gesture, l: w.offsetLeft, t: w.offsetTop, w: w.offsetWidth, h: w.offsetHeight }; });
      g.addEventListener("pointermove", function (e) {
        if (!drag) return;
        var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 6) return;
        drag.moved = true; w.classList.add("drag");
        var rr = root.getBoundingClientRect(), box = lastBox || { x: 0, y: 0, w: rr.width, h: rr.height };
        var nx = drag.l + dx, ny = drag.t + dy, edgeNow = (state[p.id] && state[p.id].edge) || "";
        if (p.dock && (edgeNow === "left" || edgeNow === "right")) nx = drag.l;
        else if (p.dock && (edgeNow === "top" || edgeNow === "bottom")) ny = drag.t;
        var maxX = box.x + Math.max(0, box.w - drag.w), maxY = box.y + Math.max(0, box.h - drag.h);
        nx = Math.max(box.x, Math.min(maxX, nx)); ny = Math.max(box.y, Math.min(maxY, ny));
        w.style.transform = "translate(" + (nx - drag.l) + "px," + (ny - drag.t) + "px)";
      });
      function end(e) {
        if (!drag) { interacting = false; return; }
        var moved = drag.moved, token = drag.g; drag = null; interacting = false;
        if (!moved || token !== gesture) return;
        p.justDragged = true;
        var rr = root.getBoundingClientRect(), r = w.getBoundingClientRect(); w.style.transform = ""; w.classList.remove("drag");
        var bx = lastBox || { x: 0, y: 0, w: rr.width, h: rr.height }, px = e.clientX - rr.left, py = e.clientY - rr.top;
        var d = { left: px - bx.x, right: bx.x + bx.w - px, top: py - bx.y, bottom: bx.y + bx.h - py };
        var edge = Object.keys(d).sort(function (a, b) { return d[a] - d[b]; })[0], s = state[p.id];
        if (p.dock && d[edge] >= SNAP) edge = s.edge || edge;
        if (p.dock || d[edge] < SNAP) { s.edge = edge; dockSize(p, s); var vert = edge === "left" || edge === "right"; s.t = Math.max(0, Math.min(1, vert ? (py - bx.y) / Math.max(1, bx.h) : (px - bx.x) / Math.max(1, bx.w))); }
        else { s.edge = null; s.x = Math.max(0, (r.left - rr.left) / rr.width); s.y = Math.max(0, (r.top - rr.top) / rr.height); if (s.userSize) { s.w = Math.round(r.width); s.h = Math.round(r.height); } else dockSize(p, s); }
        save(); layout();
      }
      g.addEventListener("pointerup", end); g.addEventListener("pointercancel", end);
      g.addEventListener("click", function () { if (p.justDragged) { p.justDragged = false; return; } var s = state[p.id]; dockSize(p, s); s.edge = EDGES[(EDGES.indexOf(s.edge || "top") + 1) % 4]; s.t = s.t || 0; save(); layout(); g.focus(); });
      w.querySelector(".zws-min").onclick = function () { state[p.id].min = true; save(); layout(); w.querySelector(".zws-chip").focus(); };
      w.querySelector(".zws-chip").onclick = function () { if (p.justDragged) { p.justDragged = false; return; } p.pri = p.chipPri = Date.now(); state[p.id].min = false; save(); layout(); };
      var hb = w.querySelector(".zws-hide"); if (hb) hb.onclick = function () { setHidden(p.id, true); };
      w.querySelectorAll("[data-dir]").forEach(function (el) {
        var dir = el.dataset.dir, rz = null;
        el.addEventListener("pointerdown", function (e) { e.preventDefault(); e.stopPropagation(); try { el.setPointerCapture(e.pointerId); } catch (er) {} interacting = true; var r = w.getBoundingClientRect(); rz = { x: e.clientX, y: e.clientY, l: r.left, t: r.top, w: r.width, h: r.height, g: gesture }; });
        el.addEventListener("pointermove", function (e) {
          if (!rz) return;
          var dx = e.clientX - rz.x, dy = e.clientY - rz.y, L = rz.l, T = rz.t, W = rz.w, H = rz.h, rr = root.getBoundingClientRect();
          var box = lastBox || { x: 0, y: 0, w: rr.width, h: rr.height };
          var minL = rr.left + box.x, minT = rr.top + box.y, maxR = minL + box.w, maxB = minT + box.h;
          if (dir.indexOf("e") >= 0) W = rz.w + dx;
          if (dir.indexOf("s") >= 0) H = rz.h + dy;
          if (dir.indexOf("w") >= 0) { W = rz.w - dx; L = rz.l + rz.w - W; }
          if (dir.indexOf("n") >= 0) { H = rz.h - dy; T = rz.t + rz.h - H; }
          W = Math.max(160, W); H = Math.max(120, H);
          if (L < minL) { W -= minL - L; L = minL; }
          if (T < minT) { H -= minT - T; T = minT; }
          if (L + W > maxR) W = Math.max(160, maxR - L);
          if (T + H > maxB) H = Math.max(120, maxB - T);
          w.style.left = (L - rr.left) + "px"; w.style.top = (T - rr.top) + "px";
          w.style.width = W + "px"; w.style.height = H + "px"; w.style.maxWidth = W + "px"; w.style.maxHeight = H + "px";
        });
        var re = function () {
          if (!rz) return; var token = rz.g; rz = null; interacting = false; if (token !== gesture) return;
          var r = w.getBoundingClientRect(), rr = root.getBoundingClientRect(), s = state[p.id];
          s.userSize = true; s.w = Math.round(r.width); s.h = Math.round(r.height);
          if (p.dock) s.edge = s.edge || currentDef(p).edge || "left";
          else s.edge = null;
          s.x = Math.max(0, (r.left - rr.left) / Math.max(1, rr.width)); s.y = Math.max(0, (r.top - rr.top) / Math.max(1, rr.height));
          save(); layout();
        };
        el.addEventListener("pointerup", re); el.addEventListener("pointercancel", re);
      });
    }
    function rekey() { load(); layout(); }
    function setHidden(id, h) { var p = P.find(function (x) { return x.id === id; }); if (!p || p.core && h) return false; state[id].hidden = !!h; if (p.w) p.w.hidden = !!h || !!p.el.hidden; if (!h) { state[id].min = false; p.pri = Date.now(); } save(); layout(); return true; }
    function home(p) { if (!p.w || p.el.parentElement !== p.body) return; if (p.home) p.home.insertBefore(p.el, p.next && p.next.parentNode === p.home ? p.next : null); p.w.remove(); }
    function mount() { var fa = document.activeElement; P.forEach(function (p) { if (p.skip && p.skip()) return home(p); if (p.el.parentElement !== p.body) { p.body.append(p.el); root.append(p.w); } }); if (!on) root.classList.add("zws"); on = true; refocus(fa); }
    function unmount() { var fa = document.activeElement; P.forEach(function (p) { if (p.el.parentElement === p.body) { p.home.insertBefore(p.el, p.next && p.next.parentNode === p.home ? p.next : null); p.w.remove(); } }); root.classList.remove("zws"); on = false; refocus(fa); }
    function refocus(fa) { if (fa && fa !== document.body && fa.isConnected && document.activeElement !== fa) try { fa.focus({ preventScroll: true }); } catch (e) {} }   // moving a node drops focus: keep it
    function obstacles(rr) {
      var out = []; (o.obstacles || []).forEach(function (s) { document.querySelectorAll(s).forEach(function (el) {
        if (el.hidden || !el.getClientRects().length || el.closest(".zws-p")) return; var r = rel(el, rr); if (r.w && r.h) out.push({ x: r.x - 4, y: r.y - 4, w: r.w + 8, h: r.h + 8 }); }); });
      return out;
    }
    /* Top strip: Exit and the primary action. Bottom strip: the object-tool dock and the process sheet.
       Only elements already sitting in that band count, so a mid-right view control is not treated as a header. */
    function chromeBand(rr, sel, top) {
      var edge = 0;
      root.querySelectorAll(sel).forEach(function (el) {
        if (el.hidden || !el.getClientRects().length) return;
        var r = rel(el, rr);
        if (r.w < 1 || r.h < 1) return;
        if (top) { if (r.y < 140) edge = Math.max(edge, r.y + r.h); }
        else if (r.y > rr.height * 0.25) edge = Math.max(edge, rr.height - r.y);
      });
      return edge;
    }
    function place(p, s, box, obs, share, openCount) {
      if (p.dock && !s.edge) s.edge = currentDef(p).edge || "left";
      var w = p.w;
      w.dataset.crowded = ""; w.dataset.fit = ""; w.dataset.blocked = "";
      w.classList.remove("auto-min", "auto-off");
      function shareLimit(total, floor) {
        var n = Math.max(1, openCount || 1), usable = Math.floor(total / n);
        return Math.min(total, Math.max(floor, usable));
      }
      function applyEdge(edge) {
        if (s.userSize && !s.min && !p.dock) {
          w.classList.add("user-size", "free"); w.classList.remove("v", "h", "auto-min", "auto-off"); w.dataset.edge = "free"; return;
        }
        var vert = edge === "left" || edge === "right";
        w.classList.remove("user-size", "auto-min", "auto-off");
        w.classList.toggle("v", !!edge && vert); w.classList.toggle("h", !!edge && !vert); w.classList.toggle("free", !edge);
        w.dataset.edge = edge || "free";
      }
      function measureEdge(edge) {
        applyEdge(edge);
        w.style.left = "0px"; w.style.top = "0px";
        if (s.userSize && !s.min) {
          var Wu = Math.max(1, Math.min(Math.max(160, s.w || 220), box.w));
          var Hu = Math.max(1, Math.min(Math.max(120, s.h || 180), box.h));
          if (share) { Wu = Math.min(Wu, shareLimit(box.w, 160)); Hu = Math.min(Hu, shareLimit(box.h, 120)); }
          w.style.width = Wu + "px"; w.style.height = Hu + "px"; w.style.maxWidth = Wu + "px"; w.style.maxHeight = Hu + "px";
          return { W: Wu, H: Hu };
        }
        var maxW = box.w, maxH = box.h;
        if (share) { maxW = shareLimit(box.w, p.bare ? 44 : 160); maxH = shareLimit(box.h, p.bare ? 48 : 120); }
        if (!s.min && s.w) maxW = Math.min(maxW, s.w);
        if (!s.min && s.h) maxH = Math.min(maxH, s.h);
        w.style.width = !s.min && s.w ? Math.min(s.w, maxW) + "px" : "";
        w.style.height = "";
        w.style.maxWidth = Math.max(1, maxW) + "px";
        w.style.maxHeight = Math.max(1, maxH) + "px";
        var r = w.getBoundingClientRect();
        return { W: Math.min(box.w, Math.max(1, r.width || 44)), H: Math.min(box.h, Math.max(1, r.height || 44)) };
      }
      function cands(edge, t, W, H) {
        var out = [], L = edge ? (edge === "left" || edge === "right" ? box.h - H : box.w - W) : 0, p0 = Math.round(Math.max(0, Math.min(1, t || 0)) * Math.max(0, L));
        if (L < 0) L = 0;
        if (!edge) {
          var x0 = box.x + Math.min(Math.max(0, box.w - W), Math.max(0, (s.x || 0) * box.w));
          var y0 = box.y + Math.min(Math.max(0, box.h - H), Math.max(0, (s.y || 0) * box.h));
          for (var d = 0; d < Math.max(box.w, box.h); d += 8) [[0, d], [d, 0], [0, -d], [-d, 0]].forEach(function (k) {
            var x = x0 + k[0], y = y0 + k[1];
            if (x >= box.x - 0.5 && y >= box.y - 0.5 && x + W <= box.x + box.w + 0.5 && y + H <= box.y + box.h + 0.5) out.push({ x: x, y: y, w: W, h: H });
          });
          return out;
        }
        for (var dd = 0; dd <= L; dd += 4) [p0 - dd, p0 + dd].forEach(function (q) {
          if (q < -0.5 || q > L + 0.5) return;
          out.push(edge === "left" ? { x: box.x, y: box.y + q, w: W, h: H } : edge === "right" ? { x: box.x + box.w - W, y: box.y + q, w: W, h: H } : edge === "top" ? { x: box.x + q, y: box.y, w: W, h: H } : { x: box.x + q, y: box.y + box.h - H, w: W, h: H });
        });
        return out;
      }
      function edgeDist(r, edge) {
        if (edge === "left") return r.x - box.x;
        if (edge === "right") return (box.x + box.w) - (r.x + r.w);
        if (edge === "top") return r.y - box.y;
        if (edge === "bottom") return (box.y + box.h) - (r.y + r.h);
        return Math.abs(r.x - box.x - (s.x || 0) * box.w) + Math.abs(r.y - box.y - (s.y || 0) * box.h);
      }
      function slotIn(fr, W, H, edge) {
        if (fr.w + 0.5 < W || fr.h + 0.5 < H) return null;
        var x = fr.x, y = fr.y;
        if (edge === "right") x = fr.x + fr.w - W;
        else if (edge !== "left") x = Math.min(fr.x + fr.w - W, Math.max(fr.x, box.x + Math.max(0, (s.x || 0) * box.w)));
        if (edge === "bottom") y = fr.y + fr.h - H;
        else if (edge !== "top") y = Math.min(fr.y + fr.h - H, Math.max(fr.y, box.y + Math.max(0, (s.y || 0) * box.h)));
        return { x: x, y: y, w: W, h: H };
      }
      function markFit(rect, sz) {
        if (sz.W - rect.w < 8 && sz.H - rect.h < 8) { w.dataset.fit = ""; return; }
        var tight = p.bare ? (rect.h < 40 || rect.w < 44) : (rect.h < Math.min(sz.H, 160) || rect.w < Math.min(sz.W, 200));
        w.dataset.fit = tight ? "tight" : "viewport";
      }
      function commit(rect, edge, sz) {
        measureEdge(edge);
        w.style.left = Math.round(rect.x) + "px"; w.style.top = Math.round(rect.y) + "px";
        if ((s.userSize && !s.min) || rect.w < sz.W - 1 || rect.h < sz.H - 1) {
          w.style.width = Math.round(rect.w) + "px"; w.style.maxWidth = Math.round(rect.w) + "px";
          if (s.userSize && !s.min) w.style.height = Math.round(rect.h) + "px";
          w.style.maxHeight = Math.round(rect.h) + "px";
        }
        markFit(rect, sz);
        return { x: rect.x, y: rect.y, w: rect.w, h: rect.h };
      }
      var order = [], prefer = (s.userSize && !p.dock) ? null : (s.edge || null);
      function pushE(e) { if (order.indexOf(e) < 0) order.push(e); }
      pushE(prefer); EDGES.forEach(pushE); if (prefer !== null) pushE(null);
      var chosen = null, chosenEdge = null, chosenSize = null;
      for (var i = 0; i < order.length && !chosen; i++) {
        var edge = order[i], sz = measureEdge(edge);
        var hitAt = null, list = cands(edge, i ? 0 : s.t, sz.W, sz.H);
        for (var c = 0; c < list.length; c++) if (!overlaps(list[c], obs)) { hitAt = list[c]; break; }
        if (hitAt) { chosen = hitAt; chosenEdge = edge; chosenSize = sz; }
      }
      if (!chosen) {
        var sz0 = measureEdge(prefer), frees = freeRects(box, obs), best = null;
        frees.forEach(function (fr) {
          var slot = slotIn(fr, sz0.W, sz0.H, prefer);
          if (!slot || overlaps(slot, obs)) return;
          var dist = edgeDist(slot, prefer);
          if (!best || dist < best.dist) best = { slot: slot, dist: dist };
        });
        if (best) { chosen = best.slot; chosenEdge = prefer; chosenSize = sz0; }
      }
      if (!chosen) {
        var sz1 = measureEdge(prefer), frees2 = freeRects(box, obs), best2 = null;
        var minW = p.bare ? 44 : Math.min(sz1.W, 160), minH = p.bare ? 40 : Math.min(sz1.H, 120);
        frees2.forEach(function (fr) {
          var ww = Math.min(sz1.W, fr.w), hh = Math.min(sz1.H, fr.h);
          if (ww < minW - 0.5 || hh < minH - 0.5) return;
          var slot = slotIn(fr, ww, hh, prefer);
          if (!slot || overlaps(slot, obs)) return;
          var area = ww * hh, dist = edgeDist(slot, prefer);
          if (!best2 || area > best2.area + 1 || (Math.abs(area - best2.area) <= 1 && dist < best2.dist)) best2 = { slot: slot, area: area, dist: dist };
        });
        if (best2) { chosen = best2.slot; chosenEdge = prefer; chosenSize = sz1; }
      }
      if (chosen) return commit(chosen, chosenEdge, chosenSize);
      var szB = measureEdge(prefer);   // undo the trial edges' classes
      var fb = cands(prefer, s.t, szB.W, szB.H)[0] || { x: box.x, y: box.y, w: Math.min(szB.W, box.w), h: Math.min(szB.H, box.h) };
      if (overlaps(fb, obs)) w.dataset.blocked = "1";
      return commit(fb, prefer, szB);
    }
    var queued = false, lastBox = null, api_watch = null, interacting = false;
    function rootAlive() { try { return !!(root && root.ownerDocument && root.ownerDocument.defaultView && root.isConnected !== false); } catch (e) { return false; } }
    function layout() { if (interacting) return; if (queued) return; queued = true; var token = epoch; Promise.resolve().then(function () { queued = false; if (token !== epoch || interacting || !rootAlive()) return; doLayout(); }); }   // before the next paint: no frame with a panel on top of another
    function rank(p) { return Math.max(p.pri || 0, p.chipPri || 0); }   // chipPri records the panel the user just opened so it is placed first; layout does not minimise or hide another panel
    function placeAll(box, share, openCount, rr) {
      var obs = obstacles(rr), tight = false;
      P.slice().sort(function (a, b) { return rank(b) - rank(a) || (b.lead ? 1 : 0) - (a.lead ? 1 : 0) || (b.core ? 1 : 0) - (a.core ? 1 : 0); }).forEach(function (p) {
        if (p.skip && p.skip()) return;
        var s = state[p.id];
        p.w.hidden = !!s.hidden || p.el.hidden;
        p.w.classList.toggle("min", !!s.min);
        p.w.classList.remove("auto-min", "auto-off");
        p.w.dataset.crowded = ""; p.w.dataset.fit = ""; p.w.dataset.blocked = "";
        if (p.w.hidden) return;
        var rect = place(p, s, box, obs, share, openCount);
        if (p.w.dataset.blocked === "1" || p.w.dataset.fit === "tight") tight = true;
        if (rect && rect.w && rect.h) obs.push(pad(rect));
      });
      return tight;
    }
    function doLayout() {
      if (laying) { again = true; return; }
      if (!rootAlive()) return;
      laying = true;
      try {
        var want = !o.active || o.active(); if (want) mount(); else if (on) unmount(); if (!on) return;
        if (o.before) o.before(); if (api_watch) api_watch();
        var rr = root.getBoundingClientRect(), sa = safe(), vv = window.visualViewport;
        var bottom = vv ? Math.min(rr.height, vv.height + vv.offsetTop - rr.top) : rr.height;   // keyboard open: stay above it
        var box = { x: M + sa.l, y: M + Math.max(0, sa.t - rr.top), w: rr.width - 2 * M - sa.l - sa.r, h: Math.max(120, bottom - 2 * M - Math.max(0, sa.t - rr.top) - (rr.bottom >= innerHeight - 1 ? sa.b : 0)) };
        if (o.inset) { var ins = o.inset(); box.x += ins.l || 0; box.y += ins.t || 0; box.w -= (ins.l || 0) + (ins.r || 0); box.h -= (ins.t || 0) + (ins.b || 0); }
        var topChrome = chromeBand(rr, ":scope > .wsbar", true);
        var botChrome = chromeBand(rr, ":scope > .bed-bar, :scope > .objdock, :scope > .proc-sheet, :scope > .bed-sheet", false);
        if (topChrome + 4 > box.y) { var cut = topChrome + 4 - box.y; box.y += cut; box.h -= cut; }
        if (botChrome > 0) box.h -= botChrome + 4;
        if (box.w < 1) box.w = 1; if (box.h < 80) box.h = 80;
        var chromeH = Math.round(topChrome) + "px";
        if (root.style.getPropertyValue("--chrome-h") !== chromeH) root.style.setProperty("--chrome-h", chromeH);
        lastBox = box;
        var openCount = P.filter(function (q) { return !(q.skip && q.skip()) && state[q.id] && !state[q.id].hidden && !state[q.id].min && !q.el.hidden; }).length;
        var tight = placeAll(box, false, openCount, rr);
        if (tight) placeAll(box, true, openCount, rr);   // a core panel never steps aside: cap height into usable bands instead of hiding
        root.dispatchEvent(new CustomEvent("zws:layout"));
      } finally {
        laying = false;
        if (again) { again = false; layout(); }
      }
    }
    function pad(r) { return { x: r.x - 3, y: r.y - 3, w: r.w + 6, h: r.h + 6 }; }
    function reset() {
      epoch++; gesture++; interacting = false;
      if (orientTimer) { clearTimeout(orientTimer); orientTimer = 0; }
      P.forEach(function (p) {
        p.pri = 0; p.chipPri = 0;
        if (!p.w) return;
        p.w.style.left = p.w.style.top = p.w.style.width = p.w.style.height = "";
        p.w.style.maxWidth = p.w.style.maxHeight = p.w.style.transform = "";
        p.w.classList.remove("user-size", "auto-min", "auto-off", "min", "free", "v", "h", "drag");
        p.w.dataset.crowded = ""; p.w.dataset.fit = ""; p.w.dataset.blocked = ""; p.w.dataset.edge = "";
      });
      P.forEach(function (p) {
        var def = currentDef(p);
        state[p.id] = Object.assign({}, def, { hidden: !p.core && !!def.hidden, min: !!def.min, userSize: false, edge: def.edge || null, t: def.t || 0, x: def.x, y: def.y, w: def.w, h: def.h });
      });
      var base = K();
      [base, base + ".land", base + ".port"].forEach(function (k) { wr(k, null); });
      if (rd(base) || rd(base + ".land") || rd(base + ".port")) save();
      layout();
    }
    function keyboardOpen() {
      var vv = window.visualViewport;
      return !!(vv && ((innerHeight - vv.height) > 120 || (vv.offsetTop || 0) > 80));
    }
    function onBreakpoint() {
      if (keyboardOpen()) { layout(); return; }
      if (!rd(K()) && !rd(KP())) load();
      layout();
    }

    /* Customise workspace */
    var dlg = document.createElement("dialog"); dlg.className = "zws-dlg"; dlg.id = "zwsDlg-" + o.id; dlg.setAttribute("aria-label", "Customise workspace");
    function fillDlg() {
      dlg.innerHTML = '<form method="dialog"><h2>Customise workspace' + (o.title ? ": " + (typeof o.title === "function" ? o.title() : o.title) : "") + '</h2><p class="help">Show or hide each panel here. Drag a panel by its grip to move it or dock it to any side. Drag an edge to resize left, right, up or down. Exit stays in front of every panel.</p><ul class="zws-list">' +
        P.map(function (p) { return '<li><label><input type="checkbox" data-zws="' + p.id + '"' + (state[p.id].hidden ? "" : " checked") + (p.core ? " disabled" : "") + "> " + p.label + (p.core ? ' <small>(always shown)</small>' : "") + "</label>" + (p.core ? "" : '<button type="button" class="btn small" data-zws-remove="' + p.id + '">Remove</button>') + "</li>"; }).join("") +
        '</ul><div class="zws-row"><button type="button" class="btn" data-zws-reset>Reset layout</button><button class="btn primary" value="ok">Done</button></div></form>';
      dlg.querySelectorAll("input[data-zws]").forEach(function (c) { c.onchange = function () { setHidden(c.dataset.zws, !c.checked); }; });
      dlg.querySelectorAll("[data-zws-remove]").forEach(function (b) { b.onclick = function () { setHidden(b.getAttribute("data-zws-remove"), true); fillDlg(); }; });
      dlg.querySelector("[data-zws-reset]").onclick = function () { reset(); fillDlg(); };
    }
    document.body.append(dlg);
    var btn = document.createElement("button"); btn.type = "button"; btn.className = (o.btnClass || "btn small") + " zws-cust"; btn.id = "zwsCust-" + o.id;
    btn.setAttribute("aria-haspopup", "dialog"); btn.title = "Customise workspace: show, hide, move panels; reset layout"; btn.setAttribute("aria-label", "Customise workspace");
    btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg><span class="lbl">Customise</span>';
    btn.onclick = function () { open(); };
    function open() { fillDlg(); dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", ""); }
    /* In the top strip, after the primary action, so the label cannot sit over Slice. */
    if (o.customise) {
      var slot = o.customise, bar = slot.querySelector && slot.querySelector(":scope > .wsbar");
      if (bar) {
        var end = document.createElement("div");
        end.className = "ws-end";
        var go = bar.querySelector(":scope > .ws-go");
        if (go) end.append(go);
        end.append(btn);
        bar.append(end);
      } else slot.append(btn);
    }
    if (o.title) dlg.dataset.title = o.title;
    (o.panels || []).forEach(function (p) { if (p.el) { P.push(p); wrap(p); } });
    load();
    var ro = track(new ResizeObserver(layout)); ro.observe(root); P.forEach(function (p) { ro.observe(p.el); track(new MutationObserver(function () { var h = !!state[p.id].hidden || p.el.hidden; if (p.w.hidden !== h) p.w.hidden = h; layout(); })).observe(p.el, { attributes: true, attributeFilter: ["hidden"] }); });
    listen(window, "resize", layout);
    listen(window, "orientationchange", function () {
      if (keyboardOpen()) { layout(); return; }
      load();
      if (orientTimer) clearTimeout(orientTimer);
      var token = ++epoch;
      orientTimer = setTimeout(function () { orientTimer = 0; if (token === epoch) layout(); }, 150);
    });
    var orientMq = window.matchMedia("(orientation: landscape)");
    listen(orientMq, "change", function () { if (!keyboardOpen()) load(); layout(); });
    if (window.visualViewport) listen(window.visualViewport, "resize", layout);
    var phoneMq = window.matchMedia(PHONE_Q);
    listen(phoneMq, "change", onBreakpoint);
    /* an obstacle (e.g. the "Making your model" overlay) showing pushes panels aside; it going away must bring them
       back, so watch each obstacle too (the selector's :not(...) part is dropped so a hidden one is still found) */
    var watched = [];
    function alive(el) { return !!(el && el.ownerDocument && el.ownerDocument.documentElement && el.ownerDocument.documentElement.contains(el)); }
    function watchObstacles() {
      watched = watched.filter(function (w) { if (alive(w.el)) return true; try { w.ob.disconnect(); } catch (e) {} return false; });
      (o.obstacles || []).forEach(function (s) { document.querySelectorAll(s.replace(/:not\([^)]*\)/g, "")).forEach(function (el) {
        if (watched.some(function (w) { return w.el === el; })) return;
        var ob = track(new MutationObserver(layout)); ob.observe(el, { attributes: true, attributeFilter: ["hidden", "class", "style"] });
        watched.push({ el: el, ob: ob });
      }); });
    }
    watchObstacles(); api_watch = watchObstacles;
    (o.watch || []).forEach(function (s) { var el = $(s); if (el) track(new MutationObserver(layout)).observe(el, { attributes: true, attributeFilter: ["hidden", "class", "style", "data-sheet"], childList: !!o.watchChildren }); });
    layout();
    var api;
    function destroy() {
      epoch++; gesture++; interacting = false; again = false;
      if (orientTimer) { clearTimeout(orientTimer); orientTimer = 0; }
      drop.splice(0).forEach(function (fn) { fn(); });
      obsers.splice(0).forEach(function (ob) { try { ob.disconnect(); } catch (e) {} });
      watched = [];
      try { unmount(); } catch (e) {}
      if (dlg && dlg.parentNode) dlg.remove();
      if (btn && btn.parentNode) btn.remove();
      if (WS[o.id] === api) delete WS[o.id];
    }
    api = { id: o.id, layout: layout, reset: reset, open: open, setHidden: setHidden, state: function () { return JSON.parse(JSON.stringify(state)); }, load: load, rekey: rekey, button: btn, panels: P, destroy: destroy };
    WS[o.id] = api; return api;
  }
  window.ZWS = { create: create, all: WS, freeRects: freeRects, phoneQuery: PHONE_Q };
})();
