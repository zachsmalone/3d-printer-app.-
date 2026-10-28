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

async function run(port, debug, metrics) {
  const logs = [];
  const server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1"], { cwd: root.pathname, stdio: ["ignore", "pipe", "pipe"] });
  listen(server, logs);
  const chrome = spawn("/usr/local/bin/google-chrome", [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--remote-debugging-port=" + debug, "--window-size=" + metrics.width + "," + metrics.height,
    "--user-data-dir=/tmp/chrome-build-chrome-" + debug,
    "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  listen(chrome, logs);
  try {
    const page = await waitFor(async () => {
      const r = await fetch("http://127.0.0.1:" + debug + "/json/list");
      if (!r.ok) return null;
      const pages = await r.json();
      return pages.find((p) => p.type === "page" && p.webSocketDebuggerUrl) || null;
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
    // Headless Chrome will not open a window narrower than 500. Device metrics is the 390px phone width.
    await send("Emulation.setDeviceMetricsOverride", {
      width: metrics.width, height: metrics.height, deviceScaleFactor: 1, mobile: metrics.width < 500,
    });
    await send("Page.navigate", { url: "http://127.0.0.1:" + port + "/tests/fixtures/build-chrome.html" });
    const data = await waitFor(async () => {
      const ev = await send("Runtime.evaluate", { expression: "document.getElementById('out').textContent", returnByValue: true });
      const text = ev.result && ev.result.value;
      if (!text || text === "WAIT") return null;
      return JSON.parse(text);
    }, 20000);
    ws.close();
    return data;
  } finally {
    chrome.kill("SIGKILL");
    server.kill("SIGKILL");
  }
}

test("headless chrome: Exit stays clickable with panels dragged at it", { timeout: 60000 }, async (t) => {
  if (!fs.existsSync("/usr/local/bin/google-chrome")) {
    t.skip("environment blocker: google-chrome is not installed");
    return;
  }
  const desk = await run(8941, 9341, { width: 1280, height: 800 });
  assert.equal(desk.width, 1280);
  assert.deepEqual(desk.fails, [], (desk.fails || []).join("\n"));
  const phone = await run(8942, 9342, { width: 390, height: 844 });
  assert.equal(phone.width, 390);
  assert.deepEqual(phone.fails, [], (phone.fails || []).join("\n"));
});
