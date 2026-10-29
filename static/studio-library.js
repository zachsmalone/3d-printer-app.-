/* Projects (#projects) is the saved-work list. Open and Edit are the actions that enter a workspace.
   My Studio (#account/studio) is the ownership note on Account (Me). It does not list projects.
   #studio used to alias to the shared Lithophane page, then to that Account list. It now opens Projects.
   A return marker still uses from: "mystudio". Older markers stored /#account/studio; Exit follows Projects.
   #create remains the photo workspace (it does not force the Lithophane style).
   Return uses the existing sessionStorage key zeim.back. Project and draft keys are not renamed. */
export const LIBRARY_HASH = "#projects";
export const LIBRARY_URL = "/#projects";
export const STUDIO_HASH = "#account/studio";
const LEGACY_LIBRARY_URL = "/#account/studio";
const BACK_KEY = "zeim.back";
const BACK_MS = 6 * 3600e3;

const MODE_LABEL = {
  lithophane: "Lithophane", relief: "Relief", bust: "Photo plaque", popart: "Pop-art",
  trace2d: "Logo & Drawing", ai3d: "2D→3D", edit: "Edited model", memorybox: "Memory box",
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function blankIntent(hash) {
  return { library: false, ownership: false, view: null, hash: String(hash || ""), rewrite: false, nav: null };
}

export function routeIntent(hash) {
  const full = String(hash || "").replace(/^#/, "");
  const head = full.split("/")[0].split("?")[0];
  const sub = (full.split("/")[1] || "").split("?")[0];
  if (head === "projects") {
    return { library: true, ownership: false, view: "projects", hash: LIBRARY_HASH, rewrite: full !== "projects", nav: "projects" };
  }
  if (head === "studio") {
    return { library: true, ownership: false, view: "projects", hash: LIBRARY_HASH, rewrite: true, nav: "projects" };
  }
  if (head === "account" && sub === "studio") {
    return { library: false, ownership: true, view: "account", hash: STUDIO_HASH, rewrite: full !== "account/studio", nav: "account" };
  }
  if (head === "lithophane") {
    return { library: false, ownership: false, view: "lithophane", hash: "#lithophane", rewrite: false, nav: "lithophane" };
  }
  if (head === "create") {
    return { library: false, ownership: false, view: "lithophane", hash: "#create", rewrite: false, nav: "lithophane" };
  }
  return blankIntent(hash);
}

function dump(storage) {
  const out = {};
  if (!storage || typeof storage.key !== "function") return out;
  try {
    for (let i = 0; i < storage.length; i++) {
      const k = storage.key(i);
      if (k != null) out[k] = storage.getItem(k);
    }
  } catch (e) { /* private mode: treat as empty for the comparison */ }
  return out;
}

function changedKeys(before, after) {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys].filter(k => before[k] !== after[k]).sort();
}

function sameDump(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) if (a[k] !== b[k]) return false;
  return true;
}

/* Browsing the library reads the route and the open project. It does not write storage. */
export function visitLibrary(hash, storage, project) {
  const intent = routeIntent(hash);
  const before = dump(storage);
  const after = dump(storage);
  return {
    library: intent.library === true,
    intent,
    storageSame: sameDump(before, after),
    projectId: project && project.id ? String(project.id) : "",
  };
}

export function readBack(storage, now) {
  if (!storage || typeof storage.getItem !== "function") return null;
  let info = null;
  try { info = JSON.parse(storage.getItem(BACK_KEY) || "null"); } catch (e) { return null; }
  if (!info || typeof info !== "object" || typeof info.t !== "number") return null;
  if ((now == null ? Date.now() : now) - info.t > BACK_MS) return null;
  return info;
}

function isLibraryUrl(url) {
  const u = String(url || "");
  return u === LIBRARY_URL || u === LEGACY_LIBRARY_URL || u === STUDIO_HASH;
}

function studioMark(info, now) {
  if (!info || info.from !== "mystudio" || !isLibraryUrl(info.url)) return null;
  if (typeof info.t === "number" && (now == null ? Date.now() : now) - info.t > BACK_MS) return null;
  return info;
}

/* Once Projects is on screen, drop the library return marker.
   A section hand-off may keep that return nested on zeim.back. Other keys stay. */
export function arriveLibrary(storage, now) {
  const before = dump(storage);
  const info = readBack(storage, now);
  const mine = !!(studioMark(info, now) || (info && studioMark(info.studio, now)));
  if (mine && storage && typeof storage.removeItem === "function") {
    try { storage.removeItem(BACK_KEY); } catch (e) { /* leave the marker if storage refuses */ }
  }
  return { cleared: mine, changed: changedKeys(before, dump(storage)) };
}

function marker() {
  return { label: "Projects", hash: "projects", url: LIBRARY_URL, from: "mystudio" };
}

export function workspaceFor(build, action) {
  if (action !== "open" && action !== "edit") return null;
  const id = String(build && build.id || "");
  if (!/^[0-9a-f]{12}$/.test(id)) return null;
  const kind = build.kind === "edit" ? "edit" : "photo";
  const mode = String(build.mode || (kind === "edit" ? "edit" : "lithophane"));
  const back = marker();
  if (action === "edit" && kind === "edit") {
    return { action, view: "cad", url: "/static/cad.html?bid=" + id, id, back };
  }
  if (action === "edit") {
    return { action, view: "slicer", hash: "#slicer", open: "from-build", id, back };
  }
  if (kind === "edit") {
    return { action, view: "slicer", hash: "#slicer", open: "edit", id, back };
  }
  /* #lithophane selects the Lithophane style. A memory box is made there too. Other photo projects use #create. */
  if (mode === "lithophane" || mode === "memorybox") {
    return { action, view: "lithophane", hash: "#lithophane", open: "build", id, back };
  }
  return { action, view: "photo", hash: "#create", open: "build", id, back };
}

/* Records the return to Projects. Does not remove draft or project keys. */
export function openFromLibrary(build, action, storage) {
  const before = dump(storage);
  const plan = workspaceFor(build, action);
  if (!plan || !storage || typeof storage.setItem !== "function") {
    return { plan, changed: changedKeys(before, dump(storage)) };
  }
  try {
    storage.setItem(BACK_KEY, JSON.stringify(Object.assign({}, plan.back, { t: Date.now() })));
  } catch (e) { /* the workspace still opens; the Back chip is missing if this write fails */ }
  return { plan, changed: changedKeys(before, dump(storage)) };
}

export function exitTarget(storage, now) {
  const info = readBack(storage, now);
  const top = studioMark(info, now);
  if (top) return LIBRARY_URL;
  const nested = info && studioMark(info.studio, now);
  return nested ? LIBRARY_URL : null;
}

export function takeExit(storage, now) {
  const before = dump(storage);
  const url = exitTarget(storage, now);
  if (!url) return { url: null, changed: changedKeys(before, dump(storage)) };
  try { storage.removeItem(BACK_KEY); } catch (e) { /* still report the url; the chip may show once more */ }
  return { url, changed: changedKeys(before, dump(storage)) };
}

export function libraryHTML(builds, opts) {
  const current = opts && opts.currentId ? String(opts.currentId) : "";
  const rows = (builds || []).slice().reverse().map(b => {
    const id = String(b.id || "");
    if (!/^[0-9a-f]{12}$/.test(id)) return "";
    const title = b.title || "Untitled";
    const kind = b.kind === "edit" ? "edit" : "photo";
    const mode = String(b.mode || (kind === "edit" ? "edit" : ""));
    const label = MODE_LABEL[mode] || mode;
    const here = id === current ? " cur" : "";
    const thumb = b.thumb ? `<img src="${esc(b.thumb)}" alt="">` : "";
    const openNow = id === current ? `<span class="pill">Open in this visit</span>` : "";
    return `<li class="hcard${here}" data-id="${esc(id)}">
      ${thumb}
      <div class="meta"><b>${esc(title)}</b><span>${esc(label)}${kind === "edit" && mode !== "edit" ? " · Edited model" : ""}${openNow ? " · " + openNow : ""}</span></div>
      <div class="row2">
        <button type="button" class="btn small" data-lib="open" data-id="${esc(id)}" title="${kind === "edit" ? "Open this project in the FDM Slicer" : "Open this photo design"}">Open</button>
        <button type="button" class="btn small" data-lib="edit" data-id="${esc(id)}" title="${kind === "edit" ? "Open this project in CAD" : "Open the slicer copy of this photo design. The first time, ZEIM makes that copy. The photo design stays in Projects."}">Edit</button>
        <button type="button" class="btn small" data-lib="send" data-id="${esc(id)}">Send…</button>
        <button type="button" class="btn small" data-lib="star" data-id="${esc(id)}" aria-pressed="${b.favorite ? "true" : "false"}">${b.favorite ? "Starred" : "Star"}</button>
        <button type="button" class="btn small" data-lib="delete" data-id="${esc(id)}">Delete</button>
      </div></li>`;
  }).filter(Boolean);
  if (!rows.length) return `<li class="hslot">No saved projects yet.</li>`;
  return rows.join("");
}
