/* Calibration wizard (Smart Fix page): pick printer + nozzle + filament -> four test prints (first layer, temperature
   tower, flow, retraction) with plain-words steps, what good/bad look like, and the PrusaSlicer settings they tune.
   Download the STL for your own slicer, or slice it here (temperature tower changes are added for you). */
import { api, esc, $ } from "/static/app.js";
import { P, loadCatalog, pickerHTML, wirePicker, readPicker, matWarnHTML } from "/static/printer.js";

const q = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v != null && v !== "")).toString();
let cur = null;

function sel() {
  const p = readPicker("cal") || P.pref;
  return { printer_id: p.printer_id, nozzle: p.nozzle, material: $("#calMat").value };
}

function testHTML(t, i) {
  const s = sel(), stl = `/api/calibration/${t.id}.stl?${q(s)}`;
  const bad = t.bad.map(b => `<li><b>${esc(b.see)}</b> → ${esc(b.means)}. ${esc(b.do)}</li>`).join("");
  const keys = t.settings.filter(k => k.key).map(k => `<code>${esc(k.key)}</code>`).join(", ");
  return `<li class="caltest" id="cal_${t.id}"><details ${i === 0 ? "open" : ""}><summary><h3>${esc(t.title)}</h3></summary>
    <p>${esc(t.why)}</p><p class="help">${esc(t.prints)}</p>
    <h4>Steps</h4><ol>${t.steps.map(x => `<li>${esc(x)}</li>`).join("")}</ol>
    <h4>Good</h4><ul>${t.good.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <h4>If you see…</h4><ul>${bad}</ul>
    ${t.pick ? `<p><b>Then:</b> ${esc(t.pick)}</p>` : ""}
    ${keys ? `<p class="help">PrusaSlicer settings: ${keys}. ZEIM never changes them for you; you decide.</p>` : ""}
    <div class="row"><a class="btn" href="${stl}" download>⬇ STL</a><button type="button" class="btn primary" data-calslice="${t.id}">Slice in ZEIM</button></div>
    <div class="calout" id="calout_${t.id}" aria-live="polite"></div></details></li>`;
}

async function showPlan() {
  const box = $("#calPlan");
  box.innerHTML = `<p class="help">Making your tests…</p>`;
  try {
    cur = await api("/api/calibration/plan?" + q(sel()));
  } catch (e) { box.innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`; return; }
  if (cur.resin) {
    box.innerHTML = `<p role="status">${esc(cur.message)}</p><p class="help warn">${esc(cur.safety)}</p>`; return;
  }
  box.innerHTML = `<p class="help" role="status">${esc(cur.order_note)} ${esc(cur.estimate_note)}</p>
    ${(cur.temp_notes || []).map(n => `<p class="help warn">${esc(n)}</p>`).join("")}
    ${cur.material_warning ? matWarnHTML(cur.material) : ""}
    <ol class="caltests">${cur.tests.map(testHTML).join("")}</ol>`;
  box.querySelectorAll("[data-calslice]").forEach(b => b.onclick = () => sliceTest(b.dataset.calslice, false));
}

async function sliceTest(id, ventOk) {
  const out = $("#calout_" + id), s = sel(), fd = new FormData();
  for (const [k, v] of Object.entries(s)) if (v != null && v !== "") fd.append(k, v);
  if (ventOk) fd.append("ventilation_ok", "true");
  out.innerHTML = `<p class="help">Slicing…</p>`;
  try {
    const r = await api(`/api/calibration/${id}/slice`, { method: "POST", body: fd });
    out.innerHTML = `<p class="slicestats"><span class="pill">⏱ ${esc(r.print_time_human || "time unknown")}</span><span class="pill">🧵 ${r.filament_grams != null ? "about " + r.filament_grams + " g" : "?"}</span></p>
      ${r.temperature_bands_c ? `<p class="help">Temperature changes added: ${r.temperature_bands_c.map(t => t + " °C").join(" → ")} (bottom to top).</p>` : ""}
      <p class="help">${esc(r.printer)}, ${esc(r.material)}, ${r.nozzle} mm nozzle. Time and grams are estimates. ${esc(r.estimate_note)}</p>
      ${(r.temp_notes || []).map(n => `<p class="help warn">${esc(n)}</p>`).join("")}
      <div class="row"><a class="btn primary" href="${r.downloads.gcode}" download>⬇ G-code</a><a class="btn" href="${r.downloads["3mf"]}" download>⬇ 3MF</a></div>`;
  } catch (e) {
    if (e.status === 409 && e.body?.detail?.code === "ventilation_check") {
      const w = e.body.detail.warning || {};
      out.innerHTML = `<div class="matwarn" role="alert"><p><b>⚠ ${esc(w.title || "Ventilation")}</b></p><p>${esc(w.message || e.message)}</p>
        <div class="row"><button type="button" class="btn primary" id="calVentOk_${id}">${esc(w.confirm || "I understand, slice it")}</button></div></div>`;
      $(`#calVentOk_${id}`).onclick = () => sliceTest(id, true);
      $(`#calVentOk_${id}`).focus();
    } else out.innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`;
  }
}

async function openWizard() {
  const box = $("#calBox");
  box.hidden = false;
  try { await loadCatalog(); } catch { $("#calPick").innerHTML = `<p class="help">Printer list unavailable right now.</p>`; return; }
  if (!$("#cal_pr")) {
    $("#calPick").innerHTML = pickerHTML("cal") + `<div class="field"><label for="calMat">Filament</label><select id="calMat">${Object.keys(P.cat.materials).map(m => `<option>${esc(m)}</option>`).join("")}</select></div>`;
    wirePicker("cal", () => showPlan());
    $("#calMat").onchange = () => showPlan();
  }
  await showPlan();
  $("#calH").scrollIntoView?.({ block: "start" }); $("#calH").focus();
}

const btn = $("#calOpen");
if (btn) btn.onclick = openWizard;
if (location.hash === "#smartfix/calibrate") setTimeout(openWizard, 300);
addEventListener("hashchange", () => { if (location.hash === "#smartfix/calibrate") openWizard(); });
