/* Multi-printer board + manual queue + bambu limits (print-send10). */
const $ = (s, r = document) => r.querySelector(s);

async function api(url, opts) {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.message || r.statusText);
  return j;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function renderBoard() {
  const list = $("#boardList"), q = $("#queueList"), alerts = $("#boardAlerts"), note = $("#boardNote");
  if (!list) return;
  list.innerHTML = "<p class='help'>Loading…</p>";
  try {
    const [board, queue, lim] = await Promise.all([
      api("/api/printers/board"),
      api("/api/print-queue"),
      api("/api/bambu/limits"),
    ]);
    if (note) note.textContent = (board.note || "") + (board.verification ? ` · ${board.verification}` : "");
    if ($("#bambuLimitsNote")) {
      $("#bambuLimitsNote").textContent = lim.note || "Bambu LAN needs LAN Only; control needs Developer Mode. Keep Open in Bambu Studio as fallback.";
    }
    const alertBits = [];
    for (const p of board.printers || []) {
      if (p.new_alerts) for (const a of p.new_alerts) alertBits.push(a.message);
    }
    if (alerts) alerts.textContent = alertBits.length ? alertBits.join(" · ") : "";
    list.innerHTML = (board.printers || []).map(p => {
      const pct = p.progress_pct != null ? `${Number(p.progress_pct).toFixed(1)}%` : "—";
      const flags = [
        p.alert_done ? "done-alert" : "",
        p.alert_failed ? "fail-alert" : "",
        p.watch_failures ? "pause-on-fail" : "",
        p.timelapse ? "timelapse" : "",
      ].filter(Boolean).join(", ");
      return `<div class="printer" data-pid="${esc(p.id)}">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>${esc(p.name || "Printer")}</strong>
          <span class="pill">${esc(p.state || "—")} · ${esc(pct)}</span>
        </div>
        <p class="help">${esc(p.job_name || "No active job")} · ${esc(p.type || "")}${flags ? " · " + esc(flags) : ""}
        ${p.verification ? " · " + esc(p.verification) : ""}</p>
        <p class="help">${esc(p.message || "")}</p>
        <div class="row">
          <button type="button" class="btn small" data-act="pause">Pause</button>
          <button type="button" class="btn small" data-act="resume">Resume</button>
          <button type="button" class="btn small danger" data-act="cancel">Stop</button>
          <button type="button" class="btn small ghost" data-act="tl-start">Timelapse start</button>
          <button type="button" class="btn small ghost" data-act="tl-tick">Frame</button>
          <button type="button" class="btn small ghost" data-act="tl-stop">Timelapse stop</button>
        </div>
        <img alt="" width="240" height="135" style="max-width:100%;margin-top:6px;border-radius:6px;background:#111"
             src="/api/printers/${encodeURIComponent(p.id)}/camera?t=${Date.now()}" onerror="this.style.display='none'">
      </div>`;
    }).join("") || "<p class='help'>No printers saved yet. Add one in Settings.</p>";

    q.innerHTML = (queue.jobs || []).map(j => `<div class="printer" data-qid="${esc(j.id)}">
      <div class="row" style="justify-content:space-between"><strong>${esc(j.name)}</strong><span class="pill">${esc(j.status)}</span></div>
      <p class="help">Build ${esc(j.build_id)} → printer ${esc(j.printer_id)}</p>
      <div class="row">
        <button type="button" class="btn small primary" data-q="start" ${j.status === "sent" ? "disabled" : ""}>Start</button>
        <button type="button" class="btn small danger" data-q="rm">Remove</button>
      </div>
    </div>`).join("") || "<p class='help'>Queue is empty.</p>";
  } catch (e) {
    list.innerHTML = `<p class="help">✖ ${esc(e.message)}</p>`;
  }
}

async function openPrinterBoard() {
  const dlg = $("#dlgPrinterBoard");
  if (!dlg) return;
  await renderBoard();
  dlg.showModal();
}

$("#btnBoardRefresh")?.addEventListener("click", () => renderBoard());
$("#boardList")?.addEventListener("click", async e => {
  const btn = e.target.closest("[data-act]"); if (!btn) return;
  const card = btn.closest("[data-pid]"); const id = card?.dataset.pid; if (!id) return;
  const act = btn.dataset.act;
  try {
    if (act === "pause" || act === "resume" || act === "cancel") {
      if (act === "cancel" && !confirm("Stop this print on the printer?")) return;
      const fd = new FormData(); fd.append("action", act);
      await api(`/api/printers/${id}/control`, { method: "POST", body: fd });
    } else if (act === "tl-start") await api(`/api/printers/${id}/timelapse/start`, { method: "POST" });
    else if (act === "tl-stop") await api(`/api/printers/${id}/timelapse/stop`, { method: "POST" });
    else if (act === "tl-tick") await api(`/api/printers/${id}/timelapse/tick`, { method: "POST" });
    await renderBoard();
  } catch (er) { alert(er.message); }
});
$("#queueList")?.addEventListener("click", async e => {
  const btn = e.target.closest("[data-q]"); if (!btn) return;
  const card = btn.closest("[data-qid]"); const id = card?.dataset.qid; if (!id) return;
  try {
    if (btn.dataset.q === "start") await api(`/api/print-queue/${id}/start`, { method: "POST" });
    else if (btn.dataset.q === "rm") await api(`/api/print-queue/${id}`, { method: "DELETE" });
    await renderBoard();
  } catch (er) { alert(er.message); }
});

window.ZEIM_openPrinterBoard = openPrinterBoard;
