/* Print cost estimate under a finished slice: grams / metres / time come from PrusaSlicer's G-code; the cost is
   grams x the price YOU type for 1 kg of that filament. Kept only in this browser (localStorage), per material.
   Always labelled an estimate: it leaves out power, failed prints, wear and shipping. Nothing is charged or sent. */
import { esc, $ } from "/static/app.js";

const KEY = "zeim.filamentPrice";
const CURRENCIES = ["$", "€", "£", "¥", "₹", "R$", "kr"];
function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } }
function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { } }

export function costOf(grams, perKg) {
  if (!(grams > 0) || !(perKg > 0)) return null;
  return grams / 1000 * perKg;
}
export function money(v, cur) {
  if (v == null) return "";
  const tiny = v > 0 && v < 0.005, s = (tiny ? 0.01 : v).toFixed(2);     // money always to 2 decimals
  const t = /^[a-z]/i.test(cur) ? `${s} ${cur}` : `${cur}${s}`;
  return tiny ? `under ${t}` : t;
}
function hm(sec) {
  if (sec == null) return "";
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${Math.max(1, m)} min`;
}

export function costHTML(r) {
  const mat = r.settings?.material || "PLA", st = load(), cur = st.currency || "$", price = (st.per_kg || {})[mat] ?? "";
  if (r.filament_grams == null) return `<p class="help" id="costBox">No filament amount in this G-code, so ZEIM can't estimate the cost.</p>`;
  return `<div class="costbox" id="costBox" data-grams="${r.filament_grams}" data-material="${esc(mat)}">
    <p class="costline"><b>Estimate:</b> about <b>${r.filament_grams} g</b> of ${esc(mat)}${r.filament_mm ? ` (${(r.filament_mm / 1000).toFixed(2)} m)` : ""}${r.print_time_seconds ? ` · about <b>${hm(r.print_time_seconds)}</b>` : ""}.</p>
    <div class="row costrow">
      <label for="costCur" class="sr-only">Currency</label>
      <select id="costCur">${CURRENCIES.map(c => `<option ${c === cur ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>
      <label for="costKg">Your price for 1 kg of ${esc(mat)}</label>
      <input id="costKg" type="number" inputmode="decimal" min="0" max="1000" step="0.01" value="${price}" placeholder="e.g. 20">
    </div>
    <p class="costout" id="costOut" aria-live="polite"></p>
    <p class="help">An estimate from the G-code: filament only. It leaves out power, failed prints, printer wear and shipping. Your price stays in this browser.</p>
  </div>`;
}

export function wireCost() {
  const box = $("#costBox"), kg = $("#costKg"), curEl = $("#costCur"); if (!box || !kg) return;
  const grams = +box.dataset.grams, mat = box.dataset.material;
  const show = () => {
    const v = kg.value === "" ? null : +kg.value, cur = curEl.value, out = $("#costOut");
    const st = load(); st.currency = cur; st.per_kg = st.per_kg || {};
    if (v != null && v >= 0 && v <= 1000) { if (v > 0) st.per_kg[mat] = v; else delete st.per_kg[mat]; }
    save(st);
    const c = costOf(grams, v);
    out.textContent = c == null ? "Type your price per kg to see about how much filament this print uses in money."
      : `About ${money(c, cur)} of filament (${grams} g × ${money(v, cur)} per kg). Estimate only.`;
  };
  kg.addEventListener("input", show); curEl.addEventListener("change", show); show();
}
