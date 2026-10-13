import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const A = require("../../static/zeim-auth.js");
const { b64urlToBytes, bytesToB64url, creationOptions, requestOptions, credentialToJSON } = A._internal;

test("base64url round-trips including bytes that need url-safe chars", () => {
  const bytes = Uint8Array.from([251, 255, 254, 0, 1, 2, 250]);
  const s = bytesToB64url(bytes);
  assert.ok(!/[+/=]/.test(s));
  assert.deepEqual([...b64urlToBytes(s)], [...bytes]);
});

test("creation options: challenge, user id and excludeCredentials become bytes", () => {
  const o = creationOptions({ challenge: "AQID", user: { id: "BAUG", name: "n", displayName: "n" }, excludeCredentials: [{ id: "BwgJ", type: "public-key" }], rp: { id: "x" } });
  assert.deepEqual([...o.challenge], [1, 2, 3]);
  assert.deepEqual([...o.user.id], [4, 5, 6]);
  assert.deepEqual([...o.excludeCredentials[0].id], [7, 8, 9]);
});

test("request options: empty allowCredentials stays empty (discoverable sign-in)", () => {
  const o = requestOptions({ challenge: "AQID", rpId: "x" });
  assert.deepEqual([...o.challenge], [1, 2, 3]);
  assert.deepEqual(o.allowCredentials, []);
});

test("assertion credentials are serialised to base64url strings", () => {
  const buf = n => Uint8Array.from(n).buffer;
  const j = credentialToJSON({ id: "abc", rawId: buf([1, 2]), type: "public-key",
    response: { clientDataJSON: buf([1]), authenticatorData: buf([2]), signature: buf([3]), userHandle: buf([4]) } });
  assert.equal(j.response.signature, "Aw");
  assert.equal(j.response.userHandle, "BA");
});

function fakeFetch(status, body, headers = {}) {
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push({ url, init }); return { ok: status < 400, status, json: async () => body, headers: { get: k => headers[k] ?? null } }; };
  return calls;
}

test("every request sends the CSRF header, same-origin credentials and JSON", async () => {
  const calls = fakeFetch(200, { signed_in: true });
  await A.signOutEverywhere(true);
  const { url, init } = calls[0];
  assert.equal(url, "/api/auth/sessions/revoke-all");
  assert.equal(init.credentials, "same-origin");
  assert.equal(init.headers["X-Requested-With"], "zeim");
  assert.deepEqual(JSON.parse(init.body), { keep_current: true });
});

test("API errors become AuthApiError with the friendly message, code and Retry-After", async () => {
  fakeFetch(429, { detail: { code: "rate_limited", message: "Too many attempts. Please wait a bit and try again." } }, { "Retry-After": "42" });
  await assert.rejects(() => A.requestEmailCode("a@b.co"), e => e instanceof A.AuthApiError && e.code === "rate_limited" && e.retryAfter === 42 && /wait a bit/.test(e.message));
});

test("ids are URL-encoded in paths", async () => {
  const calls = fakeFetch(200, { ok: true });
  await A.revokeDevice("a/b c");
  assert.equal(calls[0].url, "/api/auth/sessions/a%2Fb%20c");
});

// ---- tiny fake DOM to prove untrusted text is never parsed as HTML
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this._text = ""; this.ownerDocument = null; }
  set textContent(v) { this._text = String(v); this.children = []; }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
  setAttribute(k, v) { this.attrs[k] = v; }
  appendChild(c) { this.children.push(c); return c; }
  set innerHTML(_) { throw new Error("innerHTML must never be used"); }
}
const fakeDoc = { createElement: t => { const e = new El(t); e.ownerDocument = fakeDoc; return e; } };

test("device labels and passkey names render as text, not HTML", async () => {
  const evil = '<img src=x onerror="alert(1)">';
  fakeFetch(200, { display_name: "S", email: null, passkeys: [{ id: "k1", name: evil, created_at: 1, last_used_at: null }],
    devices: [{ id: "d1", label: evil, last_seen_at: 1, current: true }] });
  const box = new El("div"); box.ownerDocument = fakeDoc;
  await A.mountSecurityPanel(box);
  const text = box.textContent;
  assert.ok(text.includes(evil));                       // present only as literal text
  assert.ok(text.includes("Sign out everywhere") && text.includes("(this device)"));
});

test("signed-out visitors see a prompt instead of an error", async () => {
  fakeFetch(401, { detail: { code: "not_signed_in", message: "Please sign in first." } });
  const box = new El("div"); box.ownerDocument = fakeDoc;
  await A.mountSecurityPanel(box);
  assert.match(box.textContent, /sign in/i);
});
