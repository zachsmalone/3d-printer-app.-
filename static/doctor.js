/* Failure photo doctor (Smart Fix page): pick what went wrong and/or describe it, optionally add a photo, get fixes in
   plain words with the real PrusaSlicer setting names. Nothing changes by itself: "Use in my next slice" asks first
   (before -> after), then the Slicer panel shows the change with an Undo. */
import { api, esc, $, $$, askConfirm, toast } from "/static/app.js";
import { P, loadCatalog, troubleshootingPrinterLabel } from "/static/printer.js";

const KEY = "zeim.smartfix.apply";
let PROBS = null;

function fixHTML(f, pi, fi) {
  const tag = !f.slicer_setting ? `<span class="pill">On the printer</span>` : f.verified ? "" : `<span class="pill warn">Not verified</span>`;
  const btn = f.apply ? `<button type="button" class="btn" data-apply="${pi}:${fi}">Use in my next slice (${esc(String(f.apply.from))} → ${esc(String(f.apply.to))}${esc(f.apply.unit ? " " + f.apply.unit : "")})</button>` : "";
  return `<li><p>${esc(f.plain)} ${tag}</p><p class="help">${esc(f.where)}</p>${btn}</li>`;
}

function render(r) {
  const out = $("#docOut");
  if (!r.matched) { out.innerHTML = `<p role="status">${esc(r.help)}</p>`; return; }
  out.innerHTML = `<p class="help" role="status">${esc(r.printer_honesty || "")} ${esc(r.estimate_note)}${r.photo?.note ? " " + esc(r.photo.note) : ""}</p>` +
    r.problems.map((p, pi) => `<section class="docfix" aria-labelledby="dp_${pi}"><h3 id="dp_${pi}">${esc(p.name)}</h3>
      <p class="help">Looks like: ${esc(p.symptoms.join(", "))}.</p>${p.printer_note ? `<p class="help">Your printer: ${esc(p.printer_note)}</p>` : ""}
      <ul>${p.fixes.map((f, fi) => fixHTML(f, pi, fi)).join("")}</ul></section>`).join("") +
    `<p class="help">Change one thing, print a small test (try the Calibration wizard above), then change the next.</p>`;
  out.querySelectorAll("[data-apply]").forEach(b => b.onclick = async () => {
    const [pi, fi] = b.dataset.apply.split(":").map(Number), a = r.problems[pi].fixes[fi].apply;
    const unit = a.unit ? " " + a.unit : "";
    const yes = await askConfirm({ title: "Change this setting?", danger: false, okLabel: "Yes, use it",
      message: `Change ${a.label} from ${a.from}${unit} to ${a.to}${unit} for your next slice? ZEIM won't change anything else. You can undo it in the Slicer.` });
    if (!yes) return;
    const pend = JSON.parse(sessionStorage.getItem(KEY) || "{}");
    pend[a.field] = { to: a.to, from: a.from, label: a.label, unit: a.unit };
    sessionStorage.setItem(KEY, JSON.stringify(pend));
    b.disabled = true; b.textContent = `Will use ${a.to}${unit} in your next slice`;
    toast?.(`Saved for your next slice: ${a.label} ${a.to}${unit}.`);
  });
}

async function go() {
  const fd = new FormData(), picked = $$("#docSyms input:checked").map(x => x.value), f = $("#docPhoto").files[0];
  fd.append("problems", picked.join(",")); fd.append("text", $("#docText").value);
  if (f) { fd.append("photo", f); fd.append("photo_ack", $("#docAck").checked); }
  if (P.chosen) { fd.append("printer_id", P.pref.printer_id); if (P.pref.nozzle) fd.append("nozzle", P.pref.nozzle); }
  fd.append("material", $("#docMat").value);
  $("#docOut").innerHTML = `<p class="help">Looking…</p>`;
  try { render(await api("/api/doctor/diagnose", { method: "POST", body: fd })); }
  catch (e) { $("#docOut").innerHTML = `<p class="help warn" role="alert">${esc(e.message)}</p>`; }
}

async function openDoctor() {
  $("#docBox").hidden = false;
  if (!PROBS) {
    try { await loadCatalog(); PROBS = (await api("/api/doctor/problems")).problems; }
    catch (e) { $("#docForm").innerHTML = `<p class="help warn">${esc(e.message)}</p>`; return; }
    $("#docSyms").innerHTML = `<legend>What went wrong? <em>pick any</em></legend>` +
      PROBS.map(p => `<label title="${esc(p.symptoms.join(", "))}"><input type="checkbox" value="${esc(p.id)}"> ${esc(p.name)}</label>`).join("");
    $("#docMat").innerHTML = Object.keys(P.cat.materials).map(m => `<option>${esc(m)}</option>`).join("");
    $("#docPrinter").textContent = troubleshootingPrinterLabel();
    $("#docPhoto").onchange = () => {
      const f = $("#docPhoto").files[0], img = $("#docPrev");
      if (img.src) URL.revokeObjectURL(img.src);
      img.hidden = !f; if (f) { img.src = URL.createObjectURL(f); img.alt = "Your photo of the failed print"; }
      $("#docAckF").hidden = !f;
    };
    $("#docGo").onclick = go;
  }
  $("#docH").scrollIntoView?.({ block: "start" }); $("#docH").focus();
}

const b = $("#docOpen");
if (b) b.onclick = openDoctor;
if (location.hash === "#smartfix/doctor") setTimeout(openDoctor, 300);
addEventListener("hashchange", () => { if (location.hash === "#smartfix/doctor") openDoctor(); });
document.addEventListener("zeim:printer", () => { if ($("#docPrinter")) $("#docPrinter").textContent = troubleshootingPrinterLabel(); });
