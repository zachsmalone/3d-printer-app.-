/* Parts builder UI — original code. Builds a recipe of primitives, the server composes it
   (step 1 of an ordinary edit project, so the recipe stays parametric and the model flows
   into the existing slice / print / share pipeline). Does not touch edit.js or the viewer:
   the Viewer class is reused as-is. */
import { Viewer } from "/static/viewer.js";

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const api = async (url, opt) => {
  const r = await fetch(url, opt);
  let j = null;
  try { j = await r.json(); } catch { }
  if (!r.ok) {
    const d = j?.detail ?? j?.message;
    const e = new Error(typeof d === "string" && d ? d : r.statusText || "Something went wrong.");
    e.status = r.status; e.body = j; throw e;
  }
  return j;
};

/* ---------- recipe state (mirrors the server's schema exactly) ---------- */
const KINDS = {
  box:      { dims: [["size", 3, [20, 20, 20]]], label: "Size X/Y/Z (mm)" },
  cylinder: { dims: [["diameter", 1, [20]], ["height", 1, [20]]], label: "Diameter / height" },
  sphere:   { dims: [["diameter", 1, [20]]], label: "Diameter" },
  cone:     { dims: [["diameter", 1, [20]], ["height", 1, [20]]], label: "Diameter / height" },
  tube:     { dims: [["outer", 1, [24]], ["inner", 1, [16]], ["height", 1, [20]]], label: "Outer / inner / height" },
  torus:    { dims: [["outer", 1, [30]], ["tube", 1, [6]]], label: "Outer / tube" },
};
let parts = [{ kind: "box", role: "solid", dims: { size: [40, 40, 10] }, position: [0, 0, 0], rotation: [0, 0, 0] }];
let bid = new URLSearchParams(location.search).get("bid");   // reopen a saved recipe
let busy = false;

/* ---------- rendering (pure: never touches the network) ---------- */
function partCard(p, i) {
  const k = KINDS[p.kind];
  const el = document.createElement("div");
  el.className = "part";
  el.innerHTML = `
    <div class="prow" style="justify-content:space-between">
      <span style="font-weight:600">${i + 1}. ${p.kind}</span>
      <span style="display:flex;gap:4px">
        <button class="btn small" data-up="${i}" ${i === 0 ? "disabled" : ""}>↑</button>
        <button class="btn small" data-down="${i}" ${i === parts.length - 1 ? "disabled" : ""}>↓</button>
        <button class="btn small ghost" data-del="${i}">✕</button>
      </span>
    </div>
    <div class="prow" style="margin-top:6px;gap:8px">
      <label class="mini">Role</label>
      <select data-f="role" style="width:auto" class="${p.role === "hole" ? "roleHole" : ""}">
        <option value="solid" ${p.role === "solid" ? "selected" : ""}>Solid (adds)</option>
        <option value="hole" ${p.role === "hole" ? "selected" : ""}>Hole (cuts)</option>
      </select>
    </div>
    ${k.dims.map(([name, n, def]) => `
      <div class="field" style="margin:8px 0 0"><label class="mini">${name}${n > 1 ? " (X/Y/Z, mm)" : " (mm)"}</label>
        ${n === 1
          ? `<input type="number" step="0.1" data-dim="${name}" value="${p.dims[name] ?? def[0]}">`
          : `<div class="dim3">${[0, 1, 2].map(a => `<input type="number" step="0.1" data-dim="${name}:${a}" value="${(p.dims[name] ?? def)[a]}">`).join("")}</div>`}
      </div>`).join("")}
    <div class="field" style="margin:8px 0 0"><label class="mini">Position X/Y/Z (mm)</label>
      <div class="dim3">${[0, 1, 2].map(a => `<input type="number" step="1" data-pos="${a}" value="${p.position[a]}">`).join("")}</div></div>
    <div class="field" style="margin:8px 0 0"><label class="mini">Rotation X/Y/Z (degrees)</label>
      <div class="dim3">${[0, 1, 2].map(a => `<input type="number" step="15" data-rot="${a}" value="${p.rotation[a]}">`).join("")}</div></div>`;
  el.querySelectorAll("[data-f]").forEach(sel => sel.onchange = () => { p.role = sel.value; render(); });
  el.querySelectorAll("[data-dim]").forEach(inp => inp.onchange = () => {
    const [name, a] = inp.dataset.dim.split(":");
    const v = parseFloat(inp.value);
    if (!isFinite(v)) return;
    if (a === undefined) p.dims[name] = v;
    else p.dims[name] = [...p.dims[name]].map((x, i) => i === +a ? v : x);
  });
  el.querySelectorAll("[data-pos]").forEach(inp => inp.onchange = () => {
    const v = parseFloat(inp.value);
    if (isFinite(v)) p.position[+inp.dataset.pos] = v;
  });
  el.querySelectorAll("[data-rot]").forEach(inp => inp.onchange = () => {
    const v = parseFloat(inp.value);
    if (isFinite(v)) p.rotation[+inp.dataset.rot] = v;
  });
  el.querySelector("[data-del]").onclick = () => { parts.splice(i, 1); render(); };
  el.querySelector("[data-up]").onclick = () => { [parts[i - 1], parts[i]] = [parts[i], parts[i - 1]]; render(); };
  el.querySelector("[data-down]").onclick = () => { [parts[i + 1], parts[i]] = [parts[i], parts[i + 1]]; render(); };
  return el;
}

function render() {
  const host = $("#parts");
  host.innerHTML = "";
  parts.forEach((p, i) => host.appendChild(partCard(p, i)));
  $("#partsHelp").hidden = parts.length > 0;
  $("#partsHelp").textContent = "Add a primitive to start. The first part must be a solid.";
  $("#btnCreate").hidden = !!bid;
  $("#btnUpdate").hidden = !bid;
}

$$("[data-add]").forEach(b => b.onclick = () => {
  const kind = b.dataset.add;
  const dims = {};
  for (const [name, n, def] of KINDS[kind].dims) dims[name] = n === 1 ? def[0] : [...def];
  parts.push({ kind, role: "solid", dims, position: [0, 0, 0], rotation: [0, 0, 0] });
  render();
});

/* ---------- viewer (reused, not modified) ---------- */
let viewer = null;
try { viewer = new Viewer($("#viewer")); } catch (e) { console.warn("WebGL unavailable", e); }
$("#vReset").onclick = () => viewer?.controls.reset();
$("#vWire").onclick = () => { if (viewer) { viewer.wire = !viewer.wire; viewer.load(lastPreview, "edit", { flat: true }); } };
let lastPreview = null;
function show(p) {
  lastPreview = p.preview;
  viewer?.load(p.preview, "edit", { flat: true });
  const s = p.stats || {};
  $("#stats").textContent = s.triangles ? `${s.triangles.toLocaleString()} triangles${s.watertight ? " · watertight" : ""}` : "";
}

/* ---------- create / update ---------- */
async function run(fn) {
  if (busy) return;
  busy = true;
  $("#btnCreate").disabled = true; $("#btnUpdate").disabled = true;
  try {
    await fn();
  } catch (e) {
    $("#status").textContent = e.message || "Something went wrong.";
    $("#status").classList.add("roleHole");
  } finally {
    busy = false; $("#btnCreate").disabled = false; $("#btnUpdate").disabled = false;
  }
}

$("#btnCreate").onclick = () => run(async () => {
  $("#status").classList.remove("roleHole");
  $("#status").textContent = "Building…";
  const out = await api("/api/parts/new", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ title: $("#title").value.trim() || "My parts build", recipe: { parts } }),
  });
  bid = out.id;
  history.replaceState(null, "", `/builder.html?bid=${bid}`);        // the reopen link IS the address bar now
  show(out);
  $("#status").textContent = "Built. Every number above stays editable — change one and press Update.";
  $("#handoff").hidden = false;
  $("#handoff").innerHTML = `Saved — this page is your recipe's home, so bookmark it. Next steps: slice & print it from the <a href="/#slicer">main page</a> — your model is in Recent builds, or <a href="/api/download/${bid}/stl">download the STL</a>.`;
  render();
});

$("#btnUpdate").onclick = () => run(async () => {
  $("#status").classList.remove("roleHole");
  $("#status").textContent = "Updating…";
  const out = await api(`/api/parts/${bid}/recipe`, {
    method: "PUT", headers: { "content-type": "application/json" },
    body: JSON.stringify({ recipe: { parts } }),
  });
  show(out);
  $("#status").textContent = "Updated.";
});

/* ---------- initial render, THEN startup-complete flags. The form must be on screen
   before the watchdog is told the page started: a rendering failure can then still
   raise the banner (it cannot happen after a successful render). ---------- */
render();
window.__zeimStarted = true;
window.__zeimEditStarted = true;

/* ---------- reopening a saved recipe (builder.html?bid=...) — runs ONCE at startup ---------- */
/* Saved-project picker: the reachable 'edit recipe' path for existing builds. */
(async function loadSavedList() {
  try {
    const r = await fetch("/api/parts/projects");
    if (!r.ok) return;
    const projects = (await r.json()).projects || [];
    if (!projects.length) return;
    const ul = $("#savedList");
    for (const p of projects.slice(0, 8)) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = "builder.html?bid=" + encodeURIComponent(p.id);
      a.textContent = p.title + (p.triangles ? ` (${p.triangles.toLocaleString()} triangles)` : "");
      li.appendChild(a);
      ul.appendChild(li);
    }
    $("#savedProjects").hidden = false;
  } catch (e) { /* the picker is optional: never block the builder */ }
})();

(async function openSaved() {
  if (!bid) return;                        // fresh page: already rendered above
  try {
    const rec = await api(`/api/parts/${bid}/recipe`);
    if (rec?.recipe?.parts?.length) parts = rec.recipe.parts;
    const p = await api(`/api/edit/${bid}`);
    show(p);
    $("#status").textContent = "Reopened your recipe — change any number and press Update.";
    $("#handoff").hidden = false;
    $("#handoff").innerHTML = `Next steps: slice & print it from the <a href="/#slicer">main page</a> — your model is in Recent builds, or <a href="/api/download/${bid}/stl">download the STL</a>.`;
  } catch (e) {
    $("#status").textContent = e.status === 409
      ? "That project wasn't made in the parts builder."
      : (e.message || "Could not reopen that project.");
    bid = null;
  }
  render();
})();
