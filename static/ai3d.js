/* 2D→3D tab: one photo -> mesh (TripoSR worker). Server: app/api/ai3d.py.
   Photo prep runs first (crop, light, grey). The preview mesh is the mesh that exports.
   The result is a private ZEIM build, so Export, CAD, repair, and the slicer use the shared hand-off.
   Warnings are shown, never block. The cooldown is one status line; the rest of ZEIM stays usable. */
import { api, toast, loadHistory, $, esc } from "/static/app.js";
import { Viewer } from "/static/viewer.js";
import { open as openExport } from "/static/exportpick.js";
import { sendTo } from "/static/handoff.js";

let file = null, viewer = null, status = null, timer = null, poll = null, jobGen = 0, prepGen = 0, prepTimer = 0, resultId = null;
const ico = id => `<svg class="i" aria-hidden="true" focusable="false"><use href="#i-${id}"/></svg>`;
const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const mode = () => document.querySelector("input[name=a3Mode]:checked")?.value || "figure";
const flag = id => $(id)?.checked ? "true" : "false";
const resin = () => document.body.dataset.printKind === "resin";

function ready() {
  const p = status?.plan, e = status?.engine;
  const ok = !!file && $("#a3Ack").checked && e?.installed && p?.allowed && !poll;
  $("#a3Go").disabled = !ok;
}

function paintEngine() {
  const e = status.engine, el = $("#a3Engine");
  if (!e.installed) {
    el.className = "a3note warn";
    el.innerHTML = `${ico("wrench")}<div><b>The 2D to 3D engine is not installed on this server yet.</b><p>It runs as a separate, optional part of ZEIM. The owner of this server can add it with the steps in <code>workers/ai3d/README.md</code>. Everything else in ZEIM works without it.</p></div>`;
  } else if (!e.ready) {
    el.className = "a3note warn";
    el.innerHTML = `${ico("clock")}<div><b>The engine is starting or still downloading its files.</b><p>Try again in a few minutes.</p></div>`;
  } else {
    const device = e.device === "cuda" ? "graphics card" : e.device === "cpu" ? "processor; this can take several minutes" : e.device;
    el.className = "a3note";
    el.innerHTML = `${ico("cube")}<div><p>Photo to mesh with ${esc(e.name)} by ${esc(e.by)}, an open model (${esc(e.licence)}). Running on this server${device ? " (" + esc(device) + ")" : ""}.</p></div>`;
  }
}

function pauseLine(p) {
  const mins = Number(p.cooldown_min) || 0;
  if (!mins) return "No pause between photo to mesh runs on this server.";
  return `${mins} min between finished photo to mesh runs. Editing this mesh does not start the wait again.`;
}

function paintPlan() {
  const p = status.plan, el = $("#a3Plan"), tick = $("#a3Tick");
  clearInterval(timer);
  if (tick) { tick.hidden = true; tick.textContent = ""; }
  if (p.testing_mode && p.reason !== "cap") {
    el.textContent = p.allow_paid
      ? "Testing mode is on for this server. The pause and the daily model cap are off. Sign-in checks still apply."
      : (p.cap ? `Testing mode is on for this server. The pause between models is off. ${p.used_today} of ${p.cap} photo to mesh runs today.` : "Testing mode is on for this server. The pause between models is off.");
    ready(); return;
  }
  if (p.reason === "pro") { el.textContent = "2D to 3D is part of Pro."; ready(); return; }
  const capTxt = p.cap ? `Testing period: ${p.used_today} of ${p.cap} models today.` : "";
  if (p.reason === "cap") { el.textContent = `That is today's ${p.cap} test models. More tomorrow.`; ready(); return; }
  if (p.wait_s > 0) {
    let left = p.wait_s;
    const about = Math.max(1, Math.ceil(left / 60));
    el.textContent = `Next photo to mesh in about ${about} min. ${pauseLine(p)} ${capTxt}`.trim();
    const show = () => { if (tick) { tick.hidden = false; tick.textContent = mmss(Math.max(0, left)); } };
    show();
    timer = setInterval(() => {
      left -= 1;
      show();
      if (left <= 0) { clearInterval(timer); refresh(); }
    }, 1000);
  } else el.textContent = `${pauseLine(p)} ${capTxt}`.trim();
  ready();
}

function paintClosed() {
  const nav = document.querySelector('#mainNav [data-view="ai3d"]');
  if (nav) { nav.hidden = true; nav.disabled = true; }
  const grid = document.querySelector("#viewAi3d .a3grid");
  if (grid) grid.hidden = true;
  const goBtn = $("#a3Go");
  if (goBtn) { goBtn.disabled = true; goBtn.hidden = true; }
  const el = $("#a3Engine");
  if (el) {
    el.className = "a3note";
    el.innerHTML = "<div><b>2D to 3D is coming later.</b><p>Lithophanes, the slicers, CAD and Showcase stay available. Nothing here starts a mesh.</p></div>";
  }
}

async function refresh() {
  try { status = await api("/api/ai3d/status"); } catch (e) { $("#a3Engine").textContent = e.message; return; }
  if (status.enabled === false) { paintClosed(); return; }
  paintEngine(); paintPlan();
}

function setFile(f) {
  file = f;
  const img = $("#a3Img"); img.src = URL.createObjectURL(f); img.hidden = false; $("#a3DropTxt").hidden = true;
  ready();
  schedulePrep();
}

function schedulePrep() {
  clearTimeout(prepTimer);
  prepTimer = setTimeout(runPrep, 250);
}

async function runPrep() {
  const gen = ++prepGen;
  const note = $("#a3PrepNote");
  if (!file || status?.enabled === false) return;
  if (!$("#a3Ack").checked) {
    if (note) note.textContent = "Tick the permission line to preview photo prep. The photo stays on this page until then.";
    return;
  }
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", mode());
  fd.append("photo_ack", "true");
  fd.append("prep_crop", flag("#a3Crop"));
  fd.append("prep_tone", flag("#a3Tone"));
  fd.append("prep_bg", flag("#a3Bg"));
  try {
    const r = await api("/api/ai3d/prep", { method: "POST", body: fd });
    if (gen !== prepGen) return;
    if (r.png_b64) {
      const img = $("#a3Img");
      img.src = "data:image/png;base64," + r.png_b64;
      img.alt = "Prepared photo sent to TripoSR";
    }
    if (note) note.textContent = (r.notes && r.notes.length) ? r.notes.join(" ") : "Photo prep left this photo as it is.";
  } catch (e) {
    if (gen !== prepGen) return;
    if (note) note.textContent = e.message || "Photo prep could not run. You can still make the mesh.";
  }
}

function showResult(r) {
  resultId = r.id || null;
  if (!viewer) try { viewer = new Viewer($("#a3View")); } catch { }
  $("#a3Empty").hidden = true;
  viewer?.load(r.preview, "ai3d", { flat: true });
  const rep = r.report || {}, notes = rep.notes || [], warns = rep.warnings || [];
  const sz = r.stats?.size_mm || [];
  const toSlicer = resin() ? "torchc0" : "slicer";
  const slicerLabel = resin() ? "Send to TorchC0" : "Send to Slicer";
  $("#a3Res").hidden = false;
  $("#a3Res").innerHTML = `<p class="a3title"><b>${esc(r.title)}</b> <span class="ailbl" title="Made with an open model">${ico("sparkle")} ${esc(r.ai_label || "AI-made")}</span></p>
    <p class="help">${sz.length ? sz.map(n => Math.round(n)).join(" × ") + " mm" : ""} · ${rep.watertight ? ico("check") + " Watertight, ready to slice" : "Not fully watertight"}</p>
    <p class="help">Preview matches this mesh. Export, repair, CAD, and the slicer use the same triangles. Those buttons do not send it to Showcase.</p>
    ${notes.length ? `<ul class="a3list">${notes.map(n => `<li>${ico("check")} ${esc(n)}</li>`).join("")}</ul>` : ""}
    ${warns.length ? `<ul class="a3list warn">${warns.map(n => `<li>${ico("alert")} ${esc(n)}</li>`).join("")}</ul>` : ""}
    <div class="row a3handoff" role="group" aria-label="Open this mesh in another ZEIM tool">
      <button type="button" class="btn" id="a3Slicer" data-to="${toSlicer}">${ico("send")} ${slicerLabel}</button>
      <button type="button" class="btn" id="a3Repair">${ico("wrench")} Check &amp; Repair</button>
      <button type="button" class="btn" id="a3Cad">${ico("cube")} Send to CAD</button>
      <button type="button" class="btn primary" id="a3Export">${ico("download")} Export</button>
      <button type="button" class="btn" id="a3Publish" title="Open the Showcase form for this mesh. Nothing is published until you confirm in that form.">${ico("globe")} Send to Showcase</button>
    </div>`;
  const go = async (btn, target, tool) => {
    if (!resultId || btn.disabled) return;
    btn.disabled = true; btn.setAttribute("aria-busy", "true");
    try { await sendTo(target, "ai3d", { editId: resultId, tool: tool || "" }); }
    finally { btn.disabled = false; btn.removeAttribute("aria-busy"); }
  };
  $("#a3Slicer").onclick = () => go($("#a3Slicer"), toSlicer, "");
  $("#a3Repair").onclick = () => go($("#a3Repair"), "slicer", "repair");
  $("#a3Cad").onclick = () => go($("#a3Cad"), "cad", "");
  $("#a3Export").onclick = () => openExport({ ws: "ai3d", bid: r.id });
  $("#a3Publish").onclick = () => {
    if (!resultId) return;
    const title = ($("#a3Title")?.value || "").trim() || r.title || "";
    if (typeof window.zeimOpenShowcase !== "function") { toast("Send to Showcase is not available on this page.", "err"); return; }
    window.zeimOpenShowcase({ id: resultId, title, ai: true, mode: "ai3d" });
  };
}

function clearAi3dWork() {
  jobGen += 1;
  prepGen += 1;
  if (poll) { clearInterval(poll); poll = null; }
  file = null;
  resultId = null;
  const inp = $("#a3File"); if (inp) inp.value = "";
  const img = $("#a3Img"); if (img) { img.hidden = true; img.removeAttribute("src"); img.alt = "Your photo"; }
  const drop = $("#a3DropTxt"); if (drop) drop.hidden = false;
  const res = $("#a3Res"); if (res) { res.hidden = true; res.innerHTML = ""; }
  const empty = $("#a3Empty"); if (empty) empty.hidden = false;
  const st = $("#a3Status"); if (st) st.innerHTML = "";
  const ack = $("#a3Ack"); if (ack) ack.checked = false;
  const note = $("#a3PrepNote");
  if (note) note.textContent = "ZEIM does this before TripoSR runs. Uncheck a line to leave that part of the photo alone.";
  if (viewer && viewer.group) viewer.group.clear();
  ready();
}
document.addEventListener("zeim:new-build", e => {
  if (!e.detail || e.detail.section !== "ai3d" || e.detail.publish) return;
  clearAi3dWork();
});

async function go() {
  if (!status || status.enabled === false) return;
  const gen = ++jobGen;
  const fd = new FormData();
  fd.append("file", file); fd.append("mode", mode()); fd.append("photo_ack", $("#a3Ack").checked ? "true" : "false");
  fd.append("prep_crop", flag("#a3Crop")); fd.append("prep_tone", flag("#a3Tone")); fd.append("prep_bg", flag("#a3Bg"));
  const title = ($("#a3Title").value.trim() || $("#a3Title").placeholder);
  fd.append("title", title);
  if ($("#a3H").value) fd.append("height_mm", $("#a3H").value);
  $("#a3Go").disabled = true;
  const st = $("#a3Status");
  let j;
  try { j = await api("/api/ai3d/jobs", { method: "POST", body: fd }); }
  catch (e) { st.innerHTML = `<p class="a3err" role="alert">${ico("alert")} ${esc(e.message)}</p>`; refresh(); return; }
  st.innerHTML = `<p class="a3busy"><span class="a3spin" aria-hidden="true"></span> Turning this photo into a mesh with TripoSR… <span id="a3El">0:00</span></p><p class="help">You can keep using ZEIM. This page shows the mesh when it is done.</p>`;
  const watch = setInterval(async () => {
    if (gen !== jobGen) { clearInterval(watch); if (poll === watch) poll = null; return; }
    let s; try { s = await api("/api/ai3d/jobs/" + j.job); } catch (e) { return; }
    if (gen !== jobGen) { clearInterval(watch); if (poll === watch) poll = null; return; }
    const el = $("#a3El"); if (el) el.textContent = mmss(s.elapsed_s || 0);
    if (s.state === "running") return;
    clearInterval(watch); if (poll === watch) poll = null;
    if (s.state === "done") { st.innerHTML = ""; showResult(s.result); toast("Your mesh is ready", "ok"); loadHistory?.(); if (s.plan) { status.plan = s.plan; paintPlan(); } }
    else { st.innerHTML = `<p class="a3err" role="alert">${ico("alert")} ${esc(s.error || "That did not work.")} Your photo is still here, so you can try again.</p>`; refresh(); }
  }, 1500);
  poll = watch;
}

$("#a3File").onchange = e => { const f = e.target.files?.[0]; if (f) { delete $("#a3Title").dataset.sample; $("#a3Title").placeholder = mode() === "bust" ? "My bust" : "My figure"; setFile(f); } };
$("#a3Sample").onclick = async () => { const b = await (await fetch("/static/sample.jpg")).blob(); setFile(new File([b], "sample.jpg", { type: "image/jpeg" })); $("#a3Ack").checked = true; $("#a3Title").dataset.sample = "Tango"; if (!$("#a3Title").value) $("#a3Title").placeholder = "Tango"; ready(); schedulePrep(); };
$("#a3Ack").onchange = () => { ready(); schedulePrep(); };
$("#a3Go").onclick = go;
["#a3Crop", "#a3Tone", "#a3Bg"].forEach(id => { const el = $(id); if (el) el.onchange = schedulePrep; });
document.querySelectorAll("input[name=a3Mode]").forEach(r => r.onchange = () => { $("#a3H").placeholder = mode() === "bust" ? "60" : "80"; $("#a3Title").placeholder = $("#a3Title").dataset.sample || (mode() === "bust" ? "My bust" : "My figure"); schedulePrep(); });
document.addEventListener("zeim:ai3d-shown", refresh);
if (document.body.dataset.view === "ai3d") refresh();
