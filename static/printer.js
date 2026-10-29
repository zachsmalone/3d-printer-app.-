/* Printer + nozzle choice, slicer settings panel, exports and the "Will it print?" badge.
   Choice: signed-up users keep it on their profile (PUT /api/me/printer); everyone else in localStorage. Default Creality K1 at 0.4 mm. */
import { api, esc, $, toast } from "/static/app.js";
import { layerPreviewHTML, wireLayerPreview } from "/static/layers.js";
import { gcodePreviewHTML, wireGcodePreview } from "/static/gcodeview.js";
const HAS_GL = (() => { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; } })();
let gcDispose = null;  // previous G-code preview (freed on the next slice)
import { mountPaint, getStrokes } from "/static/supportpaint.js";
import { costHTML, wireCost } from "/static/cost.js";

const J = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const KEY = "zeim.printer";
export const P = { cat: null, pref: { printer_id: "creality_k1", nozzle: 0.4 }, signedUp: false, chosen: false };

export async function loadCatalog() {
  if (!P.cat) P.cat = await api("/api/printers/catalog");
  try {
    const me = await api("/api/me/printer");
    P.signedUp = me.signed_up;
    P.chosen = false;
    if (me.signed_up && me.saved) {
      P.pref = { printer_id: me.printer_id, nozzle: me.nozzle };
      P.chosen = true;
    } else {
      const l = JSON.parse(localStorage.getItem(KEY) || "null");
      if (l && P.cat.printers.some(p => p.id === l.printer_id)) { P.pref = l; P.chosen = true; }
    }
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

const prHit = q => { const words = q.toLowerCase().split(/\s+/).filter(Boolean); return p => words.every(w => `${p.name} ${p.technology}`.toLowerCase().includes(w)); };
const prOptions = (sel, optional, q = "") => {
  const hit = prHit(q);
  const list = P.cat.printers.filter(p => hit(p) || p.id === sel);   // the chosen printer always stays visible
  return (optional ? `<option value="">Not now</option>` : "") + [...new Set(list.map(p => p.brand))].sort((a, b) => a.localeCompare(b)).map(b => `<optgroup label="${esc(b)}">` + list.filter(p => p.brand === b).map(p => `<option value="${p.id}" ${p.id === sel ? "selected" : ""}>${esc(p.name)}${p.technology === "Resin" ? " (TorchC0 resin)" : ""}</option>`).join("") + `</optgroup>`).join("");  // grouped by brand
};
/* Picker markup. `uid` keeps ids unique when the picker appears twice on a page (sign-up + Account). */
export function pickerHTML(uid, pref = P.pref, { optional = false } = {}) {
  const opts = prOptions(optional ? "" : pref.printer_id, optional);
  const pid = optional ? P.cat.default.printer_id : pref.printer_id;
  const nb = new Set(P.cat.printers.map(p => p.brand)).size;
  return `<div class="grid2 printerpick" data-uid="${uid}" data-optional="${optional ? 1 : ""}">
    <div class="field prsearch" style="grid-column:1/-1"><label for="${uid}_q">Find your printer</label><input id="${uid}_q" type="search" autocomplete="off" enterkeyhint="search" placeholder="Brand or model, e.g. Longer LK5" aria-describedby="${uid}_qn"><span class="help" id="${uid}_qn" aria-live="polite">${P.cat.printers.length} printers from ${nb} brands</span></div>
    <div class="field"><label for="${uid}_pr">Printer${optional ? " <em>optional</em>" : ""}</label><select id="${uid}_pr">${opts}</select></div>
    <div class="field" id="${uid}_nzf"><label for="${uid}_nz">Nozzle size</label><select id="${uid}_nz">${nozOptions(pid, pickNozzle(pid, pref.nozzle))}</select></div>
    <p class="help" id="${uid}_info" aria-live="polite" style="grid-column:1/-1"></p></div>`;
}
export function wirePicker(uid, onChange) {
  const pr = $(`#${uid}_pr`), nz = $(`#${uid}_nz`);
  const info = () => {
    const p = printerOf(pr.value);
    $(`#${uid}_nzf`).hidden = !p || p.technology === "Resin";
    $(`#${uid}_info`).innerHTML = !p ? "" : `Build volume ${p.bed_mm.map(v => +v).join(" × ")} mm. ` + (p.technology === "Resin" ? "Resin printer: no nozzle. Prepare it in the TorchC0 tab, then make the layer file in " + esc(p.official_slicer || "its own resin slicer") + "." : mfrHTML(p.id, +nz.value));
  };
  pr.onchange = () => { const p = printerOf(pr.value); if (p) nz.innerHTML = nozOptions(p.id, pickNozzle(p.id, +nz.value)); info(); onChange?.(readPicker(uid)); };
  nz.onchange = () => { info(); onChange?.(readPicker(uid)); };
  const q = $(`#${uid}_q`);
  if (q) q.oninput = () => {
    const before = pr.value, optional = !!pr.closest(".printerpick")?.dataset.optional;
    pr.innerHTML = prOptions(before, optional, q.value);
    const matches = P.cat.printers.filter(prHit(q.value)), n = matches.length;
    $(`#${uid}_qn`).textContent = q.value.trim() ? (n ? `${n} match${n === 1 ? "" : "es"}. Pick one below.` : "No printer matches. Try the brand name, or pick a similar printer.") : `${P.cat.printers.length} printers`;
    // one match: select it straight away (saves a tap on phones)
    if (q.value.trim() && n === 1 && matches[0].id !== before) { pr.innerHTML = prOptions(matches[0].id, optional, q.value); pr.value = matches[0].id; pr.onchange(); }
  };
  info();
}
export function readPicker(uid) {
  const id = $(`#${uid}_pr`)?.value;
  if (!id) return null;
  return { printer_id: id, nozzle: isResin(id) ? null : +$(`#${uid}_nz`).value };
}
export async function savePref(pref) {
  P.pref = pref; P.chosen = true; localStorage.setItem(KEY, JSON.stringify(pref));
  const r = await api("/api/me/printer", J("PUT", pref));
  document.dispatchEvent(new CustomEvent("zeim:printer", { detail: pref }));
  return r;
}
export const prefLabel = (pref = P.pref) => { const p = printerOf(pref.printer_id); return p ? p.name + (pref.nozzle ? ` · ${pref.nozzle} mm` : "") : ""; };
export function troubleshootingPrinterLabel() {
  if (!P.chosen) return "No printer saved yet. Fixes stay general until you save one in Account.";
  return prefLabel() || "No printer saved yet. Fixes stay general until you save one in Account.";
}

/* ---------- "Will it print?" badge ---------- */
const VERDICT = { yes: ["ok", "✔"], likely: ["ok", "✔"], maybe: ["warn", "!"], unchecked: ["warn", "!"], no: ["bad", "✖"], unknown: ["", "?"] };
export function badgeHTML(r, { detail = false } = {}) {
  if (!r) return "";
  const [cls, ico] = VERDICT[r.verdict] || VERDICT.unknown;
  const c = r.checks || {}, row = (ok, t) => `<li class="${ok === false ? "bad" : ok ? "ok" : ""}">${ok === false ? "✖" : ok ? "✔" : "…"} ${t}</li>`;
  const pill = `<span class="pill willprint ${cls}" title="Will it print on the ${esc(r.printer || "")}?"><span aria-hidden="true">${ico}</span> ${esc(r.label)}<span class="sr-only"> on the ${esc(r.printer || "")}</span></span>`;
  if (!detail || !c.bed_fit) return pill;
  return `<div class="willbox"><p><b>Will it print?</b> ${pill} <span class="help">${esc(r.printer)}${r.nozzle ? ` · ${r.nozzle} mm nozzle` : ""}</span></p><ul class="checks">
    ${row(c.bed_fit.ok, c.bed_fit.ok ? `Fits the bed (${c.bed_fit.size_mm.join(" × ")} mm)` : `Won't fit your bed: ${c.bed_fit.size_mm.join(" × ")} mm on a ${c.bed_fit.bed_mm.join(" × ")} mm printer`)}
    ${row(c.slices.ok, c.slices.ok ? "Slices OK" : c.slices.ok === false ? "Slicing failed" : "Not sliced yet (press Slice)")}
    ${row(c.thin_wall.ok, c.thin_wall.ok === false ? `Thin walls under ${c.thin_wall.min_mm} mm (${c.thin_wall.thinnest_mm < c.thin_wall.min_mm ? `thinnest ${c.thin_wall.thinnest_mm} mm, ` : ""}${Math.round(c.thin_wall.thin_fraction * 100)}% of the surface)` : c.thin_wall.ok ? `No walls thinner than one ${c.thin_wall.min_mm} mm line` : "Wall check not available")}</ul>
    ${gapRow(c.gaps)}
    ${(r.tips || []).filter(t => !(c.gaps?.warning && t === c.gaps.warning)).map(t => `<p class="help">${esc(t)}</p>`).join("")}</div>`;
}
/* Print-in-place gap check: a warning only, never blocks slicing. "Got it, slice anyway" hides it for this visit. */
const GAP_KEY = "zeim_gap_ok";
const gapDismissed = w => { try { return JSON.parse(sessionStorage.getItem(GAP_KEY) || "[]").includes(w); } catch { return false; } };
function gapRow(g) {
  if (!g || g.ok !== false || !g.warning || gapDismissed(g.warning)) return "";
  return `<p class="help gapwarn" role="status"><svg class=i aria-hidden=true focusable=false><use href=#i-alert></use></svg> ${esc(g.warning)} <button type="button" class="btn small" data-gapok="${esc(g.warning)}">Got it, slice anyway</button></p>`;
}
document.addEventListener("click", e => {
  const b = e.target.closest?.("[data-gapok]"); if (!b) return;
  try { const l = JSON.parse(sessionStorage.getItem(GAP_KEY) || "[]"); l.push(b.dataset.gapok); sessionStorage.setItem(GAP_KEY, JSON.stringify(l.slice(-50))); } catch { }
  b.closest(".gapwarn")?.remove();
});
const q = (pref = P.pref) => `printer_id=${encodeURIComponent(pref.printer_id)}&nozzle=${pref.nozzle ?? ""}`;
export const checkBuild = (id, slice = false) => api(`/api/willprint/build/${id}?${q()}${slice ? "&slice=true" : ""}`);
export const checkShowcase = (id, slice = false) => api(`/api/showcase/${id}/willprint?${q()}${slice ? "&slice=true" : ""}`);

/* ---------- slicer settings panel ---------- */
const presetOf = id => P.cat.presets.find(x => x.id === id) || P.cat.presets.find(x => x.id === P.cat.default_preset) || {};
// same formula as print_setup.preset_layer(): the nozzle's recommended layer scaled by the preset, kept in the nozzle's range
export const presetLayer = (pv, rec, lo, hi) => +Math.min(Math.max(rec * (pv.layer_frac ?? 0.5) / 0.5, lo), hi).toFixed(3);
/* Per-slot filament + colour when the printer has AMS / CFS / MMU / ACE. Single-head printers stay simple. */
function slotsHTML(p, mats) {
  const n = +p?.filament_slots || 1, systems = p?.multi_color_system || [];
  if (n <= 1 || !systems.length) return "";
  const label = systems.join(" / ");
  const defCols = ["#FFFFFF", "#FF0000", "#00AA00", "#0066FF", "#FFD000", "#FF00AA", "#00DDDD", "#222222"];
  return `<fieldset class="spslots" id="spSlots"><legend>Filament per ${esc(label)} slot</legend>
    <p class="help">Turn on only the slots this print uses. Unused ports are not heated, primed or purged.</p>
    ${Array.from({ length: n }, (_, i) => {
      const s = i + 1, col = defCols[i % defCols.length];
      return `<div class="spslot" data-slot="${s}">
        <label class="inl chk"><input type="checkbox" name="spSlotOn" value="${s}" ${s === 1 ? "checked" : ""}> Slot ${s}</label>
        <label class="sr-only" for="spSlotMat${s}">Slot ${s} material</label>
        <select id="spSlotMat${s}">${mats.map(m => `<option value="${esc(m)}" ${m === "PLA" ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
        <label class="sr-only" for="spSlotCol${s}">Slot ${s} colour</label>
        <input type="color" id="spSlotCol${s}" value="${col}" title="Slot ${s} colour">
      </div>`;
    }).join("")}
    <p class="help" id="spSlotNotes" aria-live="polite"></p></fieldset>`;
}
const svg = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
/* Beginner keeps the short row. Advanced adds every PrusaSlicer 2.9 sparse pattern.
   Tri-hexagon is Creality Print's name for the stars key. Zigzag is PrusaSlicer's zigzag,
   not Creality's first Zig-zag option (that one is rectilinear in their source). */
const PAT = {
  grid: { label: "Grid", note: "Everyday strength. A good lid under the top.", icon: svg("M4 8h16M4 12h16M4 16h16M8 4v16M12 4v16M16 4v16") },
  gyroid: { label: "Gyroid", note: "Strong in every direction. Uses more time.", icon: svg("M3 8c3-4 6 4 9 0s6 4 9 0M3 16c3-4 6 4 9 0s6 4 9 0") },
  honeycomb: { label: "Honeycomb", note: "Stiff in the layer. Slower than grid.", icon: svg("M8 4h8l4 7-4 7H8l-4-7z") },
  cubic: { label: "Cubic", note: "Strong up and down. A good functional part.", icon: svg("M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9") },
  lines: { label: "Lines", note: "Fast and light. Weaker than grid.", icon: svg("M5 7h14M5 12h14M5 17h14") },
  lightning: { label: "Lightning", note: "Fastest. Only holds the top up. Not for strength.", icon: svg("M4 14l6-2-2 8 12-12-6 2 2-8z") },
  rectilinear: { label: "Solid lines", note: "Creality's Rectilinear. Fine at 100% fill.", icon: svg("M5 19L19 5M9 19l10-10M5 15L15 5") },
  adaptivecubic: { label: "Adaptive cubic", note: "Denser near the walls, sparse in the middle. Saves filament.", icon: svg("M12 3l8 4.5v9L12 21l-8-4.5v-9zM8 9l4 2 4-2M12 11v6") },
  supportcubic: { label: "Support cubic", note: "Dense only under inner overhangs. Light everywhere else.", icon: svg("M4 18h16M7 14h10M10 10h4M12 6v4") },
  triangles: { label: "Triangles", note: "Stiff in the layer. More crossings than lines.", icon: svg("M12 4l8 14H4zM12 4v14M4 18l8-7 8 7") },
  stars: { label: "Tri-hexagon", note: "Creality's Tri-hexagon. This slicer runs it as stars.", icon: svg("M12 3l2.5 6h6l-5 4 2 6-5.5-3.5L6.5 19l2-6-5-4h6z") },
  concentric: { label: "Concentric", note: "Rings that follow the walls. Fast and flexible. Fine at 100%.", icon: svg("M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0M12 12m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0") },
  alignedrectilinear: { label: "Aligned rectilinear", note: "Lines keep one direction. Faster, weaker than grid. Fine at 100%.", icon: svg("M5 6h14M5 10h14M5 14h14M5 18h14") },
  zigzag: { label: "Zig zag", note: "Connected lines, fewer travels. PrusaSlicer key zigzag.", icon: svg("M4 8l4 4 4-4 4 4 4-4M4 16l4 4 4-4 4 4 4-4") },
  "3dhoneycomb": { label: "3D honeycomb", note: "Honeycomb stacked through the height. Slower, stronger.", icon: svg("M8 3h8l4 5-4 5H8L4 8zM8 11h8l4 5-4 5H8l-4-5z") },
  hilbertcurve: { label: "Hilbert curve", note: "One long curl. Slow and flexible. Fine at 100%.", icon: svg("M6 6h4v4H6zM14 6h4v4h-4zM6 14h4v4H6zM10 8v8h4") },
  archimedeanchords: { label: "Archimedean chords", note: "A spiral. Slow, mostly for looks. Fine at 100%.", icon: svg("M12 12c2 0 3-2 2-3s-3 0-4 2-1 5 2 6 6-2 6-5-3-6-6-6") },
  octagramspiral: { label: "Octagram spiral", note: "A star spiral. Slow. Fine at 100%.", icon: svg("M12 3l2 6 6 1-5 4 2 6-5-3-5 3 2-6-5-4 6-1z") },
};
const PAT_LABEL = Object.fromEntries(Object.entries(PAT).map(([id, meta]) => [id, meta.label]));
const SUP_META = {
  off: ["Off", "No extra material under overhangs."],
  auto: ["From the bed", "Supports grow up from the bed only."],
  everywhere: ["Everywhere", "Supports can also start on the model."],
};
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
  const patCur = pv.pattern || "grid";
  const beginnerPats = new Set(P.cat.patterns || Object.keys(PAT).slice(0, 7));
  const allPats = P.cat.patterns_advanced || P.cat.patterns || [...beginnerPats];
  const pats = allPats.map(id => {
    const meta = PAT[id] || { label: id, note: "", icon: "" };
    const advancedOnly = !beginnerPats.has(id);
    return `<button type="button" class="pat" data-pat="${esc(id)}" data-pat-level="${advancedOnly ? "advanced" : "beginner"}" ${advancedOnly && beginner ? "hidden" : ""} aria-pressed="${id === patCur ? "true" : "false"}">${meta.icon || ""}<span>${esc(meta.label)}</span><small>${esc(meta.note)}</small></button>`;
  }).join("");
  const sups = (P.cat.supports || []).map(id => {
    const meta = SUP_META[id] || [id, ""];
    return `<button type="button" class="supchoice" data-sup="${esc(id)}" aria-pressed="${id === "off" ? "true" : "false"}"><b>${esc(meta[0])}</b><small>${esc(meta[1])}</small></button>`;
  }).join("");
  const tab = (id, label, on) => `<button type="button" role="tab" id="procTab-${id}" data-proc="${id}" aria-selected="${on ? "true" : "false"}" aria-controls="procPane-${id}">${label}</button>`;
  return `<h3 class="sr-only">Slice for your printer</h3>
    <p class="help">Printer: <b id="spPrinter">${esc(prefLabel())}</b> · <a href="#account" id="spChange">Change printer</a></p>
    ${p?.technology === "Resin" ? `<p class="help warn">The ${esc(p.name)} is a resin printer. The FDM Slicer is for filament printers only. Open the <a href="#torchc0">TorchC0</a> tab to get this model ready for resin.</p>` : `
    <p class="help nozzlespec">${mfrHTML(pref.printer_id, n)}</p>
    <p class="help">Starting values for this printer. Filament and the machine can differ. These are not a promise about the finished print.</p>
    <div class="segmented" role="group" aria-label="Settings level"><button type="button" id="spBeginner" aria-pressed="${beginner}">Beginner</button><button type="button" id="spAdvanced" aria-pressed="${!beginner}">Advanced</button></div>
    <div id="spAdv"></div>
    <div class="proc-tabs" role="tablist" aria-label="Process">${tab("quality", "Quality", true)}${tab("filament", "Filament", false)}${tab("strength", "Strength", false)}${tab("speed", "Speed", false)}${tab("cooling", "Cooling", false)}${tab("support", "Support", false)}${tab("infill", "Infill", false)}${tab("adhesion", "Adhesion", false)}</div>
    <div id="procPane-quality" role="tabpanel" aria-labelledby="procTab-quality">
      <div class="presets" role="radiogroup" aria-label="Preset">${P.cat.presets.map(x => `<label class="preset" title="${esc(x.help)}"><input type="radio" name="spPreset" value="${x.id}" ${x.id === wantPreset ? "checked" : ""}><span><b>${esc(x.label)}</b></span></label>`).join("")}</div>
      <p class="help" id="spPresetHelp">${esc(pv.help || "")}</p>
      <div class="sp-adv" ${beginner ? "hidden" : ""}>
        <div class="grid3">
          ${num("spLayer", "Layer height", presetLayer(pv, lh.recommended, lo, hi), lo, hi, 0.01, `mm (${lo} to ${hi})`).replace("<input ", `<input data-rec="${lh.recommended}" `)}
          ${num("spLine", "Line width", o?.line_width_mm.recommended ?? n, o?.line_width_mm.min ?? n * 0.75, o?.line_width_mm.max ?? n * 1.5, 0.01, "mm")}
        </div>
        <p class="help">Seam is where each layer starts. Ironing runs a hot pass over the top. Both are starting points, not a finished-surface promise.</p>
        <div class="patgrid" role="group" aria-label="Seam">${["aligned", "nearest", "rear", "random"].map(id => `<button type="button" class="pat" data-seam="${id}" aria-pressed="${id === "aligned" ? "true" : "false"}"><span>${id[0].toUpperCase() + id.slice(1)}</span></button>`).join("")}</div>
        <div class="sr-only">${sel("spSeam", "Seam", ["aligned", "nearest", "rear", "random"], "aligned", { aligned: "Aligned", nearest: "Nearest", rear: "Rear", random: "Random" })}</div>
        <div class="adhgrid" role="group" aria-label="Ironing">
          <button type="button" class="supchoice" data-iron="off" aria-pressed="true"><b>Off</b><small>No ironing pass.</small></button>
          <button type="button" class="supchoice" data-iron="top" aria-pressed="false"><b>Top</b><small>A slow pass on the top surface.</small></button>
        </div>
        <div class="sr-only">${sel("spIron", "Ironing", ["off", "top"], "off", { off: "Off", top: "Top" })}</div>
        ${num("spIronFlow", "Ironing flow", 15, 5, 40, 1, "%")}
        <p class="help">Line width starts at ${o?.line_width_mm.recommended ?? n} mm for the ${n} mm nozzle. Changing the preset fills layer height in again.</p>
      </div>
    </div>
    <div id="procPane-filament" role="tabpanel" aria-labelledby="procTab-filament" hidden>
      <div class="patgrid" role="group" aria-label="Filament">${mats.map(id => `<button type="button" class="pat" data-mat="${esc(id)}" aria-pressed="${id === "PLA" ? "true" : "false"}"><span>${esc(id)}</span></button>`).join("")}</div>
      <div class="sr-only" id="spMatRow">${sel("spMat", "Material", mats, "PLA")}</div>
      ${slotsHTML(p, mats)}
      <div id="spMatWarn" aria-live="polite">${matWarnHTML("PLA")}</div>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>
        ${num("spNozT", "Nozzle temp", t.nozzle_c, 150, p?.max_nozzle_c || 300, 1, "°C")}${num("spBedT", "Bed temp", t.bed_c, 0, p?.max_bed_c || 110, 1, "°C")}
        <p class="help">Temperatures start from the material's reference values and stay inside what this printer can reach.</p>
      </div>
    </div>
    <div id="procPane-strength" role="tabpanel" aria-labelledby="procTab-strength" hidden>
      <p class="help">Walls and solid layers come from the preset until you expand.</p>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>
        ${num("spWalls", "Walls", pv.walls ?? 2, 1, 10, 1, "")}${num("spTB", "Top/bottom layers", pv.top_bottom ?? 4, 0, 20, 1, "")}
        ${num("spOverlap", "Infill overlap", 25, 0, 50, 1, "%")}
      </div>
    </div>
    <div id="procPane-speed" role="tabpanel" aria-labelledby="procTab-speed" hidden>
      <p class="help">Expand sends these speeds. Print speed starts from the preset.</p>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>
        ${num("spSpeed", "Print speed", pv.speed ?? 80, 10, 500, 5, "mm/s")}
        ${num("spTravel", "Travel speed", 150, 10, 500, 5, "mm/s")}
        ${num("spFirst", "First layer speed", 20, 5, 200, 1, "mm/s")}
      </div>
    </div>
    <div id="procPane-cooling" role="tabpanel" aria-labelledby="procTab-cooling" hidden>
      <p class="help">PLA usually wants a strong fan. ABS, ASA and PC usually want less. These are starting points.</p>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>
        ${num("spFanMin", "Fan minimum", 100, 0, 100, 5, "%")}${num("spFanMax", "Fan maximum", 100, 0, 100, 5, "%")}
        ${num("spFanOff", "Fan off for", 1, 0, 10, 1, "layers")}
      </div>
    </div>
    <div id="procPane-support" role="tabpanel" aria-labelledby="procTab-support" hidden>
      <div class="supgrid" role="group" aria-label="Supports">${sups}</div>
      <div class="sr-only">${sel("spSup", "Supports", P.cat.supports, "off", { off: "Off", auto: "Auto (from the bed only)", everywhere: "Everywhere" })}</div>
      <div id="spPaintHost"></div>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>
        ${num("spSupAngle", "Overhang angle", 0, 0, 90, 5, "°")}
        ${num("spSupSpace", "Support spacing", 2.5, 1, 8, 0.1, "mm")}
        <p class="help">0° leaves the overhang check to the slicer. Spacing is the gap between support lines.</p>
      </div>
    </div>
    <div id="procPane-infill" role="tabpanel" aria-labelledby="procTab-infill" hidden>
      <div class="patgrid" role="listbox" aria-label="Infill pattern">${pats}</div>
      <p class="help" id="spInfillRead"></p>
      <p class="help">At full fill, Solid lines works. Advanced can also use Concentric, Aligned rectilinear, Hilbert curve, Archimedean chords, or Octagram spiral. Other patterns can be refused at 100%.</p>
      <p class="help sp-adv" ${beginner ? "hidden" : ""}>Advanced is every sparse pattern PrusaSlicer 2.9 can slice. Quarter cubic, octet, cross, cross 3D, and TPMS are in Creality Print only, so they are not here.</p>
      <div class="sr-only">${sel("spPattern", "Infill pattern", allPats, patCur, PAT_LABEL)}</div>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>${num("spInfill", "Infill", pv.infill ?? 15, 0, 100, 1, "%")}</div>
    </div>
    <div id="procPane-adhesion" role="tabpanel" aria-labelledby="procTab-adhesion" hidden>
      <div class="adhgrid" role="group" aria-label="Brim">
        <button type="button" class="supchoice" data-brim="0" aria-pressed="true"><b>None</b><small>No brim.</small></button>
        <button type="button" class="supchoice" data-brim="5" aria-pressed="false"><b>Brim</b><small>5 mm outline. A starting width, not a promise it stays down.</small></button>
        <button type="button" class="supchoice" data-brim="10" aria-pressed="false"><b>Wide brim</b><small>10 mm. Uses more of the bed.</small></button>
      </div>
      <div class="sp-adv grid3" ${beginner ? "hidden" : ""}>
        ${num("spBrim", "Brim", 0, 0, 30, 1, "mm")}
        ${num("spSkirt", "Skirt loops", 0, 0, 10, 1, "")}
        ${num("spSkirtDist", "Skirt distance", 2, 0, 20, 0.5, "mm")}
        ${num("spRaft", "Raft layers", 0, 0, 8, 1, "")}
        <p class="help">Expand sends skirt and raft with the slice. 0 means none.</p>
      </div>
    </div>
    <label class="inl chk"><input type="checkbox" id="spFit"> Scale down to fit this printer if it's too big</label>
    <div class="row"><button class="btn primary big" id="spGo">Slice</button></div>`}
    <div id="spOut" aria-live="polite"></div>`;
}
/* ABS / ASA / PC (significant fumes): ventilation + enclosure note shown as soon as the material is picked, and again before slicing. */
export function matWarnHTML(m, { ask = false } = {}) {
  const w = P.cat?.materials?.[m]?.warning;
  if (!w) return "";
  return `<div class="matwarn" ${ask ? `role="alert"` : ""}><p><b><svg class=i aria-hidden=true focusable=false><use href=#i-alert></use></svg> ${esc(w.title)}</b></p><p>${esc(w.message)}</p><p class="help">${esc(w.tested)}</p>` +
    (ask ? `<div class="row"><button type="button" class="btn primary" id="spVentOk">${esc(w.confirm)}</button><button type="button" class="btn" id="spVentNo">Pick another material</button></div>` : "") + `</div>`;
}
function readPanel() {
  const fd = new FormData(), pref = P.pref, adv = $("#spAdvanced")?.getAttribute("aria-pressed") === "true";
  fd.append("printer_id", pref.printer_id); if (pref.nozzle) fd.append("nozzle", pref.nozzle);
  fd.append("preset", document.querySelector("[name=spPreset]:checked")?.value || "standard");
  fd.append("material", $("#spMat").value); fd.append("supports", $("#spSup").value);
  if (adv) for (const [k, id] of [["layer_height", "spLayer"], ["line_width", "spLine"], ["walls", "spWalls"], ["top_bottom", "spTB"], ["infill", "spInfill"], ["infill_overlap", "spOverlap"], ["speed", "spSpeed"], ["travel_speed", "spTravel"], ["first_layer_speed", "spFirst"], ["nozzle_temp", "spNozT"], ["bed_temp", "spBedT"], ["seam", "spSeam"], ["ironing", "spIron"], ["ironing_flow", "spIronFlow"], ["support_angle", "spSupAngle"], ["support_spacing", "spSupSpace"], ["skirt", "spSkirt"], ["skirt_distance", "spSkirtDist"], ["raft", "spRaft"], ["fan_min", "spFanMin"], ["fan_max", "spFanMax"], ["fan_off_layers", "spFanOff"]]) {
    const el = $("#" + id); if (el) fd.append(k, el.value);
  }
  if ($("#spPattern")) fd.append("infill_pattern", $("#spPattern").value);
  if ($("#spBrim")) fd.append("brim", $("#spBrim").value);
  if ($("#spFit").checked) fd.append("scale_to_fit", "true");
  const paint = getStrokes();
  if (paint.length) fd.append("support_paint", JSON.stringify(paint));
  const on = [...document.querySelectorAll("[name=spSlotOn]:checked")].map(c => +c.value);
  if ($("#spSlots") && on.length) {
    fd.append("slots", on.join(","));
    fd.append("slot_materials", JSON.stringify(on.map(s => ($("#spSlotMat" + s)?.value) || "PLA")));
    fd.append("slot_colours", JSON.stringify(on.map(s => ($("#spSlotCol" + s)?.value) || "#FFFFFF")));
    const m0 = $("#spSlotMat" + on[0]); if (m0) fd.set("material", m0.value);
  }
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
  mountPaint($("#spPaintHost"));
  const slotBox = $("#spSlots");
  if (slotBox) {
    // Multi-head: per-slot material replaces the single Material field (slot 1 is primary).
    const matField = mat.closest(".field");
    if (matField) matField.hidden = true;
    const syncSlots = () => {
      const on = [...slotBox.querySelectorAll("[name=spSlotOn]:checked")].map(c => +c.value);
      const note = $("#spSlotNotes");
      if (!on.length) { slotBox.querySelector("[name=spSlotOn]").checked = true; return syncSlots(); }
      on.forEach(s => { const sel = $("#spSlotMat" + s), col = $("#spSlotCol" + s); if (sel) sel.disabled = false; if (col) col.disabled = false; });
      slotBox.querySelectorAll("[name=spSlotOn]").forEach(c => {
        const s = +c.value, off = !c.checked;
        const sel = $("#spSlotMat" + s), col = $("#spSlotCol" + s);
        if (sel) sel.disabled = off; if (col) col.disabled = off;
      });
      const m0 = $("#spSlotMat" + on[0]); if (m0) { mat.value = m0.value; mat.dispatchEvent(new Event("change")); }
      if (note) note.textContent = on.length === 1
        ? `Only slot ${on[0]} will be heated and primed. Other ports stay unused.`
        : `Slots ${on.join(", ")} will be used. Other ports are not heated, primed or purged.`;
    };
    slotBox.addEventListener("change", syncSlots);
    syncSlots();
  }
  const mode = adv => {
    localStorage.setItem("zeim.slicerMode", adv ? "advanced" : "beginner");
    document.querySelectorAll("#slicePanel .sp-adv").forEach(el => { el.hidden = !adv; });
    document.querySelectorAll("#slicePanel [data-pat-level=advanced]").forEach(el => { el.hidden = !adv; });
    if (!adv && $("#spPattern")) {
      const cur = $("#spPattern").value;
      const shown = document.querySelector(`#slicePanel [data-pat="${CSS.escape(cur)}"]`);
      if (shown && shown.dataset.patLevel === "advanced") {
        const next = presetOf(document.querySelector("[name=spPreset]:checked")?.value).pattern;
        $("#spPattern").value = document.querySelector(`#slicePanel [data-pat="${CSS.escape(next)}"][data-pat-level=beginner]`) ? next : "grid";
      }
    }
    $("#spBeginner").setAttribute("aria-pressed", !adv); $("#spAdvanced").setAttribute("aria-pressed", adv);
    paintProcess();
  };
  $("#spBeginner").onclick = () => mode(false); $("#spAdvanced").onclick = () => mode(true);
  const showProc = id => {
    document.querySelectorAll("#slicePanel [data-proc]").forEach(b => {
      const on = b.dataset.proc === id;
      b.setAttribute("aria-selected", on);
      const pane = document.getElementById(b.getAttribute("aria-controls"));
      if (pane) pane.hidden = !on;
    });
  };
  document.querySelectorAll("#slicePanel [data-proc]").forEach(b => { b.onclick = () => showProc(b.dataset.proc); });
  const paintProcess = () => {
    const sup = $("#spSup")?.value, pat = $("#spPattern")?.value, brim = $("#spBrim") ? String($("#spBrim").value) : "";
    const seam = $("#spSeam")?.value, iron = $("#spIron")?.value, matName = $("#spMat")?.value;
    document.querySelectorAll("#slicePanel [data-sup]").forEach(b => b.setAttribute("aria-pressed", b.dataset.sup === sup ? "true" : "false"));
    document.querySelectorAll("#slicePanel [data-pat]").forEach(b => b.setAttribute("aria-pressed", b.dataset.pat === pat ? "true" : "false"));
    document.querySelectorAll("#slicePanel [data-brim]").forEach(b => b.setAttribute("aria-pressed", b.dataset.brim === brim ? "true" : "false"));
    document.querySelectorAll("#slicePanel [data-seam]").forEach(b => b.setAttribute("aria-pressed", b.dataset.seam === seam ? "true" : "false"));
    document.querySelectorAll("#slicePanel [data-iron]").forEach(b => b.setAttribute("aria-pressed", b.dataset.iron === iron ? "true" : "false"));
    document.querySelectorAll("#slicePanel [data-mat]").forEach(b => b.setAttribute("aria-pressed", b.dataset.mat === matName ? "true" : "false"));
    const read = $("#spInfillRead"), pv = presetOf(document.querySelector("[name=spPreset]:checked")?.value);
    if (read) read.textContent = `Infill ${$("#spInfill")?.value || pv.infill || ""}% · ${PAT_LABEL[pat] || pat || ""}. ${PAT[pat]?.note || ""}`.trim();
    const help = $("#spPresetHelp"); if (help) help.textContent = pv.help || "";
  };
  document.querySelectorAll("#slicePanel [data-sup]").forEach(b => b.onclick = () => { $("#spSup").value = b.dataset.sup; paintProcess(); });
  document.querySelectorAll("#slicePanel [data-pat]").forEach(b => b.onclick = () => { $("#spPattern").value = b.dataset.pat; paintProcess(); });
  document.querySelectorAll("#slicePanel [data-brim]").forEach(b => b.onclick = () => { $("#spBrim").value = b.dataset.brim; paintProcess(); });
  document.querySelectorAll("#slicePanel [data-seam]").forEach(b => b.onclick = () => { $("#spSeam").value = b.dataset.seam; paintProcess(); });
  document.querySelectorAll("#slicePanel [data-iron]").forEach(b => b.onclick = () => { $("#spIron").value = b.dataset.iron; paintProcess(); });
  document.querySelectorAll("#slicePanel [data-mat]").forEach(b => b.onclick = () => { $("#spMat").value = b.dataset.mat; $("#spMat").dispatchEvent(new Event("change")); paintProcess(); });
  // reference temps, capped to what this printer can reach (the server caps them the same way and says so)
  const cap = (v, el) => Math.min(v, +el.max || v);
  mat.onchange = () => { const t = P.cat.materials[mat.value]; $("#spNozT").value = cap(t.nozzle_c, $("#spNozT")); $("#spBedT").value = cap(t.bed_c, $("#spBedT")); $("#spMatWarn").innerHTML = matWarnHTML(mat.value); };
  // Advanced fields follow the preset: picking Strong in Advanced really slices with Strong's walls / infill (not Standard's numbers)
  document.querySelectorAll("[name=spPreset]").forEach(r => r.onchange = () => {
    const pv = presetOf(r.value), l = $("#spLayer");
    l.value = presetLayer(pv, +(l.dataset.rec || l.value), +l.min, +l.max);
    $("#spWalls").value = pv.walls; $("#spTB").value = pv.top_bottom; $("#spInfill").value = pv.infill; $("#spPattern").value = pv.pattern;
    $("#spSpeed").value = Math.min(pv.speed, +$("#spSpeed").max || pv.speed);
    paintProcess();
  });
  paintProcess();
  const bedBusy = (on, text) => {
    const el = document.getElementById("editBusy"), label = document.getElementById("editBusyText");
    if (!el) return;
    el.hidden = !on;
    if (label && text) label.textContent = text;
  };
  const doSlice = async (ventOk = false) => {
    const out = $("#spOut"), fd = readPanel(); fd.append("model_id", getModelId());
    if (ventOk) fd.append("ventilation_ok", "true");
    $("#spMatWarn").hidden = false;
    if (gcDispose) { gcDispose(); gcDispose = null; }
    out.innerHTML = `<p class="help">Slicing for the ${esc(prefLabel())}…</p>`; $("#spGo").disabled = true;
    bedBusy(true, "Slicing…");
    try {
      const r = await api("/api/slice", { method: "POST", body: fd });
      const notes = [...(r.temp_notes || []), r.material_warning ? `${r.material_warning.title}: ventilate the room and use an enclosure while it prints.` : ""].filter(Boolean);
      const paintNote = r.support_paint
        ? `<p class="help">Paint-on supports: ${r.support_paint.enforcers || 0} need / ${r.support_paint.blockers || 0} never. ${esc(r.support_paint.supports_note || r.support_paint.note || "")}</p>`
        : "";
      out.innerHTML = `<p class="slicestats"><span class="pill"><svg class=i aria-hidden=true focusable=false><use href=#i-clock></use></svg> ${esc(r.print_time_human || "time unknown")}</span><span class="pill"><svg class=i aria-hidden=true focusable=false><use href=#i-spool></use></svg> ${r.filament_grams != null ? "about " + r.filament_grams + " g" : "?"}${r.filament_mm ? ` · ${(r.filament_mm / 1000).toFixed(2)} m` : ""}</span>${r.scaled_pct ? `<span class="pill warn">Scaled to ${r.scaled_pct}%</span>` : ""}</p>
        <p class="help">Estimates read from the G-code. ${esc(r.settings.material)}, ${r.settings.layer_height} mm layers, ${r.settings.infill}% ${esc(r.settings.infill_pattern)}.</p>
        ${costHTML(r)}
        ${paintNote}
        ${r.skipped_objects?.length ? `<div class="help warn" role="alert" id="spSkipped"><p>${esc(r.skipped_note)}</p><div class="row"><button type="button" class="btn small" id="spSplit">Split onto another plate</button><button type="button" class="btn small ghost" id="spSkipX" aria-label="Dismiss this warning">Dismiss</button></div></div>` : ""}
        ${r.grams_note ? `<p class="help">${esc(r.grams_note)}</p>` : ""}
        ${(r.slot_notes || []).map(n => `<p class="help">${esc(n)}</p>`).join("")}
        ${r.slots ? `<p class="help">Filament slots used: ${esc((r.slots || []).join(", "))}. Unused ports are not heated, primed or purged.</p>` : ""}
        ${notes.map(n => `<p class="help warn">${esc(n)}</p>`).join("")}
        ${badgeHTML(r.will_print, { detail: true })}
        <div class="row"><a class="btn primary" href="${r.downloads.gcode}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> G-code</a><a class="btn" href="${r.downloads["3mf"]}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> 3MF</a><a class="btn" href="${r.downloads.stl}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> STL</a></div>
        ${HAS_GL ? gcodePreviewHTML() : r.downloads.layers ? layerPreviewHTML() : ""}
        ${openInHTML(r.downloads)}`;
      wireCost();
      if ($("#spSkipX")) $("#spSkipX").onclick = () => $("#spSkipped").remove();
      if ($("#spSplit")) $("#spSplit").onclick = async () => {
        const b = $("#spSplit"); b.disabled = true;
        try {
          const j = await api(`/api/edit/${encodeURIComponent(getModelId())}/plate/split`, { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ printer_id: P.pref?.printer_id }) });
          $("#spSkipped").innerHTML = `<p>${esc(j.message)}</p>${j.new_project ? `<a class="btn small" href="/?edit=${encodeURIComponent(j.new_project)}#slicer">Open plate 2</a>` : ""}`;
        } catch (e) { b.disabled = false; $("#spSkipped p").textContent = e.message || "Couldn't split the plate."; }
      };
      if (HAS_GL) gcDispose = wireGcodePreview(r.downloads.gcode, { time: r.print_time_human, grams: r.filament_grams, mm: r.filament_mm },
        { firmware: r.firmware, markers: r.problem_markers, pausedUrl: r.downloads.gcode + "-paused" });
      else if (r.downloads.layers) wireLayerPreview(r.downloads.layers);
      if ($("#spGo")?.dataset.reveal === "1") {
        delete $("#spGo").dataset.reveal;
        const sheet = document.getElementById("processSheet");
        if (sheet) sheet.hidden = false;
        out.querySelector("a[download]")?.focus();
      }
    } catch (e) {
      if (e.status === 409 && e.body?.detail?.code === "ventilation_check") {     // warn, then allow: the maker must read this once
        const sheet = document.getElementById("processSheet"); if (sheet) sheet.hidden = false;
        out.innerHTML = matWarnHTML(e.body.detail.warning?.material || $("#spMat").value, { ask: true });
        $("#spMatWarn").hidden = true;                                           // one copy on screen (the one that asks)
        $("#spVentOk").onclick = () => doSlice(true);
        $("#spVentNo").onclick = () => { out.innerHTML = ""; $("#spMatWarn").hidden = false; $("#spMat").focus(); };
        $("#spVentOk").focus();
      } else out.innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`;
    }
    finally { $("#spGo").disabled = false; bedBusy(false); }
  };
  $("#spGo").onclick = () => doSlice(false);
  applySmartFix();
  let armed = "";
  try { armed = sessionStorage.getItem("zeim.sliceNow") || ""; } catch { armed = ""; }
  if (armed === "1") {
    try { sessionStorage.removeItem("zeim.sliceNow"); } catch { /* the click still runs */ }
    $("#spGo").dataset.reveal = "1";
    $("#spGo").click();
  }
}
document.addEventListener("zeim:fdm-slice", () => {
  const go = document.getElementById("spGo");
  if (!go || go.disabled) return;
  try { sessionStorage.removeItem("zeim.sliceNow"); } catch { /* click still exports */ }
  go.dataset.reveal = "1";
  go.click();
});

/* Changes the maker said yes to in the Failure photo doctor (Smart Fix): filled into Advanced once, shown with Undo. */
function applySmartFix() {
  let pend = {};
  try { pend = JSON.parse(sessionStorage.getItem("zeim.smartfix.apply") || "{}"); } catch { }
  const ids = Object.keys(pend).filter(id => /^sp[A-Za-z]+$/.test(id) && $("#" + id));
  if (!ids.length) return;
  const before = {};
  ids.forEach(id => { const el = $("#" + id); before[id] = el.value; el.value = pend[id].to; });
  sessionStorage.removeItem("zeim.smartfix.apply");
  if ($("#spAdvanced")?.getAttribute("aria-pressed") !== "true") $("#spAdvanced").click();
  const note = document.createElement("div");
  note.className = "matwarn"; note.id = "spSmartFix"; note.setAttribute("role", "status");
  note.innerHTML = `<p><b>Smart Fix changes in use:</b> ${ids.map(id => `${esc(pend[id].label)} ${esc(String(pend[id].to))}${pend[id].unit ? " " + esc(pend[id].unit) : ""}`).join(", ")}.</p>
    <div class="row"><button type="button" class="btn" id="spSmartUndo">Undo</button></div>`;
  $("#spAdv").prepend(note);
  $("#spSmartUndo").onclick = () => { ids.forEach(id => { $("#" + id).value = before[id]; }); note.remove(); };
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

/* Printer and nozzle on the FDM device sheet. Same save path as Account. */
export async function mountSlicerPrinter() {
  const box = document.getElementById("devicePick");
  if (!box || box.dataset.ready === "1") return;
  try { await loadCatalog(); } catch { return; }
  if (!P.cat) return;
  box.dataset.ready = "1";
  box.innerHTML = pickerHTML("fdm") + `<div class="row"><button type="button" class="btn" id="fdmPrSave">Use this printer</button><span class="help" id="fdmPrMsg" aria-live="polite"></span></div>`;
  wirePicker("fdm");
  const save = document.getElementById("fdmPrSave");
  if (save) save.onclick = async () => {
    const msg = document.getElementById("fdmPrMsg");
    try {
      const picked = readPicker("fdm");
      if (!picked) { if (msg) msg.textContent = "Pick a printer first."; return; }
      const r = await savePref(picked);
      if (msg) msg.textContent = `Saved: ${prefLabel()}` + (r.stored === "profile" ? " (on your profile)." : " (in this browser).");
    } catch (e) { if (msg) msg.textContent = e.message; }
  };
}
