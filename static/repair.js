// Repair page (POST /api/repair). The repaired file stays on the server.
// Open in the FDM Slicer asks the server to open that file as one slicer project.
// The browser does not download it and upload it again.
import { bindFlow, planHop, readFlow, rememberRepair, reuseRepair, slicerUrlForNewProject } from "/static/project-flow.js";

const $ = s => document.querySelector(s);
const esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const yn = b => b ? "yes" : "no";

let repairId = "";
let editId = "";
let opening = null;

function flowContext() {
  return { view: "repair", editId, kind: "fdm", tool: "" };
}

function beginner() {
  try { return localStorage.level !== "expert"; } catch { return true; }
}

function nextCopy(hasProject) {
  if (hasProject) {
    return "The repaired file is kept here for one hour. Open in the FDM Slicer continues the project for this repair, if it is still on Account. If it was deleted, a new project is started from the repaired file. The file you uploaded stays as it was.";
  }
  return "The repaired file is kept here for one hour. The first time you open it in the FDM Slicer, ZEIM starts a new project from that file. After that, the same project opens. The file you uploaded stays as it was.";
}

function showErr(message) {
  const host = $("#rpOut") || document.body;
  let p = $("#rpSlicerErr");
  if (!p) {
    p = document.createElement("p");
    p.id = "rpSlicerErr";
    p.className = "bad";
    host.append(p);
  }
  p.textContent = message;
}

function clearErr() {
  const p = $("#rpSlicerErr");
  if (p) p.remove();
}

function handoff(rid) {
  const remembered = reuseRepair(readFlow(sessionStorage), rid);
  const fd = new FormData();
  fd.append("beginner", beginner() ? "true" : "false");
  if (remembered) fd.append("edit", remembered);
  return fetch("/api/repair/" + rid + "/slicer", { method: "POST", body: fd, credentials: "same-origin" })
    .then(async made => {
      const body = await made.json().catch(() => ({}));
      if (made.status === 409) {
        throw new Error(typeof body.message === "string" ? body.message : "Your recent builds are full. Delete one on Account, then try again.");
      }
      if (!made.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The FDM Slicer could not open that file.");
      if (!slicerUrlForNewProject(body.id)) throw new Error("The FDM Slicer did not return a project.");
      const had = repairId === rid ? editId : "";
      rememberRepair(sessionStorage, rid, body.id);
      if (repairId === rid) {
        editId = body.id;
        const note = $("#rpNext");
        if (note) {
          note.textContent = had && had !== body.id
            ? "The earlier project for this repair is gone. This is a new project from the repaired file. The file you uploaded stays as it was."
            : nextCopy(true);
        }
        document.dispatchEvent(new CustomEvent("zeim:flow"));
      }
      return body;
    });
}

function ensureProject() {
  const rid = repairId;
  if (!rid) return Promise.reject(new Error("Repair a file first."));
  if (opening && opening.rid === rid) return opening.promise;
  const promise = handoff(rid).finally(() => {
    if (opening && opening.promise === promise) opening = null;
  });
  opening = { rid, promise };
  return promise;
}

function follow(plan) {
  if (!plan || plan.stay) return;
  if (plan.open === "edit" && plan.id) {
    location.href = "/?edit=" + plan.id + (plan.hash || "#slicer");
    return;
  }
  if (plan.url) { location.href = plan.url; return; }
  if (plan.hash) location.href = "/" + (plan.hash.startsWith("#") ? plan.hash : "#" + plan.hash);
}

async function go(plan) {
  if (!plan || plan.stay) return;
  let next = plan;
  const needsProject = plan.stage === "slice" || plan.stage === "prepare" || plan.stage === "design";
  if (needsProject && repairId) {
    const rid = repairId;
    try { await ensureProject(); }
    catch (err) { showErr(err.message || "The FDM Slicer could not open that file."); return; }
    if (repairId !== rid) return;
    next = planHop(plan.stage, flowContext());
  }
  follow(next);
}

async function openSlicer() {
  const btn = $("#rpOpenSlicer");
  if (btn) btn.disabled = true;
  clearErr();
  const rid = repairId;
  try {
    const body = await ensureProject();
    if (repairId !== rid) { if (btn) btn.disabled = false; return; }
    const url = slicerUrlForNewProject(body.id);
    if (!url) throw new Error("The FDM Slicer did not return a project.");
    location.href = url;
  } catch (err) {
    if (btn) btn.disabled = false;
    showErr(err.message || "The FDM Slicer could not open that file.");
  }
}

$("#rpFile").onchange = () => {
  const f = $("#rpFile").files[0];
  $("#rpName").textContent = f ? `${f.name} · ${(f.size / 2 ** 20).toFixed(1)} MB` : "";
  $("#rpGo").disabled = !f;
};

$("#rpForm").onsubmit = async e => {
  e.preventDefault();
  const f = $("#rpFile").files[0];
  if (!f) return;
  const out = $("#rpOut");
  if (f.size > 500 * 1024 * 1024) {
    out.innerHTML = `<p class="bad">That file is over 500 MB. Try a smaller one, or simplify it first.</p>`;
    return;
  }
  out.innerHTML = "<p>Repairing… big files can take a minute.</p>";
  $("#rpGo").disabled = true;
  repairId = "";
  editId = "";
  try {
    const fd = new FormData();
    fd.append("file", f);
    const r = await fetch("/api/repair", { method: "POST", body: fd });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "That file couldn't be repaired.");
    repairId = j.id || "";
    editId = reuseRepair(readFlow(sessionStorage), repairId);
    const b = j.before, a = j.after, x = j.fixed;
    const rows = [["Watertight", yn(b.watertight), yn(a.watertight)], ["Triangles", b.triangles, a.triangles],
      ["Open (hole) edges", b.boundary_edges, a.boundary_edges], ["Non-manifold edges", b.nonmanifold_edges, a.nonmanifold_edges],
      ["Separate shells", b.shells ?? "?", a.shells ?? "?"], ["Volume (mm³)", b.volume_mm3 ?? "–", a.volume_mm3 ?? "–"]];
    const fx = [["Hole edges closed", x.hole_edges_closed], ["Flipped triangles turned outward", x.flipped_triangles_reoriented],
      ["Duplicate triangles removed", x.duplicate_triangles], ["Zero-area triangles removed", x.degenerate_triangles],
      ["Loose debris pieces removed", x.debris_shells_removed], ["Non-manifold edges fixed", x.nonmanifold_edges_fixed]];
    out.innerHTML = `<h2>${a.watertight ? "✔ Repaired: watertight" : "Partly repaired"}</h2>
      <p><button type="button" class="btn big primary rp-open" id="rpOpenSlicer">Open in the FDM Slicer</button></p>
      <p class="help" id="rpNext">${esc(nextCopy(!!editId))}</p>
      <a class="btn big rp-dl" href="${esc(j.download_url)}" download="${esc(j.filename)}">Download ${esc(j.filename)}</a>
      <table class="rp-t"><thead><tr><th scope="col"></th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>
      ${rows.map(([k, p, q]) => `<tr><th scope="row">${k}</th><td>${esc(p)}</td><td>${esc(q)}</td></tr>`).join("")}</tbody></table>
      <ul class="rp-fx">${fx.map(([k, v]) => `<li>${k}: <b>${esc(v)}</b></li>`).join("")}</ul>
      ${(j.warnings || []).map(w => `<p class="help">${esc(w)}</p>`).join("")}
      ${(j.notes || []).map(n => `<p class="help rp-note" role="note">${esc(n.text)} <button type="button" class="link rp-note-x" aria-label="Dismiss note">Dismiss</button></p>`).join("")}`;
    out.querySelectorAll(".rp-note-x").forEach(btn => btn.onclick = () => btn.parentElement.remove());
    const goSlicer = $("#rpOpenSlicer");
    if (goSlicer) goSlicer.onclick = () => { openSlicer(); };
    document.dispatchEvent(new CustomEvent("zeim:flow"));
  } catch (err) {
    out.innerHTML = `<p class="bad">${esc(err.message)}</p>`;
  } finally {
    $("#rpGo").disabled = !$("#rpFile").files[0];
  }
};

bindFlow(flowContext, go);
