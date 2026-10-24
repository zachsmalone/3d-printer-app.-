/* 2D→3D tab: one photo -> AI figure or bust (TripoSR worker). Server: app/api/ai3d.py.
   The result is a normal private ZEIM build (auto-repaired), so Export uses the shared picker and file names.
   Warnings are shown, never block. The cooldown shows a countdown; the rest of ZEIM stays usable. */
import { api, toast, loadHistory, $, esc } from "/static/app.js";
import { Viewer } from "/static/viewer.js";
import { open as openExport } from "/static/exportpick.js";

let file = null, viewer = null, status = null, timer = null, poll = null, coolNoteOff = false;
try { coolNoteOff = sessionStorage.getItem("zeim.ai3d.coolnote") === "off"; } catch { }
const ico = id => `<svg class="i" aria-hidden="true" focusable="false"><use href="#i-${id}"/></svg>`;
const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const mode = () => document.querySelector("input[name=a3Mode]:checked")?.value || "figure";

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
    el.className = "a3note";
    el.innerHTML = `${ico("sparkle")}<div><p>Made with ${esc(e.name)} by ${esc(e.by)}, an open model (${esc(e.licence)}). Running on this server${e.device ? " (" + esc(e.device === "cuda" ? "graphics card" : e.device === "cpu" ? "processor; this can take several minutes" : e.device) + ")" : ""}.</p></div>`;
  }
}

function paintPlan() {
  const p = status.plan, el = $("#a3Plan"); clearInterval(timer);
  $("#a3Cool").hidden = true;
  if (p.testing_mode) { el.textContent = "Testing mode: no limits or pauses."; ready(); return; }
  if (p.reason === "pro") { el.textContent = "2D to 3D is part of Pro."; ready(); return; }
  const capTxt = p.cap ? `Testing period: ${p.used_today} of ${p.cap} models today.` : "";
  if (p.reason === "cap") { el.textContent = `That is today's ${p.cap} test models. More tomorrow.`; ready(); return; }
  if (p.wait_s > 0) {
    let left = p.wait_s;
    $("#a3Cool").hidden = coolNoteOff;
    const tick = () => {
      el.innerHTML = `${ico("clock")} Next model in <b>${mmss(left)}</b>. ${esc(capTxt)}`;
      if (left-- <= 0) { clearInterval(timer); refresh(); }
    };
    tick(); timer = setInterval(tick, 1000);
  } else el.textContent = capTxt;
  ready();
}

function paintClosed() {
  const nav = document.querySelector('[data-view="ai3d"]');
  if (nav) { nav.hidden = true; nav.disabled = true; }
  const grid = document.querySelector("#viewAi3d .a3grid");
  if (grid) grid.hidden = true;
  const goBtn = $("#a3Go");
  if (goBtn) { goBtn.disabled = true; goBtn.hidden = true; }
  const cool = $("#a3Cool");
  if (cool) cool.hidden = true;
  const el = $("#a3Engine");
  if (el) {
    el.className = "a3note";
    el.innerHTML = "<div><b>2D to 3D is coming later.</b><p>Lithophanes, the slicers, CAD and Showcase stay available. Nothing here starts a model.</p></div>";
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
}

function showResult(r) {
  if (!viewer) try { viewer = new Viewer($("#a3View")); } catch { }
  $("#a3Empty").hidden = true;
  viewer?.load(r.preview, "ai3d");
  const rep = r.report || {}, notes = rep.notes || [], warns = rep.warnings || [];
  const sz = r.stats?.size_mm || [];
  $("#a3Res").hidden = false;
  $("#a3Res").innerHTML = `<p class="a3title"><b>${esc(r.title)}</b> <span class="ailbl" title="Made with an AI model">${ico("sparkle")} ${esc(r.ai_label || "AI-made")}</span></p>
    <p class="help">${sz.length ? sz.map(n => Math.round(n)).join(" × ") + " mm" : ""} · ${rep.watertight ? ico("check") + " Watertight, ready to slice" : "Not fully watertight"}</p>
    ${notes.length ? `<ul class="a3list">${notes.map(n => `<li>${ico("check")} ${esc(n)}</li>`).join("")}</ul>` : ""}
    ${warns.length ? `<ul class="a3list warn">${warns.map(n => `<li>${ico("alert")} ${esc(n)}</li>`).join("")}</ul>` : ""}
    <div class="row"><button type="button" class="btn primary" id="a3Export">${ico("download")} Export</button></div>`;
  $("#a3Export").onclick = () => openExport({ ws: "ai3d", bid: r.id });
}

async function go() {
  if (!status || status.enabled === false) return;
  const fd = new FormData();
  fd.append("file", file); fd.append("mode", mode()); fd.append("photo_ack", $("#a3Ack").checked ? "true" : "false");
  fd.append("title", ($("#a3Title").value.trim() || $("#a3Title").placeholder));   // what the field shows is what gets saved if ($("#a3H").value) fd.append("height_mm", $("#a3H").value);
  $("#a3Go").disabled = true;
  const st = $("#a3Status");
  let j;
  try { j = await api("/api/ai3d/jobs", { method: "POST", body: fd }); }
  catch (e) { st.innerHTML = `<p class="a3err" role="alert">${ico("alert")} ${esc(e.message)}</p>`; refresh(); return; }
  st.innerHTML = `<p class="a3busy"><span class="a3spin" aria-hidden="true"></span> Making your model… <span id="a3El">0:00</span></p><p class="help">You can keep using ZEIM; this tab will show the model when it is done.</p>`;
  poll = setInterval(async () => {
    let s; try { s = await api("/api/ai3d/jobs/" + j.job); } catch (e) { return; }
    const el = $("#a3El"); if (el) el.textContent = mmss(s.elapsed_s || 0);
    if (s.state === "running") return;
    clearInterval(poll); poll = null;
    if (s.state === "done") { st.innerHTML = ""; showResult(s.result); toast("Your model is ready", "ok"); loadHistory?.(); if (s.plan) { status.plan = s.plan; paintPlan(); } }
    else { st.innerHTML = `<p class="a3err" role="alert">${ico("alert")} ${esc(s.error || "That did not work.")} Your photo is still here, so you can try again.</p>`; refresh(); }
  }, 1500);
}

$("#a3File").onchange = e => { const f = e.target.files?.[0]; if (f) { delete $("#a3Title").dataset.sample; $("#a3Title").placeholder = mode() === "bust" ? "My bust" : "My figure"; setFile(f); } };
$("#a3Sample").onclick = async () => { const b = await (await fetch("/static/sample.jpg")).blob(); setFile(new File([b], "sample.jpg", { type: "image/jpeg" })); $("#a3Ack").checked = true; $("#a3Title").dataset.sample = "Tango"; if (!$("#a3Title").value) $("#a3Title").placeholder = "Tango"; ready(); };
$("#a3Ack").onchange = ready;
$("#a3Go").onclick = go;
$("#a3CoolX").onclick = () => { coolNoteOff = true; $("#a3Cool").hidden = true; try { sessionStorage.setItem("zeim.ai3d.coolnote", "off"); } catch { } };
document.querySelectorAll("input[name=a3Mode]").forEach(r => r.onchange = () => { $("#a3H").placeholder = mode() === "bust" ? "60" : "80"; $("#a3Title").placeholder = $("#a3Title").dataset.sample || (mode() === "bust" ? "My bust" : "My figure"); });
document.addEventListener("zeim:ai3d-shown", refresh);
if (document.body.dataset.view === "ai3d") refresh();
