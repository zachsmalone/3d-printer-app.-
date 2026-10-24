/* Account dialog controller for real authentication (passkeys + email codes).
   Original code. Uses ZeimAuth (static/zeim-auth.js) and renders into the existing
   #dlgAccount dialog. community.js delegates here when auth is available; when it is
   not, the legacy cookie-account UI renders exactly as before.
   States: guest (sign up / sign in), legacy cookie account (secure it with a passkey),
   signed-in account (profile + security panel + sign out). */
(function (root) {
  "use strict";
  const $ = s => document.querySelector(s);

  function say(msg, bad) {
    const el = $("#accMsg");
    if (!el) return;
    el.textContent = msg || "";
    el.className = "help" + (bad ? " roleHole" : "");
  }

  const esc = t => {
    const d = document.createElement("div");
    d.textContent = String(t == null ? "" : t);
    return d.innerHTML;                               /* safe by construction: no markup survives */
  };

  function afterIdentityChange() {
    /* Both the account state AND everything account-scoped (builds, Showcase, share
       links) must refresh: a reload is the honest way to get a consistent page. */
    location.reload();
  }

  function calm(e) {
    /* A cancelled WebAuthn prompt is a normal user action, not an error to report loudly. */
    if (e && e.name === "NotAllowedError") { say("No problem — the passkey prompt was cancelled."); return true; }
    if (e && e.name === "SecurityError") { say("This browser blocked the passkey prompt. Try signing in on the page you opened ZEIM from.", true); return true; }
    return false;
  }

  /* ---------- state 1: guest (no account yet) ---------- */
  function renderGuest(me, emailOk) {
    const body = $("#accBody");
    body.innerHTML = `
      <p class="help">Accounts are for adults 18 and over. A passkey is your account — it stays on
        your device, nothing to type or remember. Anyone can build and download without an account.</p>
      <div id="accMsg" class="help" style="min-height:1.2em"></div>
      <div class="field"><label for="au_name">Display name (not your full name)</label>
        <input id="au_name" maxlength="40" autocomplete="nickname"></div>
      <div class="field"><label for="au_dob">Date of birth <em>only to confirm you are 18 or over</em></label>
        <input id="au_dob" type="date"></div>
      <button class="btn primary" id="au_go">Create my account with a passkey</button>
      <p class="mini" style="margin:10px 0 0">Already have a passkey?</p>
      <button class="btn" id="au_in">Sign in with my passkey</button>
      ${emailOk ? `
      <details style="margin-top:10px"><summary>Sign in with an email code instead</summary>
        <div class="field"><label for="au_em">Email</label><input id="au_em" type="email" autocomplete="email"></div>
        <button class="btn small" id="au_em_go">Send my code</button>
        <div class="field" style="margin-top:6px"><label for="au_code">6-digit code</label><input id="au_code" maxlength="6" inputmode="numeric" autocomplete="one-time-code"></div>
        <button class="btn small" id="au_code_go">Verify my code</button>
        <p class="mini">Codes sign you in to an existing account — they do not create one.</p>
      </details>` : ""}
      <h4>Plans</h4><div id="accPlans" class="acc-plans"><p class="help">Loading plans…</p></div>
      <details class="recover" style="margin-top:10px"><summary>Signed out before? Get your account back with a recovery code</summary>
        <div class="field"><label for="rc_code">Recovery code</label><input id="rc_code" maxlength="40" autocomplete="off" autocapitalize="characters" spellcheck="false"></div>
        <button class="btn" id="rc_go">Get my account back</button></details>`;
    $("#au_go").onclick = async () => {
      const name = $("#au_name").value.trim();
      const dob = $("#au_dob").value;
      if (!name) { say("Pick a display name first.", true); return; }
      if (!dob) { say("Your date of birth confirms you are 18 or over — it is required.", true); return; }
      say("Your browser will ask you to save a passkey…");
      try {
        await root.ZeimAuth.signUp(name, dob, "This device");
        afterIdentityChange();
      } catch (e) {
        if (calm(e)) return;
        say(e.message || "The passkey sign-up did not go through.", true);
      }
    };
    $("#au_in").onclick = async () => {
      say("Your browser will ask for your passkey…");
      try {
        await root.ZeimAuth.signInWithPasskey();
        afterIdentityChange();
      } catch (e) {
        if (calm(e)) return;
        say(e.message || "Passkey sign-in did not work.", true);
      }
    };
    $("#rc_go").onclick = async () => {
      try {
        const r = await fetch("/api/me/recover", { method: "POST",
          headers: { "Content-Type": "application/json", "X-Requested-With": "zeim" },
          body: JSON.stringify({ code: $("#rc_code").value }) });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error((j.detail && j.detail.message) || j.message || "That recovery code did not work.");
        body.innerHTML = `<div class="calm" role="status" tabindex="-1"><p>Welcome back, <b>@${esc(j.username || "")}</b>.</p><p>Your new recovery code is <b class="code">${esc(j.recovery_code)}</b>. The old one no longer works. Write this one down and keep it like a password.</p><button class="btn primary" id="rc_done">Done</button></div>`;
        $("#rc_done").onclick = () => afterIdentityChange();
      } catch (e) { say(e.message || "That recovery code did not work.", true); }
    };
    if (emailOk) {
      $("#au_em_go").onclick = async () => {
        const em = $("#au_em").value.trim();
        if (!em) { say("Type your email first.", true); return; }
        try {
          await root.ZeimAuth.requestEmailCode(em);
          say("Code sent — it works for 10 minutes. Check your inbox.");
        } catch (e) { say(e.message || "Could not send the code.", true); }
      };
      $("#au_code_go").onclick = async () => {
        try {
          await root.ZeimAuth.verifyEmailCode($("#au_em").value.trim(), $("#au_code").value.trim());
          afterIdentityChange();
        } catch (e) { say(e.message || "That code did not work.", true); }
      };
    }
  }

  /* ---------- state 2: legacy cookie account -> secure it with a passkey ---------- */
  function renderLegacy(me) {
    const body = $("#accBody");
    body.innerHTML = `
      <div class="calm" role="status">
        <p>You are signed in as <b>${esc(me.display_name)}</b> with an old-style browser account.</p>
        <p>Add a passkey to secure this account — your name, projects and settings stay exactly
          as they are, and this browser stops depending on its cookie.</p>
      </div>
      <div id="accMsg" class="help" style="min-height:1.2em"></div>
      <button class="btn primary" id="au_up">Secure my account with a passkey</button>
      <p class="mini" style="margin-top:10px">Or keep using the cookie account for now — everything keeps working.</p>
      <h4>Plans</h4><div id="accPlans" class="acc-plans"><p class="help">Loading plans…</p></div>`;
    $("#au_up").onclick = async () => {
      say("Your browser will ask you to save a passkey…");
      try {
        await root.ZeimAuth.addPasskey("This device");
        afterIdentityChange();                       /* the server retires the legacy cookie */
      } catch (e) {
        if (calm(e)) return;
        say(e.message || "The passkey upgrade did not go through.", true);
      }
    };
  }

  /* ---------- state 3: signed in with a real auth session ---------- */
  function renderSignedIn(me) {
    const body = $("#accBody");
    body.innerHTML = `
      <div class="calm" role="status">
        <p>Signed in as <b>${esc(me.display_name)}</b>${me.username ? ` (@${esc(me.username)})` : ""}.</p>
      </div>
      <div id="accMsg" class="help" style="min-height:1.2em"></div>
      <div id="accSecurity"></div>
      <button class="btn" id="au_out" style="margin-top:10px">Sign out</button>
      <h4>Plans</h4><div id="accPlans" class="acc-plans"><p class="help">Loading plans…</p></div>`;
    root.ZeimAuth.mountSecurityPanel($("#accSecurity"), {
      onSignedOut: afterIdentityChange,
      emailAvailable: !!(me.auth && me.auth.email_codes),   /* do not offer email adding when the server cannot send codes */
    });
    $("#au_out").onclick = async () => {
      try {
        await root.ZeimAuth.signOut();
        afterIdentityChange();
      } catch (e) { say(e.message || "Sign out did not work.", true); }
    };
  }

  /* ---------- entry points ---------- */
  function handles(me) {
    /* Synchronous on purpose: community.js must not await this decision, or a Promise
       (always truthy) would hide the legacy UI. Only confirmed unavailability falls back. */
    return !!(root.ZeimAuth && me && me.auth && me.auth.available);
  }

  async function render(me) {
    if (!handles(me)) return false;
    try {
      if (me.auth.session) renderSignedIn(me);
      else if (me.signed_up) renderLegacy(me);       // cookie account: offer the upgrade
      else renderGuest(me, !!me.auth.email_codes);
      return true;
    } catch (e) {
      /* Auth is available but rendering failed: show the failure — never silently
         downgrade to the legacy cookie signup as if passkeys did not exist. */
      try {
        $("#accBody").innerHTML = `<div class="calm" role="alert"><p>The account panel could not load.</p>
          <p class="help">Refresh the page and try again. You can keep building either way.</p></div>`;
      } catch (_) { /* nothing more we can do */ }
      return true;
    }
  }

  root.ZeimAccount = { handles, render };
})(window);
