import test from "node:test";
import assert from "node:assert/strict";

const store = new Map(), sent = [];
globalThis.localStorage = { getItem: k => store.has(k) ? store.get(k) : null, setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) };
globalThis.fetch = (u, o) => { sent.push(JSON.parse(o.body)); return Promise.resolve({}); };
Object.defineProperty(globalThis, "navigator", { value: { doNotTrack: null }, configurable: true });
globalThis.window = {};
const m = await import("../../static/metrics.js");

test("sends once, coarse seconds only", () => {
  store.set("zeim.firstSeen", "1000");
  assert.equal(m.firstPrint(61000), true);
  assert.equal(m.firstPrint(99000), false);
  assert.deepEqual(sent, [{ event: "first_print", secs: 60 }]);
});

test("opt-out and DNT respected", () => {
  store.clear(); sent.length = 0;
  m.setMetricsOff(true); assert.equal(m.firstPrint(), false);
  m.setMetricsOff(false); navigator.doNotTrack = "1"; assert.equal(m.firstPrint(), false);
  navigator.doNotTrack = null; navigator.globalPrivacyControl = true; assert.equal(m.firstPrint(), false);
  assert.equal(sent.length, 0);
});

test("print download detection", () => {
  const a = (d, h) => ({ hasAttribute: n => n === "download" && d !== null, getAttribute: n => n === "download" ? d : h });
  assert.ok(m.isPrintDownload(a("ZEIM-build.3mf", "/x")));
  assert.ok(m.isPrintDownload(a("", "/api/builds/abc/model.3mf")));
  assert.ok(!m.isPrintDownload(a(null, "/x.3mf")));
  assert.ok(!m.isPrintDownload(a("photo.png", "/x.png")));
});
