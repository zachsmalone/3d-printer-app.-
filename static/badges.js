/* Account badges. The server decides what was earned. This only draws the box and a small toast. */
(function () {
  var toasted = {};
  var GLYPH = {
    tester: '<path d="M12 19s-6-3.6-6-7.4A3.2 3.2 0 0 1 12 9a3.2 3.2 0 0 1 6 2.6C18 15.4 12 19 12 19z"/>',
    official_og: '<circle cx="12" cy="12" r="7"/><path d="M12 8.2l1.1 2.2 2.4.3-1.8 1.7.4 2.4L12 13.6 9.9 14.8l.4-2.4-1.8-1.7 2.4-.3z"/>',
    first_slice: '<path d="M5 8h14M5 12h14M5 16h14"/>',
    first_export: '<path d="M12 5v9M8 10l4 4 4-4M6 19h12"/>',
    first_print: '<path d="M8 7h8v3H8zM6 10h12v5H6zM9 15v3h6v-3"/>',
    first_lithophane: '<rect x="6" y="4" width="12" height="16" rx="1.2"/><path d="M8 15l2.5-2.5 2 2 3.5-3.5"/>',
    first_resin: '<path d="M12 4c2.2 3.2 4 5.2 4 8a4 4 0 0 1-8 0c0-2.8 1.8-4.8 4-8z"/>',
    first_cad: '<path d="M12 4l7 4v8l-7 4-7-4V8z"/><path d="M12 12l7-4M12 12v8M12 12L5 8"/>',
    first_showcase: '<circle cx="12" cy="12" r="7"/><path d="M5 12h14M12 5c2.2 2.2 2.2 9.6 0 14M12 5c-2.2 2.2-2.2 9.6 0 14"/>',
    first_remix: '<path d="M8 7h7l-2-2M16 17H9l2 2"/><path d="M15 5v4h4M9 19v-4H5"/>',
    challenge_entrant: '<path d="M6 20V5h9l-1.6 3.2L15 11H6"/>',
    prints_10: '<text x="12" y="16" text-anchor="middle" font-size="9" fill="currentColor" stroke="none">10</text>'
  };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function toast(msg) {
    var host = document.getElementById("toasts");
    if (!host) return false;
    var t = document.createElement("div");
    t.className = "toast ok";
    t.textContent = msg;
    host.appendChild(t);
    setTimeout(function () { t.remove(); }, 4200);
    return true;
  }

  function announce(list) {
    if (!list || !list.length) return;
    var shown = false;
    list.forEach(function (b) {
      if (!b || !b.id || toasted[b.id]) return;
      toasted[b.id] = true;
      if (toast("Badge earned: " + (b.name || "Badge"))) shown = true;
    });
    if (shown) {
      fetch("/api/me/badges/seen", { method: "POST", credentials: "same-origin" }).catch(function () {});
    }
  }

  function parseHeader(h) {
    return String(h).split(",").map(function (part) {
      var bits = part.split("|");
      var id = (bits[0] || "").trim();
      var name = (bits.slice(1).join("|") || id).trim();
      return id ? { id: id, name: name } : null;
    }).filter(Boolean);
  }

  var orig = window.fetch;
  if (typeof orig === "function" && !orig.__zeimBadges) {
    window.fetch = function () {
      return orig.apply(this, arguments).then(function (res) {
        try {
          var h = res.headers && res.headers.get && res.headers.get("X-Zeim-Badges");
          if (h && res.ok) announce(parseHeader(h));
          var ct = (res.headers && res.headers.get && res.headers.get("content-type")) || "";
          if (res.ok && ct.indexOf("application/json") !== -1) {
            res.clone().json().then(function (j) {
              if (j && Array.isArray(j.badges_new)) announce(j.badges_new);
            }).catch(function () {});
          }
        } catch (e) { /* a toast must never break the request */ }
        return res;
      });
    };
    window.fetch.__zeimBadges = true;
  }

  function emblem(id) {
    var body = GLYPH[id] || '<circle cx="12" cy="12" r="4"/>';
    return '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + body + "</svg>";
  }

  function render(data) {
    var box = document.getElementById("accBadges");
    if (!box) return;
    if (!data || !data.signed_up) {
      box.innerHTML = '<p class="help">Sign in to see badges.</p>';
      return;
    }
    var rows = data.badges || [];
    if (!rows.length) {
      box.innerHTML = '<p class="help">No badges yet.</p>';
      return;
    }
    box.innerHTML = '<ul class="badgegrid">' + rows.map(function (b) {
      var locked = !b.earned;
      var sub = locked ? (b.how || "") : (b.label || "");
      if (locked && b.need > 1 && b.progress) sub = (sub ? sub + " " : "") + b.progress + " of " + b.need + " so far.";
      var inner = '<span class="emblem">' + emblem(b.id) + '</span><span class="meta"><span class="name">' + esc(b.name) + "</span>" +
        (sub ? '<span class="' + (locked ? "how" : "label") + '">' + esc(sub) + "</span>" : "") + "</span>";
      if (b.note) {
        return '<li><button type="button" class="badge earned" data-kind="' + esc(b.id) + '" data-note="1">' + inner + "</button></li>";
      }
      return '<li><div class="badge ' + (locked ? "locked" : "earned") + '" data-kind="' + esc(b.id) + '">' + inner + "</div></li>";
    }).join("") + "</ul>";
    box.querySelectorAll("button[data-note]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var kind = btn.getAttribute("data-kind");
        var row = (data.badges || []).filter(function (b) { return b.id === kind; })[0];
        if (!row || !row.note) return;
        var dlg = document.getElementById("dlgBadge");
        var title = document.getElementById("badgeDlgTitle");
        var text = document.getElementById("badgeDlgText");
        if (!dlg || !title || !text) return;
        title.textContent = row.label || row.name;
        text.textContent = row.note;
        if (typeof dlg.showModal === "function") dlg.showModal();
      });
    });
  }

  function load() {
    var box = document.getElementById("accBadges");
    if (!box) return;
    fetch("/api/me/badges", { credentials: "same-origin" }).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (data) {
      if (!data) return;
      render(data);
      announce(data.unseen || []);
    }).catch(function () {});
  }

  document.addEventListener("zeim:me", load);
  document.addEventListener("zeim:badges", load);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load);
  else load();
})();
