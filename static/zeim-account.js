/* Account dialog controller for real authentication (passkeys + password + email codes).
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

  function needPasskey() {
    if (root.ZeimAuth.supportsPasskeys()) return false;
    say("This browser has no passkey. Use a username and password instead.", true);
    return true;
  }

  /* ---------- state 1: guest (no account yet) ---------- */
  function renderGuest(me, emailOk) {
    const body = $("#accBody");
    body.innerHTML = `
      <p class="help">Accounts are for adults 18 and over. Sign in with a username or email and a password, or with a passkey. Anyone can build and download without an account.</p>
      <div id="accMsg" class="help" style="min-height:1.2em"></div>
      <div class="auth-stack">
        <h4>Sign in</h4>
        <div class="field"><label for="au_id">Username or email</label>
          <input id="au_id" maxlength="254" autocomplete="username" autocapitalize="none" spellcheck="false"></div>
        <div class="field"><label for="au_pw">Password</label>
          <input id="au_pw" type="password" maxlength="128" autocomplete="current-password"></div>
        <button class="btn primary" type="button" id="au_pw_go">Sign in</button>
        <button class="btn" type="button" id="au_in">Sign in with my passkey</button>
        ${emailOk ? `
        <details><summary>Forgot your password? Set a new one with an email code</summary>
          <div class="field"><label for="au_reset_em">Email on the account</label>
            <input id="au_reset_em" type="email" autocomplete="email"></div>
          <button class="btn" type="button" id="au_reset_send">Email me a code</button>
          <div class="field"><label for="au_reset_code">6-digit code</label>
            <input id="au_reset_code" maxlength="6" inputmode="numeric" autocomplete="one-time-code"></div>
          <div class="field"><label for="au_reset_pw">New password</label>
            <input id="au_reset_pw" type="password" maxlength="128" autocomplete="new-password"></div>
          <p class="mini">At least 10 characters. A short phrase works well. This signs you in and leaves your passkey in place.</p>
          <button class="btn primary" type="button" id="au_reset_ok">Set password and sign in</button>
        </details>
        <details><summary>Sign in with an email code instead</summary>
          <div class="field"><label for="au_em">Email</label><input id="au_em" type="email" autocomplete="email"></div>
          <button class="btn small" type="button" id="au_em_go">Send my code</button>
          <div class="field" style="margin-top:6px"><label for="au_code">6-digit code</label><input id="au_code" maxlength="6" inputmode="numeric" autocomplete="one-time-code"></div>
          <button class="btn small" type="button" id="au_code_go">Verify my code</button>
          <p class="mini">Codes sign you in to an existing account — they do not create one.</p>
        </details>` : `<p class="mini">Password reset by email is not available on this server. Sign in with your passkey on the phone that saved it, then add a password.</p>`}
        <h4>Create an account</h4>
        <div class="field"><label for="au_name">Display name (not your full name)</label>
          <input id="au_name" maxlength="40" autocomplete="nickname"></div>
        <div class="field"><label for="au_user">Username</label>
          <input id="au_user" maxlength="18" autocomplete="username" autocapitalize="none" spellcheck="false">
          <small class="help">3 to 18 letters, numbers or underscores. This is what you type to sign in. Not your real name or email.</small></div>
        ${emailOk ? `<div class="field"><label for="au_email">Email <em>optional, so you can set a new password later</em></label>
          <input id="au_email" type="email" autocomplete="email"></div>` : ""}
        <div class="field"><label for="au_pw_new">Password</label>
          <input id="au_pw_new" type="password" maxlength="128" autocomplete="new-password">
          <small class="help">At least 10 characters. A short phrase you can remember works well.</small></div>
        <div class="field"><label for="au_pw_new2">Password again</label>
          <input id="au_pw_new2" type="password" maxlength="128" autocomplete="new-password"></div>
        <div class="field"><label for="au_dob">Date of birth <em>only to confirm you are 18 or over</em></label>
          <input id="au_dob" type="date"></div>
        <button class="btn primary" type="button" id="pw_go">Create account</button>
        <button class="btn" type="button" id="au_go">Create my account with a passkey</button>
        <p class="mini">A passkey account uses the display name and birth date. ZEIM picks a username you can change later.</p>
      </div>
      <h4>Plans</h4><div id="accPlans" class="acc-plans"><p class="help">Loading plans…</p></div>
      <details class="recover" style="margin-top:10px"><summary>Signed out before? Get your account back with a recovery code</summary>
        <div class="field"><label for="rc_code">Recovery code</label><input id="rc_code" maxlength="40" autocomplete="off" autocapitalize="characters" spellcheck="false"></div>
        <button class="btn" id="rc_go">Get my account back</button></details>`;
    $("#au_pw_go").onclick = async () => {
      const id = $("#au_id").value.trim();
      const pw = $("#au_pw").value;
      if (!id || !pw) { say("Enter your username or email, and your password.", true); return; }
      say("Signing in…");
      try {
        await root.ZeimAuth.signInWithPassword(id, pw);
        afterIdentityChange();
      } catch (e) { say(e.message || "That sign-in didn't match.", true); }
    };
    $("#pw_go").onclick = async () => {
      const name = $("#au_name").value.trim();
      const user = $("#au_user").value.trim();
      const pw = $("#au_pw_new").value;
      const dob = $("#au_dob").value;
      const email = $("#au_email") ? $("#au_email").value.trim() : "";
      if (!name) { say("Pick a display name first.", true); return; }
      if (!user) { say("Pick a username. You'll type it to sign in.", true); return; }
      if (!pw) { say("Choose a password of at least 10 characters.", true); return; }
      if (pw !== $("#au_pw_new2").value) { say("Those passwords don't match.", true); return; }
      if (!dob) { say("Your date of birth confirms you are 18 or over — it is required.", true); return; }
      say("Creating your account…");
      try {
        const r = await root.ZeimAuth.registerWithPassword(name, dob, user, pw, email);
        if (r && r.email_pending) {
          body.innerHTML = `<div class="calm" role="status"><p>Account created. We sent a code to that email. Enter it to attach the address, so you can set a new password later. You can also skip and do this from Account.</p></div>
            <div id="accMsg" class="help" style="min-height:1.2em"></div>
            <div class="auth-stack">
              <div class="field"><label for="au_email_code">6-digit code</label>
                <input id="au_email_code" maxlength="6" inputmode="numeric" autocomplete="one-time-code"></div>
              <button class="btn primary" type="button" id="au_email_ok">Attach email</button>
              <button class="btn" type="button" id="au_email_skip">Skip for now</button>
            </div>`;
          $("#au_email_ok").onclick = async () => {
            try {
              await root.ZeimAuth.addEmailVerify(email, $("#au_email_code").value.trim());
              afterIdentityChange();
            } catch (e) { say(e.message || "That code didn't work.", true); }
          };
          $("#au_email_skip").onclick = () => afterIdentityChange();
          return;
        }
        if (email && r && r.email_skipped) say("Account created. This server can't send email, so that address wasn't saved.");
        afterIdentityChange();
      } catch (e) { say(e.message || "The account was not created.", true); }
    };
    $("#au_go").onclick = async () => {
      const name = $("#au_name").value.trim();
      const dob = $("#au_dob").value;
      if (!name) { say("Pick a display name first.", true); return; }
      if (!dob) { say("Your date of birth confirms you are 18 or over — it is required.", true); return; }
      if (needPasskey()) return;
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
      if (needPasskey()) return;
      say("Your browser will ask for your passkey…");
      try {
        await root.ZeimAuth.signInWithPasskey();
        afterIdentityChange();
      } catch (e) {
        if (calm(e)) return;
        say(e.message || "Passkey sign-in did not work.", true);
      }
    };
    if (emailOk) {
      $("#au_reset_send").onclick = async () => {
        const em = $("#au_reset_em").value.trim();
        if (!em) { say("Type the email on the account first.", true); return; }
        try {
          await root.ZeimAuth.requestPasswordReset(em);
          say("If that email belongs to an account, a code is on its way. It works for 10 minutes.");
        } catch (e) { say(e.message || "Could not send the code.", true); }
      };
      $("#au_reset_ok").onclick = async () => {
        const pw = $("#au_reset_pw").value;
        if (!pw) { say("Choose a new password of at least 10 characters.", true); return; }
        try {
          await root.ZeimAuth.confirmPasswordReset($("#au_reset_em").value.trim(), $("#au_reset_code").value.trim(), pw);
          afterIdentityChange();
        } catch (e) { say(e.message || "That code didn't work.", true); }
      };
    }
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
        <p>Add a password or a passkey to secure this account — your name, projects and settings stay exactly
          as they are.</p>
      </div>
      <div id="accMsg" class="help" style="min-height:1.2em"></div>
      <div class="auth-stack">
        <div class="field"><label for="au_leg_pw">Password</label>
          <input id="au_leg_pw" type="password" maxlength="128" autocomplete="new-password">
          <small class="help">At least 10 characters. You can then sign in with your username and this password.</small></div>
        <button class="btn primary" type="button" id="au_leg_go">Add a password</button>
        <button class="btn" type="button" id="au_up">Secure my account with a passkey</button>
      </div>
      <p class="mini" style="margin-top:10px">Or keep using the cookie account for now — everything keeps working.</p>
      <h4>Plans</h4><div id="accPlans" class="acc-plans"><p class="help">Loading plans…</p></div>`;
    $("#au_leg_go").onclick = async () => {
      const pw = $("#au_leg_pw").value;
      if (!pw) { say("Choose a password of at least 10 characters.", true); return; }
      say("Saving your password…");
      try {
        await root.ZeimAuth.addPassword(pw);
        afterIdentityChange();
      } catch (e) { say(e.message || "The password was not saved.", true); }
    };
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

  function focusGuest(which) {
    const el = document.getElementById(which === "signup" ? "au_name" : "au_id");
    if (!el) return;
    try { el.scrollIntoView({ block: "center" }); } catch (e) { /* dialog may not be open yet */ }
    try { el.focus(); } catch (e2) { /* ignore */ }
  }

  async function render(me, opts) {
    if (!handles(me)) return false;
    const focus = opts && opts.focus;
    try {
      if (me.auth.session) renderSignedIn(me);
      else if (me.signed_up) renderLegacy(me);       // cookie account: offer the upgrade
      else {
        renderGuest(me, !!me.auth.email_codes);
        if (focus === "signin" || focus === "signup") focusGuest(focus);
      }
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
