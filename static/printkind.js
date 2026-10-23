/* FDM / Resin switch ("My printer"). Remembers the choice (localStorage, plus the account profile when signed up),
   preselects from the chosen printer's technology, and sets app defaults: which slicer tab is primary (first in the nav,
   target of #print), where print/hollow shortcuts point, and the printer the "Will it print?" checks use.
   Both the FDM Slicer and TorchC0 tabs always stay reachable. Notes are dismissible and never block. */
import { api } from "/static/app.js";
import { P, loadCatalog, printerOf } from "/static/printer.js";

const KEY = "zeim.printKind", NOTE = "zeim.printKindNoteOff";
const VIEW = { fdm: "slicer", resin: "torchc0" };
const J = b => ({ method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });
let kind = null;

export const printKind = () => kind;

function apply() {
  document.body.dataset.printKind = kind;
  document.querySelectorAll("#kindPick [data-kind]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.kind === kind)));
  document.querySelectorAll("#mainNav [data-view=slicer],#mainNav [data-view=torchc0]").forEach(b => {
    const on = b.dataset.view === VIEW[kind];
    b.classList.toggle("kind-primary", on);
    b.dataset.tip = b.dataset.tip || b.title;
    b.title = b.dataset.tip + (on ? " (your printer type)" : "");
  });
  // Hollow shortcut: resin users hollow in TorchC0 (with drain hole); filament users in the Slicer editor.
  document.querySelectorAll('a[href="#slicer/hollow"],a[href="#torchc0"][data-kind-link]').forEach(a => {
    a.dataset.kindLink = "1"; a.setAttribute("href", kind === "resin" ? "#torchc0" : "#slicer/hollow");
  });
  note();
}

function note() {   // one small dismissible hint on the non-primary slicer tab
  document.querySelectorAll(".kindnote").forEach(n => n.remove());
  if (localStorage.getItem(NOTE) === "1") return;
  const other = kind === "resin" ? "#viewEdit" : "#viewTorch", host = document.querySelector(other);
  if (!host) return;
  const d = document.createElement("div");
  d.className = "kindnote"; d.setAttribute("role", "note");
  d.innerHTML = `<svg class="i" aria-hidden="true" focusable="false"><use href="#i-printer"/></svg><span>You picked <b>${kind === "resin" ? "Resin" : "FDM"}</b> as your printer type. ${kind === "resin" ? "Resin prints are prepared in <a href=\"#torchc0\">TorchC0</a>; this FDM Slicer is for filament printers." : "Filament prints are sliced in the <a href=\"#slicer\">FDM Slicer</a>; TorchC0 is for resin printers."}</span><button type="button" class="btn small ghost x" aria-label="Dismiss this note">Dismiss</button>`;
  d.querySelector(".x").onclick = () => { localStorage.setItem(NOTE, "1"); d.remove(); };
  host.prepend(d);
}

async function matchPrinter() {   // keep the chosen printer (used by "Will it print?" + exports) on the same technology
  try {
    await loadCatalog();
    const tech = kind === "resin" ? "Resin" : "FDM";
    if (printerOf(P.pref.printer_id)?.technology === tech) return;
    const p = P.cat.printers.find(x => x.id === "creality_k1" && tech === "FDM") || P.cat.printers.find(x => x.technology === tech);
    if (!p) return;
    const pref = { printer_id: p.id, nozzle: tech === "Resin" ? null : (p.nozzle_options?.find(o => o.mm === 0.4)?.mm ?? p.nozzle_options?.[0]?.mm ?? 0.4) };
    try { const r = await api("/api/me/printer", J(pref)); pref.nozzle = r.nozzle ?? pref.nozzle; } catch { }
    P.pref = pref; localStorage.setItem("zeim.printer", JSON.stringify(pref));
    document.dispatchEvent(new CustomEvent("zeim:printer", { detail: pref }));
  } catch { }
}

export async function setKind(k, { save = true } = {}) {
  if (k !== "fdm" && k !== "resin") return;
  const changed = kind && kind !== k;
  kind = k; localStorage.setItem(KEY, k); apply();
  if (save) { api("/api/me/printer-kind", J({ kind: k })).catch(() => { }); await matchPrinter(); }
  document.dispatchEvent(new CustomEvent("zeim:printkind", { detail: k }));
  if (changed && (location.hash === "#slicer" || location.hash === "#torchc0")) location.hash = VIEW[k];
}

document.querySelectorAll("#kindPick [data-kind]").forEach(b => b.onclick = () => setKind(b.dataset.kind));
addEventListener("hashchange", () => { if (location.hash === "#print") location.replace("#" + VIEW[kind || "fdm"]); });

(async function init() {
  let k = localStorage.getItem(KEY);
  if (k !== "fdm" && k !== "resin") k = null;
  kind = k || "fdm"; apply();   // instant paint, then refine
  try { const r = await api("/api/me/printer-kind"); if (r.signed_up && r.kind) k = r.kind; } catch { }
  if (!k) { try { await loadCatalog(); k = printerOf(P.pref.printer_id)?.technology === "Resin" ? "resin" : "fdm"; } catch { k = "fdm"; } }
  await setKind(k, { save: false });
  if (location.hash === "#print") location.replace("#" + VIEW[kind]);
})();

/* S1: one source of truth for printer kind. The header "My printer" switch drives the lithophane material (its own select is hidden). */
function syncLithKind() {
  const sel = document.querySelector("#lithMaterial"), nm = document.querySelector("#lithKindName"); if (!sel) return;
  const k = (kind || "fdm") === "resin" ? "resin" : "filament";
  if (nm) nm.textContent = k === "resin" ? "Resin (SLA / MSLA)" : "Filament (FDM)";
  if (sel.value !== k) { sel.value = k; sel.dispatchEvent(new Event("change")); }
}
document.addEventListener("zeim:printkind", syncLithKind);
setTimeout(syncLithKind, 0);

/* S2: Print dialog with Resin chosen: no FDM slicers; "Open in TorchC0" instead */
document.querySelector("#printToTorch")?.addEventListener("click", () => {
  document.querySelector("#dlgPrint")?.close(); location.hash = "#torchc0";
});

/* Photo tips: one quiet line plus "More tips", never blocking. Studio + Lithophane get it under the photo drop;
   other photo pickers (e.g. select mode) can call window.zeimPhotoTips(el). */
export function photoTips(host, where = "afterend") {
  if (!host || host.parentElement?.querySelector(":scope > .phototips")) return null;
  const d = document.createElement("div"); d.className = "phototips help";
  d.innerHTML = `<span>Photos that work best: a clear subject, good contrast and a simple background. Busy photos give muddy results.</span> <details><summary>More tips</summary><ul>
    <li>Fill the frame with the subject; crop away clutter.</li><li>Even, soft light. Avoid harsh shadows and very dark photos.</li>
    <li>Sharp, in-focus photos at least 800 px wide.</li><li>Faces and pets: one or two at a time work better than groups.</li></ul></details>`;
  host.insertAdjacentElement(where, d); return d;
}
window.zeimPhotoTips = photoTips;
photoTips(document.querySelector("#viewCreate #drop"));
