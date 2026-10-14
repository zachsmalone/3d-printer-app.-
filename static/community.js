import { S, api, toast, inlineMsg, clearInline, askConfirm, $, $$, esc, MODE_LABEL, ago, applyMode, loadHistory } from "/static/app.js";
import { P, loadCatalog, pickerHTML, wirePicker, readPicker, savePref, badgeHTML, checkShowcase } from "/static/printer.js";

const J = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
let CFG = null, ME = null, shTab = "trending";

/* ---------- config / branding (names come from app/branding.py) ---------- */
async function init() {
  CFG = await api("/api/config");
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
const VIEWS = { showcase: "#viewShowcase", slicer: "#viewEdit", cad: "#viewCad", lithophane: "#viewCreate", smartfix: "#viewFix", account: "#viewAccount", learn: "#viewLearn" };
const ALIAS = { "": "showcase", edit: "slicer", create: "lithophane", studio: "lithophane" };
function show(view) {
  const tab = view === "learn" ? "account" : view;
  $$("#mainNav button").forEach(b => { b.classList.toggle("on", b.dataset.view === tab); if (b.dataset.view === tab) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  Object.entries(VIEWS).forEach(([k, sel]) => { const m = $(sel); if (m) m.hidden = k !== view; });
  document.body.dataset.view = view;
  if (view === "slicer") document.dispatchEvent(new CustomEvent("zeim:edit-shown"));
  if (view === "showcase") loadShowcase();
  if (view === "learn") loadLearn();
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
  if (v === "account") loadFavorites();
}
addEventListener("hashchange", route);

/* ---------- account ---------- */
$("#btnAccount").onclick = () => { renderAccount(); $("#dlgAccount").showModal(); };
function renderAccount() {
  if (!ME.signed_up) {
    $("#accBody").innerHTML = `<p class="help">Accounts are for adults 18 and over. An account lets you save your settings and share projects. Anyone can build and learn in the ${esc(CFG.sections.learn)} without an account, and families can print designs together with an adult account holder.</p>
      <div class="field"><label for="su_name">Display name (not your full name)</label><input id="su_name" maxlength="40"></div>
      <div class="field"><label for="su_user">Username <em>optional · this is the name your projects are credited to</em></label><input id="su_user" maxlength="20" autocomplete="off" autocapitalize="none" spellcheck="false">
        <small class="help">3 to 20 letters, numbers or underscores. Leave it empty and ZEIM makes you a friendly nickname you can change later. Not your real name, email or phone number.</small></div>
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
      <div class="field"><label for="un_new">New username</label><input id="un_new" maxlength="20" autocomplete="off" autocapitalize="none" spellcheck="false" ${nextUn ? "disabled" : ""}>
        <small class="help" id="un_help">${nextUn ? "You can change your username again on " + esc(nextUn) + "." : "3 to 20 letters, numbers or underscores. You can change it once every 90 days. The old name stays saved for you, so nobody else can take it. Please don't use your real name."}</small></div>
      <div class="row"><button class="btn small" id="un_save" ${nextUn ? "disabled" : ""}>Change username</button><button class="btn small ghost" id="un_suggest" ${nextUn ? "disabled" : ""}>Suggest names</button></div>
      <div class="row" id="un_sugg"></div>
      <p class="help">Public page: <a href="/u/${ME.id}" target="_blank">/u/${ME.id}</a> (only if your profile is visible to the viewer)</p>
      <h4>🔒 Privacy</h4>
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
  (adult ? $("#soCodeBtn") : $("#soOk")).focus();            // a11y #10: start on the first thing to do, not the ✕
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
const MODE_ICON = { lithophane: "🖼️", relief: "⛰️", popart: "🎨", edit: "✏️" };
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
    ${i.files.map(f => `<a class="btn small" href="${f.url}" download>⬇ ${i.files.length > 1 ? `Plate ${i.files.indexOf(f) + 1} ` : ""}STL<span class="sr-only"> for ${esc(i.title)}</span></a>`).join("")}</div>`;
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
  try { r = await api(`/api/showcase?tab=${shTab}&q=${encodeURIComponent(q)}&category=${encodeURIComponent(shCat)}`); } catch (e) { toast(e.message, "err"); return; }
  $("#shNotice").textContent = r.originals_notice || "";
  // category filters: built from what THIS viewer may see (hidden categories never reach under-13s)
  $("#shCats").innerHTML = ["", ...(r.categories || [])].map(c => `<button type="button" class="chip${c === shCat ? " on" : ""}" data-cat="${esc(c)}" aria-pressed="${c === shCat}">${c ? esc(c) : "All"}</button>`).join("");
  $("#shSub").textContent = r.subtitle || "";
  loadRecent();
  $("#shCount").textContent = q ? `${r.result_count} project${r.result_count === 1 ? "" : "s"} match "${q}"` : "";
  // Example cards show NO numbers at all (not 0, not a dash); counts also arrive as null for non-public items.
  $("#shGrid").innerHTML = r.items.map(i => `<li class="pcard" data-item="${i.id}"><div class="ph${i.nsfw ? " nsfw" : ""}" aria-hidden="true">${i.thumb ? `<img src="${i.thumb}" alt="">` : (MODE_ICON[i.mode] || "🧊")}${i.example ? '<span class="ex">EXAMPLE</span>' : ""}</div>${matLabel(i)}
    <div class="meta"><h2><a href="#" data-open="${i.id}">${esc(i.title)}</a></h2><span>${i.original ? esc(i.creator) : `<a class="creator-link" href="/u/${i.creator_id}">${esc(i.creator)}</a>`}${i.credit?.licence ? ` · ${esc(i.credit.licence)}` : ""}</span>${i.visibility && i.visibility !== "public" ? `<span class="pill">${esc(i.visibility)}</span>` : ""}</div>
    ${i.original ? origHTML(i) : ""}<div class="cardfoot"><span class="wp" data-wp="${i.files?.length && !i.no_model && !i.example ? i.id : ""}"></span>${nzHTML(i, { uid: "g" })}${favHTML(i)}${i.downloads != null ? `<span class="dl">⬇ ${i.downloads}<span class="sr-only"> downloads</span></span>` : ""}</div></li>`).join("");
  showcaseBadges();
  if (!r.items.length) {
    const e = r.empty || { text: "Nothing here yet. Check back soon.", action: null };
    $("#shGrid").innerHTML = `<li class="empty"><p>${esc(e.text)}</p>${e.action ? `<button class="btn" data-empty="${e.action.do}">${esc(e.action.label)}</button>` : ""}</li>`;
  }
}
$("#shTabs").onclick = e => { const b = e.target.closest("[data-tab]"); if (!b) return; shTab = b.dataset.tab; $$("#shTabs button").forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-pressed", String(x === b)); }); loadShowcase(); };
$("#shGrid").addEventListener("click", e => { const c = e.target.closest("a[data-open]"); if (c) { e.preventDefault(); openItem(c.dataset.open); } });
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
    ${i.original ? origHTML(i).replace(/<a class="btn small"[^]*?<\/a>/g, "") : ""}${i.original ? origMoreHTML(i) : ""}<p class="help">by ${i.original ? esc(i.creator) : `<a class="creator-link" href="/u/${i.creator_id}" target="_blank" rel="noopener noreferrer">${esc(i.creator)}</a>`} · free${i.downloads != null ? ` · ⬇ ${i.downloads}` : ""}</p>
    ${i.credit ? `<p class="credit-line">Credit: <b>${esc(i.credit.creator)}</b>${i.credit.licence ? ` · Licence: ${/^https:\/\//.test(i.credit.licence_url) ? `<a href="${esc(i.credit.licence_url)}" target="_blank" rel="noopener noreferrer">${esc(i.credit.licence)}</a>` : esc(i.credit.licence)}` : ""} · <a href="/credits">Thank you &amp; credits</a></p>` : ""}
    ${i.owned ? `<div class="field"><label>Who can see this project <em>changes apply immediately</em></label><select id="itVis">${["private", "followers", "public"].map(v => `<option value="${v}" ${i.visibility === v ? "selected" : ""}>${{ private: "🔒 Private — only me", followers: "👥 Followers only", public: "🌐 Public" }[v]}</option>`).join("")}</select></div>` : ""}
    <div class="row">${i.no_model ? '<span class="pill">No model yet</span>' : i.files.map(f => `<a class="btn" href="${f.url}" download>⬇ ${esc(f.name)}</a>`).join("")}
      ${nzHTML(i, { large: true, uid: "d" })}${favHTML(i, true)}
      ${i.can_follow && !i.example ? `<button class="btn" id="itFollow">${i.following_creator ? "✔ Following" : "＋ Follow creator"}</button>` : ""}
      <button class="btn ghost" id="itShare">🔗 Copy link</button>
      ${i.example ? "" : '<button class="btn ghost danger" id="itReport">⚑ Report</button>'}</div>
    <div id="itWill" aria-live="polite"></div>
    <p class="help">Nozzles and downloads are counted once per person and only for public projects. Projects by makers you follow show up in the Following tab.</p>
    <section class="prints" aria-labelledby="prH"><h4 id="prH">I printed this</h4><ul class="pgallery" id="prGallery"></ul>
      ${ME?.signed_up && i.visibility === "public" ? `<details class="prform"><summary class="btn">📷 Add a photo of your print</summary>
        <p class="help">A photo of the printed object only, please: no people, faces, names or addresses. Location data is removed. Every photo is checked by a moderator before anyone else can see it.</p>
        <div class="field"><label for="prFile">Photo</label><input type="file" id="prFile" accept="image/*"></div>
        <div class="field"><label for="prCap">Caption <em>optional</em></label><input id="prCap" maxlength="140" placeholder="Printed in PLA, came out great"></div>
        <label class="inl"><input type="checkbox" id="prAck"> This is my photo and there are no people in it</label>
        <fieldset class="reasons"><legend>Is this NSFW (mild nudity / mature art)? <em>required</em></legend>
          <label class="choice"><input type="radio" name="prNsfw" value="no"> <span>No</span></label><label class="choice"><input type="radio" name="prNsfw" value="yes"> <span>Yes</span></label></fieldset>
        <div class="row"><button class="btn primary" id="prSend" type="button">Share photo</button></div></details>` : ""}</section>`;
  if (i.remix_chain?.length) $("#itBody").insertAdjacentHTML("afterbegin", remixHTML(i.remix_chain));
  loadPrints(id);
  if ($("#prSend")) $("#prSend").onclick = async () => {
    const f = $("#prFile").files[0]; if (!f) return inlineMsg($("#prSend"), "Choose a photo first.");
    const nv = $("[name=prNsfw]:checked")?.value; if (!nv) return inlineMsg($("#prSend"), "Please answer: Is this NSFW (mild nudity / mature art)?");
    const fd = new FormData(); fd.append("photo", f); fd.append("caption", $("#prCap").value); fd.append("photo_ack", $("#prAck").checked); fd.append("nsfw", nv);
    $("#prSend").disabled = true;
    try { await api(`/api/showcase/${id}/prints`, { method: "POST", body: fd }); clearInline($("#prSend")); toast("Thanks! Your photo is waiting for review. Only you can see it until a moderator approves it.", "ok"); $("#prFile").value = ""; $("#prCap").value = ""; loadPrints(id); }
    catch (e) { inlineMsg($("#prSend"), e.message); } finally { $("#prSend").disabled = false; }
  };
  if ($("#itVis")) $("#itVis").onchange = async e => { try { await api(`/api/showcase/${id}/visibility`, J("PUT", { visibility: e.target.value })); toast("Visibility updated", "ok"); loadShowcase(); } catch (er) { toast(er.message, "err"); openItem(id); } };
  if ($("#itFollow")) $("#itFollow").onclick = async () => { try { await api("/api/follow/" + i.creator_id, { method: i.following_creator ? "DELETE" : "POST" }); openItem(id); } catch (e) { toast(e.message, "err"); } };
  if (!i.no_model && !i.example && i.files?.length) loadCatalog().then(async () => {
    const put = r => { const w = $("#itWill"); if (!w) return; w.innerHTML = badgeHTML(r, { detail: true }) + (r.checks?.slices?.ok == null ? `<button type="button" class="btn" id="itSliceCheck">Test-slice it for my printer</button>` : "");
      const b = $("#itSliceCheck"); if (b) b.onclick = async () => { b.disabled = true; b.textContent = "Slicing…"; try { put(await checkShowcase(id, true)); } catch (e) { b.textContent = e.message; } }; };
    put(await checkShowcase(id)); }).catch(() => { });
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
  $("#pub_title").value = S.current.title; $("#pub_vis").value = ME.privacy?.default_visibility || "private"; $$("[name=pub_nsfw]").forEach(r => r.checked = false); $("#dlgPublish").showModal();
};
$("#btnDoPublish").onclick = async () => {
  const nsfw = $("[name=pub_nsfw]:checked")?.value;
  if (!nsfw) return inlineMsg($("#btnDoPublish"), "Please answer: Is this NSFW (mild nudity / mature art)? Yes or No.");
  try {
    const i = await api("/api/showcase", J("POST", { build_id: S.current.id, title: $("#pub_title").value, description: $("#pub_desc").value,
      tags: $("#pub_tags").value.split(","), accept_guidelines: $("#pub_ok").checked, visibility: $("#pub_vis").value, remix_of: $("#pub_remix").value.trim(), nsfw: nsfw === "yes" }));
    clearInline($("#btnDoPublish")); $("#dlgPublish").close(); toast(i.visibility === "private" ? "Saved as Private — only you can see it. Change it any time." : "Shared! " + location.origin + i.share_url, "ok");
  } catch (e) { inlineMsg($("#btnDoPublish"), e.message); }
};

/* What ZEIM knows about you (Kenji S-07): live view, download metadata, delete everything I made */
$("#btnMyData").onclick = openData;
$("#hideMature").onchange = async e => {
  if (!ME?.signed_up) { e.target.checked = false; return toast("Make a free account to change this setting.", "err"); }
  try { await api("/api/me/mature", J("PUT", { hide_mature: e.target.checked })); ME.hide_mature = e.target.checked; loadShowcase(); } catch (er) { toast(er.message, "err"); }
};
async function openData() {
  $("#hideMature").checked = !!ME?.hide_mature;
  const d = await api("/api/me/data");
  const ints = Object.entries(d.interests || {}).sort((a, b) => b[1] - a[1]);
  const acct = d.account;
  const who = acct ? `Signed in as <b>@${esc(acct.username || "")}</b>${acct.display_name ? ` (${esc(acct.display_name)})` : ""}.`
                   : "You are using ZEIM without an account (this browser session only).";
  const pr = acct?.printer ? `<li>Your printer choice: <b>${esc(acct.printer.printer_id || "")}${acct.printer.nozzle != null ? ` · ${esc(String(acct.printer.nozzle))} mm` : ""}</b></li>` : "";
  $("#dataBody").innerHTML = `<p class="help">${esc(d.note)}</p>
    <p>${who}</p>
    <ul class="help">
      <li>Builds and Edit projects: <b>${d.builds_count ?? 0}</b>${(d.builds || []).some(b => b.favorite) ? " (some starred ★)" : ""}</li>
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
  $("#lessonGrid").innerHTML = r.lessons.map(l => `<div class="pcard" data-lesson="${l.id}"><div class="ph">${l.emoji}</div>
    <div class="meta"><h3 class="lt"><a href="#" class="stretch" data-open-lesson="${l.id}">${esc(l.title)}</a></h3><span>${l.minutes} min · ages ${l.age}</span><div class="help">${esc(l.summary)}</div>
    <div class="bar"><i style="width:${100 * l.done_steps / l.steps}%"></i></div><span>${l.completed ? l.badge : `${l.done_steps}/${l.steps} steps`}</span></div></div>`).join("");
}
$("#lessonGrid").onclick = e => { const c = e.target.closest("[data-lesson]"); if (c) { e.preventDefault(); openLesson(c.dataset.lesson); } };   // the title link (keyboard) and a tap anywhere on the card
async function openLesson(id) {
  const l = await api("/api/learn/lessons/" + id), box = $("#lessonDetail"), p = l.progress;
  box.hidden = false;
  box.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">${l.emoji} ${esc(l.title)}</h2><div class="row"><button class="btn small ghost" id="lsCopy">🔗 Copy share link</button><button class="btn small ghost" id="lsClose">Close</button></div></div>
    <p class="help">${esc(l.objective)}</p>
    <ol>${l.steps.map((s, i) => `<li class="st ${p.steps_done.includes(i) ? "done" : ""}"><label><input type="checkbox" data-step="${i}" ${p.steps_done.includes(i) ? "checked" : ""}><b>${i + 1}. ${esc(s.title)}</b></label><p>${esc(s.body)}</p></li>`).join("")}</ol>
    <div class="row" style="margin-top:12px"><button class="btn primary" id="lsTry">🚀 ${esc(l.try.label)}</button>${p.completed ? '<span class="pill ok">🏅 Lesson complete!</span>' : ""}</div>`;
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
  box.innerHTML = `<span class="help">Recent searches</span><ul class="chips">${r.searches.map(q => `<li class="rchip"><button type="button" class="chip" data-recent="${esc(q)}">${esc(q)}</button><button type="button" class="chip x" data-unrecent="${esc(q)}" aria-label="Remove ${esc(q)} from history">✕</button></li>`).join("")}</ul><button type="button" class="btn small ghost" id="shClearHist">Clear history</button>`;
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
  g.innerHTML = r.items.length ? r.items.map(i => `<li class="pcard" data-item="${i.id}"><div class="ph${i.nsfw ? " nsfw" : ""}" aria-hidden="true">${i.thumb ? `<img src="${i.thumb}" alt="">` : "🧊"}</div>${matLabel(i)}
    <div class="meta"><h2><a href="#" data-open="${i.id}">${esc(i.title)}</a></h2><span>${esc(i.creator)}</span></div><div class="cardfoot">${favHTML(i)}</div></li>`).join("")
    : `<li class="empty"><p>No favorites yet. Tap the heart on any project to save it here.</p><a class="btn" href="#showcase">Open Showcase</a></li>`;
}
$("#favGrid").addEventListener("click", e => { const c = e.target.closest("a[data-open]"); if (c) { e.preventDefault(); openItem(c.dataset.open); } });

/* ---------- remix credit chain ---------- */
function remixHTML(chain) {
  const step = x => x.id ? `<a href="#" data-open-item="${x.id}">${esc(x.title)}</a> by ${x.creator_id && x.creator !== "ZEIM" ? `<a href="#u/${x.creator_id}">${esc(x.creator)}</a>` : esc(x.creator || "")}` : esc(x.title);
  return `<p class="remix">🔁 Remixed from ${step(chain[0])}${chain.length > 1 ? `<span class="remix-more">, which was remixed from ${chain.slice(1).map(step).join(", remixed from ")}</span>` : ""}</p>`;
}
document.addEventListener("click", e => { const a = e.target.closest("a[data-open-item]"); if (a) { e.preventDefault(); openItem(a.dataset.openItem); } });

/* ---------- 'I printed this' gallery ---------- */
async function loadPrints(id) {
  const g = $("#prGallery"); if (!g) return;
  let r; try { r = await api(`/api/showcase/${id}/prints`); } catch { return; }
  g.innerHTML = r.prints.length ? r.prints.map(p => `<li><figure><img src="${p.url}" alt="Photo of a print${p.caption ? ": " + esc(p.caption) : ""}" loading="lazy"><figcaption>${p.pending ? '<span class="pill">Waiting for review</span> ' : ""}${esc(p.caption)} <span class="help">${esc(p.by)}</span>
      ${p.mine ? `<button type="button" class="btn small ghost" data-prdel="${p.id}">Delete</button>` : `<button type="button" class="btn small ghost danger" data-prrep="${p.id}">⚑ Report</button>`}</figcaption></figure></li>`).join("")
    : `<li class="help">No print photos yet.</li>`;
  g.onclick = async e => {
    const d = e.target.closest("[data-prdel]"), rp = e.target.closest("[data-prrep]");
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
  $("#pfBody").innerHTML = `<p class="counts">${n(u.followers, u.followers === 1 ? "follower" : "followers")} ${n(u.following, "following")}</p>
    ${u.can_follow ? `<button type="button" class="btn ${u.following_creator ? "" : "primary"}" id="pfFollow" aria-pressed="${!!u.following_creator}">${u.following_creator ? "✔ Following" : "＋ Follow"}</button>` : ""}
    <p class="help">Following shows their new projects in the Following tab. There are no messages in ZEIM.</p>
    <h4>Projects</h4><ul class="plist">${u.projects.map(i => `<li><a href="#" data-open-item="${i.id}">${esc(i.title)}</a></li>`).join("") || "<li class='help'>None yet</li>"}</ul>`;
  if ($("#pfFollow")) $("#pfFollow").onclick = async () => { try { await api("/api/follow/" + uid, { method: u.following_creator ? "DELETE" : "POST" }); openProfile(uid); } catch (e) { toast(e.message, "err"); } };
  if (!$("#dlgProfile").open) $("#dlgProfile").showModal();
}
document.addEventListener("click", e => { const a = e.target.closest("a.creator-link"); if (a) { e.preventDefault(); openProfile(a.getAttribute("href").split("/").pop()); } });
