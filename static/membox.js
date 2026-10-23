/* Memory box helpers (kept out of app.js): the light base / lid / fit sizes shown under the preview. */
const n = v => (Math.round(v * 10) / 10).toString();
function dims(info, el) {
  if (!el || !info) return;
  const rows = [];
  const b = info.base;
  if (b) {
    const room = b.light_shape === "round" ? `${n(b.light_room_mm[0])} mm wide` : `${n(b.light_room_mm[0])} x ${n(b.light_room_mm[1])} mm`;
    rows.push(`Light base: ${n(b.outer_mm[0])} x ${n(b.outer_mm[1])} x ${n(b.outer_mm[2])} mm, open underneath. Room for the light: ${room}, ${n(b.light_room_mm[2])} mm tall.`);
    rows.push(`Light opening: ${n(b.opening_mm[0])}${b.light_shape === "round" ? "" : " x " + n(b.opening_mm[1])} mm. Locating ring: ${n(b.ring_mm[0])} mm, ${n(b.ring_mm[2])} mm high.`);
    rows.push(b.notch_mm[0] ? `Cable notch: ${n(b.notch_mm[0])} mm wide x ${n(b.notch_mm[1])} mm high, at the back.` : "No cable notch.");
  } else rows.push("No light base: the box sits straight over the light.");
  rows.push(`Box: ${n(info.panel_mm)} mm cube. Fit clearance ${n(info.clearance_mm)} mm` + (info.groove_mm ? `, groove ${n(info.groove_mm)} mm.` : "."));
  if (info.sample_sides?.length) rows.push(`Sample photo on side ${info.sample_sides.join(", ")}.`);
  rows.push("Sizes and fits are starting points; adjust the clearance for your printer.");
  el.innerHTML = rows.map(r => `<span class="mbrow">${r.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))}</span>`).join("<br>");
  el.hidden = false;
}
window.zeimMembox = { dims };
