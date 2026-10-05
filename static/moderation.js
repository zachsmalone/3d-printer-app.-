/* Minimal moderator page (CR-11 d): lists OPEN reports oldest first with a preview and Hide / Restore / Dismiss. The token lives in memory only. */
let TOKEN = "";
const $ = s => document.querySelector(s);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); kids.forEach(k => e.append(k)); return e; };
async function call(path, opt = {}) {
  const r = await fetch(path, { ...opt, headers: { ...(opt.headers || {}), "X-Admin-Token": TOKEN, "Content-Type": "application/json" } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
const ago = s => s == null ? "" : s < 90 ? s + " seconds" : s < 5400 ? Math.round(s / 60) + " minutes" : s < 172800 ? Math.round(s / 3600) + " hours" : Math.round(s / 86400) + " days";
async function load() {
  $("#msg").textContent = "Loading…";
  try {
    const q = await call("/api/moderation/queue");
    $("#msg").textContent = q.reports.length ? "" : "No open reports.";
    $("#age").textContent = q.oldest_open_age_s == null ? "" : "Oldest open report: " + ago(q.oldest_open_age_s) + " old.";
    const list = $("#list"); list.replaceChildren();
    for (const r of q.reports) {
      const p = r.preview || {};
      const card = el("div", { className: "printer" });
      card.append(el("b", {}, `${p.title || r.item_id} `), el("span", { className: "pill" }, r.reason), el("span", { className: "help" }, ` · ${p.kind || ""} · filed ${r.created}`));
      if (p.text) card.append(el("p", {}, p.text));
      if (r.details) card.append(el("p", { className: "help" }, "Reporter said: " + r.details));
      if (p.hidden) card.append(el("p", { className: "help" }, "Currently hidden."));
      const row = el("div", { className: "row" });
      for (const [a, label] of [["hide", "Hide"], ["restore", "Restore"], ["dismiss", "Dismiss"]]) {
        const b = el("button", { type: "button", className: "btn small" + (a === "hide" ? " danger" : "") }, label);
        b.onclick = async () => { b.disabled = true; try { await call(`/api/moderation/${r.id}/resolve`, { method: "POST", body: JSON.stringify({ action: a }) }); await load(); } catch (e) { $("#msg").textContent = e.message; b.disabled = false; } };
        row.append(b);
      }
      card.append(row); list.append(card);
      if (p.thumb) { fetch(p.thumb, { headers: { "X-Admin-Token": TOKEN } }).then(x => x.ok ? x.blob() : null).then(bl => { if (bl) { const im = el("img", { alt: "", width: 120 }); im.src = URL.createObjectURL(bl); card.prepend(im); } }); }
    }
  } catch (e) { $("#msg").textContent = e.message; $("#list").replaceChildren(); }
}
$("#tokForm").addEventListener("submit", e => { e.preventDefault(); TOKEN = $("#tok").value; load(); });
