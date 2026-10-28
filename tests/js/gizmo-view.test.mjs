/* Headless check: a bead drag writes the plate transform, and a bead over Exit is not a hit target. */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawn } from "node:child_process";
import { once } from "node:events";

const root = new URL("../..", import.meta.url);

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
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(last || "timed out");
}

test("headless chrome: gizmo drag commits a plate transform and stays off Exit", { timeout: 40000 }, async (t) => {
  if (!fs.existsSync("/usr/local/bin/google-chrome")) {
    t.skip("environment blocker: google-chrome is not installed");
    return;
  }
  const logs = [];
  const server = spawn("python3", ["-m", "http.server", "8955", "--bind", "127.0.0.1"], { cwd: root.pathname, stdio: ["ignore", "pipe", "pipe"] });
  listen(server, logs);
  const chrome = spawn("/usr/local/bin/google-chrome", [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--remote-debugging-port=9355", "--window-size=800,600",
    "--user-data-dir=/tmp/chrome-gizmo",
    "http://127.0.0.1:8955/tests/fixtures/gizmo.html",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  listen(chrome, logs);
  try {
    const page = await waitFor(async () => {
      const r = await fetch("http://127.0.0.1:9355/json/list");
      if (!r.ok) return null;
      const pages = await r.json();
      return pages.find((p) => (p.url || "").includes("gizmo.html") && p.webSocketDebuggerUrl) || null;
    }, 15000);
    const ws = new WebSocket(page.webSocketDebuggerUrl);
    await once(ws, "open");
    let seq = 0;
    const pending = new Map();
    ws.addEventListener("message", (ev) => {
      const raw = typeof ev.data === "string" ? ev.data : String(ev.data);
      const msg = JSON.parse(raw);
      if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    });
    const send = (method, params) => new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, (msg) => (msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)));
      ws.send(JSON.stringify({ id, method, params }));
    });
    const data = await waitFor(async () => {
      const ev = await send("Runtime.evaluate", { expression: "document.getElementById('out').textContent", returnByValue: true });
      const text = ev.result && ev.result.value;
      if (!text || text === "WAIT") return null;
      return JSON.parse(text);
    }, 15000);
    ws.close();
    assert.deepEqual(data.fails, [], (data.fails || []).join("\n"));
  } finally {
    chrome.kill("SIGKILL");
    server.kill("SIGKILL");
  }
});
