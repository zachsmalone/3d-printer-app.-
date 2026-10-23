/* UI6 (approved 2026-10): settings search + Recommended/Advanced switch, context-aware floating toolbar over the 3D views.
   Pure DOM; proxies clicks to the existing buttons, so the 3D views still render only on demand. Own code, no third-party. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const ico = n => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-${n}"/></svg>`;
  const vis = el => !!el && !el.hidden && !el.closest("[hidden]") && el.getClientRects().length > 0;

  // header height for the full-height desktop layout
  const top = () => { const t = $(".topbar"); if (t) document.documentElement.style.setProperty("--ui6-top", t.offsetHeight + "px"); };
  addEventListener("resize", top); top();

  /* ---- 2. settings search ---- */
  let n = 0;
  function addSearch(host, before, label) {
    if (!host || host.dataset.ui6s) return; host.dataset.ui6s = "1";
    const id = "setq" + (++n), box = document.createElement("div");
    box.className = "setsearch"; box.setAttribute("role", "search");
    box.innerHTML = `<label class="sr-only" for="${id}">${label}</label><input type="search" id="${id}" placeholder="${label}" autocomplete="off" enterkeyhint="search"><span class="setcount" aria-live="polite"></span>`;
    (before || host).before(box);
    const none = document.createElement("p"); none.className = "setnone"; none.hidden = true; none.textContent = "No settings match. Try another word.";
    box.after(none);
    const q = box.querySelector("input"), cnt = box.querySelector(".setcount");
    q.addEventListener("input", () => {
      const t = q.value.trim().toLowerCase();
      const items = $$(".field, details.tool, .bigtool", host);
      let shown = 0;
      items.forEach(el => {
        const hit = !t || el.textContent.toLowerCase().includes(t) || $$("input,select", el).some(i => (i.name || i.id || "").toLowerCase().includes(t));
        el.classList.toggle("ui6-hide", !hit); if (hit && !el.closest(".ui6-hide")) shown++;
        if (hit && t && el.tagName === "DETAILS") el.open = true;
      });
      $$("details", host).forEach(d => {
        if (d.classList.contains("tool")) return;
        const any = $$(".field", d).some(f => !f.classList.contains("ui6-hide"));
        d.classList.toggle("ui6-hide", !!t && !any); if (t && any) d.open = true;
      });
      cnt.textContent = t ? `${shown} match${shown === 1 ? "" : "es"}` : "";
      none.hidden = !t || shown > 0;
    });
  }
  // Studio: Advanced settings
  const ex = $("#expertOpts"), bo = $("#beginnerOpts"), mode = $("#modeSel");
  if (ex) {
    const h = document.createElement("h3"); h.className = "sethead"; h.textContent = "Advanced settings"; ex.prepend(h);
    addSearch(ex, h.nextSibling, "Search settings");
    const back = document.createElement("button"); back.type = "button"; back.className = "linkbtn"; back.id = "toRecommended"; back.textContent = "Back to recommended settings";
    ex.append(back);
    back.onclick = () => { mode.value = "beginner"; mode.dispatchEvent(new Event("change", { bubbles: true })); };
  }
  if (bo) {
    const a = document.createElement("button"); a.type = "button"; a.className = "linkbtn"; a.id = "toAdvanced"; a.textContent = "Show advanced settings";
    bo.append(a);
    a.onclick = () => { mode.value = "expert"; mode.dispatchEvent(new Event("change", { bubbles: true })); setTimeout(() => $("#expertOpts input[type=search]")?.focus(), 50); };
  }
  // Print dialog: built-in slicer settings
  const sh = [...$$("h4")].find(h => /Slice here/.test(h.textContent));
  if (sh && sh.nextElementSibling) addSearch(sh.nextElementSibling, null, "Search slicer settings");
  // Edit: tool panel + slicer panel are rendered later by edit.js
  const later = () => { const ep = $("#editPanel"); if (ep && ep.children.length) addSearch(ep, ep.firstElementChild, "Search tools and settings");
    const sp = $("#slicePanel"); if (sp && sp.querySelector(".field")) addSearch(sp, sp.querySelector(".field")?.closest(".grid2,.grid3,.field"), "Search slicer settings"); };
  new MutationObserver(later).observe(document.body, { childList: true, subtree: true }); later();

  /* ---- 3. context-aware floating toolbar ---- */
  function bar(viewer, compute) {
    if (!viewer) return;
    const el = document.createElement("div"); el.className = "ctxbar"; el.setAttribute("role", "toolbar"); el.hidden = true;
    el.id = viewer.id + "Ctx"; viewer.after(el);   // a sibling, not a child: #viewer is role=img (no nested interactive content); CSS pulls it up over the view
    let sig = "";
    const upd = () => {
      const { label, acts } = compute(); const live = acts.filter(a => a.el && !a.el.disabled && (a.always || vis(a.el)));
      const s = label + "|" + live.map(a => a.t).join(","); if (s === sig) return; sig = s;
      el.setAttribute("aria-label", label ? `Actions: ${label}` : "Actions");
      el.innerHTML = (label ? `<span class="ctxlbl">${label}</span>` : "") + live.map((a, i) => `<button type="button" data-i="${i}" class="${a.pri ? "pri" : ""}" aria-label="${a.t}" title="${a.t}">${ico(a.i)}<span>${a.t}</span></button>`).join("");
      $$("button", el).forEach(b => b.onclick = () => live[+b.dataset.i].el.click());
      el.hidden = !live.length;
    };
    new MutationObserver(() => requestAnimationFrame(upd)).observe(document.body, { attributes: true, attributeFilter: ["hidden", "disabled", "class"], subtree: true, childList: true });
    document.addEventListener("change", upd); upd();
  }
  const styleName = () => { const r = $("input[name=style]:checked"); return r ? r.closest("label")?.querySelector("b")?.textContent || "" : ""; };
  bar($("#viewer"), () => {
    if (vis($("#busy"))) return { label: "Making…", acts: [] };
    if (!$("#result")?.hidden) return { label: styleName(), acts: [
      { t: "Reset view", i: "compass", el: $("#vReset"), always: true },
      { t: "Wireframe", i: "grid", el: $("#vWire"), always: true },
      { t: "Light", i: "bulb", el: $("#vLight") },
      { t: "Edit", i: "pencil", el: $("#btnEditThis"), always: true },
      { t: "Print", i: "printer", el: $("#btnPrint"), always: true },
      { t: "Save", i: "download", el: $("#btnSendSheet"), pri: true, always: true }] };
    return { label: styleName(), acts: [
      { t: "Take a photo", i: "camera", el: $("#sTake") },
      { t: "Choose a photo", i: "image", el: $("#sChoose"), pri: !$("#dropPreview") || $("#dropPreview").hidden, always: true },
      { t: "Make model", i: "sparkle", el: $("#btnBuild"), pri: true, always: true }] };
  });
  bar($("#editViewer"), () => {
    if (vis($("#editBusy"))) return { label: "Working…", acts: [] };
    if ($("#editVtools")?.hidden) return { label: "", acts: [{ t: "Choose a model", i: "upload", el: $("#editChooseModel"), pri: true, always: true }] };
    const tool = $(".bigtool.on b")?.textContent;
    return { label: tool ? "Tool: " + tool : "Edit", acts: [
      { t: "Undo", i: "repeat", el: $("#eUndo"), always: true },
      { t: "Measure", i: "ruler", el: $("#eMeasure"), always: true },
      { t: "Reset view", i: "compass", el: $("#eReset"), always: true },
      { t: "Print", i: "printer", el: $("#editPrint"), always: true },
      { t: "Save", i: "download", el: $("#editSend"), pri: true, always: true }] };
  });
})();
