import { S, api, toast, inlineMsg, clearInline, $, $$, esc, MODE_LABEL, ago, applyMode } from "/static/app.js";

const J = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
let CFG = null, ME = null, shTab = "trending";

/* ---------- config / branding (names come from app/branding.py) ---------- */
async function init() {
  CFG = await api("/api/config");
  document.title = CFG.product;
  $$("[data-sec]").forEach(e => e.textContent = CFG.sections[e.dataset.sec] || e.textContent);
  $("#logoImg").alt = CFG.product;
  $("#shTabs").innerHTML = Object.entries(CFG.showcase_tabs).map(([k, v]) => `<button data-tab="${k}" class="${k === shTab ? "on" : ""}">${esc(v)}</button>`).join("");
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
  refreshClassBar();
}
/* Teacher mode's bar: reads the teacher's own classes; shows nothing it cannot read. */
async function refreshClassBar() {
  const box = $("#cbRooms"); if (!box) return;
  if (!(ME.signed_up && ME.age_group === "adult")) return;
  try {
    const rooms = (await api("/api/classrooms")).rooms;
    box.innerHTML = rooms.length ? rooms.slice(0, 3).map(r => `<span class="cbroom"><b>${esc(r.name)}</b> · Join code <span class="code" aria-label="${esc(r.code.split("").join(" "))}">${esc(r.code)}</span> · Students sending files out of ZEIM: <b>${r.send_enabled ? "On" : "Off"}</b></span>`).join(" ") + (rooms.length > 3 ? ` <span>+${rooms.length - 3} more in Teacher tools</span>` : "")
      : "No class yet. Open Teacher tools to make one.";
  } catch { box.textContent = "Open Teacher tools to see your classes."; }
}
document.addEventListener("zeim:level", () => { if (S.level === "teacher" && typeof ME !== "undefined" && ME) refreshClassBar(); });
$("#btnTeacherTools").onclick = () => $("#btnTeacher").click();

/* ---------- views ---------- */
function show(view) {
  $$("#mainNav button").forEach(b => { b.classList.toggle("on", b.dataset.view === view); if (b.dataset.view === view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  $("#viewCreate").hidden = view !== "create"; $("#viewShowcase").hidden = view !== "showcase"; $("#viewLearn").hidden = view !== "learn"; $("#viewEdit").hidden = view !== "edit";
  if (view === "edit") document.dispatchEvent(new CustomEvent("zeim:edit-shown"));
  if (view === "showcase") loadShowcase();
  if (view === "learn") loadLearn();
}
$$("#mainNav button").forEach(b => b.onclick = () => { location.hash = b.dataset.view === "create" ? "" : b.dataset.view; });
function route() {
  const h = location.hash.replace("#", "").split("/");
  if (h[0] === "join") { show("learn"); $("#j_code").value = (h[1] || "").toUpperCase(); $("#dlgJoin").showModal(); history.replaceState({}, "", "#learn"); return; }
  show(["showcase", "learn", "edit"].includes(h[0]) ? h[0] : "create");
  if (h[0] === "learn" && h[1]) setTimeout(() => openLesson(h[1]), 150);
}
addEventListener("hashchange", route);

/* ---------- account ---------- */
$("#btnAccount").onclick = () => { renderAccount(); $("#dlgAccount").showModal(); };
function renderAccount() {
  if (!ME.signed_up) {
    $("#accBody").innerHTML = `<p class="help">An account lets you save your settings and share projects. Learning with a class? You don't need an account — ask your teacher for the class code and join in the ${esc(CFG.sections.learn)}.</p>
      <div class="field"><label>Display name (not your full name)</label><input id="su_name" maxlength="40"></div>
      <div class="field"><label for="su_user">Username <em>optional · this is the name your projects are credited to</em></label><input id="su_user" maxlength="20" autocomplete="off" autocapitalize="none" spellcheck="false">
        <small class="help">3 to 20 letters, numbers or underscores. Under 18? ZEIM makes you a friendly nickname instead, and you can change it later. Not your real name, email or phone number.</small></div>
      <div class="field"><label>Date of birth <em>used only to apply age-appropriate safety defaults</em></label><input id="su_dob" type="date"></div>
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
    $("#su_go").onclick = async () => {
      try { ME = await api("/api/me/signup", J("POST", { display_name: $("#su_name").value, dob: $("#su_dob").value, username: $("#su_user").value.trim() })); await refreshMe(); renderAccount(); toast("Account created. Your username is @" + ME.username, "ok"); }
      catch (e) {
        if (e.status === 403 && /^We can't create an account/.test(e.message)) {     // the neutral age refusal: a calm panel instead of an unchanged form
          $("#accBody").innerHTML = `<div class="calm" role="alert" tabindex="-1"><p>${esc(e.message)}</p><p class="help">You can still join a class with a code from your teacher.</p><button class="btn primary" id="suJoin">Join a class</button></div>`;
          $("#suJoin").onclick = () => { $("#dlgAccount").close(); $("#dlgJoin").showModal(); };
          $("#accBody .calm").focus();
        } else inlineMsg($("#su_go"), e.message);
      }
    };
  } else {
    const r = ME.restrictions, pv = ME.privacy;
    const nextUn = ME.username_next_change ? new Date(ME.username_next_change).toLocaleDateString() : null;
    $("#accBody").innerHTML = `<p><b>${esc(ME.display_name)}</b> <span class="pill">${ME.age_group}</span></p>
      <h4>Your username</h4>
      <p>Credit for what you share goes to <b id="un_now">@${esc(ME.username || "")}</b>. Your email is never shown to anyone.</p>
      <div class="field"><label for="un_new">New username</label><input id="un_new" maxlength="20" autocomplete="off" autocapitalize="none" spellcheck="false" ${nextUn ? "disabled" : ""}>
        <small class="help" id="un_help">${nextUn ? "You can change your username again on " + esc(nextUn) + "." : "3 to 20 letters, numbers or underscores. You can change it once every 90 days. The old name stays saved for you, so nobody else can take it. Please don't use your real name."}</small></div>
      <div class="row"><button class="btn small" id="un_save" ${nextUn ? "disabled" : ""}>Change username</button><button class="btn small ghost" id="un_suggest" ${nextUn ? "disabled" : ""}>Suggest names</button></div>
      <div class="row" id="un_sugg"></div>
      <p class="help">Public page: <a href="/u/${ME.id}" target="_blank">/u/${ME.id}</a> (only if your profile is visible to the viewer)</p>
      <h4>🔒 Privacy</h4>
      <div class="field"><label>Profile page</label><select id="pv_profile">${[["public", "Public"], ["followers", "Followers only"], ["private", "Private — only me"]].map(([v, t]) => `<option value="${v}" ${pv.profile === v ? "selected" : ""} ${v !== "private" && ME.age_group === "teen" ? "disabled" : ""}>${t}</option>`).join("")}</select></div>
      <div class="field"><label>Default for new builds &amp; projects</label><select id="pv_def">${[["private", "Private — only me"], ["followers", "Followers only"], ["public", "Public"]].map(([v, t]) => `<option value="${v}" ${pv.default_visibility === v ? "selected" : ""} ${v !== "private" && ME.age_group === "teen" ? "disabled" : ""}>${t}</option>`).join("")}</select></div>
      ${ME.age_group === "teen" ? '<p class="help">For now, accounts under 18 keep everything <b>Private</b>. You can still make, edit and download your projects.</p>' : ""}
      <label class="inl"><input type="checkbox" id="pv_social" ${pv.social === "on" ? "checked" : ""}> Allow following (I can follow others and others can follow me)</label>
      <p class="help">Turning following <b>off</b> removes all your follows and followers immediately, hides follow buttons and follower counts for you, and turns “followers only” items into private ones. Everything starts Private; every build and project can be changed individually.</p>
      <div class="row"><button class="btn small" id="pv_save">Save privacy</button><button class="btn small ghost" id="pv_followers">My followers</button></div>
      <ul class="help"><li>Direct messages from strangers: <b>off</b> (messaging between people: Coming soon)</li>
      <li>Social link-outs on your public profile: <b>${r.public_link_outs ? "shown (unverified)" : "hidden — teen account"}</b></li>
      <li>Classroom tools: <b>${r.can_create_classroom ? "available" : "adults only"}</b></li></ul>
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
    $("#pv_followers").onclick = async () => { const f = await api("/api/me/followers"); toast(!f.enabled ? "Following is off, so there are no followers." : f.followers.length ? "Followers: " + f.followers.map(x => x.display_name).join(", ") : "No followers yet."); };
  }
}

/* ---------- Sign out (there are no passwords yet, so say plainly how to get back in before anyone presses it) ---------- */
function openSignout() {
  const adult = ME.age_group === "adult", body = $("#soBody"), go = $("#soGo");
  go.disabled = true; clearInline(go.parentElement);
  body.innerHTML = adult
    ? `<p>ZEIM has no passwords yet. To open this account again later, here or on another device, you need a <b>recovery code</b>.</p>
       <p class="help">Showing a new code makes any older code stop working.</p>
       <button type="button" class="btn" id="soCodeBtn">Show my recovery code</button><p id="soCode" role="status"></p>
       <label class="inl"><input type="checkbox" id="soOk" disabled> I have written down my recovery code</label>`
    : `<p>Accounts under 18 don't have recovery codes yet, so after you sign out <b>this account can't be opened again</b>. Your projects stay private.</p>
       <label class="inl"><input type="checkbox" id="soOk"> I understand I can't get this account back</label>`;
  $("#soOk").onchange = e => { go.disabled = !e.target.checked; };
  if (adult) $("#soCodeBtn").onclick = async () => {
    try { const r = await api("/api/me/recovery-code", J("POST")); $("#soCode").innerHTML = `Your recovery code: <b class="code">${esc(r.recovery_code)}</b>`; $("#soOk").disabled = false; }
    catch (e) { $("#soCode").textContent = e.message; }
  };
  go.onclick = async () => {
    try { await api("/api/me/signout", J("POST")); try { sessionStorage.zeimSignedOut = "1"; } catch { } location.reload(); }
    catch (e) { inlineMsg(go.parentElement, e.message); }
  };
  $("#dlgSignout").showModal();
}
try { if (sessionStorage.zeimSignedOut) { delete sessionStorage.zeimSignedOut; setTimeout(() => toast("You're signed out. This browser no longer has your account.", "ok"), 300); } } catch { }

/* ---------- showcase grid ---------- */
const MODE_ICON = { lithophane: "🖼️", relief: "⛰️", popart: "🎨", edit: "✏️" };
async function loadShowcase() {
  const q = $("#shSearch").value.trim();
  $("#shClear").hidden = !q;
  let r;
  try { r = await api(`/api/showcase?tab=${shTab}&q=${encodeURIComponent(q)}`); } catch (e) { toast(e.message, "err"); return; }
  $("#shNotice").textContent = r.example_notice || "";
  $("#shSub").textContent = r.subtitle || "";
  $("#shCount").textContent = q ? `${r.result_count} project${r.result_count === 1 ? "" : "s"} match "${q}"` : "";
  // Example cards show NO numbers at all (not 0, not a dash); counts also arrive as null for under-18 creators.
  $("#shGrid").innerHTML = r.items.map(i => `<li class="pcard" data-item="${i.id}"><div class="ph" aria-hidden="true">${i.thumb ? `<img src="${i.thumb}" alt="">` : (MODE_ICON[i.mode] || "🧊")}${i.example ? '<span class="ex">EXAMPLE</span>' : ""}</div>
    <div class="meta"><h2><a href="#" data-open="${i.id}">${esc(i.title)}</a></h2><span>${esc(i.creator)}${i.credit?.licence ? ` · ${esc(i.credit.licence)}` : ""}</span>${i.visibility && i.visibility !== "public" ? `<span class="pill">${esc(i.visibility)}</span>` : ""}</div>
    <div class="cardfoot">${nzHTML(i, { uid: "g" })}${i.downloads != null ? `<span class="dl">⬇ ${i.downloads}<span class="sr-only"> downloads</span></span>` : ""}</div></li>`).join("");
  if (!r.items.length) {
    const e = r.empty || { text: "Nothing here yet. Check back soon.", action: null };
    $("#shGrid").innerHTML = `<li class="empty"><p>${esc(e.text)}</p>${e.action ? `<button class="btn" data-empty="${e.action.do}">${esc(e.action.label)}</button>` : ""}</li>`;
  }
}
$("#shTabs").onclick = e => { const b = e.target.closest("[data-tab]"); if (!b) return; shTab = b.dataset.tab; $$("#shTabs button").forEach(x => x.classList.toggle("on", x === b)); loadShowcase(); };
$("#shGrid").addEventListener("click", e => { const c = e.target.closest("a[data-open]"); if (c) { e.preventDefault(); openItem(c.dataset.open); } });
$("#shForm").onsubmit = e => { e.preventDefault(); loadShowcase(); };            // Search button, Enter and touch-keyboard "Go" all end up here
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
const NZ_OFF = "Your teacher turned nozzles off for your class.";
const nzShort = n => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k" : String(n);
const nzName = n => n == null ? "Nozzle it" : n === 0 ? "Nozzle it, no nozzles yet" : `Nozzle it, ${n} ${n === 1 ? "nozzle" : "nozzles"}`;
const nzNeedsAccount = () => !(ME?.signed_up || ME?.send?.role === "student");
function nzHTML(i, { large = false, uid = "g" } = {}) {
  if (i.example || i.no_nozzle) return "";                                   // examples are seed data: no button, no number
  const n = i.likes == null ? null : i.likes;
  if (i.owned) return `<span class="nz-static">${NZ_SVG}<span>${n == null ? "Your project" : `${n} ${n === 1 ? "nozzle" : "nozzles"}`}</span></span>`;
  if (i.can_like_reason === "not_public") return "";
  const off = i.can_like === false && i.can_like_reason === "class_off", why = `nzwhy-${uid}-${i.id}`;
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
  if (b.dataset.off) { nzSay(NZ_OFF); return; }                              // aria-disabled, not disabled: it stays focusable and says why
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
    else if (er.status === 403 && /teacher/i.test(er.message)) nzSay(er.message, true);
    else { nzSay("Couldn't save your nozzle. Check your connection and try again.", true); toast("Couldn't save your nozzle. Check your connection and try again.", "err"); }
  } finally { $$(`.nz[data-nz="${CSS.escape(id)}"]`).forEach(x => delete x.dataset.busy); }
}, true);
$("#nzAcctMake").onclick = () => { $("#dlgNzAcct").close(); window.__nzWantSignup = true; $("#btnAccount").click(); };
$("#nzAcctLater").onclick = () => { $("#dlgNzAcct").close(); window.__nzOpener?.focus(); };
document.addEventListener("zeim:me", () => { if (window.__nzWantSignup && ME?.signed_up) { window.__nzWantSignup = false; nzSay("Account made. You can nozzle projects now."); } });

async function openItem(id) {
  const i = await api("/api/showcase/" + id);
  $("#itTitle").textContent = i.title;
  $("#itBody").innerHTML = `${i.example ? '<p class="pill">EXAMPLE seed data — not a real creator project</p>' : ""}
    ${i.thumb ? `<img src="${i.thumb}" alt="Preview picture of ${esc(i.title)}" style="max-width:100%;border-radius:10px">` : ""}
    <p>${esc(i.description)}</p><p>${i.tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</p>
    <p class="help">by <a class="creator-link" href="/u/${i.creator_id}" target="_blank" rel="noopener noreferrer">${esc(i.creator)}</a> · free${i.downloads != null ? ` · ⬇ ${i.downloads}` : ""}</p>
    ${i.credit ? `<p class="credit-line">Credit: <b>${esc(i.credit.creator)}</b>${i.credit.licence ? ` · Licence: ${/^https:\/\//.test(i.credit.licence_url) ? `<a href="${esc(i.credit.licence_url)}" target="_blank" rel="noopener noreferrer">${esc(i.credit.licence)}</a>` : esc(i.credit.licence)}` : ""} · <a href="/credits">Thank you &amp; credits</a></p>` : ""}
    ${i.owned ? `<div class="field"><label>Who can see this project <em>changes apply immediately</em></label><select id="itVis">${["private", "followers", "public"].map(v => `<option value="${v}" ${i.visibility === v ? "selected" : ""}>${{ private: "🔒 Private — only me", followers: "👥 Followers only", public: "🌐 Public" }[v]}</option>`).join("")}</select></div>` : ""}
    <div class="row">${i.no_model ? '<span class="pill">No model yet</span>' : i.files.map(f => `<a class="btn" href="${f.url}" download>⬇ ${esc(f.name)}</a>`).join("")}
      ${nzHTML(i, { large: true, uid: "d" })}
      ${i.can_follow && !i.example ? `<button class="btn" id="itFollow">${i.following_creator ? "✔ Following" : "＋ Follow creator"}</button>` : ""}
      <button class="btn ghost" id="itShare">🔗 Copy link</button>
      ${i.example ? "" : '<button class="btn ghost danger" id="itReport">⚑ Report</button>'}</div>
    <p class="help">Nozzles and downloads are counted once per person and only for public projects. A feed of the creators you follow: <b>Coming soon</b>.</p>`;
  if ($("#itVis")) $("#itVis").onchange = async e => { try { await api(`/api/showcase/${id}/visibility`, J("PUT", { visibility: e.target.value })); toast("Visibility updated", "ok"); loadShowcase(); } catch (er) { toast(er.message, "err"); openItem(id); } };
  if ($("#itFollow")) $("#itFollow").onclick = async () => { try { await api("/api/follow/" + i.creator_id, { method: i.following_creator ? "DELETE" : "POST" }); openItem(id); } catch (e) { toast(e.message, "err"); } };
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
        $("#dlgReport").close(); toast(r.auto_hidden ? "Thank you. The project is hidden while a grown-up looks at it." : "Thank you. We got your report.", "ok");
        if (r.auto_hidden) { $("#dlgItem").close(); loadShowcase(); }
      } catch (e) { inlineMsg($("#repSend"), e.message); } finally { $("#repSend").disabled = false; }
    };
  };
  $("#dlgItem").showModal();
}

/* publish */
$("#btnPublish").onclick = () => {
  if (!ME.signed_up) { toast("Create an account first to share projects.", "err"); renderAccount(); return $("#dlgAccount").showModal(); }
  $("#pub_title").value = S.current.title; $("#pub_vis").value = ME.privacy?.default_visibility || "private"; $("#dlgPublish").showModal();
};
$("#btnDoPublish").onclick = async () => {
  try {
    const i = await api("/api/showcase", J("POST", { build_id: S.current.id, title: $("#pub_title").value, description: $("#pub_desc").value,
      tags: $("#pub_tags").value.split(","), accept_guidelines: $("#pub_ok").checked, visibility: $("#pub_vis").value }));
    clearInline($("#btnDoPublish")); $("#dlgPublish").close(); toast(i.visibility === "private" ? "Saved as Private — only you can see it. Change it any time." : "Shared! " + location.origin + i.share_url, "ok");
  } catch (e) { inlineMsg($("#btnDoPublish"), e.message); }
};

/* my data */
$("#btnMyData").onclick = openData;
async function openData() {
  const d = await api("/api/me/data");
  const ints = Object.entries(d.interests).sort((a, b) => b[1] - a[1]);
  $("#dataBody").innerHTML = `<p class="help">${esc(d.note)}</p><p>Personalization: <b>${d.enabled ? "on" : "off"}</b></p>
    <h4>Interests</h4><p>${ints.map(([t, w]) => `<span class="tag">${esc(t)} · ${w}</span>`).join("") || "<span class='help'>none yet</span>"}</p>
    <h4>Recent searches</h4><p>${d.searches.map(s => `<span class="tag">${esc(s)}</span>`).join("") || "<span class='help'>none</span>"}</p>`;
  $("#btnToggleP13n").textContent = d.enabled ? "Turn personalization off" : "Turn personalization on";
  $("#btnToggleP13n").onclick = async () => { await api("/api/me/personalization", J("PUT", { enabled: !d.enabled })); openData(); };
  $("#btnClearData").onclick = async () => { await api("/api/me/data", { method: "DELETE" }); toast("Cleared", "ok"); openData(); };
  if (!$("#dlgData").open) $("#dlgData").showModal();
}

/* ---------- learn ---------- */
async function loadLearn() {
  const r = await api("/api/learn/lessons");
  const cls = r.classroom;
  $("#classBanner").innerHTML = cls ? `<div class="banner">🎒 You're in <b>${esc(cls.name)}</b> (teacher: ${esc(cls.teacher)}) as <b>${esc(cls.nickname)}</b>. ${cls.assigned.length ? "Assigned lessons are marked ⭐." : ""}
    <p class="help" id="classNotice">${esc(cls.notice || "")}</p>
    ${cls.hand_up ? `<p class="handup" id="handState" role="status">✋ Your hand is up. Your teacher can see it. <button type="button" class="btn small" id="handDown">Lower my hand</button></p>` : `<p class="sr-only" id="handState" role="status"></p>`}
    ${cls.notifications.map(n => `<div class="note">🔔 ${esc(n.from_name)}: ${esc(n.text)}</div>`).join("")}
    <div class="row" style="margin-top:6px"><span class="help">Quick message to your teacher (pre-set only):</span>${Object.entries(cls.canned).map(([k, t]) => `<button class="btn small" data-req="${k}">${esc(t)}</button>`).join("")}
    <button class="btn small ghost" id="clsFeedback">📝 My projects &amp; feedback</button><button class="btn small ghost" id="clsSubmit">⬆ Submit a build</button></div></div>` : "";
  if (cls) {
    $("#classBanner").onclick = async e => {
      const q = e.target.closest("[data-req]");
      if (q) { try { await api(`/api/classrooms/${cls.code}/requests`, J("POST", { kind: q.dataset.req })); toast("Sent to your teacher", "ok"); if (q.dataset.req === "need_help") { await loadLearn(); $("#handDown")?.focus(); } } catch (er) { toast(er.message, "err"); } }
      if (e.target.id === "handDown") { try { await api(`/api/classrooms/${cls.code}/hand/down`, J("POST")); await loadLearn(); $("#handState").textContent = "Your hand is down."; } catch (er) { toast(er.message, "err"); } }
      if (e.target.id === "clsFeedback") openClassProjects(cls.code);
      if (e.target.id === "clsSubmit") submitToClass(cls.code);
    };
  }
  $("#lessonGrid").innerHTML = r.lessons.map(l => `<div class="pcard" data-lesson="${l.id}"><div class="ph">${l.emoji}</div>
    <div class="meta"><b>${esc(l.title)} ${r.assigned.includes(l.id) ? "⭐" : ""}</b><span>${l.minutes} min · ages ${l.age}</span><div class="help">${esc(l.summary)}</div>
    <div class="bar"><i style="width:${100 * l.done_steps / l.steps}%"></i></div><span>${l.completed ? l.badge : `${l.done_steps}/${l.steps} steps`}</span></div></div>`).join("");
}
$("#lessonGrid").onclick = e => { const c = e.target.closest("[data-lesson]"); if (c) openLesson(c.dataset.lesson); };
async function openLesson(id) {
  const l = await api("/api/learn/lessons/" + id), box = $("#lessonDetail"), p = l.progress;
  box.hidden = false;
  box.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">${l.emoji} ${esc(l.title)}</h2><div class="row"><button class="btn small ghost" id="lsCopy">🔗 Copy share link</button><button class="btn small ghost" id="lsClose">Close</button></div></div>
    <p class="help">${esc(l.objective)}</p>
    <ol>${l.steps.map((s, i) => `<li class="st ${p.steps_done.includes(i) ? "done" : ""}"><label><input type="checkbox" data-step="${i}" ${p.steps_done.includes(i) ? "checked" : ""}><b>${i + 1}. ${esc(s.title)}</b></label><p>${esc(s.body)}</p></li>`).join("")}</ol>
    <div class="quiz"><h4>Quick check</h4><p>${esc(l.quiz.q)}</p>${l.quiz.options.map((o, i) => `<label><input type="radio" name="qz" value="${i}"> ${esc(o)}</label>`).join("")}<button class="btn small" id="qzGo">Check answer</button> <span id="qzOut">${p.quiz_passed ? "✔ passed" : ""}</span></div>
    <div class="row" style="margin-top:12px"><button class="btn primary" id="lsTry">🚀 ${esc(l.try.label)}</button>${p.completed ? '<span class="pill ok">🏅 Lesson complete!</span>' : ""}</div>
    <details class="tn" ${S.level === "teacher" ? "open" : ""}><summary>Teacher notes</summary><p class="help">${esc(l.teacher_notes)}</p></details>`;
  box.scrollIntoView({ behavior: "smooth" });
  $("#lsClose").onclick = () => { box.hidden = true; loadLearn(); };
  $("#lsCopy").onclick = () => { navigator.clipboard?.writeText(location.origin + l.share_url); toast("Link copied", "ok"); };
  $$("[data-step]", box).forEach(c => c.onchange = async () => { await api(`/api/learn/lessons/${id}/steps/${c.dataset.step}`, J("POST", { done: c.checked })); openLesson(id); });
  $("#qzGo").onclick = async () => {
    const v = $$("[name=qz]", box).find(x => x.checked); if (!v) return;
    const r = await api(`/api/learn/lessons/${id}/quiz`, J("POST", { choice: +v.value }));
    $("#qzOut").textContent = r.correct ? "✔ Correct!" : "Not quite — try again"; if (r.correct) setTimeout(() => openLesson(id), 700);
  };
  $("#lsTry").onclick = () => { S.mode = l.try.mode; S.preset = l.try.preset; location.hash = ""; $$("#modeCards input").forEach(i => { i.checked = i.value === S.mode; i.closest(".card").classList.toggle("on", i.checked); }); applyMode(); $("#sSample").click(); toast("Sample photo loaded", "ok"); };
}


/* ---------- Teacher Live view: view-only roster, polled every ~12 s while the window is open ---------- */
let liveTimer = null, liveCode = "", liveHands = new Set(), liveData = null;
const liveAgo = iso => { if (!iso) return "no activity yet"; const m = (Date.now() - new Date(iso)) / 60000; return m < 1 ? "just now" : m < 15 ? Math.floor(m) + " min ago" : "inactive 15+ min"; };
function liveRender() {
  const body = $("#liveRows"), rows = liveData.students.slice();
  if ($("#liveSort").checked) rows.sort((a, b) => (b.hand - a.hand));            // only when the teacher asks; otherwise join order, so rows never jump
  $("#liveEmpty").hidden = rows.length > 0;
  const keep = new Set(rows.map(r => r.id));
  $$("tr[data-sid]", body).forEach(tr => { if (!keep.has(tr.dataset.sid)) tr.remove(); });
  rows.forEach((r, idx) => {
    let tr = body.querySelector(`tr[data-sid="${r.id}"]`);
    if (!tr) { tr = document.createElement("tr"); tr.dataset.sid = r.id; tr.innerHTML = `<th scope="row" class="c-n"></th><td class="c-l" data-l="Lesson"></td><td class="c-m" data-l="Newest model"></td><td class="c-a" data-l="Last activity"></td><td class="c-h" data-l="Hand"></td>`; body.append(tr); }
    tr.querySelector(".c-n").textContent = r.nickname;
    tr.querySelector(".c-l").textContent = r.lesson ? `${r.lesson.title}: ${r.lesson.done_steps} of ${r.lesson.steps} steps` : "No lesson yet";
    tr.querySelector(".c-m").textContent = r.model || "none yet";
    tr.querySelector(".c-a").textContent = liveAgo(r.last_active);
    const h = tr.querySelector(".c-h");
    if (r.hand && !h.dataset.up) h.innerHTML = `<span class="needs">✋ Needs help</span> <button type="button" class="btn small" data-helped="${r.id}">Helped<span class="sr-only"> ${esc(r.nickname)}</span></button>`;
    if (!r.hand && h.dataset.up) h.textContent = "";
    h.dataset.up = r.hand ? "1" : "";
    tr.classList.toggle("hand", !!r.hand);
    if ($("#liveSort").checked && body.children[idx] !== tr) body.insertBefore(tr, body.children[idx] || null);
  });
  const now = new Set(rows.filter(r => r.hand).map(r => r.id)), fresh = rows.filter(r => r.hand && !liveHands.has(r.id));
  if (fresh.length) $("#liveSay").textContent = fresh.map(r => r.nickname).join(", ") + (fresh.length === 1 ? " needs help." : " need help.");
  liveHands = now;
  $("#liveAsOf").textContent = "Updated " + new Date(liveData.as_of).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) + ".";
}
async function livePoll() {
  try { liveData = await api(`/api/classrooms/${liveCode}/live`); liveRender(); }
  catch (e) { $("#liveAsOf").textContent = "Couldn't refresh just now. " + (e.message || "") + " Trying again soon."; }
}
async function openLive(code) {
  liveCode = code; liveHands = new Set(); $("#liveRows").innerHTML = ""; $("#liveSay").textContent = ""; liveData = null;
  $("#dlgTeacher").close(); $("#dlgLive").showModal();
  await livePoll(); clearInterval(liveTimer); liveTimer = setInterval(() => { if (!document.hidden) livePoll(); }, 12000);
}
$("#dlgLive").addEventListener("close", () => { clearInterval(liveTimer); liveTimer = null; });           // stop asking the server when the teacher closes the screen
$("#liveSort").onchange = () => { if (liveData) liveRender(); };
$("#liveRows").onclick = async e => {
  const b = e.target.closest("[data-helped]"); if (!b) return;
  try { await api(`/api/classrooms/${liveCode}/students/${b.dataset.helped}/helped`, J("POST")); await livePoll(); $("#liveSay").textContent = "Marked as helped."; } catch (er) { toast(er.message, "err"); }
};
window.__liveTimer = () => liveTimer;

/* Delete class: an in-app dialog (no browser confirm box). "Keep the class" has focus first; Esc keeps it too. */
function askDeleteClass(code, name, opener) {
  const d = $("#dlgDelClass"); $("#dcName").textContent = name; clearInline($("#dcGo").parentElement);
  d.showModal(); $("#dcKeep").focus();
  $("#dcKeep").onclick = () => { d.close(); opener?.focus(); };
  $("#dcGo").onclick = async () => {
    $("#dcGo").disabled = true;
    try { await api("/api/classrooms/" + code, { method: "DELETE" }); d.close(); toast(`Deleted ${name}.`, "ok"); openTeacher(); }
    catch (e) { inlineMsg($("#dcGo").parentElement, e.message || "That didn't work. The class is still there."); }
    finally { $("#dcGo").disabled = false; }
  };
}

/* classroom */
$("#btnJoinClass").onclick = () => $("#dlgJoin").showModal();
$("#btnDoJoin").onclick = async () => {
  try { const r = await api("/api/classrooms/join", J("POST", { code: $("#j_code").value, nickname: $("#j_nick").value, password: $("#j_pw").value })); clearInline($("#btnDoJoin")); $("#dlgJoin").close(); toast("Joined " + r.name, "ok"); loadLearn(); }
  catch (e) { inlineMsg($("#btnDoJoin"), e.message); }
};
$("#btnTeacher").onclick = openTeacher;
document.addEventListener("click", async e => {
  if (e.target.id === "sendCancel") $("#dlgSend").close();
  if (e.target.id === "sendOn") {
    const code = $("#dlgSend").dataset.code;
    try { await api(`/api/classrooms/${code}/send`, J("PUT", { enabled: true, confirm: true })); } catch (er) { toast(er.message, "err"); }
    $("#dlgSend").close(); openTeacher();
  }
});
async function openTeacher() {
  if (!ME.signed_up || ME.age_group !== "adult") { toast("Teacher tools need an adult account — sign up first.", "err"); renderAccount(); return $("#dlgAccount").showModal(); }
  const [{ rooms }, ls] = await Promise.all([api("/api/classrooms"), api("/api/learn/lessons")]);
  $("#dlgTeacher").querySelector("h3").textContent = "🍎 Teacher tools";
  $("#teacherBody").innerHTML = `<div class="row"><input id="cr_name" placeholder="New class name"><input id="cr_pw" placeholder="Join password (8+ chars)"><button class="btn primary" id="cr_go">Create class</button></div>
    <p class="help">Students join with the class code (or the QR / link below) + your password + a nickname — no accounts, no personal data. Class projects are private to the class. Hand out the password separately; it is not in the QR code.</p>` +
    rooms.map(r => `<div class="printer"><div class="row" style="justify-content:space-between"><b>${esc(r.name)}</b><span>Code: <code style="font-size:15px">${r.code}</code> <button class="btn small ghost" data-cp="${r.code}">Copy code</button> <button class="btn small ghost" data-cl="${r.code}">Copy join link</button></span></div>
      <div class="row"><img src="/api/classrooms/${r.code}/qr.svg" alt="QR code to join ${esc(r.name)}" width="120" height="120" style="background:#fff;border-radius:8px"><span class="help">Scan to open the join page for code <b>${r.code}</b>. Link: <code>${esc(location.origin)}/#join/${r.code}</code> · <a href="/api/classrooms/${r.code}/qr.svg" target="_blank">open QR to print</a></span></div>
      ${r.notifications.length ? `<div class="banner">${r.notifications.map(n => `🔔 ${esc(n.from_name)}: ${esc(n.text)}`).join("<br>")} <button class="btn small" data-rd="${r.code}">Mark read</button></div>` : ""}
      ${r.failed_joins_last_hour ? `<div class="banner">${r.failed_joins_last_hour} wrong password tries in the last hour. If students can't get in, <button class="btn small" data-unlock="${r.code}">Unlock joining</button></div>` : ""}
      <div class="sendsw"><label class="sw"><input type="checkbox" role="switch" data-send="${r.code}" ${r.send_enabled ? "checked" : ""} aria-describedby="sw_${r.code}"> <b>Let students send files to other apps</b> <span class="state">${r.send_enabled ? "On" : "Off"}</span></label>
        <p class="help" id="sw_${r.code}">${r.send_enabled ? `On since ${esc(new Date(r.send_changed).toLocaleString())}. Turn off any time.` : "Off: students can download their own build and send it to you. Nothing else leaves ZEIM."} Why: a build made from a photo contains that photo. Students under 13 can never use outside apps, even if this is on.</p></div>
      <p class="help">Assign: ${ls.lessons.map(l => `<label class="inl"><input type="checkbox" data-as="${r.code}" value="${l.id}" ${r.assigned.includes(l.id) ? "checked" : ""}> ${esc(l.title)}</label>`).join(" ")}</p>
      <table class="studs"><tr><th>Student</th><th>Progress</th><th></th></tr>${r.students.map(s => `<tr><td>${esc(s.nickname)}</td><td>${s.lessons.map(x => `${x.completed ? "✅" : `${x.done_steps}/${x.steps}`}`).join(" · ")}</td><td><button class="btn small ghost" data-talk="${r.code}:${s.id}" title="${esc(r.canned.talk_next_class)}">🗨 Talk next class</button> <button class="btn small ghost" data-mu="${r.code}:${s.id}:${s.muted ? 0 : 1}">${s.muted ? "Unmute" : "Mute"}</button> <button class="btn small ghost danger" data-rs="${r.code}:${s.id}">Remove</button></td></tr>`).join("") || "<tr><td colspan=3 class='help'>No students yet</td></tr>"}</table>
      <h4>Student projects <small class="help">(private to this class)</small></h4>
      ${r.projects.map(p => `<div class="fl"><img src="${p.thumb}" alt=""><span><b>${esc(p.title)}</b> <small>by ${esc(p.student)}</small>${p.feedback.map(f => `<br><small>💬 ${esc(f.comment)}</small>`).join("")}</span><button class="btn small" data-fb="${r.code}:${p.id}">Feedback</button></div>`).join("") || "<p class='help'>No projects yet. When students send builds, they show up here for you to look at first.</p>"}
      <button class="btn small" data-live="${r.code}">Live view</button> <button class="btn small danger" data-dr="${r.code}" data-dr-name="${esc(r.name)}">Delete class</button></div>`).join("");
  if (!$("#dlgTeacher").open) $("#dlgTeacher").showModal();
  $("#cr_go").onclick = async () => { try { await api("/api/classrooms", J("POST", { name: $("#cr_name").value, password: $("#cr_pw").value })); openTeacher(); } catch (e) { inlineMsg($("#cr_go"), e.message); } };
  $("#teacherBody").onclick = async e => {
    const t = e.target;
    if (t.dataset.cp) navigator.clipboard?.writeText(t.dataset.cp), toast("Code copied", "ok");
    if (t.dataset.cl) navigator.clipboard?.writeText(location.origin + "/#join/" + t.dataset.cl), toast("Join link copied (password not included)", "ok");
    if (t.dataset.unlock) { await api(`/api/classrooms/${t.dataset.unlock}/unlock-joins`, J("POST")); toast("Joining unlocked", "ok"); openTeacher(); }
    if (t.dataset.live) { openLive(t.dataset.live); return; }
    if (t.dataset.rd) { await api(`/api/classrooms/${t.dataset.rd}/notifications/read`, J("POST")); openTeacher(); }
    if (t.dataset.talk) { const [c, sid] = t.dataset.talk.split(":"); try { await api(`/api/classrooms/${c}/requests`, J("POST", { kind: "talk_next_class", to: sid })); toast("Request sent", "ok"); } catch (er) { toast(er.message, "err"); } }
    if (t.dataset.mu) { const [c, sid, m] = t.dataset.mu.split(":"); await api(`/api/classrooms/${c}/students/${sid}/mute`, J("PUT", { muted: m === "1" })); openTeacher(); }
    if (t.dataset.fb) { const [c, pid] = t.dataset.fb.split(":"); openFeedback(c, pid); }
    if (t.dataset.rs) { const [c, s] = t.dataset.rs.split(":"); await api(`/api/classrooms/${c}/students/${s}`, { method: "DELETE" }); openTeacher(); }
    if (t.dataset.dr) { askDeleteClass(t.dataset.dr, t.dataset.drName || t.dataset.dr, t); return; }
  };
  $("#teacherBody").onchange = async e => { const t = e.target;
    if (t.dataset.send) {
      const code = t.dataset.send;
      if (!t.checked) { try { await api(`/api/classrooms/${code}/send`, J("PUT", { enabled: false })); } catch (er) { toast(er.message, "err"); } return openTeacher(); }
      t.checked = false;                                  // only turns on after the dialog's explicit Turn on
      const d = $("#dlgSend"); d.dataset.code = code;
      $("#dlgSendName").textContent = (rooms.find(r => r.code === code) || {}).name || code;
      d.showModal(); $("#sendCancel").focus(); return;
    }
    if (!t.dataset.as) return; const ids = $$(`[data-as="${t.dataset.as}"]`).filter(x => x.checked).map(x => x.value); await api(`/api/classrooms/${t.dataset.as}/assign`, J("POST", { lesson_ids: ids })); };
}

function openFeedback(code, pid) {
  const d = $("#dlgFeedback"); $("#fbText").value = ""; clearInline($("#fbSave").parentElement);
  $("#fbSave").onclick = async () => {
    const comment = $("#fbText").value.trim();
    if (!comment) return inlineMsg($("#fbSave").parentElement, "Please write a little feedback first.");
    try { await api(`/api/classrooms/${code}/projects/${pid}/feedback`, J("POST", { comment })); d.close(); toast("Feedback saved", "ok"); openTeacher(); }
    catch (er) { inlineMsg($("#fbSave").parentElement, er.message); }            // the box keeps what was typed
  };
  d.showModal(); $("#fbText").focus();
}
async function submitToClass(code) {
  const b = S.history; if (!b.length) return toast("Build something in the Studio first.", "err");
  const d = $("#dlgPickBuild"); clearInline($("#pbSend").parentElement);
  $("#pbList").innerHTML = b.map((x, i) => `<label class="choice"><input type="radio" name="pbBuild" value="${esc(x.id)}" ${i === 0 ? "checked" : ""}> <span>${esc(x.title)}</span></label>`).join("");
  $("#pbSend").onclick = async () => {
    const id = (document.querySelector('input[name="pbBuild"]:checked') || {}).value; if (!id) return inlineMsg($("#pbSend").parentElement, "Please pick a build.");
    try { await api(`/api/classrooms/${code}/projects`, J("POST", { build_id: id })); d.close(); toast("Submitted — only your class can see it.", "ok"); }
    catch (e) { inlineMsg($("#pbSend").parentElement, e.message); }
  };
  d.showModal(); document.querySelector('input[name="pbBuild"]')?.focus();
}
async function openClassProjects(code) {
  const r = await api(`/api/classrooms/${code}/projects`);
  $("#teacherBody").innerHTML = `<p class="help">Projects here are private to your class.</p>` + (r.projects.map(p => `<div class="fl"><img src="${p.thumb}" alt=""><span><b>${esc(p.title)}</b> <small>by ${esc(p.student)}</small>${p.feedback.map(f => `<br><small>💬 ${esc(f.teacher)}: ${esc(f.comment)}</small>`).join("") || "<br><small class='help'>No feedback yet</small>"}</span></div>`).join("") || "<p class='help'>Nothing here yet. Check back soon.</p>");
  $("#dlgTeacher").querySelector("h3").textContent = "📝 Class projects & feedback"; $("#dlgTeacher").showModal();
}

init();
