/* UX9: one breadcrumb bar, the same in every studio: Home › Studio › Project (project only when it has a real name). */
(function () {
  var NAMES = { slicer: "Slicer", torchc0: "Resin", lithophane: "Lithophane", smartfix: "Fix", ai3d: "2D to 3D", cad: "CAD" };
  var nav = document.createElement("nav");
  nav.className = "zcrumb"; nav.setAttribute("aria-label", "Breadcrumb"); nav.hidden = true;
  function seg(text, href) { var e = document.createElement(href ? "a" : "span"); e.textContent = text; if (href) e.href = href; return e; }
  function sep() { var s = document.createElement("span"); s.className = "zcrumb-sep"; s.setAttribute("aria-hidden", "true"); s.textContent = "›"; return s; }
  function paint(view, project) {
    var name = NAMES[view];
    nav.hidden = !name; nav.textContent = "";
    if (!name) return;
    nav.append(seg("Home", "/"), sep());
    if (project) { nav.append(seg(name, view === "cad" ? null : "#" + view), sep()); var p = seg(project); p.setAttribute("aria-current", "page"); nav.append(p); }
    else { var s = seg(name); s.setAttribute("aria-current", "page"); nav.append(s); }
  }
  function init() {
    if (document.querySelector(".zcrumb")) return;
    var cad = document.body.classList.contains("cadws");
    if (cad) {
      document.body.insertBefore(nav, document.body.firstChild);
      var t = document.getElementById("cwTitle");
      var up = function () { paint("cad", t && t.value.trim()); };
      if (t) t.addEventListener("input", up);
      nav.addEventListener("click", function (e) { var a = e.target.closest("a"), back = document.getElementById("cwBack"); if (a && back) { e.preventDefault(); back.click(); } });   // same leave/save guard as Exit
      up(); setTimeout(up, 800);
    } else {
      var top = document.querySelector("header.topbar");
      if (top) top.after(nav); else document.body.prepend(nav);
      var up2 = function () { paint(document.body.dataset.view || ""); };
      new MutationObserver(up2).observe(document.body, { attributes: true, attributeFilter: ["data-view"] });
      up2();
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
