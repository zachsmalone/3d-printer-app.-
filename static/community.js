import { S, api, toast, inlineMsg, clearInline, askConfirm, $, $$, esc, MODE_LABEL, ago, applyMode, loadHistory } from "/static/app.js";
import { P, loadCatalog, pickerHTML, wirePicker, readPicker, savePref, badgeHTML, checkShowcase } from "/static/printer.js";

const J = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
let CFG = null, ME = null, shTab = "trending";

/* ---------- config / branding (names come from app/branding.py) ---------- */
async function init() {
  CFG = await api("/api/config");
  { const tm = document.getElementById("accTestingMode"); if (tm) tm.hidden = !CFG.testing_mode; }
  document.title = CFG.product;
  $$("[data-sec]").forEach(e => e.textContent = CFG.sections[e.dataset.sec] || e.textContent);
  $("#logoImg").alt = CFG.product;
  $("#shTabs").innerHTML = Object.entries(CFG.showcase_tabs).map(([k, v]) => `<button type="button" data-tab="${k}" class="${k === shTab ? "on" : ""}" aria-pressed="${k === shTab}">${esc(v)}</button>`).join("");
  await refreshMe();
  route();
  window.__zeimStarted = true;                 // static/boot.js shows a visible error if this never happens
}
async function refreshMe() {
  ME = await api("/api/me");
  $("#btnAccount .lbl").textContent = ME.signed_up ? ME.display_name : "Sign up";
  $("#btnAccount").setAttribute("aria-label", ME.signed_up ? "Account: " + ME.display_name : "Account: sign up");
  document.body.dataset.links = ME.send?.links ? "1" : "0";     // the server decides who can use Print / slicer links; the page only reflects it
  document.body.dataset.role = ME.send?.role || "";
  document.dispatchEvent(new CustomEvent("zeim:me", { detail: ME }));
}

/* ---------- views ---------- */
const VIEWS = { showcase: "#viewShowcase", slicer: "#viewEdit", torchc0: "#viewTorch", cad: "#viewCad", lithophane: "#viewCreate", smartfix: "#viewFix", ai3d: "#viewAi3d", account: "#viewAccount", learn: "#viewLearn" };
const ALIAS = { "": "showcase", resin: "torchc0", fdm: "slicer", edit: "slicer", create: "lithophane", studio: "lithophane", "2d3d": "ai3d" };
function show(view) {
  const tab = view;   // P10: Learn has its own nav button
  $$("#mainNav button").forEach(b => { b.classList.toggle("on", b.dataset.view === tab); if (b.dataset.view === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  Object.entries(VIEWS).forEach(([k, sel]) => { const m = $(sel); if (m) m.hidden = k !== view; });
  document.body.dataset.view = view;
  if (view === "slicer") document.dispatchEvent(new CustomEvent("zeim:edit-shown"));
  if (view === "torchc0") document.dispatchEvent(new CustomEvent("zeim:torchc0-shown"));
  if (view === "showcase") loadShowcase();
  if (view === "learn") loadLearn();
  if (view === "ai3d") document.dispatchEvent(new CustomEvent("zeim:ai3d-shown"));
}
$$("#mainNav button").forEach(b => b.onclick = () => { location.hash = b.dataset.view; });
const TOOLWORDS = { smartorient: "Smart orient", cut: "Cut", orient: "Rotate", text: "Text", repair: "Repair", hollow: "Hollow", simplify: "Repair" };
function openTool(t) {   // Smart Fix / CAD shortcuts: open the matching tool in the editor once a model is loaded
  const w = TOOLWORDS[t]; if (!w) return;
  const d = [...document.querySelectorAll("#viewEdit details.tool")].find(x => x.offsetParent && x.querySelector("summary")?.textContent.includes(w));
  if (d && d.offsetParent) { d.open = true; d.scrollIntoView?.({ block: "nearest" }); return; }
  const b = document.querySelector(`#viewEdit [data-big="${t}"]:not(:disabled)`); if (b && !b.classList.contains("on")) b.click();
}
let toolDone = "";
document.addEventListener("zeim:edit-loaded", () => { const h = location.hash.split("/"); if (h[1] && toolDone !== location.hash) { toolDone = location.hash; openTool(h[1]); } });
function route() {
  const h = location.hash.replace("#", "").split("/");
  const v = ALIAS[h[0]] ?? (VIEWS[h[0]] ? h[0] : "showcase");
  show(v);
  if (v === "lithophane" && h[0] === "lithophane") { const r = document.querySelector('#modeCards input[value=lithophane]'); if (r && !r.checked) r.click(); }
  if (v === "slicer" && h[1]) setTimeout(() => openTool(h[1]), 200);
  if (h[0] === "learn" && h[1]) setTimeout(() => openLesson(h[1]), 150);
  if (h[0] === "u" && h[1]) setTimeout(() => openProfile(h[1]), 50);
  else if ($("#dlgProfile")?.open) $("#dlgProfile").close();          // leaving a profile link by tab closes the profile
  if (!(h[0] === "c" && h[1]) && $("#dlgCollection")?.open) $("#dlgCollection").close();
  if (h[0] === "c" && h[1]) setTimeout(() => openCollection(h[1]), 50);
  if (v === "account") { loadFavorites(); loadCollections(); }
  else if ($("#dlgCollection")?.open) $("#dlgCollection").close();
}
addEventListener("hashchange", route);

/* ---------- account ---------- */
$("#btnAccount").onclick = () => { renderAccount(); $("#dlgAccount").showModal(); };
function renderAccount() {
  /* Real auth (passkeys/email) renders the modern account dialog when mounted; the
     legacy cookie UI below is the fallback for when it is not. handles() is synchronous
     so a Promise can never hide the fallback. */
  if (window.ZeimAccount && window.ZeimAccount.handles(ME)) { window.ZeimAccount.render(ME); return; }
  if (!ME.signed_up) {
    $("#accBody").innerHTML = `<p class="help">Accounts are for adults 18 and over. An account lets you save your settings and share projects. You can build and learn in the ${esc(CFG.sections.learn)} without an account.</p>
      <div class="field"><label for="su_name">Display name (not your full name)</label><input id="su_name" maxlength="40"></div>
      <div class="field"><label for="su_user">Username <em>optional · this is the name your projects are credited to</em></label><input id="su_user" maxlength="18" autocomplete="off" autocapitalize="none" spellcheck="false">
        <small class="help">3 to 18 letters, numbers or underscores. Leave it empty and ZEIM makes you a friendly nickname you can change later. Not your real name, email or phone number.</small></div>
      <div class="field"><label for="su_dob">Date of birth <em>used only to confirm you are 18 or over; not kept if you are not</em></label><input id="su_dob" type="date"></div>
      <details class="su-printer"><summary>Your printer <em>optional</em></summary><div id="su_printer"><p class="help">Loading printers…</p></div></details>
      <button class="btn primary" id="su_go">Create account</button>
      <details class="recover"><summary>Signed out before? Get your account back with a recovery code</summary>
        <div class="field"><label for="rc_code">Recovery code</label><input id="rc_code" maxlength="40" autocomplete="off" autocapitalize="characters" spellcheck="false"></div>
        <button class="btn" id="rc_go">Get my account back</button></details>`;
    $("#rc_go").onclick = async () => {
      try {
        const r = await api("/api/me/recover", J("POST", { code: $("#rc_code").value }));
        $("#accBody").innerHTML = `<div class="calm" role="status" tabindex="-1"><p>Welcome back, <b>@${esc(r.username || "")}</b>.</p><p>Your new recovery code is <b class="code">${esc(r.recovery_code)}</b>. The old one no longer works. Write this one down and keep it like a password.</p><button class="btn primary" id="rc_done">Done</button></div>`;
        $("#accBody .calm").focus();
        $("#rc_done").onclick = () => location.reload();
      } catch (e) { inlineMsg($("#rc_go"), e.message); }
    };
    loadCatalog().then(() => { if ($("#su_printer")) { $("#su_printer").innerHTML = pickerHTML("su", P.pref, { optional: true }); wirePicker("su"); } }).catch(() => { });
    $("#su_go").onclick = async () => {
      const pick = $("#su_pr") ? readPicker("su") : null;
      try { ME = await api("/api/me/signup", J("POST", { display_name: $("#su_name").value, dob: $("#su_dob").value, username: $("#su_user").value.trim(), ...(pick || {}) })); if (pick) savePref(pick).catch(() => { }); await refreshMe(); renderAccount(); toast("Account created. Your username is @" + ME.username, "ok"); }
      catch (e) {
        if (e.status === 403 && /^Sorry, ZEIM accounts are for adults/.test(e.message)) {     // the 18+ refusal: a calm panel instead of an unchanged form
          $("#accBody").innerHTML = `<div class="calm" role="alert" tabindex="-1"><p>${esc(e.message)}</p><p class="help">You can still build and use the ${esc(CFG.sections.learn)} lessons without an account.</p></div>`;
          $("#accBody .calm").focus();
        } else inlineMsg($("#su_go"), e.message);
      }
    };
  } else {
    const r = ME.restrictions, pv = ME.privacy;
    const nextUn = ME.username_next_change ? new Date(ME.username_next_change).toLocaleDateString() : null;
    $("#accBody").innerHTML = `<p><b>${esc(ME.display_name)}</b> ${ME.suspended ? '<span class="pill">suspended</span>' : ""}</p>
      <h4>Your username</h4>
      <p>Credit for what you share goes to <b id="un_now">@${esc(ME.username || "")}</b>. Your email is never shown to anyone.</p>
      <div class="field"><label for="un_new">New username</label><input id="un_new" maxlength="18" autocomplete="off" autocapitalize="none" spellcheck="false" ${nextUn ? "disabled" : ""}>
        <small class="help" id="un_help">${nextUn ? "You can change your username again on " + esc(nextUn) + "." : "3 to 18 letters, numbers or underscores. You can change it once every 90 days. The old name stays saved for you, so nobody else can take it. Please don't use your real name."}</small></div>
      <div class="row"><button class="btn small" id="un_save" ${nextUn ? "disabled" : ""}>Change username</button><button class="btn small ghost" id="un_suggest" ${nextUn ? "disabled" : ""}>Suggest names</button></div>
      <div class="row" id="un_sugg"></div>
      <p class="help">Public page: <a href="/u/${ME.id}" target="_blank">/u/${ME.id}</a> (only if your profile is visible to the viewer)</p>
      <h4><svg class=i aria-hidden=true focusable=false><use href=#i-lock></use></svg> Privacy</h4>
      <div class="field"><label>Profile page</label><select id="pv_profile">${[["public", "Public"], ["followers", "Followers only"], ["private", "Private — only me"]].map(([v, t]) => `<option value="${v}" ${pv.profile === v ? "selected" : ""}${v !== "private" && ME.suspended ? " disabled" : ""}>${t}</option>`).join("")}</select></div>
      <div class="field"><label>Default for new builds &amp; projects</label><select id="pv_def">${[["private", "Private — only me"], ["followers", "Followers only"], ["public", "Public"]].map(([v, t]) => `<option value="${v}" ${pv.default_visibility === v ? "selected" : ""}${v !== "private" && ME.suspended ? " disabled" : ""}>${t}</option>`).join("")}</select></div>
      ${ME.suspended ? '<p class="help">This account is suspended, so everything stays <b>Private</b>. You can still make, edit and download your projects.</p>' : ""}
      <label class="inl"><input type="checkbox" id="pv_social" ${pv.social === "on" ? "checked" : ""}> Allow following (I can follow others and others can follow me)</label>
      <p class="help">Turning following <b>off</b> removes all your follows and followers immediately, hides follow buttons and follower counts for you, and turns “followers only” items into private ones. Everything starts Private; every build and project can be changed individually.</p>
      <div class="row"><button class="btn small" id="pv_save">Save privacy</button><button class="btn small ghost" id="pv_followers">My followers</button><button class="btn small ghost" id="pv_following" aria-expanded="false" aria-controls="pv_followingList">People I follow</button></div>
      <div id="pv_followingList" hidden></div>
      <ul class="help"><li>Direct messages from strangers: <b>off</b> (messaging between people: Coming soon)</li>
      <li>Social link-outs on your public profile: <b>${r.public_link_outs ? "shown (unverified)" : "hidden"}</b></li></ul>
      <p class="help">Add link-outs in Settings → Promote your accounts.</p>
      <h4>Sign out</h4><p class="help">Signing out makes this browser forget your account. Use it on a shared computer.</p>
      <button class="btn small" id="so_open">Sign out…</button>`;
    $("#so_open").onclick = () => openSignout();
    $("#un_save").onclick = async () => {
      try { const r = await api("/api/me/username", J("PUT", { username: $("#un_new").value.trim() })); await refreshMe(); renderAccount(); toast("Your username is now @" + r.username, "ok"); }
      catch (e) { inlineMsg($("#un_save").parentElement, e.message); }
    };
    $("#un_suggest").onclick = async () => {
      try { const r = await api("/api/me/username/suggest", J("POST", {})); $("#un_sugg").innerHTML = r.suggestions.map(n => `<button class="btn small ghost" data-un="${esc(n)}">${esc(n)}</button>`).join("");
        $("#un_sugg").querySelectorAll("[data-un]").forEach(b => b.onclick = () => { $("#un_new").value = b.dataset.un; $("#un_new").focus(); }); }
      catch (e) { inlineMsg($("#un_save").parentElement, e.message); }
    };
    $("#pv_save").onclick = async () => { try { await api("/api/me/privacy", J("PUT", { profile: $("#pv_profile").value, default_visibility: $("#pv_def").value, social: $("#pv_social").checked ? "on" : "off" })); await refreshMe(); renderAccount(); toast("Privacy saved", "ok"); } catch (e) { toast(e.message, "err"); } };
    // People I follow: only you see this list; Unfollow works even for an account that has since gone away
    const drawFollowing = async () => {
      const box = $("#pv_followingList"); let f;
      try { f = await api("/api/me/following"); } catch (e) { box.innerHTML = `<p class="help">${esc(e.message)}</p>`; return; }
      box.innerHTML = f.following.length ? `<h4 id="pv_fH">People I follow</h4><ul class="follow-list" aria-labelledby="pv_fH">${f.following.map(x => `<li>${x.profile_url ? `<a href="${esc(x.profile_url)}" target="_blank" rel="noopener noreferrer">${esc(x.name)}</a>` : `<span>${esc(x.name)}</span>`}
        <button type="button" class="btn small ghost" data-unfollow="${esc(x.id)}" aria-label="Unfollow ${esc(x.name)}">Unfollow</button></li>`).join("")}</ul>` : `<p class="help">You don't follow anyone yet. Use "Follow creator" on a project you like.</p>`;
      box.querySelectorAll("[data-unfollow]").forEach(b => b.onclick = async () => {
        b.disabled = true;
        try { await api("/api/follow/" + encodeURIComponent(b.dataset.unfollow), { method: "DELETE" }); toast("Unfollowed", "ok"); await drawFollowing(); $("#pv_following").focus(); }
        catch (e) { b.disabled = false; toast(e.message, "err"); } });
    };
    $("#pv_following").onclick = async () => { const box = $("#pv_followingList"), open = box.hidden; box.hidden = !open; $("#pv_following").setAttribute("aria-expanded", open); if (open) await drawFollowing(); };
    $("#pv_followers").onclick = async () => { const f = await api("/api/me/followers"); toast(!f.enabled ? "Following is off, so there are no followers." : f.followers.length ? "Followers: " + f.followers.map(x => x.display_name).join(", ") : "No followers yet."); };
  }
}

/* ---------- Sign out (there are no passwords yet, so say plainly how to get back in before anyone presses it) ---------- */
function openSignout() {
  const adult = !!ME.recovery, body = $("#soBody"), go = $("#soGo");
  const setGo = on => { go.setAttribute("aria-disabled", on ? "false" : "true"); $("#soWhy").textContent = on ? "" : (adult && $("#soOk")?.getAttribute("aria-disabled") === "true" ? "Show your recovery code and write it down, then tick the box to sign out." : "Tick the box above to sign out."); };
  clearInline(go.parentElement);
  body.innerHTML = adult
    ? `<p>ZEIM has no passwords yet. To open this account again later, here or on another device, you need a <b>recovery code</b>.</p>
       <p class="help">Showing a new code makes any older code stop working.</p>
       <button type="button" class="btn" id="soCodeBtn">Show my recovery code</button><p id="soCode" role="status"></p>
       <label class="inl"><input type="checkbox" id="soOk" aria-disabled="true" aria-describedby="soWhy"> I have written down my recovery code</label>`
    : `<p>This account has no recovery code, so after you sign out <b>this account can't be opened again</b>. Your projects stay private.</p>
       <label class="inl"><input type="checkbox" id="soOk"> I understand I can't get this account back</label>`;
  setGo(false);
  $("#soOk").onclick = e => { if (e.target.getAttribute("aria-disabled") === "true") { e.preventDefault(); $("#soWhy").textContent = "Show your recovery code first, then tick the box."; } };
  $("#soOk").onchange = e => setGo(e.target.checked);
  if (adult) $("#soCodeBtn").onclick = async () => {
    try { const r = await api("/api/me/recovery-code", J("POST")); $("#soCode").innerHTML = `Your recovery code: <b class="code">${esc(r.recovery_code)}</b>`; $("#soOk").setAttribute("aria-disabled", "false"); setGo(false); }
    catch (e) { $("#soCode").textContent = e.message; }
  };
  go.onclick = async () => {
    if (go.getAttribute("aria-disabled") === "true") { $("#soWhy").focus?.(); return; }
    try { await api("/api/me/signout", J("POST")); try { sessionStorage.zeimSignedOut = "1"; } catch { } location.reload(); }
    catch (e) { inlineMsg(go.parentElement, e.message); }
  };
  stackModal($("#dlgSignout"));
  (adult ? $("#soCodeBtn") : $("#soOk")).focus();            // a11y #10: start on the first thing to do, not the close button
}

/* Stacked dialogs (a11y #8): the dialog underneath is made inert while a child dialog is open, and Tab is kept inside the top dialog
   explicitly (WebKit let Tab reach the dialog underneath and the <dialog> element itself). */
function stackModal(d) {
  const under = $$("dialog[open]").filter(x => x !== d);
  under.forEach(x => { x.inert = true; });
  d.addEventListener("close", () => under.forEach(x => { x.inert = false; }), { once: true });
  d.showModal();
}
document.addEventListener("keydown", e => {
  if (e.key !== "Tab") return;
  const open = $$("dialog[open]").filter(x => !x.inert); const d = open[open.length - 1]; if (!d) return;
  const f = $$('a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"])', d).filter(x => !x.disabled && !x.hidden && x.offsetParent !== null);
  if (!f.length) return;
  const i = f.indexOf(document.activeElement);
  if (e.shiftKey && (i <= 0)) { e.preventDefault(); f[f.length - 1].focus(); }
  else if (!e.shiftKey && (i === -1 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
});
try { if (sessionStorage.zeimSignedOut) { delete sessionStorage.zeimSignedOut; setTimeout(() => toast("You're signed out. This browser no longer has your account.", "ok"), 300); } } catch { }

/* ---------- showcase grid ---------- */
const MODE_ICON = { lithophane: "<svg class=i aria-hidden=true focusable=false><use href=#i-image></use></svg>", relief: "<svg class=i aria-hidden=true focusable=false><use href=#i-mountain></use></svg>", popart: "<svg class=i aria-hidden=true focusable=false><use href=#i-palette></use></svg>", edit: "<svg class=i aria-hidden=true focusable=false><use href=#i-pencil></use></svg>" };
let shCat = "";
// ZEIM Original card details. Proof badge from the server: "Simulated" (computer checks only, the default) or
// "Test-printed" (a real ZEIM print is logged; the detail names the printer that was logged). Never more than that.
const proofHTML = i => { const p = i.proof || { badge: "simulated", label: "Simulated", detail: "Checked on a computer only. Untested print: not printed by the ZEIM team yet." };
  return `<span class="pill ${p.badge === "test_printed" ? "ok" : "warn"} proof" data-proof="${esc(p.badge)}">${esc(p.label)}</span>`; };
const origHTML = i => `<div class="orig">${i.credit?.credit_line ? `<p class="credit-line">${esc(i.credit.credit_line)}</p>` : ""}
    <p><span class="pill">${esc(i.difficulty)}</span> <span class="pill" title="${esc(i.printer_note)}">Suggested: ${esc(i.printer_suggested)}</span> ${proofHTML(i)}${i.needs_supports ? ' <span class="pill">Needs supports</span>' : ""}</p>
    <p class="help proof-detail">${esc((i.proof && i.proof.detail) || "Checked on a computer only. Untested print: not printed by the ZEIM team yet.")}</p>
    ${i.low_contact ? `<p class="help caveat"><b>Brim:</b> ${esc(i.low_contact)}</p>` : ""}${i.plates ? `<p class="help">Prints as ${i.files.length} separate plates, each fits a 220 × 220 mm bed.</p>` : ""}
    ${i.material || i.caveats ? `<p class="help caveat">${esc([i.material, i.caveats].filter(Boolean).join(" "))}</p>` : ""}
    ${i.files.map(f => `<a class="btn small" href="${f.url}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> ${i.files.length > 1 ? `Plate ${i.files.indexOf(f) + 1} ` : ""}STL<span class="sr-only"> for ${esc(i.title)}</span></a>`).join("")}</div>`;
// ZEIM Original detail page: the real facts from the Originals manifest (size, supports, parts, how to use, assembly). Nothing is guessed:
// a missing fact is simply left out.
const mm = v => `${Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 })}`;
const origMoreHTML = i => {
  const s = i.size_mm, out = [];
  if (i.how_used) out.push(`<h4>How to use it</h4><p>${esc(i.how_used)}</p>`);
  if (s) out.push(`<p class="orig-size"><b>Size:</b> ${mm(s.x)} × ${mm(s.y)} × ${mm(s.z)} mm <span class="help">(width × depth × height${s.note ? `, ${esc(s.note)}` : ""})</span></p>`);
  if (i.supports_detail) out.push(`<p class="orig-supports"><b>Supports${i.supports_level ? ` (${esc(i.supports_level)})` : ""}:</b> ${esc(i.supports_detail)}</p>`);
  if (i.parts?.length) out.push(`<h4>Parts in this kit</h4><ul class="orig-parts">${i.parts.map(p => `<li>${esc(p.name)}: ${p.size_mm ? `${p.size_mm.map(mm).join(" × ")} mm` : esc(p.about || "")}</li>`).join("")}</ul>`);
  if (i.assembly_steps?.length) out.push(`<h4>Put it together</h4><ul class="orig-steps">${i.assembly_steps.map(t => `<li>${esc(t)}</li>`).join("")}</ul>`);
  return out.length ? `<section class="orig-more" aria-label="About this ZEIM Original">${out.join("")}</section>` : "";
};
async function loadShowcase() {
  const q = $("#shSearch").value.trim();
  $("#shClear").hidden = !q;
  let r;
  if (!$("#shGrid").children.length) $("#shGrid").innerHTML = '<li class="skel" aria-hidden="true"></li>'.repeat(4);      // loading skeletons (first load only)
  try { r = await api(`/api/showcase?tab=${shTab}&q=${encodeURIComponent(q)}&category=${encodeURIComponent(shCat)}&ai=${encodeURIComponent(shAiVal())}${shFilterQS()}`); } catch (e) { toast(e.message, "err"); return; }
  $("#shNotice").textContent = r.originals_notice || "";
  if (r.filters && $("#shMature")) $("#shMature").value = r.filters.mature;
  // category filters: built from what THIS viewer may see (hidden categories never reach under-13s)
  $("#shCats").innerHTML = ["", ...(r.categories || [])].map(c => `<button type="button" class="chip${c === shCat ? " on" : ""}" data-cat="${esc(c)}" aria-pressed="${c === shCat}">${c ? esc(c) : "All"}</button>`).join("");
  $("#shSub").textContent = r.subtitle || "";
  loadRecent();
  $("#shCount").textContent = q ? `${r.result_count} project${r.result_count === 1 ? "" : "s"} match "${q}"` : "";
  // Example cards show NO numbers at all (not 0, not a dash); counts also arrive as null for non-public items.
  $("#shGrid").innerHTML = r.items.map(i => `<li class="pcard" data-item="${i.id}"><div class="ph${i.nsfw ? " nsfw" : ""}" aria-hidden="true">${i.thumb ? `<img src="${i.thumb}" alt="">` : (MODE_ICON[i.mode] || "<svg class=i aria-hidden=true focusable=false><use href=#i-cube></use></svg>")}${i.example ? '<span class="ex">EXAMPLE</span>' : ""}</div>${matLabel(i)}
    <div class="meta"><h2><a href="#" data-open="${i.id}">${esc(i.title)}</a></h2><span>${i.original ? esc(i.creator) : `<a class="creator-link" href="/u/${i.creator_id}">${esc(i.creator)}</a>`}${i.credit?.licence ? ` · ${esc(i.credit.licence)}` : ""}</span>${i.visibility && i.visibility !== "public" ? `<span class="pill">${esc(i.visibility)}</span>` : ""}${provHTML(i)}</div>
    ${i.original ? origHTML(i) : ""}<div class="cardfoot"><span class="wp" data-wp="${i.files?.length && !i.no_model && !i.example ? i.id : ""}"></span>${nzHTML(i, { uid: "g" })}${favHTML(i)}${i.downloads != null ? `<span class="dl"><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> ${i.downloads}<span class="sr-only"> downloads</span></span>` : ""}</div></li>`).join("");
  showcaseBadges();
  if (!r.items.length) {
    const filtered = !!(q || shCat || shAiVal() !== "show");
    const e = filtered ? { text: "Your filters are hiding results. Nothing matches all of them right now.", action: { do: "reset-filters", label: "Reset filters" } }
      : (r.empty || { text: "Nothing here yet. Check back soon.", action: null });
    $("#shGrid").innerHTML = `<li class="empty"><p>${esc(e.text)}</p>${e.action ? `<button class="btn" data-empty="${e.action.do}">${esc(e.action.label)}</button>` : ""}</li>`;
  }
}
$("#shTabs").onclick = e => { const b = e.target.closest("[data-tab]"); if (!b) return; shTab = b.dataset.tab; $$("#shTabs button").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); }); loadShowcase(); };
$("#shGrid").addEventListener("click", e => { const c = e.target.closest("a[data-open]"); if (c) { e.preventDefault(); openItem(c.dataset.open); } });
// AI filter survives a reload: ?ai= in the URL wins, then the last choice in localStorage
const SH_AI_OK = ["show", "hide", "only"];
function shAiVal() { const v = $("#shAi")?.value; return SH_AI_OK.includes(v) ? v : "show"; }
function shAiSave(v) {
  try { localStorage.setItem("zeim.showcase.ai", v); } catch { }
  const u = new URL(location.href); if (v === "show") u.searchParams.delete("ai"); else u.searchParams.set("ai", v);
  history.replaceState(history.state, "", u);
}
(() => { const el = $("#shAi"); if (!el) return; let v = new URLSearchParams(location.search).get("ai");
  if (!SH_AI_OK.includes(v)) { try { v = localStorage.getItem("zeim.showcase.ai"); } catch { v = null; } }
  if (SH_AI_OK.includes(v)) el.value = v; })();
$("#shAi")?.addEventListener("change", () => { shAiSave(shAiVal()); loadShowcase(); });
// printer / material / supports / licence / mature filters (server validates; 'Not stated' = the model does not say)
const SH_FILTERS = { printer: "#shPrinter", material: "#shMaterial", supports: "#shSupports", licence: "#shLicence", mature: "#shMature" };
let shMatureTouched = false;
function shFilterQS() { return Object.entries(SH_FILTERS).map(([k, sel]) => { const el = $(sel); return el && (k !== "mature" || shMatureTouched) ? `&${k}=${encodeURIComponent(el.value)}` : ""; }).join(""); }
function shFiltersReset() { Object.values(SH_FILTERS).forEach(sel => { const el = $(sel); if (el) el.selectedIndex = 0; }); shMatureTouched = false; }
$("#shMature")?.addEventListener("change", () => { shMatureTouched = true; });
Object.values(SH_FILTERS).forEach(sel => $(sel)?.addEventListener("change", () => loadShowcase()));
$("#shFiltReset")?.addEventListener("click", () => { shFiltersReset(); loadShowcase(); });
$("#shGrid").addEventListener("click", e => { if (!e.target.closest('[data-empty="reset-filters"]')) return;
  e.stopPropagation(); $("#shSearch").value = ""; shCat = ""; if ($("#shAi")) $("#shAi").value = "show"; shAiSave("show"); shFiltersReset(); loadShowcase(); }, true);
// honest provenance labels: AI-made (creator said so, or 2D to 3D tab) and 'Printed by the community' (>=1 approved print photo). No counts, no ranking.
function provHTML(i) {
  return `${i.ai_made ? '<span class="prov ai"><svg class=i aria-hidden=true focusable=false><use href=#i-chip></use></svg> AI-made</span>' : ""}${i.community_printed ? '<span class="prov printed"><svg class=i aria-hidden=true focusable=false><use href=#i-printer></use></svg> Printed by the community</span>' : ""}`;
}
function tipHTML(i) {
  if (!/^https:\/\//i.test(i.tip_url || "")) return "";
  let host = ""; try { host = new URL(i.tip_url).hostname.toLowerCase(); } catch { return ""; }
  const who = i.creator_username ? "@" + i.creator_username : i.creator;
  return `<p class="help tiplink"><a href="${esc(i.tip_url)}" target="_blank" rel="noopener nofollow noreferrer">Tip link for ${esc(who)} (${esc(host)})</a></p>`;
}
$("#shCats").addEventListener("click", e => { const b = e.target.closest("[data-cat]"); if (!b) return; shCat = b.dataset.cat; loadShowcase(); });
$("#shForm").onsubmit = e => { e.preventDefault(); loadShowcase(); };
$("#shSearch").addEventListener("focus", () => loadRecent());            // Search button, Enter and touch-keyboard "Go" all end up here
$("#shClear").onclick = () => { $("#shSearch").value = ""; loadShowcase(); $("#shSearch").focus(); };
$("#shSearch").oninput = () => { $("#shClear").hidden = !$("#shSearch").value; };
$("#shGrid").addEventListener("click", e => {
  const b = e.target.closest("[data-empty]"); if (!b) return;
  const d = b.dataset.empty;
  if (d === "clear") { $("#shClear").click(); }
  else if (d === "trending" || d === "free") { $(`#shTabs [data-tab="${d}"]`)?.click(); }
  else if (d === "mydata") { $("#btnMyData").click(); }
  else if (d === "studio") { location.hash = "create"; }
});


/* ---------- Nozzle it: the one positive-only button (replaces every like/heart). Spec: reports/design/nozzle-it-spec.md ---------- */
const NZ_SVG = `<svg class="nz-ico" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false"><g class="nz-body"><rect x="6" y="2.5" width="12" height="5.5" rx="1.5"/><path d="M8.2 8h7.6l-2 5.5h-3.6z"/><path d="M10.2 13.5h3.6V16h-3.6z"/></g><path class="nz-drop" d="M12 17.6c-1.5 1.9-2 2.7-2 3.5a2 2 0 0 0 4 0c0-.8-.5-1.6-2-3.5z"/></svg>`;
const nzShort = n => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k" : String(n);
const nzName = n => n == null ? "Nozzle it" : n === 0 ? "Nozzle it, no nozzles yet" : `Nozzle it, ${n} ${n === 1 ? "nozzle" : "nozzles"}`;
const nzNeedsAccount = () => !ME?.signed_up;
function nzHTML(i, { large = false, uid = "g" } = {}) {
  if (i.example || i.no_nozzle) return "";                                   // examples are seed data: no button, no number
  const n = i.likes == null ? null : i.likes;
  if (i.owned) return `<span class="nz-static">${NZ_SVG}<span>${n == null ? "Your project" : `${n} ${n === 1 ? "nozzle" : "nozzles"}`}</span></span>`;
  if (i.can_like_reason === "not_public") return "";
  const off = false, why = `nzwhy-${uid}-${i.id}`;
  return `<span class="nzwrap"><button type="button" class="nz${large ? " nz-lg" : ""}" data-nz="${i.id}" data-likes="${n == null ? "" : n}" aria-pressed="${!!i.liked}" aria-label="${nzName(n)}"
      ${off ? `aria-disabled="true" aria-describedby="${why}" data-off="1"` : ""}>${NZ_SVG}${large ? '<span class="nz-text" aria-hidden="true">Nozzle it</span>' : ""}<span class="nz-count" aria-hidden="true">${n ? nzShort(n) : ""}</span></button>${off ? `<span class="nz-note" id="${why}">${NZ_OFF}</span>` : ""}</span>`;
}
function nzSay(t, alert = false) {
  const el = $(alert ? "#nzAlert" : "#nzStatus"); if (!el) return;
  el.textContent = ""; setTimeout(() => el.textContent = t, 60);
}
function nzPaint(id, liked, n, pop) {
  $$(`.nz[data-nz="${CSS.escape(id)}"]`).forEach(b => {
    b.setAttribute("aria-pressed", String(!!liked)); b.dataset.likes = n == null ? "" : n; b.setAttribute("aria-label", nzName(n));
    b.querySelector(".nz-count").textContent = n ? nzShort(n) : "";
    if (pop && !matchMedia("(prefers-reduced-motion: reduce)").matches) { const c = liked ? "pop" : "pop-off"; b.classList.remove("pop", "pop-off"); void b.offsetWidth; b.classList.add(c); }
  });
}
document.addEventListener("click", async e => {
  const b = e.target.closest(".nz"); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  if (b.dataset.busy) return;                                               // one request at a time per button
  const id = b.dataset.nz;
  if (nzNeedsAccount()) { window.__nzOpener = b; $("#dlgNzAcct").showModal(); return; }
  const was = { liked: b.getAttribute("aria-pressed") === "true", n: b.dataset.likes === "" ? null : +b.dataset.likes }, want = !was.liked;
  const now = was.n == null ? null : Math.max(0, was.n + (want ? 1 : -1));
  $$(`.nz[data-nz="${CSS.escape(id)}"]`).forEach(x => x.dataset.busy = "1");
  nzPaint(id, want, now, true);
  try {
    const r = await api(`/api/showcase/${id}/like`, J("POST", { liked: want }));
    nzPaint(id, r.liked, r.likes, false);
    nzSay((r.liked ? "Nozzled." : "Nozzle removed.") + (r.likes != null ? ` ${r.likes} ${r.likes === 1 ? "nozzle" : "nozzles"}.` : ""));
  } catch (er) {
    nzPaint(id, was.liked, was.n, false);                                    // roll back to exactly what it was
    if (er.status === 401) { window.__nzOpener = b; $("#dlgNzAcct").showModal(); }                // the server says this session has no account (e.g. it expired)
    else { nzSay("Couldn't save your nozzle. Check your connection and try again.", true); toast("Couldn't save your nozzle. Check your connection and try again.", "err"); }
  } finally { $$(`.nz[data-nz="${CSS.escape(id)}"]`).forEach(x => delete x.dataset.busy); }
}, true);
$("#nzAcctMake").onclick = () => { $("#dlgNzAcct").close(); window.__nzWantSignup = true; $("#btnAccount").click(); };
$("#nzAcctLater").onclick = () => { $("#dlgNzAcct").close(); window.__nzOpener?.focus(); };
document.addEventListener("zeim:me", () => { if (window.__nzWantSignup && ME?.signed_up) { window.__nzWantSignup = false; nzSay("Account made. You can nozzle projects now."); } });

/* "Will it print?" on cards: geometry checks for the chosen printer, a few at a time so the feed stays quick. */
async function showcaseBadges() {
  try { await loadCatalog(); } catch { return; }
  const els = [...document.querySelectorAll("#shGrid [data-wp]")].filter(e => e.dataset.wp);
  for (let k = 0; k < els.length; k += 4)
    await Promise.all(els.slice(k, k + 4).map(async el => { try { el.innerHTML = badgeHTML(await checkShowcase(el.dataset.wp)); } catch { } }));
}
document.addEventListener("zeim:printer", () => { if (!$("#viewShowcase").hidden) showcaseBadges(); });

/* Mild NSFW: cards are blurred with a "Mature content" label; opening one asks once per browser session, then shows it unblurred. */
const matLabel = i => i.nsfw ? '<span class="mature-label">Mature content<span class="sr-only">: picture blurred</span></span>' : "";
const MAT_KEY = "zeim_mature_ok";
function confirmMature() {
  if (sessionStorage.getItem(MAT_KEY) === "1") return Promise.resolve(true);
  const d = $("#dlgMature"), back = document.activeElement;
  return new Promise(res => {
    const done = ok => { d.onclose = null; if (d.open) d.close(); if (ok) sessionStorage.setItem(MAT_KEY, "1"); else back?.focus?.(); res(ok); };
    $("#matYes").onclick = () => done(true); $("#matNo").onclick = () => done(false);
    d.oncancel = e => { e.preventDefault(); done(false); };           // Esc = Go back
    d.showModal(); $("#matNo").focus();
  });
}
async function openItem(id) {
  const i = await api("/api/showcase/" + id);
  if (i.nsfw && !i.owned && !(await confirmMature())) return;
  $("#itTitle").textContent = i.title;
  $("#itBody").innerHTML = `${i.example ? '<p class="pill">EXAMPLE seed data — not a real creator project</p>' : ""}
    ${i.thumb ? `<img src="${i.thumb}" alt="${i.nsfw ? "Preview picture (mature content)" : `Preview picture of ${esc(i.title)}`}" style="max-width:100%;border-radius:10px">` : ""}
    <p>${esc(i.description)}</p><p>${i.tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</p>
    ${i.original ? origHTML(i).replace(/<a class="btn small"[^]*?<\/a>/g, "") : ""}${i.original ? origMoreHTML(i) : ""}<p class="help">by ${i.original ? esc(i.creator) : `<a class="creator-link" href="/u/${i.creator_id}" target="_blank" rel="noopener noreferrer">${esc(i.creator)}</a>`} · free${i.downloads != null ? ` · <svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> ${i.downloads}` : ""}</p>
    ${provHTML(i) ? `<p class="provrow">${provHTML(i)}</p>` : ""}${tipHTML(i)}
    ${i.credit ? `<p class="credit-line">Credit: <b>${esc(i.credit.creator)}</b>${i.credit.licence ? ` · Licence: ${/^https:\/\//.test(i.credit.licence_url) ? `<a href="${esc(i.credit.licence_url)}" target="_blank" rel="noopener noreferrer">${esc(i.credit.licence)}</a>` : esc(i.credit.licence)}` : ""} · <a href="/credits">Thank you &amp; credits</a></p>` : ""}
    ${i.first_posted && !i.example ? `<p class="help first-posted">First posted on ${esc(new Date(i.first_posted + "T12:00:00Z").toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" }))}</p>` : ""}
    ${i.owned && !i.original ? `<div class="field"><label for="itViewOnly">Downloads</label><select id="itViewOnly"><option value="no" ${i.view_only ? "" : "selected"}>Anyone who can see it may download it</option><option value="yes" ${i.view_only ? "selected" : ""}>View only, no download</option></select></div>` : ""}
    ${i.owned && !i.original && !i.example ? `<div class="itcols" id="itCols" data-iid="${i.id}"></div>` : ""}
    ${i.owned && !i.original && !i.example ? `<div class="field"><label for="itTip">Tip link <em>optional</em></label><div class="row"><input id="itTip" type="url" maxlength="300" placeholder="https://…" value="${esc(i.tip_url || "")}"><button type="button" class="btn small ghost" id="itTipSave">Save</button></div><small class="help">One https link. Leave it empty to remove it.</small></div>` : ""}
    ${i.owned && !i.original ? `<div class="field"><label for="itRemixSw">Allow remixes</label><select id="itRemixSw"><option value="yes" ${i.allow_remixes ? "selected" : ""}>Yes</option><option value="no" ${i.allow_remixes ? "" : "selected"}>No</option></select><small class="help">Remixes already posted keep their credit either way.</small></div>` : ""}
    ${i.owned ? `<div class="field"><label>Who can see this project <em>changes apply immediately</em></label><select id="itVis">${["private", "followers", "public"].map(v => `<option value="${v}" ${i.visibility === v ? "selected" : ""}>${{ private: "Private — only me", followers: "Followers only", public: "Public" }[v]}</option>`).join("")}</select></div>` : ""}
    <div class="row">${i.no_model ? '<span class="pill">No model yet</span>' : i.download_blocked ? '<span class="pill">View only: the maker turned off downloads</span>' : i.files.map(f => `<a class="btn" href="${f.url}" download><svg class=i aria-hidden=true focusable=false><use href=#i-download></use></svg> ${esc(f.name)}</a>`).join("")}
      ${nzHTML(i, { large: true, uid: "d" })}${favHTML(i, true)}
      ${i.can_follow && !i.example ? `<button class="btn" id="itFollow">${i.following_creator ? "✔ Following" : "＋ Follow creator"}</button>` : ""}
      ${i.example || i.owned || !i.can_remix ? "" : `<button class="btn ghost" id="itRemix"><svg class=i aria-hidden=true focusable=false><use href=#i-repeat></use></svg> Remix</button>`}
      <button class="btn ghost" id="itShare"><svg class=i aria-hidden=true focusable=false><use href=#i-link></use></svg> Copy link</button>
      ${i.example ? "" : '<button class="btn ghost danger" id="itReport"><svg class=i aria-hidden=true focusable=false><use href=#i-flag></use></svg> Report</button>'}
      ${i.example || i.owned || i.original ? "" : '<button class="btn ghost danger" id="itStolen">Report as stolen</button>'}
      ${i.owned && !i.example && !i.original ? '<button class="btn ghost" id="itCopyBtn" aria-controls="itCopyBox"><svg class=i aria-hidden=true focusable=false><use href=#i-flag></use></svg> Report a copy</button>' : ""}</div>
    ${i.owned && !i.example && !i.original ? `<div class="reup" id="itCopyBox" hidden><p class="help">Think someone re-posted this as their own? Pick a close match we found, or paste the link. A moderator compares the two; nothing is removed automatically.</p>
      <ul class="reup-list" id="itCopyList"></ul>
      <div class="field"><label for="itCopyUrl">Link to the copy</label><input id="itCopyUrl" maxlength="200" placeholder="https://…/p/abc123"></div>
      <button type="button" class="btn" id="itCopySend">Send to moderators</button></div>` : ""}
    ${!i.example && !i.allow_remixes ? `<p class="help remix-off" id="itRemixOff"><svg class=i aria-hidden=true focusable=false><use href=#i-lock></use></svg> Remixes off${i.owned ? "" : `: ${esc(i.remix_off_reason)}`}</p>` : !i.example && !i.owned && !i.can_remix ? `<p class="help" id="itRemixWhy">Remix is off: ${esc(i.remix_off_reason)}</p>` : ""}
    <div id="itWill" aria-live="polite"></div>
    <p class="help">Nozzles and downloads are counted once per person and only for public projects. Projects by makers you follow show up in the Following tab.</p>
    <section class="prints" aria-labelledby="prH"><h4 id="prH">I printed this</h4><ul class="pgallery" id="prGallery"></ul>
      ${ME?.signed_up && i.visibility === "public" ? `<details class="prform"><summary class="btn"><svg class=i aria-hidden=true focusable=false><use href=#i-camera></use></svg> Add a photo of your print</summary>
        <p class="help">A photo of the printed object only, please: no people, faces, names or addresses. Location data is removed. Every photo is checked by a moderator before anyone else can see it.</p>
        <div class="field"><label for="prFile">Photo</label><input type="file" id="prFile" accept="image/*"></div>
        <div class="field"><label for="prCap">Caption <em>optional</em></label><input id="prCap" maxlength="140" placeholder="Printed in PLA, came out great"></div>
        <label class="inl"><input type="checkbox" id="prAck"> This is my photo and there are no people in it</label>
        <fieldset class="reasons"><legend>Is this NSFW (mild nudity / mature art)? <em>required</em></legend>
          <label class="choice"><input type="radio" name="prNsfw" value="no"> <span>No</span></label><label class="choice"><input type="radio" name="prNsfw" value="yes"> <span>Yes</span></label></fieldset>
        <div class="row"><button class="btn primary" id="prSend" type="button">Share photo</button></div></details>` : ""}</section>`;
  if (i.remix_chain?.length) $("#itBody").insertAdjacentHTML("afterbegin", remixHTML(i.remix_chain));
  loadPrints(id);
  if ($("#itCols")) mountItemCollections($("#itCols"), id);
  if ($("#prSend")) $("#prSend").onclick = async () => {
    const f = $("#prFile").files[0]; if (!f) return inlineMsg($("#prSend"), "Choose a photo first.");
    const nv = $("[name=prNsfw]:checked")?.value; if (!nv) return inlineMsg($("#prSend"), "Please answer: Is this NSFW (mild nudity / mature art)?");
    const fd = new FormData(); fd.append("photo", f); fd.append("caption", $("#prCap").value); fd.append("photo_ack", $("#prAck").checked); fd.append("nsfw", nv);
    $("#prSend").disabled = true;
    try { await api(`/api/showcase/${id}/prints`, { method: "POST", body: fd }); clearInline($("#prSend")); toast("Thanks! Your photo is waiting for review. Only you can see it until a moderator approves it.", "ok"); $("#prFile").value = ""; $("#prCap").value = ""; loadPrints(id); }
    catch (e) { inlineMsg($("#prSend"), e.message); } finally { $("#prSend").disabled = false; }
  };
  if ($("#itVis")) $("#itVis").onchange = async e => { const v = e.target.value; try { await api(`/api/showcase/${id}/visibility`, J("PUT", { visibility: v })); toast("Visibility updated", "ok"); loadShowcase(); } catch (er) {
    if (er.status === 409 && er.body?.code === "remix_offer" && confirm(er.message + "\n\nShare it as a credited remix?")) {
      try { await api(`/api/showcase/${id}/visibility`, J("PUT", { visibility: v, remix_of: er.body.original.id })); toast("Shared as a credited remix", "ok"); loadShowcase(); return openItem(id); } catch (e2) { toast(e2.message, "err"); }
    } else toast(er.message, "err");
    openItem(id); } };
  if ($("#itCopyBtn")) $("#itCopyBtn").onclick = async () => {
    const box = $("#itCopyBox"); box.hidden = !box.hidden; if (box.hidden) return;
    const list = $("#itCopyList"); list.innerHTML = '<li class="help">Looking for close matches…</li>';
    try { const r = await api(`/api/showcase/${id}/copies`);
      list.innerHTML = r.copies.length ? r.copies.map(c => `<li><a href="${esc(c.share_url)}" target="_blank" rel="noopener">${esc(c.title)}</a> by ${esc(c.creator)} <button type="button" class="btn ghost sm" data-copy="${esc(c.id)}">Report this one</button></li>`).join("")
        : '<li class="help">No close matches found. A copy that was edited a lot can still slip past, so you can paste its link below.</li>';
      list.querySelectorAll("[data-copy]").forEach(b => b.onclick = () => sendCopy(b.dataset.copy, b));
    } catch (er) { list.innerHTML = `<li class="help">${esc(er.message)}</li>`; }
  };
  const sendCopy = async (ref, b) => { b.disabled = true;
    try { const r = await api(`/api/showcase/${id}/report-copy`, J("POST", { copy_url: ref })); b.textContent = "Reported"; toast(r.message, "ok"); }
    catch (er) { b.disabled = false; toast(er.message, "err"); } };
  if ($("#itCopySend")) $("#itCopySend").onclick = () => sendCopy($("#itCopyUrl").value.trim(), $("#itCopySend"));
  if ($("#itFollow")) $("#itFollow").onclick = async () => { try { await api("/api/follow/" + i.creator_id, { method: i.following_creator ? "DELETE" : "POST" }); openItem(id); } catch (e) { toast(e.message, "err"); } };
  if (!i.no_model && !i.example && i.files?.length) loadCatalog().then(async () => {
    const put = r => { const w = $("#itWill"); if (!w) return; w.innerHTML = badgeHTML(r, { detail: true }) + (r.checks?.slices?.ok == null ? `<button type="button" class="btn" id="itSliceCheck">Test-slice it for my printer</button>` : "");
      const b = $("#itSliceCheck"); if (b) b.onclick = async () => { b.disabled = true; b.textContent = "Slicing…"; try { put(await checkShowcase(id, true)); } catch (e) { b.textContent = e.message; } }; };
    put(await checkShowcase(id)); }).catch(() => { });
  if ($("#itViewOnly")) $("#itViewOnly").onchange = async e => { try { await api(`/api/showcase/${id}/download`, J("PUT", { view_only: e.target.value === "yes" })); toast(e.target.value === "yes" ? "Now view only: nobody else can download it" : "Downloads turned on", "ok"); } catch (er) { toast(er.message, "err"); openItem(id); } };
  if ($("#itStolen")) $("#itStolen").onclick = async () => {
    const b = $("#itStolen"); b.disabled = true;
    try { const r = await api(`/api/showcase/${id}/report-stolen`, J("POST", {}));
      b.textContent = "Reported"; toast(r.message, "ok");
      b.insertAdjacentHTML("afterend", `<p class="help">Sent to the moderators${r.original_url ? `, with a link to <a href="${esc(r.original_url)}">the original</a>` : ""}. Rights holders can also send a <a href="${esc(r.dmca_url)}" target="_blank" rel="noopener">formal takedown notice</a>.</p>`);
    } catch (e) { b.disabled = false; toast(e.message, "err"); }
  };
  if ($("#itTipSave")) $("#itTipSave").onclick = async () => { try { await api(`/api/showcase/${id}/tip`, J("PUT", { tip_url: $("#itTip").value.trim() })); toast($("#itTip").value.trim() ? "Tip link saved" : "Tip link removed", "ok"); openItem(id); } catch (er) { toast(er.message, "err"); } };
  if ($("#itRemixSw")) $("#itRemixSw").onchange = async e => { try { await api(`/api/showcase/${id}/remixes`, J("PUT", { allow_remixes: e.target.value === "yes" })); toast(e.target.value === "yes" ? "Remixes allowed" : "Remixes turned off", "ok"); openItem(id); } catch (er) { toast(er.message, "err"); openItem(id); } };
  if ($("#itRemix") && i.can_remix) $("#itRemix").onclick = () => { sessionStorage.setItem("zeim_remix_of", location.origin + i.share_url); toast("Make your version in the Studio, then Share it: this project will be credited as the original.", "ok"); };
  $("#itShare").onclick = () => { navigator.clipboard?.writeText(location.origin + i.share_url); toast("Link copied", "ok"); };
  if ($("#itReport")) $("#itReport").onclick = () => {
    $$("#dlgReport [name=repReason]").forEach(r => r.checked = false); $("#repDetails").value = ""; clearInline($("#repSend"));
    $("#repSend").disabled = false; $("#dlgReport").showModal();
    $("#repSend").onclick = async () => {
      const reason = $("#dlgReport [name=repReason]:checked")?.value;
      if (!reason) return inlineMsg($("#repSend"), "Please choose what the problem is.");
      $("#repSend").disabled = true;
      try {
        const r = await api(`/api/showcase/${id}/report`, J("POST", { reason, details: $("#repDetails").value }));
        $("#dlgReport").close(); toast(r.auto_hidden ? "Thank you. The project is hidden while a moderator looks at it." : "Thank you. We got your report.", "ok");
        if (r.auto_hidden) { $("#dlgItem").close(); loadShowcase(); }
      } catch (e) { inlineMsg($("#repSend"), e.message); } finally { $("#repSend").disabled = false; }
    };
  };
  if (!$("#dlgItem").open) $("#dlgItem").showModal();
}

/* publish */
$("#btnPublish").onclick = () => {
  if (!ME.signed_up) { toast("Create an account first to share projects.", "err"); renderAccount(); return $("#dlgAccount").showModal(); }
  $("#pub_title").value = S.current.title; $("#pub_vis").value = ME.privacy?.default_visibility || "private"; $$("[name=pub_nsfw]").forEach(r => r.checked = false);
  // 2D to 3D builds are always saved as AI-made by the server, so show that honestly instead of a box that can be unticked
  const aiForced = !!(S.current?.ai || S.current?.mode === "ai3d" || S.current?.base?.from_mode === "ai3d"), aiBox = $("#pub_ai");
  if (aiBox) { aiBox.checked = aiForced || aiBox.checked && !aiBox.disabled; aiBox.disabled = aiForced; }
  if ($("#pub_ai_note")) $("#pub_ai_note").hidden = !aiForced;
  $("#pub_allow_remix").value = "yes"; $("#pub_view_only").value = "no"; if (!$("#pub_remix").value && sessionStorage.getItem("zeim_remix_of")) $("#pub_remix").value = sessionStorage.getItem("zeim_remix_of");
  $("#dlgPublish").showModal();
};
function showConflict(c) {
  const box = $("#pubConflict"), o = c.original || {};
  const offer = c.code === "remix_offer";
  box.innerHTML = `<p><svg class=i aria-hidden=true focusable=false><use href=#i-${offer ? "repeat" : "lock"}></use></svg> ${esc(c.message)}</p>
    ${o.share_url ? `<p class="help">Original: <a href="${esc(o.share_url)}" target="_blank" rel="noopener">${esc(o.title || "this project")}</a>${o.creator ? " by " + esc(o.creator) : ""}</p>` : ""}
    <div class="reup-actions">${offer ? `<button type="button" class="btn primary" id="pubAsRemix"><svg class=i aria-hidden=true focusable=false><use href=#i-repeat></use></svg> Post as a credited remix</button>` : ""}
    <button type="button" class="btn ghost" id="pubKeepPrivate"><svg class=i aria-hidden=true focusable=false><use href=#i-lock></use></svg> Keep it Private</button></div>`;
  box.hidden = false; box.scrollIntoView({ block: "end", behavior: "instant" }); box.tabIndex = -1; box.focus({ preventScroll: true });
  if ($("#pubAsRemix")) $("#pubAsRemix").onclick = () => { $("#pub_remix").value = location.origin + o.share_url; box.hidden = true; $("#btnDoPublish").click(); };
  $("#pubKeepPrivate").onclick = () => { $("#pub_vis").value = "private"; box.hidden = true; $("#btnDoPublish").click(); };
}
$("#btnDoPublish").onclick = async () => {
  if ($("#pubConflict")) $("#pubConflict").hidden = true;
  const nsfw = $("[name=pub_nsfw]:checked")?.value;
  if (!nsfw) return inlineMsg($("#btnDoPublish"), "Please answer: Is this NSFW (mild nudity / mature art)? Yes or No.");
  try {
    const i = await api("/api/showcase", J("POST", { build_id: S.current.id, title: $("#pub_title").value, description: $("#pub_desc").value,
      tags: $("#pub_tags").value.split(","), accept_guidelines: $("#pub_ok").checked, visibility: $("#pub_vis").value, remix_of: $("#pub_remix").value.trim(), nsfw: nsfw === "yes",
      allow_remixes: $("#pub_allow_remix").value === "yes", view_only: $("#pub_view_only").value === "yes",
      ai_made: !!$("#pub_ai")?.checked, tip_url: ($("#pub_tip")?.value || "").trim() }));
    if ($("#pub_remix").value.trim()) sessionStorage.removeItem("zeim_remix_of");
    clearInline($("#btnDoPublish")); $("#dlgPublish").close();
    (i.warnings || []).forEach(w => toast(w, "ok"));
    if (i.held_for_review) return toast(i.hold_message, "ok");
    toast(i.visibility === "private" ? "Saved as Private — only you can see it. Change it any time." : "Shared! " + location.origin + i.share_url, "ok");
  } catch (e) { if (e.status === 409 && e.body?.code) { clearInline($("#btnDoPublish")); return showConflict(e.body); } inlineMsg($("#btnDoPublish"), e.message); }
};

/* What ZEIM knows about you (Kenji S-07): live view, download metadata, delete everything I made */
$("#btnMyData").onclick = openData;
$("#hideMature").onchange = async e => {
  if (!ME?.signed_up) { e.target.checked = true; return toast("Make a free account to change this setting.", "err"); }
  try { await api("/api/me/mature", J("PUT", { hide_mature: e.target.checked })); ME.hide_mature = e.target.checked; loadShowcase(); } catch (er) { toast(er.message, "err"); }
};
async function openData() {
  $("#hideMature").checked = ME?.hide_mature !== false;
  const d = await api("/api/me/data");
  const ints = Object.entries(d.interests || {}).sort((a, b) => b[1] - a[1]);
  const acct = d.account;
  const who = acct ? `Signed in as <b>@${esc(acct.username || "")}</b>${acct.display_name ? ` (${esc(acct.display_name)})` : ""}.`
                   : "You are using ZEIM without an account (this browser session only).";
  const pr = acct?.printer ? `<li>Your printer choice: <b>${esc(acct.printer.printer_id || "")}${acct.printer.nozzle != null ? ` · ${esc(String(acct.printer.nozzle))} mm` : ""}</b></li>` : "";
  $("#dataBody").innerHTML = `<p class="help">${esc(d.note)}</p>
    <p>${who}</p>
    <ul class="help">
      <li>Builds and Edit projects: <b>${d.builds_count ?? 0}</b>${(d.builds || []).some(b => b.favorite) ? " (some starred)" : ""}</li>
      <li>Projects you shared to Showcase: <b>${d.shared_count ?? 0}</b></li>
      ${pr}
      <li>Personalization (For You ranking): <b>${d.enabled ? "on" : "off"}</b></li>
    </ul>
    <h4>What ZEIM does <em>not</em> keep</h4>
    <p class="help">${(d.not_collected || []).map(esc).join(" · ")}</p>
    <h4>Interests</h4><p>${ints.map(([t, w]) => `<span class="tag">${esc(t)} · ${w}</span>`).join("") || "<span class='help'>none yet</span>"}</p>
    <h4>Recent searches</h4><p>${(d.searches || []).map(s => `<span class="tag">${esc(s)}</span>`).join("") || "<span class='help'>none</span>"}</p>
    <p class="help">Download my stuff saves a JSON file of this summary (no photo or model bytes). Delete everything I made removes your builds, photos and Showcase posts; your account stays so you can keep using ZEIM.</p>`;
  $("#btnToggleP13n").textContent = d.enabled ? "Turn personalization off" : "Turn personalization on";
  $("#btnToggleP13n").onclick = async () => { await api("/api/me/personalization", J("PUT", { enabled: !d.enabled })); openData(); };
  $("#btnClearData").onclick = async () => { await api("/api/me/data", { method: "DELETE" }); toast("Personalization cleared", "ok"); openData(); };
  $("#btnDeleteStuff").onclick = async () => {
    const n = (d.builds_count || 0) + (d.shared_count || 0);
    if (!n) { toast("You have nothing to delete yet.", "ok"); return; }
    const yes = await askConfirm({
      title: "Delete everything I made?",
      message: `This permanently removes ${d.builds_count || 0} build(s) (including starred ones and their photos) and ${d.shared_count || 0} Showcase project(s). Your account stays. This cannot be undone.`,
      okLabel: "Delete everything I made",
    });
    if (!yes) return;
    try {
      const r = await api("/api/me/builds", { method: "DELETE" });
      toast(`Deleted ${r.builds} build(s) and ${r.shared} shared project(s).`, "ok");
      try { await loadHistory(); } catch { }
      openData();
    } catch (e) { toast(e.message, "err"); }
  };
  if (!$("#dlgData").open) $("#dlgData").showModal();
}

/* ---------- learn ---------- */
async function loadLearn() {
  const r = await api("/api/learn/lessons");
  $("#lessonGrid").innerHTML = r.lessons.map(l => `<div class="pcard" data-lesson="${l.id}"><div class="ph" aria-hidden="true"><svg class=i aria-hidden=true focusable=false><use href=#i-sparkle></use></svg></div>
    <div class="meta"><h3 class="lt"><a href="#" class="stretch" data-open-lesson="${l.id}">${esc(l.title)}</a></h3><span>${l.minutes} min</span><div class="help">${esc(l.summary)}</div>
    <div class="bar"><i style="width:${100 * l.done_steps / l.steps}%"></i></div><span>${l.completed ? l.badge : `${l.done_steps}/${l.steps} steps`}</span></div></div>`).join("");
}
$("#lessonGrid").onclick = e => { const c = e.target.closest("[data-lesson]"); if (c) { e.preventDefault(); openLesson(c.dataset.lesson); } };   // the title link (keyboard) and a tap anywhere on the card
async function openLesson(id) {
  const l = await api("/api/learn/lessons/" + id), box = $("#lessonDetail"), p = l.progress;
  box.hidden = false;
  box.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">${esc(l.title)}</h2><div class="row"><button class="btn small ghost" id="lsCopy"><svg class=i aria-hidden=true focusable=false><use href=#i-link></use></svg> Copy share link</button><button class="btn small ghost" id="lsClose">Close</button></div></div>
    <p class="help">${esc(l.objective)}</p>
    <ol>${l.steps.map((s, i) => `<li class="st ${p.steps_done.includes(i) ? "done" : ""}"><label><input type="checkbox" data-step="${i}" ${p.steps_done.includes(i) ? "checked" : ""}><b>${i + 1}. ${esc(s.title)}</b></label><p>${esc(s.body)}</p></li>`).join("")}</ol>
    <div class="row" style="margin-top:12px"><button class="btn primary" id="lsTry"><svg class=i aria-hidden=true focusable=false><use href=#i-rocket></use></svg> ${esc(l.try.label)}</button>${p.completed ? '<span class="pill ok"><svg class=i aria-hidden=true focusable=false><use href=#i-medal></use></svg> Lesson complete!</span>' : ""}</div>`;
  box.scrollIntoView({ behavior: "smooth" });
  $("#lsClose").onclick = () => { box.hidden = true; loadLearn(); };
  $("#lsCopy").onclick = () => { navigator.clipboard?.writeText(location.origin + l.share_url); toast("Link copied", "ok"); };
  $$("[data-step]", box).forEach(c => c.onchange = async () => { await api(`/api/learn/lessons/${id}/steps/${c.dataset.step}`, J("POST", { done: c.checked })); openLesson(id); });
  $("#lsTry").onclick = () => { S.mode = l.try.mode; S.preset = l.try.preset; location.hash = "studio"; $$("#modeCards input").forEach(i => { i.checked = i.value === S.mode; i.closest(".card").classList.toggle("on", i.checked); }); applyMode(); $("#sSample").click(); toast("Sample photo loaded", "ok"); };
}


init();


/* ---------- search history (stored per account on the server; 'Clear history' deletes it) ---------- */
async function loadRecent() {
  const box = $("#shRecent"); if (!box) return;
  let r; try { r = await api("/api/me/searches"); } catch { box.hidden = true; return; }
  if (!r.searches.length) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  box.innerHTML = `<span class="help">Recent searches</span><ul class="chips">${r.searches.map(q => `<li class="rchip"><button type="button" class="chip" data-recent="${esc(q)}">${esc(q)}</button><button type="button" class="chip x" data-unrecent="${esc(q)}" aria-label="Remove ${esc(q)} from history"><svg class="i" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6L6 18"/></svg></button></li>`).join("")}</ul><button type="button" class="btn small ghost" id="shClearHist">Clear history</button>`;
}
$("#shRecent").addEventListener("click", async e => {
  const go = e.target.closest("[data-recent]"); if (go) { $("#shSearch").value = go.dataset.recent; return loadShowcase(); }
  const rm = e.target.closest("[data-unrecent]");
  if (rm) { try { await api("/api/me/searches/remove", J("POST", { q: rm.dataset.unrecent })); loadRecent(); toast("Removed from history", "ok"); } catch (er) { toast(er.message, "err"); } return; }
  if (e.target.id === "shClearHist") { try { await api("/api/me/searches", { method: "DELETE" }); loadRecent(); toast("Search history deleted", "ok"); } catch (er) { toast(er.message, "err"); } }
});

/* ---------- Favorites: a private bookmark list (SVG heart icon) ---------- */
const FAV_SVG = `<svg class="fav-ico" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="M12 20.5s-7.5-4.6-9.2-9.4C1.6 7.6 4 4.5 7.3 4.5c2 0 3.6 1.1 4.7 2.7 1.1-1.6 2.7-2.7 4.7-2.7 3.3 0 5.7 3.1 4.5 6.6-1.7 4.8-9.2 9.4-9.2 9.4z"/></svg>`;
function favHTML(i, large = false) {
  if (i.example) return "";
  return `<button type="button" class="fav${large ? " fav-lg" : ""}" data-fav="${i.id}" aria-pressed="${!!i.favorited}" aria-label="Save to Favorites" title="Save to Favorites">${FAV_SVG}${large ? '<span class="fav-text" aria-hidden="true">Favorite</span>' : ""}</button>`;
}
document.addEventListener("click", async e => {
  const b = e.target.closest(".fav"); if (!b) return;
  e.preventDefault(); e.stopPropagation();
  if (!ME?.signed_up) { toast("Make a free account to save favorites.", "err"); return; }
  const id = b.dataset.fav, want = b.getAttribute("aria-pressed") !== "true";
  $$(`.fav[data-fav="${CSS.escape(id)}"]`).forEach(x => x.setAttribute("aria-pressed", String(want)));
  try { const r = await api(`/api/showcase/${id}/favorite`, J("POST", { favorite: want })); $$(`.fav[data-fav="${CSS.escape(id)}"]`).forEach(x => x.setAttribute("aria-pressed", String(r.favorite))); nzSay(r.favorite ? "Saved to Favorites." : "Removed from Favorites."); if (document.body.dataset.view === "account") loadFavorites(); }
  catch (er) { $$(`.fav[data-fav="${CSS.escape(id)}"]`).forEach(x => x.setAttribute("aria-pressed", String(!want))); toast(er.message, "err"); }
}, true);
async function loadFavorites() {
  const g = $("#favGrid"); if (!g) return;
  if (!ME?.signed_up) { g.innerHTML = `<li class="empty"><p>Make a free account to save favorites.</p></li>`; return; }
  let r; try { r = await api("/api/me/favorites"); } catch { return; }
  g.innerHTML = r.items.length ? r.items.map(i => `<li class="pcard" data-item="${i.id}"><div class="ph${i.nsfw ? " nsfw" : ""}" aria-hidden="true">${i.thumb ? `<img src="${i.thumb}" alt="">` : "<svg class=i aria-hidden=true focusable=false><use href=#i-cube></use></svg>"}</div>${matLabel(i)}
    <div class="meta"><h2><a href="#" data-open="${i.id}">${esc(i.title)}</a></h2><span>${esc(i.creator)}</span></div><div class="cardfoot">${favHTML(i)}</div></li>`).join("")
    : `<li class="empty"><p>No favorites yet. Tap the heart on any project to save it here.</p><a class="btn" href="#showcase">Open Showcase</a></li>`;
}
$("#favGrid").addEventListener("click", e => { const c = e.target.closest("a[data-open]"); if (c) { e.preventDefault(); openItem(c.dataset.open); } });

/* ---------- remix credit chain ---------- */
function remixHTML(chain) {
  const step = x => x.id ? `<a href="#" data-open-item="${x.id}">${esc(x.title)}</a> by ${x.creator_id && x.creator !== "ZEIM" ? `<a href="#u/${x.creator_id}">${esc(x.creator)}</a>` : esc(x.creator || "")}` : esc(x.title);
  return `<p class="remix"><svg class=i aria-hidden=true focusable=false><use href=#i-repeat></use></svg> Remixed from ${step(chain[0])}${chain.length > 1 ? `<span class="remix-more">, which was remixed from ${chain.slice(1).map(step).join(", remixed from ")}</span>` : ""}</p>`;
}
document.addEventListener("click", e => { const a = e.target.closest("a[data-open-item]"); if (a) { e.preventDefault(); openItem(a.dataset.openItem); } });

/* ---------- 'I printed this' gallery ---------- */
async function loadPrints(id) {
  const g = $("#prGallery"); if (!g) return;
  let r; try { r = await api(`/api/showcase/${id}/prints`); } catch { return; }
  g.innerHTML = r.prints.length ? r.prints.map(p => `<li><figure${p.nsfw && !p.mine ? ' class="prmature"' : ""}><img src="${p.url}" alt="${p.nsfw ? "Photo of a print (mature content)" : `Photo of a print${p.caption ? ": " + esc(p.caption) : ""}`}" loading="lazy">${p.nsfw && !p.mine ? `<button type="button" class="btn small mature-label" data-prshow="${p.id}">Mature content: show</button>` : ""}<figcaption>${p.pending ? '<span class="pill">Waiting for review</span> ' : ""}${esc(p.caption)} <span class="help">${esc(p.by)}</span>
      ${p.mine ? `<button type="button" class="btn small ghost" data-prdel="${p.id}">Delete</button>` : `<button type="button" class="btn small ghost danger" data-prrep="${p.id}"><svg class=i aria-hidden=true focusable=false><use href=#i-flag></use></svg> Report</button>`}</figcaption></figure></li>`).join("")
    : `<li class="help">No print photos yet.</li>`;
  g.onclick = async e => {
    const d = e.target.closest("[data-prdel]"), rp = e.target.closest("[data-prrep]"), sh = e.target.closest("[data-prshow]");
    if (sh) { if (await confirmMature()) { const f = sh.closest("figure"); f.classList.remove("prmature"); sh.remove(); } return; }
    try {
      if (d) { await api(`/api/prints/${d.dataset.prdel}`, { method: "DELETE" }); toast("Photo deleted", "ok"); loadPrints(id); }
      if (rp) { const r2 = await api(`/api/prints/${rp.dataset.prrep}/report`, J("POST", { reason: "not_family_friendly", details: "" })); toast(r2.auto_hidden ? "Thank you. The photo is hidden while a moderator looks at it." : "Thank you. We got your report.", "ok"); }
    } catch (er) { toast(er.message, "err"); }
  };
}

/* ---------- profiles: follow / unfollow, follower and following counts ---------- */
async function openProfile(uid) {
  let u; try { u = await api("/api/users/" + uid); } catch (e) { toast(e.message, "err"); return; }
  $("#pfName").textContent = u.display_name;
  const n = (v, w) => v == null ? "" : `<span class="stat"><b>${v}</b> ${w}</span>`;
  let cols = []; try { cols = (await api("/api/users/" + uid + "/collections")).collections || []; } catch { cols = []; }
  const colStrip = cols.length ? `<h4><svg class="i" aria-hidden="true" focusable="false"><use href="#i-folder"></use></svg> Collections</h4>
    <div class="colstrip">${cols.map(c => `<button type="button" class="colchip" data-col="${esc(c.id)}"><svg class="i" aria-hidden="true" focusable="false"><use href="#i-folder"></use></svg> ${esc(c.name)} <span class="help">${c.count}</span></button>`).join("")}</div>` : "";
  $("#pfBody").innerHTML = `<p class="counts">${n(u.followers, u.followers === 1 ? "follower" : "followers")} ${n(u.following, "following")}</p>
    ${u.can_follow ? `<button type="button" class="btn ${u.following_creator ? "" : "primary"}" id="pfFollow" aria-pressed="${!!u.following_creator}">${u.following_creator ? "✔ Following" : "＋ Follow"}</button>` : ""}
    <p class="help">Following shows their new projects in the Following tab. There are no messages in ZEIM.</p>
    ${colStrip}
    <h4>Projects</h4><ul class="plist">${u.projects.map(i => `<li><a href="#" data-open-item="${i.id}">${esc(i.title)}</a></li>`).join("") || "<li class='help'>None yet</li>"}</ul>`;
  if ($("#pfFollow")) $("#pfFollow").onclick = async () => { try { await api("/api/follow/" + uid, { method: u.following_creator ? "DELETE" : "POST" }); openProfile(uid); } catch (e) { toast(e.message, "err"); } };
  $("#pfBody").querySelectorAll("[data-col]").forEach(b => b.onclick = () => openCollection(b.dataset.col));
  if (!$("#dlgProfile").open) $("#dlgProfile").showModal();
}
document.addEventListener("click", e => { const a = e.target.closest("a.creator-link"); if (a) { e.preventDefault(); openProfile(a.getAttribute("href").split("/").pop()); } });

/* ---------- Showcase collections: group your own models; public adults browse ---------- */
async function loadCollections() {
  const host = $("#colHost"), row = $("#colNewRow"); if (!host) return;
  if (!ME?.signed_up) {
    host.innerHTML = `<p class="help">Make a free account to group your Showcase projects into collections.</p>`;
    if (row) row.hidden = true;
    return;
  }
  if (row) row.hidden = false;
  let r; try { r = await api("/api/me/collections"); } catch (e) { host.innerHTML = `<p class="help">${esc(e.message)}</p>`; return; }
  host.innerHTML = r.collections.length
    ? `<ul class="collist">${r.collections.map(c => `<li><details data-cid="${esc(c.id)}"><summary><b>${esc(c.name)}</b> <span class="help">${c.count} project${c.count === 1 ? "" : "s"} · ${c.public ? "public" : "private"}</span></summary><div class="colbody"></div></details></li>`).join("")}</ul>`
    : `<p class="help">No collections yet. Create one below, then add your projects from a project page.</p>`;
  host.querySelectorAll("details[data-cid]").forEach(d => d.addEventListener("toggle", async () => {
    if (!d.open || d.dataset.loaded) return; d.dataset.loaded = "1";
    const body = d.querySelector(".colbody");
    try {
      const c = await api(`/api/collections/${d.dataset.cid}`);
      body.innerHTML = `${c.items.length ? `<ul class="plist">${c.items.map(i => `<li><a href="#" data-open-item="${esc(i.id)}">${esc(i.title)}</a></li>`).join("")}</ul>` : `<p class="help">Empty — open one of your projects and add it here.</p>`}
        <div class="field"><label for="colRn_${esc(c.id)}">Rename</label><div class="row"><input id="colRn_${esc(c.id)}" maxlength="60" value="${esc(c.name)}"><button type="button" class="btn small colrn">Save name</button></div></div>
        <div class="row"><label class="inl"><input type="checkbox" class="colpub" ${c.public ? "checked" : ""}> Public on my profile</label>
          <button type="button" class="btn ghost danger small coldel">Delete collection</button>
          <button type="button" class="btn ghost small colopen">Open</button></div>`;
      body.querySelector(".colrn").onclick = async () => {
        try { await api(`/api/me/collections/${c.id}`, J("PUT", { name: body.querySelector("input").value.trim() })); toast("Renamed", "ok"); loadCollections(); }
        catch (er) { toast(er.message, "err"); }
      };
      body.querySelector(".colpub").onchange = async e => {
        try { await api(`/api/me/collections/${c.id}`, J("PUT", { public: e.target.checked })); toast("Collection updated", "ok"); }
        catch (er) { e.target.checked = !e.target.checked; toast(er.message, "err"); }
      };
      body.querySelector(".coldel").onclick = async () => {
        if (!(await askConfirm({ title: "Delete this collection?", message: `Delete “${c.name}”? Your projects stay in Showcase.`, okLabel: "Delete", danger: true }))) return;
        try { await api(`/api/me/collections/${c.id}`, { method: "DELETE" }); toast("Collection deleted", "ok"); loadCollections(); }
        catch (er) { toast(er.message, "err"); }
      };
      body.querySelector(".colopen").onclick = () => openCollection(c.id);
    } catch (er) { body.innerHTML = `<p class="help">${esc(er.message)}</p>`; }
  }));
}
$("#colNewGo")?.addEventListener("click", async () => {
  const name = $("#colNewName")?.value.trim(), btn = $("#colNewGo");
  if (!name) return inlineMsg(btn, "Give the collection a name.");
  try {
    await api("/api/me/collections", J("POST", { name, public: $("#colNewPub")?.checked !== false }));
    $("#colNewName").value = ""; clearInline(btn); toast("Collection created", "ok"); loadCollections();
  } catch (e) { inlineMsg(btn, e.message); }
});

async function openCollection(cid) {
  let c; try { c = await api("/api/collections/" + cid); } catch (e) { toast(e.message, "err"); return; }
  $("#colDlgName").textContent = c.name;
  $("#colDlgBody").innerHTML = `<p class="help">by ${esc(c.by || "a ZEIM maker")} · ${c.count} project${c.count === 1 ? "" : "s"}${c.public ? "" : " · private"}</p>
    <ul class="plist">${(c.items || []).map(i => `<li><a href="#" data-open-item="${esc(i.id)}">${esc(i.title)}</a></li>`).join("") || "<li class='help'>No projects visible here.</li>"}</ul>`;
  if (!$("#dlgCollection").open) $("#dlgCollection").showModal();
}

async function mountItemCollections(host, id) {
  let r; try { r = await api(`/api/me/collections?item=${encodeURIComponent(id)}`); } catch { return; }
  const on = new Set(r.holding || []);
  host.innerHTML = `<details class="itcol"><summary class="btn ghost"><svg class="i" aria-hidden="true" focusable="false"><use href="#i-folder"></use></svg> Add to a collection${on.size ? ` (${on.size})` : ""}</summary>
    <fieldset class="reasons"><legend>Your collections</legend>${r.collections.length ? r.collections.map(c =>
      `<label class="inl"><input type="checkbox" data-col="${esc(c.id)}" ${on.has(c.id) ? "checked" : ""}> ${esc(c.name)} <em class="help">${c.public ? "public" : "private"}</em></label>`).join("")
      : `<p class="help">No collections yet. Name one below.</p>`}</fieldset>
    <div class="field"><label for="itColNew">New collection</label><input id="itColNew" maxlength="60" placeholder="Desk organizers"></div>
    <label class="inl"><input type="checkbox" id="itColPub" checked> Public on my profile</label>
    <div class="row"><button type="button" class="btn" id="itColGo">Create and add</button></div></details>`;
  host.querySelectorAll("[data-col]").forEach(cb => cb.onchange = async () => {
    try { await api(`/api/me/collections/${cb.dataset.col}/items`, J("POST", { item_id: id, on: cb.checked })); toast(cb.checked ? "Added to collection" : "Removed from collection", "ok"); if (document.body.dataset.view === "account") loadCollections(); }
    catch (e) { cb.checked = !cb.checked; toast(e.message, "err"); }
  });
  host.querySelector("#itColGo").onclick = async () => {
    const name = host.querySelector("#itColNew").value.trim(), btn = host.querySelector("#itColGo");
    if (!name) return inlineMsg(btn, "Give the collection a name.");
    try {
      const c = await api("/api/me/collections", J("POST", { name, public: host.querySelector("#itColPub").checked }));
      await api(`/api/me/collections/${c.id}/items`, J("POST", { item_id: id, on: true }));
      toast(`Added to “${c.name}”`, "ok"); mountItemCollections(host, id); host.querySelector("details").open = true;
      if (document.body.dataset.view === "account") loadCollections();
    } catch (e) { inlineMsg(btn, e.message); }
  };
}
