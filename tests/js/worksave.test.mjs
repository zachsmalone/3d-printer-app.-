import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

globalThis.ZEIM_SAVE_TEST = true;

function memory(opts = {}) {
  const m = new Map();
  return {
    getItem(k) { return m.has(k) ? m.get(k) : null; },
    setItem(k, v) {
      if (opts.failSet) throw new Error("quota");
      if (!opts.drop) m.set(k, String(v));
    },
    removeItem(k) { m.delete(k); },
  };
}

globalThis.localStorage = memory();
createRequire(import.meta.url)("../../static/worksave.js");
const S = globalThis.zeimSave;

const A = "aaaaaaaaaaaa";
const B = "bbbbbbbbbbbb";

function useStore(opts) {
  globalThis.localStorage = memory(opts);
}

test("a failed write does not clear dirty or report a draft save", () => {
  useStore({ failSet: true });
  S.setAccount("guest");
  let value = { layer: "0.2" };
  S.register("failq", { collect: () => value, restore: () => true });
  S._markDirty("failq");
  assert.equal(S.saveNow(), false);
  assert.equal(S.lastResult(), "failed");
  assert.equal(S.isDirty(), true);
  assert.equal(S._label(), "Not saved");
  useStore({ drop: true });
  S._markDirty("failq");
  assert.equal(S.saveNow(), false);
  assert.equal(S.isDirty(), true);
  assert.equal(S._label(), "Not saved");
});

test("a successful draft says it is a browser draft", () => {
  useStore();
  S.setAccount("guest");
  S.register("okdraft", { collect: () => ({ layer: "0.16" }), restore: () => true });
  S._markDirty("okdraft");
  assert.equal(S.saveNow(), true);
  assert.equal(S.lastResult(), "saved");
  assert.equal(S.isDirty(), false);
  assert.match(S._label(), /^Draft saved /);
  assert.equal(S._label().startsWith("Saved "), false);
  const raw = globalThis.localStorage.getItem(S._draftKey("okdraft"));
  assert.ok(raw && raw.includes("0.16"));
  assert.ok(S._draftKey("okdraft").includes("guest"));
});

test("two accounts do not read each other's drafts", () => {
  useStore();
  const store = globalThis.localStorage;
  S.setAccount("u:" + A);
  S.register("acct", { collect: () => ({ layer: "0.2" }), restore: () => true }, null, { project: true });
  S.setProject("acct", A);
  S._markDirty("acct");
  assert.equal(S.saveNow(), true);
  const keyA = S._draftKey("acct");
  assert.ok(store.getItem(keyA).includes("0.2"));
  let seen = "untouched";
  S.register("acctB", {
    collect: () => ({ layer: "nope" }),
    restore: (v) => { seen = v; return true; },
  }, null, { project: true });
  S.setAccount("u:" + B);
  S.setProject("acctB", A);
  assert.equal(seen, "untouched");
  assert.equal(store.getItem(S._draftKey("acctB")), null);
  assert.ok(store.getItem(keyA).includes("0.2"));
});

test("two projects in one account keep separate slicer drafts", () => {
  useStore();
  const store = globalThis.localStorage;
  S.setAccount("u:" + A);
  let current = { layer: "0.2" };
  S.register("proj", {
    collect: () => current,
    restore: (v) => { current = v; return true; },
  }, null, { project: true });
  S.setProject("proj", A);
  S._markDirty("proj");
  assert.equal(S.saveNow(), true);
  const keyA = S._draftKey("proj");
  S.setProject("proj", B);
  current = { layer: "0.28" };
  S._markDirty("proj");
  assert.equal(S.saveNow(), true);
  const keyB = S._draftKey("proj");
  assert.notEqual(keyA, keyB);
  assert.ok(store.getItem(keyA).includes("0.2"));
  assert.ok(store.getItem(keyB).includes("0.28"));
  S.setProject("proj", A);
  assert.deepEqual(current, { layer: "0.2" });
  S.setProject("proj", B);
  assert.deepEqual(current, { layer: "0.28" });
});

test("exit stays put when the draft cannot be stored", () => {
  useStore({ failSet: true });
  S.setAccount("u:" + A);
  S.register("exitfail", { collect: () => ({ bid: A }), restore: () => true });
  S._markDirty("exitfail");
  let went = false;
  assert.equal(S.leave(() => { went = true; }), false);
  assert.equal(went, false);
  assert.equal(S.isDirty(), true);
});

test("exit stores a dirty draft and then leaves", () => {
  useStore();
  S.setAccount("u:" + A);
  S.register("exitok", { collect: () => ({ bid: A }), restore: () => true });
  S._markDirty("exitok");
  let went = false;
  assert.equal(S.leave(() => { went = true; }), true);
  assert.equal(went, true);
  assert.equal(S.isDirty(), false);
  assert.ok(globalThis.localStorage.getItem(S._draftKey("exitok")).includes(A));
});

test("exit with nothing dirty leaves without claiming a new save", () => {
  useStore();
  S.setAccount("guest");
  let went = false;
  assert.equal(S.leave(() => { went = true; }), true);
  assert.equal(went, true);
});
