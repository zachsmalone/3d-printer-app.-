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
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup); else setup();
})();
