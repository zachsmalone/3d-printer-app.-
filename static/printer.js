/* Printer + nozzle choice, slicer settings panel, exports and the "Will it print?" badge.
   Choice: signed-up users keep it on their profile (PUT /api/me/printer); everyone else in localStorage. Default Creality K1 at 0.4 mm. */
import { api, esc, $, toast } from "/static/app.js";

const J = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const KEY = "zeim.printer";
export const P = { cat: null, pref: { printer_id: "creality_k1", nozzle: 0.4 }, signedUp: false };

export async function loadCatalog() {
  if (!P.cat) P.cat = await api("/api/printers/catalog");
  try {
    const me = await api("/api/me/printer");
    P.signedUp = me.signed_up;
    if (me.signed_up) P.pref = { printer_id: me.printer_id, nozzle: me.nozzle };
    else { const l = JSON.parse(localStorage.getItem(KEY) || "null"); if (l && P.cat.printers.some(p => p.id === l.printer_id)) P.pref = l; }
  } catch { /* offline: keep defaults */ }
  return P.cat;
}
export const printerOf = id => P.cat?.printers.find(p => p.id === id);
const isResin = id => printerOf(id)?.technology === "Resin";

/* Nozzle sizes come from data/nozzles/nozzle-specs.json via the catalog: only the sizes this printer supports. */
export const nozzleOpt = (pid, n) => printerOf(pid)?.nozzle_options.find(o => o.mm === n);
const nozOptions = (pid, cur) => (printerOf(pid)?.nozzle_options || []).map(o =>
  `<option value="${o.mm}" ${o.mm === cur ? "selected" : ""}>${o.mm.toFixed(1)} mm${o.stock ? " (stock)" : ""}${o.advanced ? " · " + esc(P.cat.advanced_note) : ""}</option>`).join("");
const pickNozzle = (pid, want) => { const os = printerOf(pid)?.nozzle_options || []; return (os.find(o => o.mm === want) || os.find(o => o.stock) || os[0])?.mm ?? null; };
export function mfrHTML(pid, n) {
  const o = nozzleOpt(pid, n); if (!o) return "";
  const m = o.manufacturer, nice = k => k.replace(/_mm3_s$/, " (mm³/s)").replace(/_mm_s$/, " (mm/s)").replace(/_/g, " ");
  const vals = m ? Object.entries(m).filter(([k, v]) => typeof v === "number").map(([k, v]) => `${esc(nice(k))}: ${v}`) : [];
  return `Starting values for ${n} mm: layer ${o.layer_height_mm.recommended} mm (${o.layer_height_mm.min} to ${o.layer_height_mm.max}), line width ${o.line_width_mm.recommended} mm.` +
    (vals.length ? ` ${esc(o.manufacturer_name)} profile: ${vals.join(", ")}.` : "") +
    (o.advanced ? ` <b class="warn">${esc(P.cat.advanced_note)}.</b>` : "");
}

/* Picker markup. `uid` keeps ids unique when the picker appears twice on a page (sign-up + Account). */
export function pickerHTML(uid, pref = P.pref, { optional = false } = {}) {
  const opts = (optional ? `<option value="">Not now</option>` : "") + P.cat.printers.map(p => `<option value="${p.id}" ${p.id === pref.printer_id && !optional ? "selected" : ""}>${esc(p.name)}${p.technology === "Resin" ? " (resin)" : ""}</option>`).join("");
  const pid = optional ? P.cat.default.printer_id : pref.printer_id;
  return `<div class="grid2 printerpick" data-uid="${uid}">
    <div class="field"><label for="${uid}_pr">Printer${optional ? " <em>optional</em>" : ""}</label><select id="${uid}_pr">${opts}</select></div>
    <div class="field" id="${uid}_nzf"><label for="${uid}_nz">Nozzle size</label><select id="${uid}_nz">${nozOptions(pid, pickNozzle(pid, pref.nozzle))}</select></div>
    <p class="help" id="${uid}_info" aria-live="polite" style="grid-column:1/-1"></p></div>`;
}
export function wirePicker(uid, onChange) {
  const pr = $(`#${uid}_pr`), nz = $(`#${uid}_nz`);
  const info = () => {
    const p = printerOf(pr.value);
    $(`#${uid}_nzf`).hidden = !p || p.technology === "Resin";
    $(`#${uid}_info`).innerHTML = !p ? "" : `Build volume ${p.bed_mm.map(v => +v).join(" × ")} mm. ` + (p.technology === "Resin" ? "Resin printer: no nozzle. Slice it in " + esc(p.official_slicer || "its own slicer") + "." : mfrHTML(p.id, +nz.value));
  };
  pr.onchange = () => { const p = printerOf(pr.value); if (p) nz.innerHTML = nozOptions(p.id, pickNozzle(p.id, +nz.value)); info(); onChange?.(readPicker(uid)); };
  nz.onchange = () => { info(); onChange?.(readPicker(uid)); };
  info();
}
export function readPicker(uid) {
  const id = $(`#${uid}_pr`)?.value;
  if (!id) return null;
  return { printer_id: id, nozzle: isResin(id) ? null : +$(`#${uid}_nz`).value };
}
export async function savePref(pref) {
  P.pref = pref; localStorage.setItem(KEY, JSON.stringify(pref));
  const r = await api("/api/me/printer", J("PUT", pref));
  document.dispatchEvent(new CustomEvent("zeim:printer", { detail: pref }));
  return r;
}
export const prefLabel = (pref = P.pref) => { const p = printerOf(pref.printer_id); return p ? p.name + (pref.nozzle ? ` · ${pref.nozzle} mm` : "") : ""; };

/* ---------- "Will it print?" badge ---------- */
const VERDICT = { yes: ["ok", "✔"], likely: ["ok", "✔"], maybe: ["warn", "!"], no: ["bad", "✖"], unknown: ["", "?"] };
export function badgeHTML(r, { detail = false } = {}) {
  if (!r) return "";
  const [cls, ico] = VERDICT[r.verdict] || VERDICT.unknown;
  const c = r.checks || {}, row = (ok, t) => `<li class="${ok === false ? "bad" : ok ? "ok" : ""}">${ok === false ? "✖" : ok ? "✔" : "…"} ${t}</li>`;
  const pill = `<span class="pill willprint ${cls}" title="Will it print on the ${esc(r.printer || "")}?"><span aria-hidden="true">${ico}</span> ${esc(r.label)}<span class="sr-only"> on the ${esc(r.printer || "")}</span></span>`;
  if (!detail || !c.bed_fit) return pill;
  return `<div class="willbox"><p><b>Will it print?</b> ${pill} <span class="help">${esc(r.printer)}${r.nozzle ? ` · ${r.nozzle} mm nozzle` : ""}</span></p><ul class="checks">
    ${row(c.bed_fit.ok, c.bed_fit.ok ? `Fits the bed (${c.bed_fit.size_mm.join(" × ")} mm)` : `Won't fit your bed: ${c.bed_fit.size_mm.join(" × ")} mm on a ${c.bed_fit.bed_mm.join(" × ")} mm printer`)}
    ${row(c.slices.ok, c.slices.ok ? "Slices OK" : c.slices.ok === false ? "Slicing failed" : "Not sliced yet (press Slice)")}
    ${row(c.thin_wall.ok, c.thin_wall.ok === false ? `Thin walls under ${c.thin_wall.min_mm} mm (${Math.round(c.thin_wall.thin_fraction * 100)}% of the surface)` : c.thin_wall.ok ? `No walls thinner than one ${c.thin_wall.min_mm} mm line` : "Wall check not available")}</ul>
    ${(r.tips || []).map(t => `<p class="help">${esc(t)}</p>`).join("")}</div>`;
}
const q = (pref = P.pref) => `printer_id=${encodeURIComponent(pref.printer_id)}&nozzle=${pref.nozzle ?? ""}`;
export const checkBuild = (id, slice = false) => api(`/api/willprint/build/${id}?${q()}${slice ? "&slice=true" : ""}`);
export const checkShowcase = (id, slice = false) => api(`/api/showcase/${id}/willprint?${q()}${slice ? "&slice=true" : ""}`);

/* ---------- slicer settings panel ---------- */
const presetOf = id => P.cat.presets.find(x => x.id === id) || P.cat.presets.find(x => x.id === P.cat.default_preset) || {};
// same formula as print_setup.preset_layer(): the nozzle's recommended layer scaled by the preset, kept in the nozzle's range
export const presetLayer = (pv, rec, lo, hi) => +Math.min(Math.max(rec * (pv.layer_frac ?? 0.5) / 0.5, lo), hi).toFixed(3);
export function panelHTML(hintMode) {
  const pref = P.pref, p = printerOf(pref.printer_id), n = pref.nozzle || 0.4;
  const o = nozzleOpt(pref.printer_id, n), lh = o?.layer_height_mm || { min: n / 4, max: n * 0.75, recommended: n / 2 };
  const lo = +Math.max(n * P.cat.layer_fraction[0], lh.min).toFixed(3), hi = +Math.min(n * P.cat.layer_fraction[1], lh.max).toFixed(3);
  // no saved slicer choice yet: follow the app's Beginner / Experienced switch
  const saved = localStorage.getItem("zeim.slicerMode"), beginner = saved ? saved !== "advanced" : localStorage.level !== "expert";
  // Studio/Edit lithophanes open on the Lithophane preset (solid fill); other models keep Standard
  const wantPreset = (hintMode === "lithophane" && P.cat.presets.some(x => x.id === "lithophane")) ? "lithophane" : P.cat.default_preset;
  const pv = presetOf(wantPreset);
  const mats = Object.keys(P.cat.materials);
  const t = P.cat.materials.PLA;
  const sel = (id, label, vals, cur, names = {}) => `<div class="field"><label for="${id}">${label}</label><select id="${id}">${vals.map(v => `<option value="${v}" ${v === cur ? "selected" : ""}>${esc(names[v] || v)}</option>`).join("")}</select></div>`;
  const num = (id, label, v, min, max, step, unit) => `<div class="field"><label for="${id}">${label} <em>${unit}</em></label><input type="number" id="${id}" value="${v}" min="${min}" max="${max}" step="${step}" inputmode="decimal"></div>`;
  return `<h3>Slice for your printer</h3>
    <p class="help">Printer: <b id="spPrinter">${esc(prefLabel())}</b> · <a href="#account" id="spChange">Change printer</a></p>
    ${p?.technology === "Resin" ? `<p class="help warn">The ${esc(p.name)} is a resin printer. ZEIM's slicer makes G-code for filament printers only. Download the STL or 3MF below and open it in ${esc(p.official_slicer || "your resin slicer")}.</p>` : `
    <p class="help nozzlespec">${mfrHTML(pref.printer_id, n)}</p>
    <div class="segmented" role="group" aria-label="Settings level"><button type="button" id="spBeginner" aria-pressed="${beginner}">Beginner</button><button type="button" id="spAdvanced" aria-pressed="${!beginner}">Advanced</button></div>
    <div class="presets" role="radiogroup" aria-label="Preset">${P.cat.presets.map(x => `<label class="preset"><input type="radio" name="spPreset" value="${x.id}" ${x.id === wantPreset ? "checked" : ""}><span><b>${esc(x.label)}</b><small>${esc(x.help)}</small></span></label>`).join("")}</div>
    <div class="grid2">${sel("spMat", "Material", mats, "PLA")}${sel("spSup", "Supports", P.cat.supports, "off", { off: "Off", auto: "Auto (from the bed only)", everywhere: "Everywhere" })}</div>
    <div id="spMatWarn" aria-live="polite">${matWarnHTML("PLA")}</div>
    <div id="spAdv" ${beginner ? "hidden" : ""}><div class="grid3">
      ${num("spLayer", "Layer height", presetLayer(pv, lh.recommended, lo, hi), lo, hi, 0.01, `mm (${lo} to ${hi})`).replace("<input ", `<input data-rec="${lh.recommended}" `)}
      ${num("spWalls", "Walls", pv.walls ?? 2, 1, 10, 1, "")}${num("spTB", "Top/bottom layers", pv.top_bottom ?? 4, 0, 20, 1, "")}
      ${num("spInfill", "Infill", pv.infill ?? 15, 0, 100, 1, "%")}${sel("spPattern", "Infill pattern", P.cat.patterns, pv.pattern || "grid")}
      ${num("spBrim", "Brim", 0, 0, 30, 1, "mm")}${num("spSpeed", "Speed", pv.speed ?? 80, 10, 500, 5, "mm/s")}
      ${num("spNozT", "Nozzle temp", t.nozzle_c, 150, p?.max_nozzle_c || 300, 1, "°C")}${num("spBedT", "Bed temp", t.bed_c, 0, p?.max_bed_c || 110, 1, "°C")}</div>
      <p class="help">These start from the preset you picked above; changing the preset fills them in again. Line width ${o?.line_width_mm.recommended ?? n} mm for the ${n} mm nozzle (from the nozzle specs). Temperatures start from the material's reference values.</p></div>
    <label class="inl chk"><input type="checkbox" id="spFit"> Scale down to fit this printer if it's too big</label>
    <div class="row"><button class="btn primary big" id="spGo">Slice</button></div>`}
    <div id="spOut" aria-live="polite"></div>`;
}
/* ABS / ASA / PC (significant fumes): ventilation + enclosure note shown as soon as the material is picked, and again before slicing. */
export function matWarnHTML(m, { ask = false } = {}) {
  const w = P.cat?.materials?.[m]?.warning;
  if (!w) return "";
  return `<div class="matwarn" ${ask ? `role="alert"` : ""}><p><b>⚠ ${esc(w.title)}</b></p><p>${esc(w.message)}</p><p class="help">${esc(w.tested)}</p>` +
    (ask ? `<div class="row"><button type="button" class="btn primary" id="spVentOk">${esc(w.confirm)}</button><button type="button" class="btn" id="spVentNo">Pick another material</button></div>` : "") + `</div>`;
}
function readPanel() {
  const fd = new FormData(), pref = P.pref, adv = $("#spAdvanced")?.getAttribute("aria-pressed") === "true";
  fd.append("printer_id", pref.printer_id); if (pref.nozzle) fd.append("nozzle", pref.nozzle);
  fd.append("preset", document.querySelector("[name=spPreset]:checked")?.value || "standard");
  fd.append("material", $("#spMat").value); fd.append("supports", $("#spSup").value);
  if (adv) for (const [k, id] of [["layer_height", "spLayer"], ["walls", "spWalls"], ["top_bottom", "spTB"], ["infill", "spInfill"], ["infill_pattern", "spPattern"], ["brim", "spBrim"], ["speed", "spSpeed"], ["nozzle_temp", "spNozT"], ["bed_temp", "spBedT"]]) fd.append(k, $("#" + id).value);
  if ($("#spFit").checked) fd.append("scale_to_fit", "true");
  return fd;
}
export function openInHTML(dl) {
  return `<h4>Open in your slicer</h4><p class="help">${esc(P.cat.open_in_note)}</p><div class="slicers">` +
    P.cat.open_in.map(s => `<a class="btn" href="${dl[s.format]}" download="zeim-model.${s.format}" data-openin="${s.id}" aria-describedby="oi_${s.id}">Open in ${esc(s.label)}</a>`).join("") +
    `</div><ul class="openin-steps">${P.cat.open_in.map(s => `<li id="oi_${s.id}"><b>${esc(s.label)}:</b> ${esc(s.steps)}</li>`).join("")}</ul>`;
}
export function wirePanel(getModelId) {
  const mat = $("#spMat");
  if (!mat) return;
  const mode = adv => { localStorage.setItem("zeim.slicerMode", adv ? "advanced" : "beginner"); $("#spAdv").hidden = !adv; $("#spBeginner").setAttribute("aria-pressed", !adv); $("#spAdvanced").setAttribute("aria-pressed", adv); };
  $("#spBeginner").onclick = () => mode(false); $("#spAdvanced").onclick = () => mode(true);
  // reference temps, capped to what this printer can reach (the server caps them the same way and says so)
  const cap = (v, el) => Math.min(v, +el.max || v);
  mat.onchange = () => { const t = P.cat.materials[mat.value]; $("#spNozT").value = cap(t.nozzle_c, $("#spNozT")); $("#spBedT").value = cap(t.bed_c, $("#spBedT")); $("#spMatWarn").innerHTML = matWarnHTML(mat.value); };
  // Advanced fields follow the preset: picking Strong in Advanced really slices with Strong's walls / infill (not Standard's numbers)
  document.querySelectorAll("[name=spPreset]").forEach(r => r.onchange = () => {
    const pv = presetOf(r.value), l = $("#spLayer");
    l.value = presetLayer(pv, +(l.dataset.rec || l.value), +l.min, +l.max);
    $("#spWalls").value = pv.walls; $("#spTB").value = pv.top_bottom; $("#spInfill").value = pv.infill; $("#spPattern").value = pv.pattern;
    $("#spSpeed").value = Math.min(pv.speed, +$("#spSpeed").max || pv.speed);
  });
  const doSlice = async (ventOk = false) => {
    const out = $("#spOut"), fd = readPanel(); fd.append("model_id", getModelId());
    if (ventOk) fd.append("ventilation_ok", "true");
    $("#spMatWarn").hidden = false;
    out.innerHTML = `<p class="help">Slicing for the ${esc(prefLabel())}…</p>`; $("#spGo").disabled = true;
    try {
      const r = await api("/api/slice", { method: "POST", body: fd });
      const notes = [...(r.temp_notes || []), r.material_warning ? `${r.material_warning.title}: ventilate the room and use an enclosure while it prints.` : ""].filter(Boolean);
      out.innerHTML = `<p class="slicestats"><span class="pill">⏱ ${esc(r.print_time_human || "time unknown")}</span><span class="pill">🧵 ${r.filament_grams != null ? r.filament_grams + " g" : "?"}${r.filament_mm ? ` · ${(r.filament_mm / 1000).toFixed(2)} m` : ""}</span>${r.scaled_pct ? `<span class="pill warn">Scaled to ${r.scaled_pct}%</span>` : ""}</p>
        <p class="help">Estimates read from the G-code. ${esc(r.settings.material)}, ${r.settings.layer_height} mm layers, ${r.settings.infill}% ${esc(r.settings.infill_pattern)}.</p>
        ${notes.map(n => `<p class="help warn">${esc(n)}</p>`).join("")}
        ${badgeHTML(r.will_print, { detail: true })}
        <div class="row"><a class="btn primary" href="${r.downloads.gcode}" download>⬇ G-code</a><a class="btn" href="${r.downloads["3mf"]}" download>⬇ 3MF</a><a class="btn" href="${r.downloads.stl}" download>⬇ STL</a></div>
        ${openInHTML(r.downloads)}`;
    } catch (e) {
      if (e.status === 409 && e.body?.detail?.code === "ventilation_check") {     // warn, then allow: the maker must read this once
        out.innerHTML = matWarnHTML(e.body.detail.warning?.material || $("#spMat").value, { ask: true });
        $("#spMatWarn").hidden = true;                                           // one copy on screen (the one that asks)
        $("#spVentOk").onclick = () => doSlice(true);
        $("#spVentNo").onclick = () => { out.innerHTML = ""; $("#spMatWarn").hidden = false; $("#spMat").focus(); };
        $("#spVentOk").focus();
      } else out.innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`;
    }
    finally { $("#spGo").disabled = false; }
  };
  $("#spGo").onclick = () => doSlice(false);
}

/* ---------- Account: "Your printer" card ---------- */
async function initAccount() {
  const box = $("#accPrinter");
  if (!box) return;
  try { await loadCatalog(); } catch { box.innerHTML = `<p class="help">Printer list unavailable right now.</p>`; return; }
  box.innerHTML = pickerHTML("ap") + `<div class="row"><button class="btn primary" id="apSave">Save printer</button><span class="help" id="apMsg" aria-live="polite"></span></div>`;
  wirePicker("ap");
  $("#apSave").onclick = async () => {
    try { const r = await savePref(readPicker("ap")); $("#apMsg").textContent = `Saved: ${prefLabel()}` + (r.stored === "profile" ? " (on your profile)." : " (in this browser)."); }
    catch (e) { $("#apMsg").textContent = e.message; }
  };
}
document.addEventListener("zeim:me", () => { P.cat && loadCatalog().then(initAccount); });
initAccount();
