// Repair page (POST /api/repair): pick a file, show the before/after report, offer the fixed file.
const $ = s => document.querySelector(s), esc = t => String(t ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const yn = b => b ? "yes" : "no";
$("#rpFile").onchange = () => { const f = $("#rpFile").files[0]; $("#rpName").textContent = f ? `${f.name} · ${(f.size / 2 ** 20).toFixed(1)} MB` : ""; $("#rpGo").disabled = !f; };
$("#rpForm").onsubmit = async e => {
  e.preventDefault(); const f = $("#rpFile").files[0]; if (!f) return;
  const out = $("#rpOut"); out.innerHTML = "<p>Repairing… big files can take a minute.</p>"; $("#rpGo").disabled = true;
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
      <p class="help">The file is kept for one hour. Check it in your slicer before printing.</p>`;
  } catch (err) { out.innerHTML = `<p class="bad">${esc(err.message)}</p>`; }
  finally { $("#rpGo").disabled = !$("#rpFile").files[0]; }
};
