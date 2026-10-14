/* Minimal moderator page (CR-11 d): lists OPEN reports oldest first with a preview and Hide / Restore / Dismiss. The token lives in memory only. */
let TOKEN = "";
const $ = s => document.querySelector(s);
const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); kids.forEach(k => e.append(k)); return e; };
// Never show "[object Object]": a string detail as-is, a structured one by its message, a 422 list as plain words.
function errText(j, r) {
  const d = j?.detail ?? j?.message;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object" && !Array.isArray(d) && typeof d.message === "string") return d.message;
  if (Array.isArray(d)) return "Something in that request isn't right. Please try again.";
  return r.statusText || "Something went wrong. Please try again.";
}
async function call(path, opt = {}) {
  const r = await fetch(path, { ...opt, headers: { ...(opt.headers || {}), "X-Admin-Token": TOKEN, "Content-Type": "application/json" } });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(errText(j, r));
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
      card.append(el("b", {}, `${p.title || r.item_id} `), el("span", { className: "pill" }, r.reason), el("span", { className: "help" }, ` · ${p.kind || ""}${p.creator ? " · by " + p.creator : ""} · filed ${r.created}`));
      if (p.text) card.append(el("p", {}, p.text));
      if (r.details) card.append(el("p", { className: "help" }, "Reporter said: " + r.details));
      if (p.hidden) card.append(el("p", { className: "help" }, "Currently hidden."));
      const row = el("div", { className: "row" });
      if (p.suspended) card.append(el("p", { className: "help" }, "Account suspended."));
      if (p.nsfw) card.append(el("p", { className: "help" }, "Tagged NSFW (shown blurred as Mature content)."));
      const acts = [["hide", "Hide"], ["restore", "Restore"], ["dismiss", "Dismiss"]];
      if (!r.item_id?.startsWith("user:")) acts.push(p.nsfw ? ["unmark_nsfw", "Remove NSFW tag"] : ["mark_nsfw", "Mark NSFW"], ["remove", "Remove (explicit)"]);
      if (r.account_id) acts.push(["suspend", "Suspend account"]);     // e.g. 'underage_user': ZEIM is 18+ only. Data deletion: README "Underage accounts"
      for (const [a, label] of acts) {
        const b = el("button", { type: "button", className: "btn small" + (a === "hide" || a === "suspend" || a === "remove" ? " danger" : "") }, label);
        b.onclick = async () => { b.disabled = true; try { await call(`/api/moderation/${r.id}/resolve`, { method: "POST", body: JSON.stringify({ action: a }) }); await load(); } catch (e) { $("#msg").textContent = e.message; b.disabled = false; } };
        row.append(b);
      }
      card.append(row); list.append(card);
      if (p.thumb) { fetch(p.thumb, { headers: { "X-Admin-Token": TOKEN } }).then(x => x.ok ? x.blob() : null).then(bl => { if (bl) { const im = el("img", { alt: "", width: 120 }); im.src = URL.createObjectURL(bl); card.prepend(im); } }); }
    }
    // 'I printed this' photos waiting for review (all ages): approve shows it in the gallery, reject deletes it
    const pl = $("#plist") || (() => { const d = el("div", { id: "plist" }); list.after(d); return d; })();
    pl.replaceChildren(el("h2", {}, `Print photos waiting for review (${q.pending_prints.length})`));
    for (const p of q.pending_prints) {
      const card = el("div", { className: "printer" });
      card.append(el("b", {}, "I printed this "), el("span", { className: "help" }, `${p.by} · project ${p.item_id}`));
      if (p.caption) card.append(el("p", {}, p.caption));
      card.append(el("p", { className: "help" }, p.nsfw ? "Tagged NSFW by the uploader (shown blurred)." : "Not tagged NSFW."));
      const row = el("div", { className: "row" });
      const tb = el("button", { type: "button", className: "btn small" }, p.nsfw ? "Remove NSFW tag" : "Mark NSFW");
      tb.onclick = async () => { tb.disabled = true; try { await call(`/api/moderation/item/print:${p.id}/nsfw`, { method: "POST", body: JSON.stringify({ nsfw: !p.nsfw }) }); await load(); } catch (e) { $("#msg").textContent = e.message; tb.disabled = false; } };
      row.append(tb);
      for (const [a, label] of [["approve", "Approve"], ["reject", "Reject and delete"]]) {
        const b = el("button", { type: "button", className: "btn small" + (a === "reject" ? " danger" : "") }, label);
        b.onclick = async () => { b.disabled = true; try { await call(`/api/moderation/prints/${p.id}/${a}`, { method: "POST" }); await load(); } catch (e) { $("#msg").textContent = e.message; b.disabled = false; } };
        row.append(b);
      }
      card.append(row); pl.append(card);
      fetch(p.thumb, { headers: { "X-Admin-Token": TOKEN } }).then(x => x.ok ? x.blob() : null).then(bl => { if (bl) { const im = el("img", { alt: "Print photo to review", width: 160 }); im.src = URL.createObjectURL(bl); card.prepend(im); } });
    }
  } catch (e) { $("#msg").textContent = e.message; $("#list").replaceChildren(); }
}
$("#tokForm").addEventListener("submit", e => { e.preventDefault(); TOKEN = $("#tok").value; load(); });
