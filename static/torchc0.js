/* TorchC0: ZEIM's resin program, its own main tab (#torchc0). Resin only: no nozzle, filament or gcode settings here.
   Upload a model -> POST /api/resin/prepare (hollow + drain hole, tilt, supports + raft) -> STL / 3MF for the resin slicer. */
import { api, esc, $ } from "/static/app.js";
import { money } from "/static/cost.js";

const PKEY = "zeim.resinPrice";   // remembered in this browser only: {price, unit, currency}
const CURS = ["$", "€", "£", "¥", "₹", "R$", "kr"];
const loadP = () => { try { return JSON.parse(localStorage.getItem(PKEY)) || {}; } catch { return {}; } };
const saveP = v => { try { localStorage.setItem(PKEY, JSON.stringify(v)); } catch { } };

const RZ_PRESETS = { detail: [0.03, 2.0, 25, 5], standard: [0.05, 2.5, 30, 5], fast: [0.08, 3.2, 30, 4] };   // keep in step with app/core/resin.py PRESETS
let cat = null;
const num = (id, label, v, min, max, step, unit) => `<div class="field"><label for="${id}">${label} <em>${unit}</em></label><input type="number" id="${id}" value="${v}" min="${min}" max="${max}" step="${step}" inputmode="decimal"></div>`;

function panelHTML() {
  const brands = [...new Set(cat.printers.map(p => p.brand))];
  return `<h2>Resin print settings</h2>
    <div class="grid2"><div class="field"><label for="rzPrinter">Resin printer</label><select id="rzPrinter">${brands.map(b => `<optgroup label="${esc(b)}">${cat.printers.filter(p => p.brand === b).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</optgroup>`).join("")}</select></div>
    <div class="field"><label for="rzFile">Model (STL, 3MF or OBJ)</label><input type="file" id="rzFile" accept=".stl,.3mf,.obj"></div></div>
    <p class="help" id="rzInfo"></p>
    <div class="field"><label for="rzPreset">Preset</label><select id="rzPreset">${cat.presets.map(x => `<option value="${x.id}" ${x.id === cat.default_preset ? "selected" : ""}>${esc(x.label)} · ${x.layer_mm} mm</option>`).join("")}</select></div>
    <div class="grid3">${num("rzLayer", "Layer height", 0.05, 0.01, 0.2, 0.01, "mm")}${num("rzExp", "Exposure", 2.5, 0.5, 30, 0.1, "s")}${num("rzBExp", "Bottom exposure", 30, 5, 120, 1, "s")}
      ${num("rzBL", "Bottom layers", 5, 1, 15, 1, "")}${num("rzLift", "Lift distance", 6, 1, 15, 0.5, "mm")}${num("rzLiftS", "Lift speed", 65, 10, 300, 5, "mm/min")}
      ${num("rzTilt", "Tilt", 30, 0, 60, 5, "°")}${num("rzWall", "Hollow wall", 2, 0.5, 6, 0.5, "mm")}${num("rzDrain", "Drain hole Ø", 3, 0, 10, 0.5, "mm")}</div>
    <p class="help warn rzWarn" id="rzWallWarn" hidden>Walls under 1 mm crack easily in resin. Use 1 mm or more, or prepare anyway.
      <button type="button" class="btn small" id="rzWallAnyway">Prepare anyway</button> <button type="button" class="btn small" id="rzWallDismiss" aria-label="Dismiss this warning">Dismiss</button></p>
    <div class="grid3"><div class="field"><label for="rzCur">Currency</label><select id="rzCur">${CURS.map(c => `<option ${c === (loadP().currency || "$") ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
      ${num("rzCost", "Resin price", loadP().price ?? cat.default_price, 0, 10000, 0.5, "")}
      <div class="field"><label for="rzCostU">Price per</label><select id="rzCostU"><option value="l" ${(loadP().unit || cat.default_price_unit) === "l" ? "selected" : ""}>litre</option><option value="kg" ${loadP().unit === "kg" ? "selected" : ""}>kg</option></select></div></div>
    <label class="inl chk"><input type="checkbox" id="rzHollow" checked> Hollow (saves resin; needs a drain hole)</label>
    <label class="inl chk"><input type="checkbox" id="rzSup" checked> Supports and raft</label>
    <p class="help">${esc(cat.test_note)} ${esc(cat.formats_note)}</p>
    <details><summary>Resin safety</summary><ul>${cat.safety.map(s => `<li>${esc(s)}</li>`).join("")}</ul></details>
    <div class="row"><button class="btn primary big" id="rzGo">Prepare for resin</button></div>`;
}

function wire() {
  const pr = $("#rzPreset"), info = () => { const p = cat.printers.find(x => x.id === $("#rzPrinter").value); $("#rzInfo").textContent = p ? `Build volume ${p.bed_mm.map(v => +v).join(" × ")} mm. Make the layer file in ${p.official_slicer || "the printer's own resin slicer"}.` : ""; };
  $("#rzPrinter").onchange = info; info();
  pr.onchange = () => { const [l, e, b, bl] = RZ_PRESETS[pr.value]; $("#rzLayer").value = l; $("#rzExp").value = e; $("#rzBExp").value = b; $("#rzBL").value = bl; };
  // thin hollow wall: a dismissable warning, never a block (Prepare stays enabled; "Prepare anyway" just runs it)
  let wallOk = false;
  const wallWarn = () => { $("#rzWallWarn").hidden = wallOk || !($("#rzHollow").checked && +$("#rzWall").value > 0 && +$("#rzWall").value < 1); };
  $("#rzWall").addEventListener("input", () => { wallOk = false; wallWarn(); }); $("#rzHollow").addEventListener("change", wallWarn);
  $("#rzWallDismiss").onclick = () => { wallOk = true; wallWarn(); };
  $("#rzWallAnyway").onclick = () => { wallOk = true; wallWarn(); $("#rzGo").click(); };
  $("#rzGo").onclick = async () => {
    const out = $("#torchOut"), f = $("#rzFile").files[0];
    if (!f) { out.innerHTML = `<p class="help warn" role="alert">Choose an STL, 3MF or OBJ file first.</p>`; return; }
    const fd = new FormData();
    const v = { printer_id: $("#rzPrinter").value, preset: pr.value, layer_mm: $("#rzLayer").value, exposure_s: $("#rzExp").value,
      bottom_exposure_s: $("#rzBExp").value, bottom_layers: $("#rzBL").value, lift_mm: $("#rzLift").value, lift_speed_mm_min: $("#rzLiftS").value,
      tilt_deg: $("#rzTilt").value, wall_mm: $("#rzWall").value, drain_mm: $("#rzDrain").value, hollow: $("#rzHollow").checked, supports: $("#rzSup").checked,
      price: $("#rzCost").value, price_unit: $("#rzCostU").value };
    saveP({ price: +$("#rzCost").value, unit: $("#rzCostU").value, currency: $("#rzCur").value });
    Object.entries(v).forEach(([k, x]) => fd.append(k, x)); fd.append("file", f);
    out.innerHTML = `<p class="help">TorchC0 is preparing your model…</p>`; $("#rzGo").disabled = true;
    try {
      const r = await api("/api/resin/prepare", { method: "POST", body: fd }), e = r.estimate;
      out.innerHTML = `<p class="slicestats"><span class="pill">⏱ about ${esc(e.print_time_human)}</span><span class="pill">🧪 about ${e.resin_ml} ml</span><span class="pill" id="rzCostOut">💰 about ${esc(money(e.cost, $("#rzCur").value))}</span><span class="pill">${e.layers} layers</span>${r.support ? `<span class="pill">${r.support.supports} supports</span>` : ""}${r.fits === false ? `<span class="pill warn">Too big</span>` : ""}</p>
        ${r.hollow ? `<p class="help">${esc(r.hollow.message)}</p>` : ""}
        ${r.notes.map(n => `<p class="help warn rzWarn">${esc(n)} <button type="button" class="btn small rzDismiss" aria-label="Dismiss this warning">Dismiss</button></p>`).join("")}
        <p class="help">${esc(e.resin_note)} Cost estimate: ${esc(e.cost_note)}</p>
        <div class="row"><a class="btn primary" href="${r.downloads.stl}" download>⬇ STL</a><a class="btn" href="${r.downloads["3mf"]}" download>⬇ 3MF</a></div>`;
      out.querySelectorAll(".rzDismiss").forEach(b => b.onclick = () => b.closest(".rzWarn").remove());   // warnings never block: the files are already made
    } catch (err) { out.innerHTML = `<p class="help warn" role="alert">${esc(err.message)}</p>`; }
    finally { $("#rzGo").disabled = false; }
  };
}

async function load() {
  if (cat) return;
  try { cat = await api("/api/resin/catalog"); $("#torchPanel").innerHTML = panelHTML(); wire(); }
  catch (e) { cat = null; $("#torchPanel").innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`; }
}
document.addEventListener("zeim:torchc0-shown", load);
if (location.hash.startsWith("#torchc0") || location.hash.startsWith("#resin")) load();
