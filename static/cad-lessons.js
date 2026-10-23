/* ZEIM CAD lessons (original code): short step-by-step lessons in a small card over the stage.
   Each step checks that it happened (new History steps since the step began, or a UI event), and can be
   skipped; the lesson can be closed any time. Progress stays in this browser (localStorage). */
const KEY = "zeim.cad.lessons";
const isShape = (kind, mode) => o => o.op === "cad_shape" && (!kind || o.params?.kind === kind) && (!mode || (o.params?.mode || "new") === mode);
export const LESSONS = [
  { id: "keychain", title: "Your first print: a keychain", mins: 3, steps: [
    { say: "Open Shapes.", tool: "shapes", done: c => c.tool === "shapes" || c.op(isShape()) },
    { say: "Pick Large, switch on Flat, then tap Cylinder. That's the tag.", tool: "shapes", done: c => c.op(isShape("cylinder")) },
    { say: "Switch on “Hole near the edge”, then tap Hole. That's where the key ring goes.", tool: "shapes", done: c => c.op(isShape(null, "cut")) },
    { say: "Open Text, tap “Pick spot on model”, tap the top of the tag, then Apply. Short words print best.", tool: "text", done: c => c.op(o => o.op === "cad_text") },
    { say: "Open Export ▾ and download the STL, or send it to the slicer. That's it.", target: "#cwExport", done: c => c.ev("export") },
  ] },
  { id: "combine", title: "Combine shapes", mins: 2, steps: [
    { say: "Open Shapes and tap Cube.", tool: "shapes", done: c => c.op(isShape("box")) },
    { say: "Set “Adds as” to Join, then tap Sphere. It lands on top and fuses into one piece.", tool: "shapes", done: c => c.op(isShape(null, "join")) || c.op(o => o.op === "body_boolean") },
    { say: "Each shape is a step in History. Tap a step there to change its size; Undo works too.", target: "#tabHist" },
  ] },
  { id: "hole", title: "Cut a hole", mins: 2, steps: [
    { say: "Open Shapes and tap Cube.", tool: "shapes", done: c => c.op(isShape("box")) },
    { say: "Set “Adds as” to Cut out, then tap Cylinder. That makes a pocket in the top.", tool: "shapes", done: c => c.op(isShape(null, "cut")) },
    { say: "Now tap Hole: a small round hole that goes all the way through.", tool: "shapes", done: c => c.op(isShape("cylinder", "cut")) },
  ] },
  { id: "box", title: "A box with a lid", mins: 3, steps: [
    { say: "Open Shapes, pick Large (Flat off) and tap Cube.", tool: "shapes", done: c => c.op(o => isShape("box")(o) && o.params.dims?.size?.[2] >= 30) },
    { say: "Set “Adds as” to Cut out, pick Medium and tap Cube. That hollows out the inside.", tool: "shapes", done: c => c.op(isShape("box", "cut")) },
    { say: "Set “Adds as” to New piece, pick Large, switch on Flat and tap Cube. That's the lid, printed next to the box.", tool: "shapes", done: c => c.op(o => isShape("box", "new")(o) && o.params.dims?.size?.[2] <= 5) },
    { say: "Tip: a lid that sits on top is the easy version. For one that stays put, a lip a little smaller than the opening helps; how much depends on your printer, so a small test print is worth it." },
  ] },
  { id: "prep", title: "Get it ready to print", mins: 2, steps: [
    { say: "Tap Fit to see the whole design.", target: "#cwHome", done: c => c.ev("fit") },
    { say: "Shapes from the palette already sit flat on the bed. If a Print tip appears, have a read; you can dismiss it." },
    { say: "Open Export ▾. Download the STL or 3MF, or open it in the slicer to pick your printer and settings.", target: "#cwExport", done: c => c.ev("export") },
  ] },
];

export function initLessons({ S, setTool, LS, $, esc }) {
  const card = $("#cwLesson"), btn = $("#cwLearn");
  let st = {}; try { st = JSON.parse(LS?.getItem(KEY) || "{}") || {}; } catch { st = {}; }
  st.done ||= {};
  let base = 0, evs = new Set(), mode = "closed", mini = false;
  const save = () => { try { LS?.setItem(KEY, JSON.stringify(st)); } catch { } };
  const head = () => S.scene?.head ?? 0;
  const cur = () => st.cur && LESSONS.find(l => l.id === st.cur.id);
  const ctx = () => ({ tool: S.tool, ev: e => evs.has(e), op: f => (S.scene?.ops || []).some(o => o.i > base && o.i <= head() && f(o)) });
  const unpulse = () => document.querySelectorAll(".cw-pulse").forEach(e => e.classList.remove("cw-pulse"));
  function pulse(step) {
    unpulse();
    const el = step.target ? $(step.target) : step.tool ? $(`#cwRail [data-tool=${step.tool}]`) : null;
    el?.classList.add("cw-pulse");
  }
  function beginStep() { base = head(); evs = new Set(); }
  const phone = matchMedia("(max-width:820px)");
  function place() { const home = phone.matches ? $("#cwSide") : $("#cwStage"); if (card.parentElement !== home) home.prepend(card); }
  phone.addEventListener?.("change", place);
  function draw() {
    unpulse(); place(); btn.setAttribute("aria-pressed", mode !== "closed");
    card.hidden = mode === "closed"; card.classList.toggle("mini", mini);
    if (mode === "list") {
      card.innerHTML = `<div class="cw-lhead"><b>Lessons</b><button type="button" class="cw-lx" data-l="close" aria-label="Close lessons">✕</button></div>
        <div class="cw-lbody"><p class="help">Short and hands-on. Skip any step, stop any time; your place is kept on this device.</p>
        <ul class="cw-llist">${LESSONS.map(l => `<li><button type="button" data-start="${l.id}"><span>${st.done[l.id] ? "✓ " : ""}${esc(l.title)}</span><small>${l.steps.length} steps · about ${l.mins} min</small></button></li>`).join("")}</ul></div>`;
    } else if (mode === "step") {
      const L = cur(), i = st.cur.step, step = L.steps[i];
      card.innerHTML = `<div class="cw-lhead"><button type="button" class="cw-lt" data-l="mini" aria-expanded="${!mini}" aria-label="${mini ? "Show" : "Hide"} the lesson step"><b>${esc(L.title)}</b><small>Step ${i + 1} of ${L.steps.length}</small></button>
        <button type="button" class="cw-lx" data-l="exit" aria-label="Exit the lesson">✕</button></div>
        <div class="cw-lbody"><p class="cw-lsay">${esc(step.say)}</p><div class="cw-row">
          ${step.tool || step.target ? `<button type="button" data-l="show">Show me</button>` : ""}
          <button type="button" ${step.done ? "" : 'class="primary"'} data-l="next">${step.done ? "Skip" : i + 1 < L.steps.length ? "Next" : "Finish"}</button></div></div>`;
      pulse(step);
    } else if (mode === "finished") {
      card.innerHTML = `<div class="cw-lhead"><b>Nice work</b><button type="button" class="cw-lx" data-l="close" aria-label="Close lessons">✕</button></div>
        <div class="cw-lbody"><p class="cw-lsay">${esc(cur()?.title || "Lesson")} done.</p><div class="cw-row"><button type="button" class="primary" data-l="list">More lessons</button></div></div>`;
    }
  }
  function start(id) { st.cur = { id, step: 0 }; save(); mode = "step"; mini = false; beginStep(); draw(); }
  function advance() {
    const L = cur(); if (!L) return;
    if (st.cur.step + 1 >= L.steps.length) { st.done[L.id] = true; save(); mode = "finished"; draw(); st.cur = null; save(); return; }
    st.cur.step++; save(); beginStep(); draw();
  }
  function tick() {
    if (mode !== "step") return;
    const step = cur()?.steps[st.cur.step];
    if (step?.done && step.done(ctx())) advance();
  }
  card.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.start) return start(b.dataset.start);
    const a = b.dataset.l;
    if (a === "close") { mode = "closed"; draw(); }
    else if (a === "exit") { st.cur = null; save(); mode = "closed"; draw(); }
    else if (a === "list") { mode = "list"; draw(); }
    else if (a === "mini") { mini = !mini; draw(); }
    else if (a === "next") advance();
    else if (a === "show") { const step = cur().steps[st.cur.step]; if (step.tool && S.tool !== step.tool) setTool(step.tool); else if (step.target) $(step.target).focus(); pulse(step); tick(); }
  });
  btn.onclick = () => { mode = mode === "closed" ? (cur() ? "step" : "list") : "closed"; if (mode === "step") beginStep(); draw(); };
  $("#cwRail").addEventListener("click", () => setTimeout(tick, 0));
  if (cur()) { mode = "step"; mini = true; beginStep(); draw(); }   // resume where you left off, folded out of the way
  return { tick, event(e) { evs.add(e); tick(); }, start, get state() { return { mode, mini, ...st }; } };
}
