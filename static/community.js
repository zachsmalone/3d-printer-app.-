import { S, api, toast, $, $$, esc, MODE_LABEL, ago } from "/static/app.js";

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
}
async function refreshMe() {
  ME = await api("/api/me");
  $("#btnAccount").textContent = ME.signed_up ? "👤 " + ME.display_name : "👤 Sign up";
  document.body.dataset.links = ME.send?.links ? "1" : "0";     // the server decides who can use Print / slicer links; the page only reflects it
  document.body.dataset.role = ME.send?.role || "";
}

/* ---------- views ---------- */
function show(view) {
  $$("#mainNav button").forEach(b => b.classList.toggle("on", b.dataset.view === view));
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
      <div class="field"><label>Date of birth <em>used only to apply age-appropriate safety defaults</em></label><input id="su_dob" type="date"></div>
      <button class="btn primary" id="su_go">Create account</button>`;
    $("#su_go").onclick = async () => {
      try { ME = await api("/api/me/signup", J("POST", { display_name: $("#su_name").value, dob: $("#su_dob").value })); await refreshMe(); renderAccount(); toast("Account created", "ok"); }
      catch (e) { toast(e.message, "err"); }
    };
  } else {
    const r = ME.restrictions, pv = ME.privacy;
    $("#accBody").innerHTML = `<p><b>${esc(ME.display_name)}</b> <span class="pill">${ME.age_group}</span></p>
      <p class="help">Public page: <a href="/u/${ME.id}" target="_blank">/u/${ME.id}</a> (only if your profile is visible to the viewer)</p>
      <h4>🔒 Privacy</h4>
      <div class="field"><label>Profile page</label><select id="pv_profile">${[["public", "Public"], ["followers", "Followers only"], ["private", "Private — only me"]].map(([v, t]) => `<option value="${v}" ${pv.profile === v ? "selected" : ""} ${v !== "private" && ME.age_group === "teen" ? "disabled" : ""}>${t}</option>`).join("")}</select></div>
      <div class="field"><label>Default for new builds &amp; projects</label><select id="pv_def">${[["private", "Private — only me"], ["followers", "Followers only"], ["public", "Public"]].map(([v, t]) => `<option value="${v}" ${pv.default_visibility === v ? "selected" : ""} ${v !== "private" && ME.age_group === "teen" ? "disabled" : ""}>${t}</option>`).join("")}</select></div>
      ${ME.age_group === "teen" ? '<p class="help">For now, accounts under 18 keep everything <b>Private</b>. You can still make, edit and download your projects.</p>' : ""}
      <label class="inl"><input type="checkbox" id="pv_social" ${pv.social === "on" ? "checked" : ""}> Allow following (I can follow others and others can follow me)</label>
      <p class="help">Turning following <b>off</b> removes all your follows and followers immediately, hides follow buttons and follower counts for you, and turns “followers only” items into private ones. Everything starts Private; every build and project can be changed individually.</p>
      <div class="row"><button class="btn small" id="pv_save">Save privacy</button><button class="btn small ghost" id="pv_followers">My followers</button></div>
      <ul class="help"><li>Direct messages from strangers: <b>off</b> (free-text messaging isn't built)</li>
      <li>Social link-outs on your public profile: <b>${r.public_link_outs ? "shown (unverified)" : "hidden — teen account"}</b></li>
      <li>Classroom tools: <b>${r.can_create_classroom ? "available" : "adults only"}</b></li></ul>
      <p class="help">Add link-outs in Settings → Promote your accounts.</p>`;
    $("#pv_save").onclick = async () => { try { await api("/api/me/privacy", J("PUT", { profile: $("#pv_profile").value, default_visibility: $("#pv_def").value, social: $("#pv_social").checked ? "on" : "off" })); await refreshMe(); renderAccount(); toast("Privacy saved", "ok"); } catch (e) { toast(e.message, "err"); } };
    $("#pv_followers").onclick = async () => { const f = await api("/api/me/followers"); toast(!f.enabled ? "Following is off, so there are no followers." : f.followers.length ? "Followers: " + f.followers.map(x => x.display_name).join(", ") : "No followers yet."); };
  }
}

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
  $("#shGrid").innerHTML = r.items.map(i => `<div class="pcard" data-item="${i.id}"><div class="ph">${i.thumb ? `<img src="${i.thumb}" alt="">` : (MODE_ICON[i.mode] || "🧊")}${i.example ? '<span class="ex">EXAMPLE</span>' : ""}</div>
    <div class="meta"><b>${esc(i.title)}</b><span>${esc(i.creator)}${i.likes != null ? ` · ♥ ${i.likes}` : ""}${i.downloads != null ? ` · ⬇ ${i.downloads}` : ""}${i.liked_by_others ? " · ♥ liked" : ""}</span>${i.visibility && i.visibility !== "public" ? `<span class="pill">${esc(i.visibility)}</span>` : ""}</div></div>`).join("");
  if (!r.items.length) {
    const e = r.empty || { text: "Nothing here yet. Check back soon.", action: null };
    $("#shGrid").innerHTML = `<div class="empty"><p>${esc(e.text)}</p>${e.action ? `<button class="btn" data-empty="${e.action.do}">${esc(e.action.label)}</button>` : ""}</div>`;
  }
}
$("#shTabs").onclick = e => { const b = e.target.closest("[data-tab]"); if (!b) return; shTab = b.dataset.tab; $$("#shTabs button").forEach(x => x.classList.toggle("on", x === b)); loadShowcase(); };
$("#shGrid").onclick = e => { const c = e.target.closest("[data-item]"); if (c) openItem(c.dataset.item); };
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

async function openItem(id) {
  const i = await api("/api/showcase/" + id);
  $("#itTitle").textContent = i.title;
  $("#itBody").innerHTML = `${i.example ? '<p class="pill">EXAMPLE seed data — not a real creator project</p>' : ""}
    ${i.thumb ? `<img src="${i.thumb}" style="max-width:100%;border-radius:10px">` : ""}
    <p>${esc(i.description)}</p><p>${i.tags.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</p>
    <p class="help">by <a href="/u/${i.creator_id}" target="_blank">${esc(i.creator)}</a> · free${i.downloads != null ? ` · ⬇ ${i.downloads}` : ""}</p>
    ${i.owned ? `<div class="field"><label>Who can see this project <em>changes apply immediately</em></label><select id="itVis">${["private", "followers", "public"].map(v => `<option value="${v}" ${i.visibility === v ? "selected" : ""}>${{ private: "🔒 Private — only me", followers: "👥 Followers only", public: "🌐 Public" }[v]}</option>`).join("")}</select></div>` : ""}
    <div class="row">${i.files.map(f => `<a class="btn" href="${f.url}" download>⬇ ${esc(f.name)}</a>`).join("")}
      ${i.likes != null ? `<button class="btn ${i.liked ? "primary" : ""}" id="itLike" ${i.can_like ? "" : "disabled"} title="${i.can_like ? "Like this model" : "You can't like your own model"}">♥ ${i.liked ? "Liked" : "Like"} · ${i.likes}</button>` : ""}
      ${i.can_follow ? `<button class="btn" id="itFollow">${i.following_creator ? "✔ Following" : "＋ Follow creator"}</button>` : ""}
      <button class="btn ghost" id="itShare">🔗 Copy link</button>
      <button class="btn ghost danger" id="itReport">⚑ Report</button></div>
    <p class="help">Likes and downloads are counted once per visitor and only for public projects. Follow is scaffolding — a feed of followed creators isn't built yet.</p>`;
  if ($("#itLike")) $("#itLike").onclick = async () => { try { await api(`/api/showcase/${id}/like`, J("POST", {})); openItem(id); loadShowcase(); } catch (e) { toast(e.message, "err"); } };
  if ($("#itVis")) $("#itVis").onchange = async e => { try { await api(`/api/showcase/${id}/visibility`, J("PUT", { visibility: e.target.value })); toast("Visibility updated", "ok"); loadShowcase(); } catch (er) { toast(er.message, "err"); openItem(id); } };
  if ($("#itFollow")) $("#itFollow").onclick = async () => { try { await api("/api/follow/" + i.creator_id, { method: i.following_creator ? "DELETE" : "POST" }); openItem(id); } catch (e) { toast(e.message, "err"); } };
  $("#itShare").onclick = () => { navigator.clipboard?.writeText(location.origin + i.share_url); toast("Link copied", "ok"); };
  $("#itReport").onclick = async () => {
    const reason = prompt("Report reason: minor_safety, not_family_friendly, copyright, harassment, personal_info, other", "not_family_friendly");
    if (!reason) return;
    try { const r = await api(`/api/showcase/${id}/report`, J("POST", { reason, details: prompt("Details (optional)") || "" })); toast(r.auto_hidden ? "Reported — hidden pending review. Thank you." : "Report received. Thank you.", "ok"); if (r.auto_hidden) { $("#dlgItem").close(); loadShowcase(); } }
    catch (e) { toast(e.message, "err"); }
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
    $("#dlgPublish").close(); toast(i.visibility === "private" ? "Saved as Private — only you can see it. Change it any time." : "Shared! " + location.origin + i.share_url, "ok");
  } catch (e) { toast(e.message, "err"); }
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
    ${cls.notifications.map(n => `<div class="note">🔔 ${esc(n.from_name)}: ${esc(n.text)}</div>`).join("")}
    <div class="row" style="margin-top:6px"><span class="help">Quick message to your teacher (pre-set only):</span>${Object.entries(cls.canned).map(([k, t]) => `<button class="btn small" data-req="${k}">${esc(t)}</button>`).join("")}
    <button class="btn small ghost" id="clsFeedback">📝 My projects &amp; feedback</button><button class="btn small ghost" id="clsSubmit">⬆ Submit a build</button></div></div>` : "";
  if (cls) {
    $("#classBanner").onclick = async e => {
      const q = e.target.closest("[data-req]");
      if (q) { try { await api(`/api/classrooms/${cls.code}/requests`, J("POST", { kind: q.dataset.req })); toast("Sent to your teacher", "ok"); } catch (er) { toast(er.message, "err"); } }
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
    <details><summary>Teacher notes</summary><p class="help">${esc(l.teacher_notes)}</p></details>`;
  box.scrollIntoView({ behavior: "smooth" });
  $("#lsClose").onclick = () => { box.hidden = true; loadLearn(); };
  $("#lsCopy").onclick = () => { navigator.clipboard?.writeText(location.origin + l.share_url); toast("Link copied", "ok"); };
  $$("[data-step]", box).forEach(c => c.onchange = async () => { await api(`/api/learn/lessons/${id}/steps/${c.dataset.step}`, J("POST", { done: c.checked })); openLesson(id); });
  $("#qzGo").onclick = async () => {
    const v = $$("[name=qz]", box).find(x => x.checked); if (!v) return;
    const r = await api(`/api/learn/lessons/${id}/quiz`, J("POST", { choice: +v.value }));
    $("#qzOut").textContent = r.correct ? "✔ Correct!" : "Not quite — try again"; if (r.correct) setTimeout(() => openLesson(id), 700);
  };
  $("#lsTry").onclick = () => { S.mode = l.try.mode; S.preset = l.try.preset; location.hash = ""; $$("#modeCards .card").forEach(c => c.classList.toggle("on", c.dataset.mode === S.mode)); $("#sSample").click(); toast("Sample photo loaded", "ok"); };
}

/* classroom */
$("#btnJoinClass").onclick = () => $("#dlgJoin").showModal();
$("#btnDoJoin").onclick = async () => {
  try { const r = await api("/api/classrooms/join", J("POST", { code: $("#j_code").value, nickname: $("#j_nick").value, password: $("#j_pw").value })); $("#dlgJoin").close(); toast("Joined " + r.name, "ok"); loadLearn(); }
  catch (e) { toast(e.message, "err"); }
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
      <div class="sendsw"><label class="sw"><input type="checkbox" role="switch" data-send="${r.code}" ${r.send_enabled ? "checked" : ""} aria-describedby="sw_${r.code}"> <b>Let students send files to other apps</b> <span class="state">${r.send_enabled ? "On" : "Off"}</span></label>
        <p class="help" id="sw_${r.code}">${r.send_enabled ? `On since ${esc(new Date(r.send_changed).toLocaleString())}. Turn off any time.` : "Off: students can download their own build and send it to you. Nothing else leaves ZEIM."} Why: a build made from a photo contains that photo. Students under 13 can never use outside apps, even if this is on.</p></div>
      <p class="help">Assign: ${ls.lessons.map(l => `<label class="inl"><input type="checkbox" data-as="${r.code}" value="${l.id}" ${r.assigned.includes(l.id) ? "checked" : ""}> ${esc(l.title)}</label>`).join(" ")}</p>
      <table class="studs"><tr><th>Student</th><th>Progress</th><th></th></tr>${r.students.map(s => `<tr><td>${esc(s.nickname)}</td><td>${s.lessons.map(x => `${x.completed ? "✅" : `${x.done_steps}/${x.steps}`}`).join(" · ")}</td><td><button class="btn small ghost" data-talk="${r.code}:${s.id}" title="${esc(r.canned.talk_next_class)}">🗨 Talk next class</button> <button class="btn small ghost" data-mu="${r.code}:${s.id}:${s.muted ? 0 : 1}">${s.muted ? "Unmute" : "Mute"}</button> <button class="btn small ghost danger" data-rs="${r.code}:${s.id}">Remove</button></td></tr>`).join("") || "<tr><td colspan=3 class='help'>No students yet</td></tr>"}</table>
      <h4>Student projects <small class="help">(private to this class)</small></h4>
      ${r.projects.map(p => `<div class="fl"><img src="${p.thumb}" alt=""><span><b>${esc(p.title)}</b> <small>by ${esc(p.student)}</small>${p.feedback.map(f => `<br><small>💬 ${esc(f.comment)}</small>`).join("")}</span><button class="btn small" data-fb="${r.code}:${p.id}">Feedback</button></div>`).join("") || "<p class='help'>No projects yet. When students send builds, they show up here for you to look at first.</p>"}
      <button class="btn small danger" data-dr="${r.code}">Delete class</button></div>`).join("");
  if (!$("#dlgTeacher").open) $("#dlgTeacher").showModal();
  $("#cr_go").onclick = async () => { try { await api("/api/classrooms", J("POST", { name: $("#cr_name").value, password: $("#cr_pw").value })); openTeacher(); } catch (e) { toast(e.message, "err"); } };
  $("#teacherBody").onclick = async e => {
    const t = e.target;
    if (t.dataset.cp) navigator.clipboard?.writeText(t.dataset.cp), toast("Code copied", "ok");
    if (t.dataset.cl) navigator.clipboard?.writeText(location.origin + "/#join/" + t.dataset.cl), toast("Join link copied (password not included)", "ok");
    if (t.dataset.rd) { await api(`/api/classrooms/${t.dataset.rd}/notifications/read`, J("POST")); openTeacher(); }
    if (t.dataset.talk) { const [c, sid] = t.dataset.talk.split(":"); try { await api(`/api/classrooms/${c}/requests`, J("POST", { kind: "talk_next_class", to: sid })); toast("Request sent", "ok"); } catch (er) { toast(er.message, "err"); } }
    if (t.dataset.mu) { const [c, sid, m] = t.dataset.mu.split(":"); await api(`/api/classrooms/${c}/students/${sid}/mute`, J("PUT", { muted: m === "1" })); openTeacher(); }
    if (t.dataset.fb) { const [c, pid] = t.dataset.fb.split(":"); const comment = prompt("Feedback for this project (text only, max 500 characters):"); if (comment) { try { await api(`/api/classrooms/${c}/projects/${pid}/feedback`, J("POST", { comment })); toast("Feedback saved", "ok"); openTeacher(); } catch (er) { toast(er.message, "err"); } } }
    if (t.dataset.rs) { const [c, s] = t.dataset.rs.split(":"); await api(`/api/classrooms/${c}/students/${s}`, { method: "DELETE" }); openTeacher(); }
    if (t.dataset.dr && confirm("Delete this class and all student progress in it?")) { await api("/api/classrooms/" + t.dataset.dr, { method: "DELETE" }); openTeacher(); }
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

async function submitToClass(code) {
  const b = S.history.filter(x => true); if (!b.length) return toast("Build something in the Studio first.", "err");
  const pick = prompt("Which build? Type a number:\n" + b.map((x, i) => `${i + 1}. ${x.title}`).join("\n"), "1"); const x = b[(+pick || 0) - 1]; if (!x) return;
  try { await api(`/api/classrooms/${code}/projects`, J("POST", { build_id: x.id })); toast("Submitted — only your class can see it.", "ok"); } catch (e) { toast(e.message, "err"); }
}
async function openClassProjects(code) {
  const r = await api(`/api/classrooms/${code}/projects`);
  $("#teacherBody").innerHTML = `<p class="help">Projects here are private to your class.</p>` + (r.projects.map(p => `<div class="fl"><img src="${p.thumb}" alt=""><span><b>${esc(p.title)}</b> <small>by ${esc(p.student)}</small>${p.feedback.map(f => `<br><small>💬 ${esc(f.teacher)}: ${esc(f.comment)}</small>`).join("") || "<br><small class='help'>No feedback yet</small>"}</span></div>`).join("") || "<p class='help'>Nothing here yet. Check back soon.</p>");
  $("#dlgTeacher").querySelector("h3").textContent = "📝 Class projects & feedback"; $("#dlgTeacher").showModal();
}

init();
