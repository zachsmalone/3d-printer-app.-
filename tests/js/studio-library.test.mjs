/* My Studio stays on Account. Open and Edit enter a workspace. Browsing does not clear project storage. */
import test from "node:test";
import assert from "node:assert/strict";
import {
  LIBRARY_HASH, LIBRARY_URL, routeIntent, visitLibrary, arriveLibrary,
  workspaceFor, openFromLibrary, exitTarget, takeExit, libraryHTML,
} from "../../static/studio-library.js";

const PHOTO = "aaaaaaaaaaaa";
const EDIT = "bbbbbbbbbbbb";
const RELIEF = "cccccccccccc";

function mem(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    get length() { return m.size; },
    key(i) { return [...m.keys()][i] ?? null; },
    getItem(k) { return m.has(k) ? m.get(k) : null; },
    setItem(k, v) { m.set(k, String(v)); },
    removeItem(k) { m.delete(k); },
  };
}

const PROJECT = {
  "zeim.save": JSON.stringify({ mode: "auto", every: 5 }),
  "zeim.work.v2.guest._.lithophane": JSON.stringify({ t: 1, v: { width_mm: "100" } }),
  "zeim.work.v2.u:aaaaaaaaaaaa.bbbbbbbbbbbb.slicer": JSON.stringify({ t: 2, v: { s_layer: "0.2" } }),
  "zeim.edit.last": EDIT,
  "zeim.studio.return": PHOTO,
  "zeim.printer": JSON.stringify({ printer_id: "creality_k1" }),
};

function snap(storage) {
  const out = {};
  for (let i = 0; i < storage.length; i++) {
    const k = storage.key(i);
    out[k] = storage.getItem(k);
  }
  return out;
}

test("My Studio routes stay on the Account library and do not select Lithophane", () => {
  for (const hash of ["#account/studio", "#studio", "#studio/"]) {
    const intent = routeIntent(hash);
    assert.equal(intent.library, true);
    assert.equal(intent.view, "account");
    assert.equal(intent.hash, LIBRARY_HASH);
    assert.equal(intent.nav, "account");
    assert.notEqual(intent.view, "lithophane");
  }
  assert.equal(routeIntent("#account/studio").rewrite, false, "refresh keeps #account/studio");
  assert.equal(routeIntent("#studio").rewrite, true, "the old #studio bookmark is rewritten onto the library");
  const litho = routeIntent("#lithophane");
  assert.equal(litho.library, false);
  assert.equal(litho.view, "lithophane");
  assert.equal(routeIntent("#create").library, false);
  assert.equal(routeIntent("#create").view, "lithophane");
  assert.equal(routeIntent("#account").library, false);
  assert.equal(routeIntent("#account/save").library, false);
  assert.equal(routeIntent("#slicer").library, false);
});

test("browsing the library does not change project storage or the open project id", () => {
  const storage = mem(PROJECT);
  const project = { id: PHOTO, mode: "lithophane", title: "Cat" };
  const before = snap(storage);
  for (const hash of ["#account/studio", "#studio"]) {
    const visit = visitLibrary(hash, storage, project);
    assert.equal(visit.library, true);
    assert.equal(visit.storageSame, true);
    assert.equal(visit.projectId, PHOTO);
    assert.equal(project.id, PHOTO);
    assert.deepEqual(snap(storage), before);
  }
  const html = libraryHTML([
    { id: PHOTO, title: "Cat <b>", mode: "lithophane", kind: "photo", thumb: "/files/" + PHOTO + "/thumb.png" },
    { id: RELIEF, title: "Hills", mode: "relief", kind: "photo" },
  ], { currentId: PHOTO });
  assert.match(html, /data-lib="open"/);
  assert.match(html, /data-lib="edit"/);
  assert.match(html, /Open in this visit/);
  assert.match(html, /Cat &lt;b&gt;/);
  assert.equal(html.includes('href="#lithophane"'), false);
  assert.equal(html.includes('href="#studio"'), false);
  assert.equal(html.includes("Cat <b>"), false);
  assert.deepEqual(snap(storage), before);
});

test("Open and Edit reach the matching workspace and remember Account → My Studio", () => {
  const storage = mem(PROJECT);
  const before = snap(storage);
  const litho = openFromLibrary({ id: PHOTO, kind: "photo", mode: "lithophane", title: "Cat" }, "open", storage);
  assert.equal(litho.plan.hash, "#lithophane");
  assert.equal(litho.plan.view, "lithophane");
  assert.equal(litho.plan.open, "build");
  assert.deepEqual(litho.changed, ["zeim.back"]);
  const back = JSON.parse(storage.getItem("zeim.back"));
  assert.equal(back.url, LIBRARY_URL);
  assert.equal(back.from, "mystudio");
  assert.equal(back.hash, "account");
  assert.equal(back.label, "My Studio");
  for (const k of Object.keys(before)) assert.equal(storage.getItem(k), before[k], k);

  const relief = workspaceFor({ id: RELIEF, kind: "photo", mode: "relief" }, "open");
  assert.equal(relief.hash, "#create");
  assert.notEqual(relief.hash, "#lithophane");
  assert.equal(relief.view, "photo");

  const openEdit = workspaceFor({ id: EDIT, kind: "edit", mode: "edit" }, "open");
  assert.equal(openEdit.hash, "#slicer");
  assert.equal(openEdit.open, "edit");

  const editPhoto = workspaceFor({ id: PHOTO, kind: "photo", mode: "lithophane" }, "edit");
  assert.equal(editPhoto.hash, "#slicer");
  assert.equal(editPhoto.open, "from-build");

  const editCad = workspaceFor({ id: EDIT, kind: "edit", mode: "edit" }, "edit");
  assert.equal(editCad.view, "cad");
  assert.equal(editCad.url, "/static/cad.html?bid=" + EDIT);

  assert.equal(workspaceFor({ id: "nope", mode: "lithophane" }, "open"), null);
  assert.equal(workspaceFor({ id: PHOTO, mode: "lithophane" }, "star"), null);
  assert.equal(workspaceFor({ id: PHOTO, mode: "lithophane" }, "send"), null);
  const untouched = mem(PROJECT);
  const rejected = openFromLibrary({ id: "short", mode: "lithophane" }, "open", untouched);
  assert.equal(rejected.plan, null);
  assert.deepEqual(rejected.changed, []);
  assert.equal(untouched.getItem("zeim.back"), null);
});

test("leaving a project opened from My Studio returns to the library and keeps project keys", () => {
  const storage = mem(PROJECT);
  openFromLibrary({ id: PHOTO, kind: "photo", mode: "lithophane" }, "open", storage);
  const now = Date.now();
  assert.equal(exitTarget(storage, now), LIBRARY_URL);
  const left = takeExit(storage, now);
  assert.equal(left.url, LIBRARY_URL);
  assert.deepEqual(left.changed, ["zeim.back"]);
  assert.equal(storage.getItem("zeim.back"), null);
  for (const k of Object.keys(PROJECT)) assert.equal(storage.getItem(k), PROJECT[k], k);
  assert.equal(exitTarget(storage, now), null);

  const other = mem({ ...PROJECT, "zeim.back": JSON.stringify({ label: "CAD", hash: "cad", url: "/static/cad.html?bid=" + EDIT, t: now }) });
  assert.equal(exitTarget(other, now), null);
  assert.equal(takeExit(other, now).url, null);
  assert.equal(other.getItem("zeim.work.v2.guest._.lithophane"), PROJECT["zeim.work.v2.guest._.lithophane"]);
});

test("arriving on the library clears only the My Studio return marker", () => {
  const storage = mem(PROJECT);
  openFromLibrary({ id: EDIT, kind: "edit", mode: "edit" }, "open", storage);
  const arrived = arriveLibrary(storage, Date.now());
  assert.equal(arrived.cleared, true);
  assert.deepEqual(arrived.changed, ["zeim.back"]);
  for (const k of Object.keys(PROJECT)) assert.equal(storage.getItem(k), PROJECT[k], k);

  const foreign = mem({ ...PROJECT, "zeim.back": JSON.stringify({ label: "FDM Slicer", hash: "slicer", t: Date.now() }) });
  const stay = arriveLibrary(foreign, Date.now());
  assert.equal(stay.cleared, false);
  assert.equal(foreign.getItem("zeim.back").includes("FDM Slicer"), true);
  assert.equal(foreign.getItem("zeim.edit.last"), EDIT);
});

test("a refresh of the library route is still the library", () => {
  const again = routeIntent(LIBRARY_HASH);
  assert.equal(again.library, true);
  assert.equal(again.view, "account");
  assert.equal(again.rewrite, false);
  assert.equal(again.hash, LIBRARY_HASH);
});
