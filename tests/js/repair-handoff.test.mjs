/* Headless check: repair opens the FDM Slicer from the server, without posting the file to /api/edit/new. */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawn, execFileSync } from "node:child_process";
import { once } from "node:events";

const root = new URL("../..", import.meta.url).pathname;
const PORT = 8877;
const DEBUG = 9367;
const STL = "/tmp/zeim-repair-box.stl";

function listen(proc, sink) {
  proc.stdout?.on("data", (b) => sink.push(b.toString()));
  proc.stderr?.on("data", (b) => sink.push(b.toString()));
}

async function waitFor(fn, ms) {
  const start = Date.now();
  let last = "";
  while (Date.now() - start < ms) {
    try {
      const v = await fn();
      if (v) return v;
    } catch (e) { last = String(e && e.message || e); }
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(last || "timed out");
}

test("headless chrome: Open in the FDM Slicer does not upload the repaired file again", { timeout: 90000 }, async (t) => {
  if (!fs.existsSync("/usr/local/bin/google-chrome")) {
    t.skip("environment blocker: google-chrome is not installed");
    return;
  }
  execFileSync("python3", ["-c", "import trimesh; trimesh.creation.box((20,20,20)).export('/tmp/zeim-repair-box.stl')"]);
  const logs = [];
  const data = fs.mkdtempSync("/tmp/zeim-repair-data-");
  const server = spawn("python3", ["-m", "app.serve"], {
    cwd: root,
    env: {
      ...process.env,
      PORT: String(PORT),
      HOST: "127.0.0.1",
      PHOTO3D_DATA: data + "/d",
      PHOTO3D_OUT: data + "/o",
      PHOTO3D_MODE: "local",
      PHOTO3D_AGE_GATE: "0",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  listen(server, logs);
  fs.rmSync("/tmp/chrome-repair-handoff", { recursive: true, force: true });
  const chrome = spawn("/usr/local/bin/google-chrome", [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    `--remote-debugging-port=${DEBUG}`, "--window-size=1280,800",
    "--user-data-dir=/tmp/chrome-repair-handoff",
    "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  listen(chrome, logs);
  let ws;
  try {
    await waitFor(async () => {
      const r = await fetch(`http://127.0.0.1:${PORT}/static/repair.html`);
      return r.ok ? true : null;
    }, 20000);
    const page = await waitFor(async () => {
      const r = await fetch(`http://127.0.0.1:${DEBUG}/json/list`);
      if (!r.ok) return null;
      const pages = await r.json();
      return pages.find((p) => p.webSocketDebuggerUrl && p.type === "page") || null;
    }, 15000);
    ws = new WebSocket(page.webSocketDebuggerUrl);
    await once(ws, "open");
    let seq = 0;
    const pending = new Map();
    const requests = [];
    ws.addEventListener("message", (ev) => {
      const raw = typeof ev.data === "string" ? ev.data : String(ev.data);
      const msg = JSON.parse(raw);
      if (msg.method === "Network.requestWillBeSent" && msg.params && msg.params.request) {
        requests.push(msg.params.request.method + " " + msg.params.request.url);
      }
      if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    });
    const send = (method, params) => new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, (msg) => (msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)));
      ws.send(JSON.stringify({ id, method, params }));
    });
    const value = async (expression) => {
      const ev = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
      if (ev.exceptionDetails) throw new Error(JSON.stringify(ev.exceptionDetails));
      return ev.result && ev.result.value;
    };
    await send("Network.enable", {});
    await send("Page.enable", {});
    await send("DOM.enable", {});
    await send("Page.navigate", { url: `http://127.0.0.1:${PORT}/static/repair.html` });
    await waitFor(async () => (await value("!!document.getElementById('rpFile')")) ? true : null, 15000);
    assert.equal(await value("document.getElementById('projectFlow').hidden"), true);
    const doc = await send("DOM.getDocument", { depth: 1 });
    const input = await send("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#rpFile" });
    await send("DOM.setFileInputFiles", { nodeId: input.nodeId, files: [STL] });
    await waitFor(async () => (await value("document.getElementById('rpGo').disabled")) === false ? true : null, 5000);
    await value("document.getElementById('rpGo').click()");
    const note = await waitFor(async () => {
      const text = await value("document.getElementById('rpNext') && document.getElementById('rpNext').textContent");
      return text && text.includes("new project from that file") ? text : null;
    }, 30000);
    assert.match(note, /file you uploaded stays as it was/);
    assert.equal(await value("document.getElementById('projectFlow').hidden"), true);
    await value("document.getElementById('rpOpenSlicer').click()");
    const landed = await waitFor(async () => {
      const href = await value("location.href");
      if (!href || !href.includes("edit=") || !href.includes("#slicer")) return null;
      const ready = await value("!!document.getElementById('editPanel') && document.getElementById('editPanel').hidden === false");
      return ready ? href : null;
    }, 30000);
    assert.match(landed, /\/\?edit=[0-9a-f]{12}#slicer$/);
    const posted = requests.filter((r) => r.startsWith("POST "));
    assert.equal(posted.some((r) => r.includes("/api/edit/new")), false);
    assert.equal(posted.some((r) => /\/api\/repair\/[0-9a-f]{16}\/slicer/.test(r)), true);
    assert.equal(requests.some((r) => r.startsWith("GET ") && /\/api\/repair\/[0-9a-f]{16}$/.test(r.split(" ")[1])), false);
    const exitTitle = await value("document.querySelector('[data-ws-act=\"exit\"]').title");
    assert.match(exitTitle, /does not send the model to Showcase/);
    assert.equal(await value("!!document.getElementById('dlgPublish') && document.getElementById('dlgPublish').open"), false);
  } catch (err) {
    const tail = logs.join("").slice(-2000);
    throw new Error(String(err && err.stack || err) + (tail ? "\n--- logs ---\n" + tail : ""));
  } finally {
    if (ws) try { ws.close(); } catch { /* already closed */ }
    chrome.kill("SIGKILL");
    server.kill("SIGKILL");
  }
});
