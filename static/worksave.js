/* Saving your work: auto-save every 2/5/10 min (default 5), a gentle reminder instead, or off.
   Used by Lithophane/Studio, the FDM Slicer, TorchC0 (index.html) and CAD (cad.html).
   - Each section registers a saver: collect() -> JSON-able state, restore(state).
   - State lives in this browser (localStorage "zeim.work.<section>"); the preference itself is stored
     on the account when signed in (PUT /api/me/save-prefs) and in localStorage for guests.
   - Projects in the Slicer and CAD are already saved on the server after every step; this keeps the
     unsaved bits (settings, open project, sizes) so nothing is lost when you leave or reload.
   - The indicator ("Saved 9:14") is quiet; the reminder is a small dismissible toast. Nothing ever blocks. */
(function () {
  "use strict";
  var PKEY = "zeim.save", DEF = { mode: "auto", every: 5 }, savers = {}, dirty = {}, lastAt = null, timer = null, reminded = false;
  function ls(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } }
  function valid(p) { return p && ["auto", "remind", "off"].indexOf(p.mode) >= 0 && [2, 5, 10].indexOf(+p.every) >= 0; }
  function prefs() { try { var p = JSON.parse(ls(PKEY) || "null"); if (valid(p)) return { mode: p.mode, every: +p.every }; } catch (e) { } return { mode: DEF.mode, every: DEF.every }; }
  function hhmm(d) { return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }

  /* ---- indicator ---- */
  var ind = null;
  function indicator() {
    if (ind) return ind;
    ind = document.createElement("a");
    ind.id = "saveInd"; ind.className = "saveind";
    ind.href = location.pathname.indexOf("/static/cad.html") === 0 ? "/#account/save" : "#account/save";
    ind.title = "Saving settings";
    ind.setAttribute("aria-live", "polite");
    var slot = document.getElementById("saveIndSlot");      // CAD: in the top bar, never over the canvas/lessons
    if (slot) { ind.classList.add("inline"); slot.appendChild(ind); } else document.body.appendChild(ind);
    paint(); return ind;
  }
  /* ---- where your work is saved (account on the server vs. this browser only) ---- */
  var signedIn = null;
  function whereText() {
    return signedIn ? "Where your work is saved: on your account, on the ZEIM server. Sign in on any device to get it back."
      : "Where your work is saved: only in this browser (guest). Clearing this browser's site data removes it. Sign in or use Back up all to keep it.";
  }
  function isIOSSafari() {
    var ua = navigator.userAgent || "";
    return /iPhone|iPod/.test(ua) && /Safari\//.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
  }
  function paintWhere() {
    var w = document.getElementById("saveWhere"); if (w && signedIn !== null) w.textContent = whereText();
    if (ind && signedIn !== null) ind.title = whereText();
    safariNote();
  }
  function safariNote() {
    var old = document.getElementById("safariNote");
    if (signedIn !== false || !(isIOSSafari() || ls("zeim.forceSafariNote") === "1") || ls("zeim.safariNoteOff") === "1") { if (old) old.remove(); return; }
    if (old) return;
    var n = document.createElement("div"); n.id = "safariNote"; n.className = "safarinote"; n.setAttribute("role", "note");
    n.innerHTML = '<span>Heads-up: Safari on iPhone may clear saved site data if you don\u2019t visit for 7 days. <a href="' + (location.pathname.indexOf("/static/cad.html") === 0 ? "/" : "") + '#account">Sign in</a> or <a href="/api/me/backup.zip" download>back up all</a> to keep your work.</span>' +
      '<button type="button" class="btn small ghost" data-s="x" aria-label="Dismiss this note"><svg class="i" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>';
    n.querySelector("[data-s]").addEventListener("click", function () { ls("zeim.safariNoteOff", "1"); n.remove(); });
    document.body.appendChild(n);
  }
  function paint() {
    if (!ind) return; var p = prefs();
    ind.textContent = lastAt ? "Saved " + hhmm(lastAt) : p.mode === "auto" ? "Auto-save on" : p.mode === "remind" ? "Save reminders on" : "Auto-save off";
    ind.setAttribute("aria-label", ind.textContent + ". Open saving settings");
  }

  /* ---- saving ---- */
  function saveSection(k) {
    var s = savers[k]; if (!s) return false;
    try { var st = s.collect(); if (st == null) return false; ls("zeim.work." + k, JSON.stringify({ t: Date.now(), v: st })); dirty[k] = false; return true; }
    catch (e) { return false; }
  }
  function saveNow() {
    var any = false; Object.keys(savers).forEach(function (k) { if (saveSection(k)) any = true; });
    if (any) { lastAt = new Date(); reminded = false; indicator(); paint(); document.dispatchEvent(new CustomEvent("zeim:saved", { detail: { at: lastAt } })); }
    return any;
  }
  function isDirty() { return Object.keys(dirty).some(function (k) { return dirty[k]; }); }

  /* ---- reminder toast ---- */
  function remind() {
    if (reminded || document.getElementById("saveToast")) return; reminded = true;
    var t = document.createElement("div"); t.id = "saveToast"; t.className = "savetoast"; t.setAttribute("role", "status");
    t.innerHTML = '<span>You have unsaved changes.</span><button type="button" class="btn small primary" data-s="save">Save now</button>' +
      '<button type="button" class="btn small ghost" data-s="x" aria-label="Dismiss the save reminder"><svg class="i" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>';
    t.addEventListener("click", function (e) { var b = e.target.closest("[data-s]"); if (!b) return; if (b.dataset.s === "save") saveNow(); t.remove(); });
    document.body.appendChild(t);
  }
  function tick() {
    var p = prefs(); if (p.mode === "off" || !isDirty()) return;
    if (p.mode === "auto") saveNow(); else remind();
  }
  function schedule() {
    if (timer) clearInterval(timer); var p = prefs(); timer = null;
    if (p.mode !== "off") timer = setInterval(tick, p.every * 60000);
    paint();
  }
  function setPrefs(p, push) {
    if (!valid(p)) return false; p = { mode: p.mode, every: +p.every };
    ls(PKEY, JSON.stringify(p)); schedule(); syncForm();
    if (push !== false) fetch("/api/me/save-prefs", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) }).catch(function () { });
    document.dispatchEvent(new CustomEvent("zeim:save-prefs", { detail: p }));
    return true;
  }

  /* ---- generic form savers (by element id / radio name inside a root) ---- */
  function fields(root) { return Array.prototype.slice.call(root.querySelectorAll("input,select,textarea")).filter(function (el) { return !/^(file|password|search|button|submit|hidden)$/.test(el.type) && (el.id || (el.type === "radio" && el.name)) && !el.closest("[data-nosave]"); }); }
  function formSaver(rootSel) {
    return {
      collect: function () { var r = document.querySelector(rootSel); if (!r) return null; var o = {};
        fields(r).forEach(function (el) { if (el.type === "radio") { if (el.checked) o["@" + el.name] = el.value; } else o[el.id] = el.type === "checkbox" ? el.checked : el.value; });
        return Object.keys(o).length ? o : null; },
      restore: function (o) { var r = document.querySelector(rootSel); if (!r || !o) return false; var n = 0;
        Object.keys(o).forEach(function (k) {
          var el = k.charAt(0) === "@" ? r.querySelector('input[type=radio][name="' + k.slice(1) + '"][value="' + String(o[k]).replace(/"/g, "") + '"]') : r.querySelector("#" + CSS.escape(k));
          if (!el) return; n++;
          if (el.type === "radio") { if (el.checked) return; el.checked = true; }
          else if (el.type === "checkbox") { if (el.checked === !!o[k]) return; el.checked = !!o[k]; }
          else { if (el.value === String(o[k])) return; if (el.tagName === "SELECT" && !Array.prototype.some.call(el.options, function (x) { return x.value === String(o[k]); })) return; el.value = o[k]; }
          el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
        });
        return n > 0; }
    };
  }
  function register(k, s, rootSel) {
    savers[k] = s; dirty[k] = false;
    if (rootSel) {
      var mark = function (e) { if (e.isTrusted && e.target.closest && e.target.closest(rootSel)) dirty[k] = true; };
      document.addEventListener("input", mark, true); document.addEventListener("change", mark, true);
    }
    var raw = ls("zeim.work." + k); if (!raw) return;
    var st; try { st = JSON.parse(raw).v; } catch (e) { return; }
    var tries = 0; (function attempt() { if (dirty[k] || s.restore(st) || ++tries > 40) return; setTimeout(attempt, 250); })();   // never overwrite what the person already typed   // panels that render late (TorchC0) are retried briefly
  }

  /* ---- Account > Saving your work ---- */
  function syncForm() {
    var f = document.getElementById("savePrefs"); if (!f) return; var p = prefs();
    var r = f.querySelector('input[name=saveMode][value="' + p.mode + '"]'); if (r) r.checked = true;
    var s = f.querySelector("#saveEvery"); if (s) { s.value = String(p.every); s.disabled = p.mode === "off"; }
  }
  function wireForm() {
    var f = document.getElementById("savePrefs"); if (!f) return; syncForm();
    f.addEventListener("submit", function (e) { e.preventDefault(); });
    f.addEventListener("change", function () {
      var m = f.querySelector("input[name=saveMode]:checked"); var ok = setPrefs({ mode: m ? m.value : "auto", every: +f.querySelector("#saveEvery").value });
      var st = document.getElementById("saveStatus"); if (st && ok) st.textContent = "Saved. " + (prefs().mode === "off" ? "Auto-save is off." : prefs().mode === "auto" ? "Auto-saving every " + prefs().every + " minutes." : "Reminding you every " + prefs().every + " minutes.");
    });
  }

  function start() {
    indicator(); wireForm(); schedule();
    fetch("/api/me/save-prefs", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (j && j.signed_up && j.stored && valid(j.prefs)) setPrefs(j.prefs, false);   // the account wins when signed in
      if (j) { signedIn = !!j.signed_up; paintWhere(); }
    }).catch(function () { });
    if (location.pathname === "/" || location.pathname === "/index.html") {
      register("lithophane", formSaver("#viewCreate"), "#viewCreate");
      register("slicer", formSaver("#slicePanel"), "#slicePanel");
      register("torchc0", formSaver("#torchPanel"), "#torchPanel");
    }
    var go = function () { var h = location.hash; if (h === "#account/save") { var f = document.getElementById("savePrefs"); if (f) { setTimeout(function () { f.scrollIntoView({ block: "center" }); var x = f.querySelector("input:checked"); if (x) x.focus(); }, 60); } } };
    window.addEventListener("hashchange", go); go();
  }
  document.addEventListener("zeim:save-now", saveNow);
  window.addEventListener("pagehide", function () { if (prefs().mode === "auto" && isDirty()) saveNow(); });
  window.zeimSave = { where: function () { return signedIn; }, _paintWhere: paintWhere, register: register, formSaver: formSaver, saveNow: saveNow, prefs: prefs, setPrefs: setPrefs, isDirty: isDirty, _tick: tick, _markDirty: function (k) { dirty[k] = true; } };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
