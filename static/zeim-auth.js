/* ZEIM auth client: passkeys (WebAuthn) + email codes + Account security panel.
   Vanilla JS, no dependencies, no third-party requests. All text is inserted with textContent (never innerHTML). */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else root.ZeimAuth = factory(root);
})(typeof self !== "undefined" ? self : globalThis, function (root) {
  "use strict";

  class AuthApiError extends Error {
    constructor(status, detail, retryAfter) {
      super((detail && detail.message) || "Something went wrong. Please try again.");
      this.status = status; this.code = (detail && detail.code) || "error"; this.retryAfter = retryAfter || null;
    }
  }

  // ---- base64url <-> bytes
  function b64urlToBytes(s) {
    const pad = "=".repeat((4 - (s.length % 4)) % 4);
    const bin = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function bytesToB64url(buf) {
    const bytes = new Uint8Array(buf);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  // ---- WebAuthn JSON <-> browser objects (uses the native helpers when the browser has them)
  function creationOptions(json) {
    if (root.PublicKeyCredential && PublicKeyCredential.parseCreationOptionsFromJSON) return PublicKeyCredential.parseCreationOptionsFromJSON(json);
    const o = Object.assign({}, json);
    o.challenge = b64urlToBytes(json.challenge);
    o.user = Object.assign({}, json.user, { id: b64urlToBytes(json.user.id) });
    o.excludeCredentials = (json.excludeCredentials || []).map(c => Object.assign({}, c, { id: b64urlToBytes(c.id) }));
    return o;
  }
  function requestOptions(json) {
    if (root.PublicKeyCredential && PublicKeyCredential.parseRequestOptionsFromJSON) return PublicKeyCredential.parseRequestOptionsFromJSON(json);
    const o = Object.assign({}, json);
    o.challenge = b64urlToBytes(json.challenge);
    o.allowCredentials = (json.allowCredentials || []).map(c => Object.assign({}, c, { id: b64urlToBytes(c.id) }));
    return o;
  }
  function credentialToJSON(cred) {
    if (typeof cred.toJSON === "function") return cred.toJSON();
    const r = cred.response, out = { id: cred.id, rawId: bytesToB64url(cred.rawId), type: cred.type, clientExtensionResults: {}, response: {} };
    out.response.clientDataJSON = bytesToB64url(r.clientDataJSON);
    if (r.attestationObject) { out.response.attestationObject = bytesToB64url(r.attestationObject); out.response.transports = r.getTransports ? r.getTransports() : []; }
    if (r.authenticatorData) {
      out.response.authenticatorData = bytesToB64url(r.authenticatorData);
      out.response.signature = bytesToB64url(r.signature);
      out.response.userHandle = r.userHandle ? bytesToB64url(r.userHandle) : null;
    }
    return out;
  }

  // ---- HTTP
  async function api(path, method, body) {
    const res = await root.fetch("/api/auth" + path, {
      method: method || "GET", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Requested-With": "zeim" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (!res.ok) throw new AuthApiError(res.status, data && data.detail, res.headers && res.headers.get && Number(res.headers.get("Retry-After")));
    return data;
  }

  // ---- flows
  const supportsPasskeys = () => !!(root.PublicKeyCredential && root.navigator && navigator.credentials);

  async function signUp(displayName, birthDate, passkeyName) {
    const b = await api("/signup/begin", "POST", { display_name: displayName, birth_date: birthDate });
    const cred = await navigator.credentials.create({ publicKey: creationOptions(b.options) });
    return api("/signup/finish", "POST", { ceremony_id: b.ceremony_id, credential: credentialToJSON(cred), name: passkeyName || "This device" });
  }
  async function signInWithPasskey() {
    const b = await api("/signin/begin", "POST");
    const cred = await navigator.credentials.get({ publicKey: requestOptions(b.options) });
    return api("/signin/finish", "POST", { ceremony_id: b.ceremony_id, credential: credentialToJSON(cred) });
  }
  async function addPasskey(name) {
    const b = await api("/passkeys/begin", "POST");
    const cred = await navigator.credentials.create({ publicKey: creationOptions(b.options) });
    return api("/passkeys/finish", "POST", { ceremony_id: b.ceremony_id, credential: credentialToJSON(cred), name: name || "This device" });
  }

  const A = {
    AuthApiError, supportsPasskeys, signUp, signInWithPasskey, addPasskey,
    requestEmailCode: email => api("/email/request", "POST", { email }),
    verifyEmailCode: (email, code) => api("/email/verify", "POST", { email, code }),
    addEmailRequest: email => api("/email/add/request", "POST", { email }),
    addEmailVerify: (email, code) => api("/email/add/verify", "POST", { email, code }),
    removeEmail: () => api("/email", "DELETE"),
    getSession: () => api("/session"),
    getAccount: () => api("/account"),
    signOut: () => api("/logout", "POST"),
    signOutEverywhere: keepCurrent => api("/sessions/revoke-all", "POST", { keep_current: !!keepCurrent }),
    revokeDevice: id => api("/sessions/" + encodeURIComponent(id), "DELETE"),
    renamePasskey: (id, name) => api("/passkeys/" + encodeURIComponent(id), "PATCH", { name }),
    removePasskey: id => api("/passkeys/" + encodeURIComponent(id), "DELETE"),
    _internal: { b64urlToBytes, bytesToB64url, creationOptions, requestOptions, credentialToJSON, api },
  };

  // ---- Account security panel (passkeys, email, devices, sign out everywhere)
  function h(doc, tag, props, kids) {
    const el = doc.createElement(tag);
    Object.keys(props || {}).forEach(k => { if (k === "text") el.textContent = props[k]; else if (k === "onclick") el.onclick = props[k]; else el.setAttribute(k, props[k]); });
    (kids || []).forEach(k => el.appendChild(k));
    return el;
  }
  const fmt = ts => (ts ? new Date(ts * 1000).toLocaleDateString() : "never");

  async function mountSecurityPanel(container, opts) {
    const doc = container.ownerDocument || root.document, o = opts || {};
    const say = (msg, bad) => { status.textContent = msg || ""; status.setAttribute("class", "zeim-auth-status" + (bad ? " bad" : "")); };
    const run = async (fn, okMsg) => {
      try { await fn(); if (okMsg) say(okMsg); await render(); }
      catch (e) { say(e.code === "reauth_required" ? "For your security, please sign in again with your passkey, then retry." : e.message, true); }
    };
    const status = h(doc, "p", { "class": "zeim-auth-status", role: "status" });
    async function render() {
      let acct;
      try { acct = await A.getAccount(); } catch (e) { container.textContent = ""; container.appendChild(h(doc, "p", { text: "Please sign in to see your account security." })); return; }
      container.textContent = "";
      container.appendChild(h(doc, "h2", { text: "Sign-in & devices" }));
      container.appendChild(status);

      container.appendChild(h(doc, "h3", { text: "Passkeys" }));
      acct.passkeys.forEach(p => container.appendChild(h(doc, "div", { "class": "zeim-auth-row" }, [
        h(doc, "span", { text: p.name + " \u00b7 added " + fmt(p.created_at) + " \u00b7 last used " + fmt(p.last_used_at) }),
        h(doc, "button", { type: "button", text: "Rename", onclick: () => { const n = (o.prompt || root.prompt)("New name", p.name); if (n) run(() => A.renamePasskey(p.id, n)); } }),
        h(doc, "button", { type: "button", text: "Remove", onclick: () => { if ((o.confirm || root.confirm)("Remove this passkey?")) run(() => A.removePasskey(p.id), "Passkey removed."); } }),
      ])));
      container.appendChild(h(doc, "button", { type: "button", text: "Add a passkey on this device", onclick: () => run(() => A.addPasskey(), "Passkey added.") }));

      container.appendChild(h(doc, "h3", { text: "Backup email" }));
      if (acct.email) {
        container.appendChild(h(doc, "div", { "class": "zeim-auth-row" }, [
          h(doc, "span", { text: acct.email.hint + " (we only keep a scrambled copy)" }),
          h(doc, "button", { type: "button", text: "Remove", onclick: () => run(() => A.removeEmail(), "Email removed.") })]));
      } else if (o.emailAvailable === false) {
        /* The server cannot send email codes: offering the add-a-backup-email form
           would present a known nonfunctional recovery setup as usable. */
        container.appendChild(h(doc, "p", { text: "Email backup is not available on this ZEIM server.", "class": "zeim-auth-status" }));
      } else {
        const em = h(doc, "input", { type: "email", autocomplete: "email", placeholder: "you@example.com" });
        const code = h(doc, "input", { inputmode: "numeric", autocomplete: "one-time-code", placeholder: "6-digit code", maxlength: "7" });
        container.appendChild(h(doc, "div", { "class": "zeim-auth-row" }, [em,
          h(doc, "button", { type: "button", text: "Send code", onclick: () => run(() => A.addEmailRequest(em.value), "Code sent. Check your inbox.") }), code,
          h(doc, "button", { type: "button", text: "Verify", onclick: () => run(() => A.addEmailVerify(em.value, code.value), "Email added.") })]));
      }

      container.appendChild(h(doc, "h3", { text: "Your devices" }));
      acct.devices.forEach(d => container.appendChild(h(doc, "div", { "class": "zeim-auth-row" }, [
        h(doc, "span", { text: d.label + (d.current ? " (this device)" : "") + " \u00b7 last active " + fmt(d.last_seen_at) }),
        d.current ? h(doc, "span") : h(doc, "button", { type: "button", text: "Sign out", onclick: () => run(() => A.revokeDevice(d.id), "Device signed out.") }),
      ])));
      container.appendChild(h(doc, "button", { type: "button", "class": "zeim-auth-danger", text: "Sign out everywhere", onclick: () => {
        if ((o.confirm || root.confirm)("Sign out of ZEIM on every device, including this one?")) run(async () => { await A.signOutEverywhere(false); if (o.onSignedOut) o.onSignedOut(); }, "Signed out everywhere.");
      } }));
    }
    await render();
    return { refresh: render };
  }
  A.mountSecurityPanel = mountSecurityPanel;
  return A;
});
