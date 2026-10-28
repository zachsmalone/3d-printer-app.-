// Repair page (POST /api/repair): pick a file, show the before/after report, offer the fixed file.
// Continue opens a slicer project from the repaired file. That project is a copy of the download.
import { slicerUrlForNewProject } from "/static/project-flow.js";
const $ = s => document.querySelector(s), esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const yn = b => b ? "yes" : "no";
$("#rpFile").onchange = () => { const f = $("#rpFile").files[0]; $("#rpName").textContent = f ? `${f.name} · ${(f.size / 2 ** 20).toFixed(1)} MB` : ""; $("#rpGo").disabled = !f; };
$("#rpForm").onsubmit = async e => {
  e.preventDefault(); const f = $("#rpFile").files[0]; if (!f) return;
  const out = $("#rpOut");
  if (f.size > 500 * 1024 * 1024) { out.innerHTML = `<p class="bad">That file is over 500 MB. Try a smaller one, or simplify it first.</p>`; return; }
  out.innerHTML = "<p>Repairing… big files can take a minute.</p>"; $("#rpGo").disabled = true;
  try {
    const fd = new FormData(); fd.append("file", f);
    const r = await fetch("/api/repair", { method: "POST", body: fd }); const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "That file couldn't be repaired.");
    const b = j.before, a = j.after, x = j.fixed;
    const rows = [["Watertight", yn(b.watertight), yn(a.watertight)], ["Triangles", b.triangles, a.triangles],
      ["Open (hole) edges", b.boundary_edges, a.boundary_edges], ["Non-manifold edges", b.nonmanifold_edges, a.nonmanifold_edges],
      ["Separate shells", b.shells ?? "?", a.shells ?? "?"], ["Volume (mm³)", b.volume_mm3 ?? "–", a.volume_mm3 ?? "–"]];
    const fx = [["Hole edges closed", x.hole_edges_closed], ["Flipped triangles turned outward", x.flipped_triangles_reoriented],
      ["Duplicate triangles removed", x.duplicate_triangles], ["Zero-area triangles removed", x.degenerate_triangles],
      ["Loose debris pieces removed", x.debris_shells_removed], ["Non-manifold edges fixed", x.nonmanifold_edges_fixed]];
    out.innerHTML = `<h2>${a.watertight ? "✔ Repaired: watertight" : "Partly repaired"}</h2>
      <a class="btn big primary rp-dl" href="${esc(j.download_url)}" download="${esc(j.filename)}">Download ${esc(j.filename)}</a>
      <table class="rp-t"><thead><tr><th scope="col"></th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>
      ${rows.map(([k, p, q]) => `<tr><th scope="row">${k}</th><td>${esc(p)}</td><td>${esc(q)}</td></tr>`).join("")}</tbody></table>
      <ul class="rp-fx">${fx.map(([k, v]) => `<li>${k}: <b>${esc(v)}</b></li>`).join("")}</ul>
      ${(j.warnings || []).map(w => `<p class="help">${esc(w)}</p>`).join("")}
      ${(j.notes || []).map(n => `<p class="help rp-note" role="note">${esc(n.text)} <button type="button" class="link rp-note-x" aria-label="Dismiss note">Dismiss</button></p>`).join("")}
      <p class="help">The repaired file is kept for one hour. Opening it in the FDM Slicer starts a new project from that file. The file you uploaded stays as it was.</p>
      <p><button type="button" class="btn" id="rpOpenSlicer">Open in the FDM Slicer</button></p>`;
    out.querySelectorAll(".rp-note-x").forEach(b => b.onclick = () => b.parentElement.remove());
    const goSlicer = $("#rpOpenSlicer");
    if (goSlicer) goSlicer.onclick = async () => {
      goSlicer.disabled = true;
      try {
        const fileRes = await fetch(j.download_url, { credentials: "same-origin" });
        if (!fileRes.ok) throw new Error("That repaired file has expired. Repair it again.");
        const blob = await fileRes.blob();
        const fd = new FormData();
        fd.append("file", new File([blob], j.filename || "repaired.stl", { type: blob.type || "model/stl" }));
        fd.append("units", "mm");
        const made = await fetch("/api/edit/new", { method: "POST", body: fd, credentials: "same-origin" });
        const body = await made.json().catch(() => ({}));
        if (!made.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The FDM Slicer could not open that file.");
        const url = slicerUrlForNewProject(body.id);
        if (!url) throw new Error("The FDM Slicer did not return a project.");
        location.href = url;
      } catch (err) {
        goSlicer.disabled = false;
        const p = document.createElement("p");
        p.className = "bad";
        p.textContent = err.message;
        goSlicer.after(p);
      }
    };
  } catch (err) { out.innerHTML = `<p class="bad">${esc(err.message)}</p>`; }
  finally { $("#rpGo").disabled = !$("#rpFile").files[0]; }
};
