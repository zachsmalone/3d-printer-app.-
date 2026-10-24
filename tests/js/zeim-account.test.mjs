/* Behavioral tests for static/zeim-account.js — the account dialog controller.
   Original code. A tiny DOM shim is enough: the controller renders by setting
   innerHTML and wiring onclick handlers looked up by id. */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

let reloaded = 0;
let fetched = [];
function reset() {
  reloaded = 0; fetched = [];
  globalThis.location = { reload: () => { reloaded++; } };
  globalThis.fetch = async (url, init) => {
    fetched.push({ url, init });
    return { ok: true, status: 200, json: async () => ({ username: "u", recovery_code: "RC" }) };
  };
}

function makeDoc() {
  const touched = new Set();
  const els = new Map();
  const el = id => {
    touched.add(id);
    if (!els.has(id)) els.set(id, { id, _html: "", value: "", onclick: null, _cls: "", _text: "", className: "", children: [] });
    return els.get(id);
  };
  globalThis.document = {
    querySelector: sel => (sel && sel.startsWith("#")) ? el(sel.slice(1)) : null,
    createElement: tag => ({ tag, textContent: "", innerHTML: "" }),
  };
  globalThis.window = globalThis;
  return { el, html: id => (els.get(id) || {}).innerHTML || "", touched };
}

function stubAuth(over = {}) {
  globalThis.ZeimAuth = {
    supportsPasskeys: () => true,
    signUp: async () => {}, signInWithPasskey: async () => {}, addPasskey: async () => {},
    signInWithPassword: async () => {}, registerWithPassword: async () => ({}), addPassword: async () => ({}),
    signOut: async () => {}, requestEmailCode: async () => {}, verifyEmailCode: async () => {},
    requestPasswordReset: async () => {}, confirmPasswordReset: async () => {},
    mountSecurityPanel: () => {}, ...over,
  };
}

const GUEST = { signed_up: false, auth: { available: true, email_codes: false, session: false } };
const LEGACY = { signed_up: true, display_name: "Legacy Lena", auth: { available: true, email_codes: false, session: false } };
const SIGNED_IN = { signed_up: true, display_name: "Virtual Vera", username: "vera", auth: { available: true, email_codes: false, session: true } };

test("the handled/not-handled decision is synchronous — a Promise can never hide the legacy fallback", async () => {
  reset(); makeDoc(); stubAuth();
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  const decision = A.handles(GUEST);
  assert.equal(decision, true);
  assert.ok(!(decision instanceof Promise), "handles() must not be async");
  assert.equal(A.handles({ signed_up: false, auth: { available: false } }), false);
  assert.equal(A.handles({ signed_up: false }), false);
  delete globalThis.ZeimAuth;
  assert.equal(A.handles(GUEST), false);
});

test("auth unavailable -> render returns false so community.js renders the legacy UI", async () => {
  reset(); makeDoc(); stubAuth();
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  assert.equal(await A.render({ signed_up: false, auth: { available: false } }), false);
});

test("guest state renders passkey sign-up, sign-in and the recovery flow; email section only when the server can send codes", async () => {
  reset(); const d = makeDoc(); stubAuth();
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  assert.equal(await A.render(GUEST), true);
  assert.ok(d.html("accBody").includes("Create my account with a passkey"));
  assert.ok(d.html("accBody").includes("Sign in with my passkey"));
  assert.ok(d.html("accBody").includes("Username or email"), "password sign-in is on the same screen");
  assert.ok(d.html("accBody").includes('id="au_pw"'), "the password field is visible, not tucked away");
  assert.ok(d.html("accBody").includes("recovery code"), "recovery must stay reachable");
  assert.ok(!d.html("accBody").includes("Send my code"), "email sign-in must not render when email_codes is false");
  assert.ok(d.html("accBody").includes("Password reset by email is not available"));
  assert.ok(d.el("au_go").onclick && d.el("au_in").onclick && d.el("au_pw_go").onclick && d.el("pw_go").onclick && d.el("rc_go").onclick);

  reset(); const d2 = makeDoc(); stubAuth();
  assert.equal(await A.render({ ...GUEST, auth: { available: true, email_codes: true, session: false } }), true);
  assert.ok(d2.html("accBody").includes("Send my code"));
  assert.ok(d2.el("au_em_go").onclick && d2.el("au_code_go").onclick);
});

test("legacy cookie account gets the passkey upgrade, not the legacy signup", async () => {
  reset(); const d = makeDoc(); stubAuth();
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  assert.equal(await A.render(LEGACY), true);
  assert.ok(d.html("accBody").includes("Secure my account with a passkey"));
  assert.ok(!d.html("accBody").includes("Create account"), "the legacy signup must not be offered as an equivalent path");
  let called = null;
  stubAuth({ addPasskey: async () => { called = "addPasskey"; } });
  d.el("au_up").onclick();
  await new Promise(r => setTimeout(r, 0));
  assert.equal(called, "addPasskey");
});

test("signed-in state renders the security panel with the email capability, and sign out works", async () => {
  reset(); const d = makeDoc();
  let panelOpts = null;
  stubAuth({ mountSecurityPanel: (_c, o) => { panelOpts = o || {}; } });
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  assert.equal(await A.render(SIGNED_IN), true);
  assert.equal(panelOpts.emailAvailable, false, "email adding must be suppressed when the server cannot send codes");
  assert.ok(d.el("au_out").onclick);
  let out = 0;
  stubAuth({ mountSecurityPanel: () => {}, signOut: async () => { out++; } });
  d.el("au_out").onclick();
  await new Promise(r => setTimeout(r, 0));
  assert.equal(out, 1);
  assert.equal(reloaded, 1, "sign out must refresh identity + account-scoped state");
});

test("a cancelled WebAuthn prompt (simulated NotAllowedError) changes no identity and reloads nothing", async () => {
  reset(); const d = makeDoc();
  stubAuth({ signUp: async () => { const e = new Error("cancelled"); e.name = "NotAllowedError"; throw e; } });
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  await A.render(GUEST);
  d.el("au_name").value = "Nina";
  d.el("au_dob").value = "1990-01-01";
  await d.el("au_go").onclick();
  await new Promise(r => setTimeout(r, 0));
  assert.equal(reloaded, 0, "a cancelled passkey prompt must not change identity");
  assert.match(d.el("accMsg").textContent, /cancelled/i);
});

test("rendering failure with auth available shows an error — never silently downgrades to the legacy signup", async () => {
  reset(); const d = makeDoc();
  stubAuth({ mountSecurityPanel: () => { throw new Error("boom"); } });
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  assert.equal(await A.render(SIGNED_IN), true);
  assert.ok(d.html("accBody").includes("could not load"));
  assert.ok(!d.html("accBody").includes("Create account"), "no legacy signup fallback while auth is available");
});

test("password sign-in sends the username and password through ZeimAuth, then reloads", async () => {
  reset(); const d = makeDoc();
  let got = null;
  stubAuth({ signInWithPassword: async (id, pw) => { got = { id, pw }; } });
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  await A.render(GUEST);
  d.el("au_id").value = "ZeimApp";
  d.el("au_pw").value = "correct horse";
  await d.el("au_pw_go").onclick();
  await new Promise(r => setTimeout(r, 0));
  assert.deepEqual(got, { id: "ZeimApp", pw: "correct horse" });
  assert.equal(reloaded, 1);
});

test("a mismatched password on sign-up does not call the server", async () => {
  reset(); const d = makeDoc();
  let called = 0;
  stubAuth({ registerWithPassword: async () => { called++; } });
  require("../../static/zeim-account.js");
  await globalThis.ZeimAccount.render(GUEST);
  d.el("au_name").value = "Sam";
  d.el("au_user").value = "SamMaker";
  d.el("au_pw_new").value = "correct horse";
  d.el("au_pw_new2").value = "other phrase";
  d.el("au_dob").value = "1990-01-01";
  await d.el("pw_go").onclick();
  await new Promise(r => setTimeout(r, 0));
  assert.equal(called, 0);
  assert.equal(reloaded, 0);
  assert.match(d.el("accMsg").textContent, /don't match/i);
});

test("the recovery code goes to /api/me/recover with the CSRF header", async () => {
  reset(); const d = makeDoc(); stubAuth();
  require("../../static/zeim-account.js");
  const A = globalThis.ZeimAccount;
  await A.render(GUEST);
  d.el("rc_code").value = "RC123";
  await d.el("rc_go").onclick();
  await new Promise(r => setTimeout(r, 0));
  assert.equal(fetched[0].url, "/api/me/recover");
  assert.equal(fetched[0].init.headers["X-Requested-With"], "zeim");
  assert.deepEqual(JSON.parse(fetched[0].init.body), { code: "RC123" });
  assert.ok(d.html("accBody").includes("Welcome back"), "a good recovery code must bring the account back");
});
