/* Light/Dark toggle (sun/moon) in the upper-right of the top bar on every page. The theme itself is applied before first paint by the
   inline <head> snippet (THEME_HEAD); this file only adds and wires the button. Saved choice: localStorage.theme = "light" | "dark"
   ("warm" from older versions counts as light). No saved choice: follow prefers-color-scheme, otherwise light. */
(function () {
  var root = document.documentElement;
  var SUN = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  var MOON = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>';
  function isDark() { return root.getAttribute("data-theme") === "dark"; }
  function apply(dark) { if (dark) root.setAttribute("data-theme", "dark"); else root.removeAttribute("data-theme"); }
  function paint(b) {
    var d = isDark();
    b.setAttribute("aria-pressed", String(d));
    b.setAttribute("aria-label", "Dark mode");
    b.title = d ? "Switch to light mode" : "Switch to dark mode";
    b.innerHTML = d ? SUN : MOON;
  }
  function setup() {
    var b = document.getElementById("themeToggle");
    if (!b) {
      b = document.createElement("button"); b.type = "button"; b.id = "themeToggle"; b.className = "themetoggle";
      var bar = document.querySelector(".topbar");
      if (bar) bar.appendChild(b); else { b.classList.add("floating"); document.body.appendChild(b); }
    }
    paint(b);
    setupLook();
    // One delegated handler on the document (not on the button): the toggle keeps working if a page re-draws its header,
    // and pages that put the button somewhere else (CAD workspace) are covered too.
    if (!window.__zeimThemeWired) {
      window.__zeimThemeWired = true;
      document.addEventListener("click", function (e) {
        var t = e.target && e.target.closest && e.target.closest("#themeToggle"); if (!t) return;
        var d = !isDark(); apply(d);
        try { localStorage.theme = d ? "dark" : "light"; } catch (er) { }
        paint(t);
        document.dispatchEvent(new CustomEvent("zeim:theme", { detail: { dark: d } }));
      });
      addEventListener("storage", function (e) { if (e.key === "theme") { apply(e.newValue === "dark"); var x = document.getElementById("themeToggle"); if (x) paint(x); } });
    }
  }
  /* ---------- Colours & accessibility: theme (light/dark/system), accent, high contrast, colour-vision-safe palettes ---------- */
  var LOOK_KEY = "zeim_look";
  function look() { try { return JSON.parse(localStorage.getItem(LOOK_KEY) || "{}") || {}; } catch (e) { return {}; } }
  function applyLook(l) {
    ["accent", "contrast", "cb"].forEach(function (k) { if (l[k] && l[k] !== "default") root.setAttribute("data-" + k, l[k]); else root.removeAttribute("data-" + k); });
  }
  function themePref() { try { return localStorage.theme === "dark" ? "dark" : (localStorage.theme === "light" || localStorage.theme === "warm") ? "light" : "system"; } catch (e) { return "system"; } }
  function setTheme(v) {
    try { if (v === "system") localStorage.removeItem("theme"); else localStorage.theme = v; } catch (e) { }
    apply(v === "dark" || (v === "system" && matchMedia("(prefers-color-scheme: dark)").matches));
    var x = document.getElementById("themeToggle"); if (x) paint(x);
  }
  applyLook(look());
  try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () { if (themePref() === "system") setTheme("system"); }); } catch (e) { }
  var PAL = '<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3a9 9 0 1 0 0 18c1 0 1.5-.7 1.5-1.5 0-1-.8-1.4-.8-2.3 0-.8.7-1.2 1.6-1.2H16a5 5 0 0 0 5-5c0-4.4-4-8-9-8z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7.5" r="1"/><circle cx="14.5" cy="7.5" r="1"/></svg>';
  function opt(v, t, cur) { return '<option value="' + v + '"' + (v === cur ? " selected" : "") + ">" + t + "</option>"; }
  function openLook() {
    var d = document.getElementById("dlgLook");
    if (!d) { d = document.createElement("dialog"); d.id = "dlgLook"; d.setAttribute("aria-labelledby", "lookTitle"); document.body.appendChild(d); }
    var l = look(), t = themePref();
    d.innerHTML = '<div class="dlg"><div class="dh"><h3 id="lookTitle">Colours &amp; accessibility</h3><button type="button" class="x" data-lookclose aria-label="Close">✕</button></div>' +
      '<div class="body lookgrid">' +
      '<label>Theme<select id="lookTheme">' + opt("light", "Light", t) + opt("dark", "Dark", t) + opt("system", "Same as my device", t) + "</select></label>" +
      '<label>Accent colour<select id="lookAccent">' + opt("default", "Blue (ZEIM)", l.accent || "default") + opt("teal", "Teal", l.accent) + opt("orange", "Orange", l.accent) + "</select></label>" +
      '<label class="inl"><input type="checkbox" id="lookContrast"' + (l.contrast === "high" ? " checked" : "") + "> High contrast</label>" +
      '<label>Colour vision<select id="lookCb">' + opt("default", "Standard colours", l.cb || "default") + opt("redgreen", "Red-green safe (deuteranopia / protanopia)", l.cb) + opt("blueyellow", "Blue-yellow safe (tritanopia)", l.cb) + "</select></label>" +
      '<p class="help">Saved on this device. Warnings and problems always show a symbol and words, not just a colour.</p>' +
      '<div class="row"><button type="button" class="btn" id="lookReset">Reset to default</button><button type="button" class="btn primary" data-lookclose>Done</button></div></div></div>';
    var save = function () {
      var n = { accent: d.querySelector("#lookAccent").value, contrast: d.querySelector("#lookContrast").checked ? "high" : "default", cb: d.querySelector("#lookCb").value };
      try { localStorage.setItem(LOOK_KEY, JSON.stringify(n)); } catch (e) { }
      applyLook(n); setTheme(d.querySelector("#lookTheme").value);
    };
    d.querySelectorAll("select,input").forEach(function (x) { x.addEventListener("change", save); });
    d.querySelector("#lookReset").onclick = function () { try { localStorage.removeItem(LOOK_KEY); } catch (e) { } applyLook({}); setTheme("system"); openLook(); };
    d.querySelectorAll("[data-lookclose]").forEach(function (x) { x.onclick = function () { d.close(); var b = document.getElementById("lookBtn"); if (b) b.focus(); }; });
    if (!d.open) d.showModal ? d.showModal() : d.setAttribute("open", "");
  }
  window.zeimOpenLook = openLook;
  function setupLook() {
    var t = document.getElementById("themeToggle"); if (!t || document.getElementById("lookBtn")) return;
    var b = document.createElement("button"); b.type = "button"; b.id = "lookBtn"; b.className = "lookbtn" + (t.classList.contains("cw-btn") ? " cw-btn" : "");
    b.setAttribute("aria-label", "Colours and accessibility"); b.title = "Colours & accessibility"; b.innerHTML = PAL;
    b.addEventListener("click", openLook);
    t.parentNode.insertBefore(b, t);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup); else setup();
})();
