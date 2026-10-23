/* TorchC0: ZEIM's resin program, its own main tab (#torchc0). Resin only: no nozzle, filament or gcode settings here.
   Upload a model -> POST /api/resin/prepare (hollow + drain hole, tilt, supports + raft) -> STL / 3MF for the resin slicer. */
import { api, esc, $ } from "/static/app.js";
import { money } from "/static/cost.js";
import * as THREE from "three";

/* 3D result view: the prepared STL with island (red) and suction-cup (orange) markers. Lazy: only made after a result. */
let viewer = null;
async function show3D(el, url, lc) {
  try {
    const { Viewer } = await import("/static/viewer.js");
    if (!viewer || !el.contains(viewer.el)) viewer = new Viewer(el);
    const buf = await (await fetch(url)).arrayBuffer(), dv = new DataView(buf), n = dv.getUint32(80, true);
    if (84 + n * 50 > buf.byteLength) throw new Error("not a binary STL");
    const pos = new Float32Array(n * 9);
    for (let i = 0; i < n; i++) for (let k = 0; k < 9; k++) pos[i * 9 + k] = dv.getFloat32(84 + i * 50 + 12 + k * 4, true);
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.computeVertexNormals();
    viewer.group.clear();
    viewer.group.add(new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: "#8fb0e0", roughness: 0.6, transparent: true, opacity: 0.85 })));
    g.computeBoundingBox(); const sz = g.boundingBox.getSize(new THREE.Vector3()), r = Math.max(0.8, Math.max(sz.x, sz.y, sz.z) / 60);
    const mark = (p, color) => { const m = new THREE.Mesh(new THREE.SphereGeometry(r, 16, 12), new THREE.MeshBasicMaterial({ color, depthTest: false }));
      m.position.set(...p); m.renderOrder = 2; viewer.group.add(m); };
    (lc.islands || []).forEach(i => i.xyz && mark(i.xyz, "#e5484d"));
    (lc.suction || []).forEach(i => i.xyz && mark(i.xyz, "#f5a524"));
    viewer.reset(); el.dataset.markers = String(viewer.group.children.length - 1);
  } catch (e) { el.innerHTML = `<p class="help">3D preview unavailable here (${esc(e.message)}). The files below are still ready.</p>`; }
}

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
    <div class="grid2 rzRow"><div class="field"><label for="rzPrinter">Resin printer</label><select id="rzPrinter">${brands.map(b => `<optgroup label="${esc(b)}">${cat.printers.filter(p => p.brand === b).map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</optgroup>`).join("")}</select></div>
    <div class="field"><label for="rzFile">Model (STL, 3MF or OBJ)</label><div class="drop rzDrop" id="rzDrop"><svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 15V3M7 8l5-5 5 5"/><path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg><input type="file" id="rzFile" class="rzFileIn" accept=".stl,.3mf,.obj"><label for="rzFile" class="btn">Choose a model</label><span>or drop an STL, 3MF or OBJ file here</span></div>
      <p class="help" id="rzFileStatus" role="status" aria-live="polite"></p></div></div>
    <p class="help" id="rzInfo"></p>
    <div class="field"><label for="rzPreset">Preset</label><select id="rzPreset">${cat.presets.map(x => `<option value="${x.id}" ${x.id === cat.default_preset ? "selected" : ""}>${esc(x.label)} · ${x.layer_mm} mm</option>`).join("")}</select></div>
    <details class="rzAdv" id="rzAdv"${document.body.dataset.level === "expert" ? " open" : ""}><summary>Advanced resin settings</summary><div class="grid3">${num("rzLayer", "Layer height", 0.05, 0.01, 0.2, 0.01, "mm")}${num("rzExp", "Exposure", 2.5, 0.5, 30, 0.1, "s")}${num("rzBExp", "Bottom exposure", 30, 5, 120, 1, "s")}
      ${num("rzBL", "Bottom layers", 5, 1, 15, 1, "")}${num("rzLift", "Lift distance", 6, 1, 15, 0.5, "mm")}${num("rzLiftS", "Lift speed", 65, 10, 300, 5, "mm/min")}
      ${num("rzTilt", "Tilt", 30, 0, 60, 5, "°")}${num("rzWall", "Hollow wall", 2, 0.5, 6, 0.5, "mm")}${num("rzDrain", "Drain hole Ø", 3, 0, 10, 0.5, "mm")}</div></details>
    <p class="help warn rzWarn" id="rzWallWarn" hidden>Walls under 1 mm crack easily in resin. Use 1 mm or more, or prepare anyway.
      <button type="button" class="btn small" id="rzWallAnyway">Prepare anyway</button> <button type="button" class="btn small" id="rzWallDismiss" aria-label="Dismiss this warning">Dismiss</button></p>
    <div class="grid3"><div class="field"><label for="rzCur">Currency</label><select id="rzCur">${CURS.map(c => `<option ${c === (loadP().currency || "$") ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></div>
      ${num("rzCost", "Resin price", loadP().price ?? cat.default_price ?? "", 0, 10000, 0.5, "")}
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
  // file pick / drop: show name + size right away; wrong types get a friendly note (never blocks anything else)
  const st = $("#rzFileStatus"), inp = $("#rzFile"), drop = $("#rzDrop");
  const kb = n => n < 1048576 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1048576).toFixed(1)} MB`;
  // soft hint only: the server checks the content and decides (it accepts e.g. no extension or iPhone ".3mf.zip")
  const okType = f => /\.(stl|3mf|obj)(\.zip)?$/i.test(f.name);
  // displayed name only: drop bidi overrides/isolates, zero-width and control chars so the name can't be misread
  const shownName = n => n.replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]/g, "");
  const show = () => { const f = inp.files[0]; st.classList.remove("warn");
    $("#torchOut").querySelector(".rzNeedFile")?.remove();   // P1: the "choose a file first" note goes as soon as a file is chosen
    if (!f) { st.textContent = ""; return; }
    const nm = shownName(f.name) || "(unnamed file)";
    if (!okType(f)) { st.textContent = `${nm}, ${kb(f.size)}. This doesn't look like an STL, 3MF or OBJ name, but you can still press Prepare for resin and TorchC0 will check the file itself.`; return; }
    st.textContent = `${nm}, ${kb(f.size)}, ready. Press Prepare for resin.`; };
  inp.addEventListener("change", show);
  // tapping anywhere on the drop zone opens the picker (phones can't drop); the input itself already does
  drop.addEventListener("click", e => { if (e.target !== inp && !e.target.closest("a,button,label")) inp.click(); });
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => { const fs = e.dataTransfer?.files; if (!fs?.length) return;
    const dt = new DataTransfer(); dt.items.add(fs[0]); inp.files = dt.files; show(); });
  $("#rzGo").onclick = async () => {
    const out = $("#torchOut"), f = $("#rzFile").files[0];
    if (!f) { out.innerHTML = `<p class="help warn rzNeedFile" role="alert">Choose an STL, 3MF or OBJ file first.</p>`; return; }
    const fd = new FormData();
    const v = { printer_id: $("#rzPrinter").value, preset: pr.value, layer_mm: $("#rzLayer").value, exposure_s: $("#rzExp").value,
      bottom_exposure_s: $("#rzBExp").value, bottom_layers: $("#rzBL").value, lift_mm: $("#rzLift").value, lift_speed_mm_min: $("#rzLiftS").value,
      tilt_deg: $("#rzTilt").value, wall_mm: $("#rzWall").value, drain_mm: $("#rzDrain").value, hollow: $("#rzHollow").checked, supports: $("#rzSup").checked,
      price: $("#rzCost").value, price_unit: $("#rzCostU").value };
    last = { v, f, isl: [], drains: [] };
    await run();
  };
  let last = null;
  $("#torchOut").addEventListener("click", async e => {      // one-click fixes re-run the same job with the extra points
    const b = e.target.closest("#rzFixIsl,#rzFixCup"); if (!b || !last || !last.rep) return;
    const lc = last.rep.layer_check;
    if (b.id === "rzFixIsl") last.isl = last.isl.concat(lc.islands.map(i => i.at).filter(Boolean));
    else last.drains = last.drains.concat(lc.suction.map(i => i.at).filter(Boolean));
    await run();
  });
  async function run() {
    const out = $("#torchOut"), { v, f } = last, fd = new FormData();
    saveP({ price: $("#rzCost").value === "" ? null : +$("#rzCost").value, unit: $("#rzCostU").value, currency: $("#rzCur").value });
    Object.entries(v).forEach(([k, x]) => fd.append(k, x)); fd.append("file", f);
    if (last.isl.length) fd.append("island_supports", JSON.stringify(last.isl));
    if (last.drains.length) fd.append("drains", JSON.stringify(last.drains));
    out.innerHTML = `<p class="help" role="status" aria-live="polite">Preparing… TorchC0 is hollowing, tilting and adding supports. Larger models can take a minute.</p>`;
    const go = $("#rzGo"); go.disabled = true; go.setAttribute("aria-busy", "true"); go.textContent = "Preparing…";
    try {
      const r = await api("/api/resin/prepare", { method: "POST", body: fd }), e = r.estimate;
      last.rep = r;
      const lc = r.layer_check || { islands: [], suction: [] }, nI = lc.islands.length, nS = lc.suction.length;
      const costTxt = e.cost == null ? "<svg class=i aria-hidden=true focusable=false><use href=#i-coin></use></svg> enter a price for a cost estimate" : `<svg class=i aria-hidden=true focusable=false><use href=#i-coin></use></svg> about ${esc(money(e.cost, $("#rzCur").value))} (estimate)`;
      out.innerHTML = `<h2 class="rzResHead">Result</h2><div id="rzView" class="rzView" role="img" aria-label="3D view of the prepared model: red dots are islands, orange dots are suction cups" style="position:relative;width:100%;height:min(60vw,360px);min-height:220px;border-radius:8px;overflow:hidden"></div>
        <div class="rzChecks" id="rzChecks">
        <p class="help ${nI ? "warn rzWarn" : ""}" id="rzIslands"><span class="pill"><svg class=i i-red aria-hidden=true focusable=false><use href=#i-dot></use></svg> ${nI} island${nI === 1 ? "" : "s"}</span> ${nI ? "Parts that start in mid-air (red dots)." : "No unsupported islands found."}
          ${nI ? `<button type="button" class="btn small" id="rzFixIsl" style="min-height:44px">Add supports to islands</button> <button type="button" class="btn small rzDismiss" style="min-height:44px" aria-label="Dismiss the island warning">Dismiss</button>` : ""}</p>
        <p class="help ${nS ? "warn rzWarn" : ""}" id="rzCups"><span class="pill"><svg class=i i-amber aria-hidden=true focusable=false><use href=#i-dot></use></svg> ${nS} suction cup${nS === 1 ? "" : "s"}</span> ${nS ? "Hollows sealed on the plate side trap resin and pull a vacuum (orange dots)." : "No suction cups found."}
          ${nS ? `<button type="button" class="btn small" id="rzFixCup" style="min-height:44px">Add drain hole${nS === 1 ? "" : "s"}</button> <button type="button" class="btn small rzDismiss" style="min-height:44px" aria-label="Dismiss the suction cup warning">Dismiss</button>` : ""}</p></div>
        <p class="slicestats"><span class="pill"><svg class=i aria-hidden=true focusable=false><use href=#i-clock></use></svg> about ${esc(e.print_time_human)}</span><span class="pill"><svg class=i aria-hidden=true focusable=false><use href=#i-flask></use></svg> about ${e.resin_ml} ml</span><span class="pill" id="rzCostOut">${costTxt}</span><span class="pill">${e.layers} layers</span>${r.support ? `<span class="pill">${r.support.supports} supports</span>` : ""}${r.fits === false ? `<span class="pill warn">Too big</span>` : ""}</p>
        ${r.hollow ? `<p class="help">${esc(r.hollow.message)}</p>` : ""}
        ${r.notes.filter(n => !/ island\(s\)| suction cup\(s\)/.test(n)).map(n => `<p class="help warn rzWarn">${esc(n)} <button type="button" class="btn small rzDismiss" style="min-height:44px" aria-label="Dismiss this warning">Dismiss</button></p>`).join("")}
        <p class="help">${esc(e.resin_note)} ${esc(e.cost_note)}</p>
        <div class="row"><a class="btn primary" href="${r.downloads.stl}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> STL</a><a class="btn" href="${r.downloads["3mf"]}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> 3MF</a></div>`;
      out.classList.add("rzResult");
      out.querySelectorAll(".rzDismiss").forEach(b => b.onclick = () => b.closest(".rzWarn").remove());   // warnings never block: the files are already made
      show3D($("#rzView"), r.downloads.stl, lc);
    } catch (err) { out.innerHTML = `<p class="help warn" role="alert">${esc(err.message)}</p>`; }
    finally { const go = $("#rzGo"); go.disabled = false; go.removeAttribute("aria-busy"); go.textContent = "Prepare for resin"; }
  }
}

async function load() {
  if (cat) return;
  try { cat = await api("/api/resin/catalog"); $("#torchPanel").innerHTML = panelHTML(); wire(); }
  catch (e) { cat = null; $("#torchPanel").innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`; }
}
document.addEventListener("zeim:torchc0-shown", load);
document.addEventListener("zeim:level", () => { const d = $("#rzAdv"); if (d) d.open = document.body.dataset.level === "expert"; });   // S9: Beginner sees preset + Hollow/Supports
if (location.hash.startsWith("#torchc0") || location.hash.startsWith("#resin")) load();
