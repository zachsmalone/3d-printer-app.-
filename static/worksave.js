/* Saving your work: auto-save every 2/5/10 min (default 5), a gentle reminder instead, or off.
   Used by Lithophane/Studio, the FDM Slicer, TorchC0 (index.html) and CAD (cad.html).
   - Each section registers a saver: collect() -> JSON-able state, restore(state).
   - A draft is this browser only. The key is zeim.work.v2.<account>.<project>.<section>, so two
     accounts (and, for project-scoped sections, two projects) do not share one draft.
   - The account id comes from /api/me. Nothing is written until that returns.
   - Projects in the Slicer and CAD are saved on the server after every step. This file keeps the
     unsaved bits (settings, open project, sizes). The indicator says "Draft saved" for that browser
     copy, or "Not saved" when the write did not stick. It does not claim the server confirmed it.
   - The reminder is a small dismissible toast. Exit asks before leaving a draft that did not store. */
(function () {
  "use strict";
  var root = typeof globalThis !== "undefined" ? globalThis : window;
  var PKEY = "zeim.save", DEF = { mode: "auto", every: 5 }, savers = {}, dirty = {}, scopeProject = {}, projects = {}, held = {};
  var lastAt = null, timer = null, reminded = false, saveFailed = false, lastResult = "empty", account = "", signedIn = null, typedEarly = false;
  function storage() { try { return root.localStorage; } catch (e) { return null; } }
  function readRaw(k) { var ls = storage(); if (!ls) return null; try { return ls.getItem(k); } catch (e) { return null; } }
  function removeRaw(k) { var ls = storage(); if (!ls) return; try { ls.removeItem(k); } catch (e) { } }
  function writeRaw(k, v) {
    var ls = storage(); if (!ls) return false;
    try { ls.setItem(k, v); } catch (e) { return false; }
    try { return ls.getItem(k) === v; } catch (e) { return false; }
  }
  function ls(k, v) {
    if (v === undefined) return readRaw(k);
    if (v === null) { removeRaw(k); return null; }
    return writeRaw(k, v) ? v : null;
  }
  function valid(p) { return p && ["auto", "remind", "off"].indexOf(p.mode) >= 0 && [2, 5, 10].indexOf(+p.every) >= 0; }
  function prefs() { try { var p = JSON.parse(readRaw(PKEY) || "null"); if (valid(p)) return { mode: p.mode, every: +p.every }; } catch (e) { } return { mode: DEF.mode, every: DEF.every }; }
  function hhmm(d) { return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
  function pathName() { return (typeof location !== "undefined" && location.pathname) || ""; }
  function sanitizeProject(id) { id = String(id || ""); return /^[0-9a-f]{12}$/.test(id) ? id : ""; }
  function projectOf(section) { return scopeProject[section] ? (projects[section] || "_") : "_"; }
  function draftKey(section) { return "zeim.work.v2." + account + "." + projectOf(section) + "." + section; }

  /* ---- indicator ---- */
  var ind = null;
  function indicator() {
    if (ind) return ind;
    if (typeof document === "undefined" || !document.createElement || !document.body) return null;
    ind = document.createElement("a");
    ind.id = "saveInd"; ind.className = "saveind";
    ind.href = pathName().indexOf("/static/cad.html") === 0 ? "/#account/save" : "#account/save";
    ind.title = "Saving settings";
    ind.setAttribute("aria-live", "polite");
    var slot = document.getElementById("saveIndSlot");
    if (slot) { ind.classList.add("inline"); slot.appendChild(ind); } else document.body.appendChild(ind);
    paint(); return ind;
  }
  /* ---- where the project lives (account on the server vs this browser only). The clock is the draft, not a server receipt. ---- */
  function whereText() {
    if (signedIn === null) return "Where your work is saved: checking…";
    return signedIn ? "Where your work is saved: on your account, on the ZEIM server. Sign in on any device to get it back."
      : "Where your work is saved: only in this browser (guest). Clearing this browser's site data removes it. Sign in or use Back up all to keep it.";
  }
  function indicatorLabel() {
    var p = prefs();
    if (saveFailed) return "Not saved";
    if (lastAt) return "Draft saved " + hhmm(lastAt);
    return p.mode === "auto" ? "Auto-save on" : p.mode === "remind" ? "Save reminders on" : "Auto-save off";
  }
  function isIOSSafari() {
    var ua = (typeof navigator !== "undefined" && navigator.userAgent) || "";
    return /iPhone|iPod/.test(ua) && /Safari\//.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA\//.test(ua);
  }
  function paintWhere() {
    if (typeof document === "undefined") return;
    var w = document.getElementById("saveWhere"); if (w && signedIn !== null) w.textContent = whereText();
    safariNote();
    paint();
  }
  function safariNote() {
    if (typeof document === "undefined") return;
    var old = document.getElementById("safariNote");
    if (signedIn !== false || !(isIOSSafari() || readRaw("zeim.forceSafariNote") === "1") || readRaw("zeim.safariNoteOff") === "1") { if (old) old.remove(); return; }
    if (old) return;
    var n = document.createElement("div"); n.id = "safariNote"; n.className = "safarinote"; n.setAttribute("role", "note");
    n.innerHTML = '<span>Heads-up: Safari on iPhone may clear saved site data if you don\u2019t visit for 7 days. <a href="' + (pathName().indexOf("/static/cad.html") === 0 ? "/" : "") + '#account">Sign in</a> or <a href="/api/me/backup.zip" download>back up all</a> to keep your work.</span>' +
      '<button type="button" class="btn small ghost" data-s="x" aria-label="Dismiss this note"><svg class="i" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button>';
    n.querySelector("[data-s]").addEventListener("click", function () { writeRaw("zeim.safariNoteOff", "1"); n.remove(); });
    document.body.appendChild(n);
  }
  function paint() {
    if (!ind) return;
    var label = indicatorLabel();
    ind.textContent = label;
    if (ind.classList) { if (saveFailed) ind.classList.add("bad"); else ind.classList.remove("bad"); }
    var title = saveFailed
      ? "Not saved. The last draft did not store in this browser. This label is not a server confirmation. "
      : lastAt
        ? "Draft saved in this browser. This time is not a server confirmation. "
        : indicatorLabel() + ". This label is not a server confirmation. ";
    ind.title = title + whereText();
    ind.setAttribute("aria-label", label + ". Open saving settings");
  }

  /* ---- saving ---- */
  function pack(st) { return JSON.stringify({ t: Date.now(), v: st }); }
  function saveSection(k) {
    var s = savers[k]; if (!s) return "empty";
    var st; try { st = s.collect(); } catch (e) { return dirty[k] ? "failed" : "empty"; }
    if (st == null) return "empty";
    if (!account) return dirty[k] ? "failed" : "empty";
    var key = draftKey(k), packed = pack(st);
    if (!writeRaw(key, packed)) { if (dirty[k]) held[key] = packed; return dirty[k] ? "failed" : "empty"; }
    delete held[key]; dirty[k] = false; return "saved";
  }
  function capture(k) {
    /* Park the current form on its current key before the account or project changes. */
    var s = savers[k]; if (!s) return;
    var st; try { st = s.collect(); } catch (e) { dirty[k] = false; return; }
    if (st == null) { dirty[k] = false; return; }
    if (!account) { held["pending." + k] = pack(st); dirty[k] = false; return; }
    var key = draftKey(k), packed = pack(st);
    if (!writeRaw(key, packed)) held[key] = packed; else delete held[key];
    dirty[k] = false;
  }
  function flushHeld() {
    Object.keys(held).forEach(function (key) { if (key.indexOf("pending.") === 0) return; if (writeRaw(key, held[key])) delete held[key]; });
  }
  function saveNow() {
    flushHeld();
    var saved = 0, failed = 0;
    Object.keys(savers).forEach(function (k) { var outcome = saveSection(k); if (outcome === "saved") saved++; else if (outcome === "failed") failed++; });
    if (failed || Object.keys(held).length) { saveFailed = true; lastResult = "failed"; indicator(); paint(); return false; }
    if (saved) {
      lastAt = new Date(); saveFailed = false; reminded = false; lastResult = "saved"; indicator(); paint();
      if (typeof document !== "undefined" && document.dispatchEvent) document.dispatchEvent(new CustomEvent("zeim:saved", { detail: { at: lastAt } }));
      return true;
    }
    saveFailed = false; lastResult = "empty"; return false;
  }
  function isDirty() { return Object.keys(held).length > 0 || Object.keys(dirty).some(function (k) { return dirty[k]; }); }

  function confirmLeave(go, why) {
    if (typeof document === "undefined" || !document.body) return;
    if (document.getElementById("saveExit")) return;
    var t = document.createElement("div"); t.id = "saveExit"; t.className = "savetoast"; t.setAttribute("role", "alertdialog"); t.setAttribute("aria-label", "Exit workspace");
    var text = why === "account"
      ? "Still checking which account this draft belongs to. Stay, or exit without storing this browser's draft."
      : "This browser could not store the workspace draft. The design on the server is unchanged. Exit anyway?";
    t.innerHTML = "<span>" + text + "</span>" +
      '<button type="button" class="btn small primary" data-s="stay">Stay</button>' +
      '<button type="button" class="btn small ghost" data-s="exit">Exit anyway</button>';
    t.addEventListener("click", function (e) { var b = e.target.closest && e.target.closest("[data-s]"); if (!b) return; t.remove(); if (b.getAttribute("data-s") === "exit") go(); });
    document.body.appendChild(t);
    var stay = t.querySelector("[data-s=stay]"); if (stay) stay.focus();
  }
  function leave(go) {
    if (typeof go !== "function") return false;
    if (!account) { confirmLeave(go, "account"); return false; }
    if (isDirty()) saveNow();
    if (isDirty()) { confirmLeave(go, "failed"); return false; }
    go(); return true;
  }

  /* ---- reminder toast ---- */
  function remind() {
    if (reminded || typeof document === "undefined" || document.getElementById("saveToast")) return; reminded = true;
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
    if (!writeRaw(PKEY, JSON.stringify(p))) return false;
    schedule(); syncForm();
    if (push !== false && typeof fetch === "function") fetch("/api/me/save-prefs", { method: "PUT", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) }).catch(function () { });
    if (typeof document !== "undefined" && document.dispatchEvent) document.dispatchEvent(new CustomEvent("zeim:save-prefs", { detail: p }));
    return true;
  }

  /* ---- generic form savers (by element id / radio name inside a root) ---- */
  function fields(rootEl) { return Array.prototype.slice.call(rootEl.querySelectorAll("input,select,textarea")).filter(function (el) { return !/^(file|password|search|button|submit|hidden)$/.test(el.type) && (el.id || (el.type === "radio" && el.name)) && !el.closest("[data-nosave]"); }); }
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
  function restoreSection(k) {
    /* null: nothing stored. false: a draft exists but the screen could not take it yet. true: applied. */
    var s = savers[k]; if (!s || !account || dirty[k]) return null;
    var raw = readRaw(draftKey(k));
    if (!raw && scopeProject[k] && projects[k]) {
      var loose = readRaw("zeim.work.v2." + account + "._." + k);
      if (loose && writeRaw(draftKey(k), loose)) { removeRaw("zeim.work.v2." + account + "._." + k); raw = loose; }
    }
    if (!raw) return null;
    var st; try { st = JSON.parse(raw).v; } catch (e) { return false; }
    try { return !!s.restore(st); } catch (e) { return false; }
  }
  function setAccount(next) {
    next = String(next || "");
    if (!/^u:[0-9a-f]{12}$|^guest$/.test(next)) return false;
    if (account === next) return true;
    if (account) Object.keys(savers).forEach(function (k) { if (dirty[k]) capture(k); });
    account = next;
    Object.keys(savers).forEach(function (k) { if (!dirty[k]) restoreSection(k); });
    paintWhere();
    return true;
  }
  function setProject(section, projectId, opts) {
    var next = sanitizeProject(projectId);
    var cur = projects[section] || "";
    scopeProject[section] = true;
    if (cur === next) { if (opts && opts.restore && savers[section] && !dirty[section]) restoreSection(section); return true; }
    if (savers[section] && dirty[section]) capture(section);
    projects[section] = next;
    if (savers[section] && !dirty[section]) restoreSection(section);
    return true;
  }
  function register(k, s, rootSel, opts) {
    savers[k] = s; dirty[k] = false;
    if (opts && opts.project) scopeProject[k] = true;
    if (typedEarly) dirty[k] = true;
    if (rootSel && typeof document !== "undefined" && document.addEventListener) {
      var mark = function (e) { if (e.isTrusted && e.target.closest && e.target.closest(rootSel)) dirty[k] = true; };
      document.addEventListener("input", mark, true); document.addEventListener("change", mark, true);
    }
    var waits = 0, tries = 0;
    (function attempt() {
      if (!account) { if (++waits < 80) setTimeout(attempt, 50); return; }
      if (dirty[k]) return;
      var applied = restoreSection(k);
      if (applied === null || applied === true || ++tries > 40) return;
      setTimeout(attempt, 250);
    })();
  }

  /* ---- Account > Saving your work ---- */
  function syncForm() {
    if (typeof document === "undefined") return;
    var f = document.getElementById("savePrefs"); if (!f) return; var p = prefs();
    var r = f.querySelector('input[name=saveMode][value="' + p.mode + '"]'); if (r) r.checked = true;
    var s = f.querySelector("#saveEvery"); if (s) { s.value = String(p.every); s.disabled = p.mode === "off"; }
  }
  function wireForm() {
    var f = document.getElementById("savePrefs"); if (!f || !f.addEventListener) return; syncForm();
    f.addEventListener("submit", function (e) { e.preventDefault(); });
    f.addEventListener("change", function () {
      var m = f.querySelector("input[name=saveMode]:checked"); var everyEl = f.querySelector("#saveEvery");
      var ok = setPrefs({ mode: m ? m.value : "auto", every: everyEl ? +everyEl.value : 5 });
      var st = document.getElementById("saveStatus");
      if (st && ok) st.textContent = "Saved. " + (prefs().mode === "off" ? "Auto-save is off." : prefs().mode === "auto" ? "Auto-saving every " + prefs().every + " minutes." : "Reminding you every " + prefs().every + " minutes.");
      if (st && !ok) st.textContent = "Could not store that choice in this browser.";
    });
  }
  function noteEarly(e) { if (e && e.isTrusted) typedEarly = true; }
  function applyMe(j) {
    if (j && j.signed_up && typeof j.id === "string" && /^[0-9a-f]{12}$/.test(j.id)) setAccount("u:" + j.id);
    else if (j) setAccount("guest");
    if (j) signedIn = !!j.signed_up;
    paintWhere();
  }
  function registerIndex() {
    if (pathName() !== "/" && pathName() !== "/index.html") return;
    register("lithophane", formSaver("#viewCreate"), "#viewCreate");
    register("slicer", formSaver("#slicePanel"), "#slicePanel", { project: true });
    register("torchc0", formSaver("#torchPanel"), "#torchPanel");
  }
  function boot() {
    indicator(); wireForm(); schedule();
    if (document.addEventListener) { document.addEventListener("input", noteEarly, true); document.addEventListener("change", noteEarly, true); }
    var meDone = fetch("/api/me", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(applyMe).catch(function () { });
    fetch("/api/me/save-prefs", { credentials: "same-origin" }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (j && j.signed_up && j.stored && valid(j.prefs)) setPrefs(j.prefs, false);
      if (j && signedIn === null) { signedIn = !!j.signed_up; paintWhere(); }
    }).catch(function () { });
    meDone.then(registerIndex);
    var go = function () { var h = location.hash; if (h === "#account/save") { var f = document.getElementById("savePrefs"); if (f) { setTimeout(function () { f.scrollIntoView({ block: "center" }); var x = f.querySelector("input:checked"); if (x) x.focus(); }, 60); } } };
    window.addEventListener("hashchange", go); go();
  }
  root.zeimSave = {
    where: function () { return signedIn; }, _paintWhere: paintWhere, register: register, formSaver: formSaver,
    saveNow: saveNow, prefs: prefs, setPrefs: setPrefs, isDirty: isDirty, leave: leave, hold: function (k) { if (dirty[k]) capture(k); },
    setAccount: setAccount, setProject: setProject, lastResult: function () { return lastResult; }, _label: indicatorLabel,
    _draftKey: draftKey, _tick: tick, _markDirty: function (k) { dirty[k] = true; }
  };
  if (!root.ZEIM_SAVE_TEST && typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("zeim:save-now", saveNow);
    window.addEventListener("pagehide", function () { if (prefs().mode === "auto" && isDirty()) saveNow(); });
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
  }
})();
