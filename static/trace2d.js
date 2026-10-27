/* 'Logo & Drawing to 3D': settings panel + live traced-outline preview. The build itself goes through /api/generate
   (mode=trace2d), so the photo permission tick, upload checks, history, 3D viewer, plate editor and slicer are the same as every build. */
import { S, api, $, $$, applyMode } from "/static/app.js";

const OUT_HELP = {
  extrude: "Your shape, raised to the height you pick. Add a base or a keyring hole if you like.",
  cutter: "A thin cutting wall along the outline with a wide flange to push on. Print it flange-down.",
  stamp: "Your design on a base: raised for an ink stamp, or pressed in for clay and dough.",
  layers: "Each colour is its own piece at its own height. Great for AMS / CFS colour printers.",
};
const out = () => ($("#tOut input:checked") || {}).value || "extrude";

function opts() {
  const o = { out: out() };
  $$("#traceOpts [data-t]").forEach(el => {
    if (el.closest("[hidden]")) return;                   // only the settings that are showing for this choice
    const k = el.dataset.t;
    o[k] = el.type === "checkbox" ? el.checked : el.tagName === "SELECT" && /^(true|false)$/.test(el.value) ? el.value === "true" : el.value;
  });
  o.threshold = $("#t_auto").checked ? -1 : +$("#t_threshold").value;
  return o;
}
window.zeimTraceOpts = opts;

function applyOut() {
  const v = out();
  $$("#traceOpts [data-tout]").forEach(e => e.hidden = e.dataset.tout !== v);
  $$("#traceOpts [data-tnot]").forEach(e => e.hidden = e.dataset.tnot === v);
  $("#tOutHelp").textContent = OUT_HELP[v];
  const byColour = $("#t_color_mode").value === "true";
  if (v !== "layers") $("#t_colors").closest(".field").hidden = !byColour;
  $("#t_auto").closest(".field").hidden = byColour || v === "layers"; $("#t_threshold").closest(".field").hidden = byColour || v === "layers";
}

let timer = null, seq = 0;
function schedule() { clearTimeout(timer); timer = setTimeout(preview, 350); }
async function preview() {
  if (S.mode !== "trace2d" || !S.file) return;
  const my = ++seq, st = $("#traceStatus"), box = $("#tracePrev");
  st.textContent = "Tracing your picture…";
  const fd = new FormData();
  fd.append("file", S.file); fd.append("photo_ack", $("#sAck")?.checked || false);
  fd.append("width_mm", $("#width_mm").value); fd.append("trace", JSON.stringify(opts()));
  try {
    const r = await api("/api/trace2d/preview", { method: "POST", body: fd });
    if (my !== seq) return;
    box.innerHTML = r.svg;                                  // server-built SVG: only numbers and fixed colours
    const holes = r.holes ? `, ${r.holes} ${r.holes > 1 ? "holes" : "hole"} kept` : "";
    const line = `${r.pieces} ${r.pieces > 1 ? "pieces" : "piece"}${holes}, ${r.size_mm[0]} × ${r.size_mm[1]} mm` +
      (r.threshold != null && $("#t_auto").checked ? `. Cut-off picked: ${r.threshold}` : "");
    box.setAttribute("aria-label", "Traced outline: " + line.replace(" × ", " by "));
    st.textContent = line + "." + (r.warnings.length ? " " + r.warnings.join(" ") : "") + (r.notes.length ? " " + r.notes.join(" ") : "") +
      (r.thin && !$("#t_thicken").checked ? " Thin bits are shown in red." : "");
    if (r.threshold != null && $("#t_auto").checked) { $("#t_threshold").value = r.threshold; }
  } catch (e) {
    if (my === seq) { st.textContent = "We couldn't trace that: " + (e.message || "please try again."); }
  }
}

$("#tOut").addEventListener("change", () => { applyOut(); schedule(); });
$("#traceOpts").addEventListener("input", e => {
  if (e.target.id === "t_threshold") $("#t_thrOut").textContent = e.target.value;
  if (e.target.id === "t_despeckle") $("#t_despOut").textContent = e.target.value;
  if (e.target.id === "t_smooth") $("#t_smOut").textContent = e.target.value;
  schedule();
});
$("#traceOpts").addEventListener("change", e => {
  if (e.target.id === "t_color_mode") applyOut();
  if (e.target.id === "t_auto") { $("#t_threshold").disabled = e.target.checked; $("#t_thrOut").textContent = e.target.checked ? "auto" : $("#t_threshold").value; }
  schedule();
});
$("#width_mm").addEventListener("change", schedule);
document.addEventListener("zeim:file", schedule);
document.addEventListener("zeim:mode", e => { if (e.detail === "trace2d") { applyOut(); schedule(); } });
applyOut();
$("#cadTrace")?.addEventListener("click", () => {          // CAD tab shortcut: same tool, in the Create flow
  S.mode = "trace2d"; location.hash = "create"; applyMode();
  setTimeout(() => $("#modeCards input[value=trace2d]")?.focus(), 300);
});
