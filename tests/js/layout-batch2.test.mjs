import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { once } from "node:events";

const require = createRequire(import.meta.url);
const root = new URL("../..", import.meta.url);
const read = (rel) => fs.readFileSync(new URL(rel, root), "utf8");
const PHONE_Q = "(max-width:820px), (max-height:500px) and (pointer:coarse)";

test("layout source does not minimise, hide, or mark a crowd to make room", () => {
  const js = read("static/wslayout.js");
  assert.match(js, /function watchObstacles\(\)/);
  assert.match(js, /watchObstacles\(\);/);
  assert.match(js, /undo the trial edges' classes/);
  assert.match(js, /chipPri/);
  assert.match(js, /layout does not minimise or hide another panel/);
  assert.match(js, /a core panel never steps aside/);
  assert.match(js, /userSize/);
  assert.match(js, /data-dir="n"/);
  assert.match(js, /Remove/);
  assert.match(js, /interacting/);
  assert.equal(js.includes('classList.add("min", "auto-min")'), false);
  assert.equal(js.includes('classList.add("auto-off")'), false);
  assert.equal(js.includes('dataset.crowded = "1"'), false);
  assert.equal(js.includes("shrink = ["), false);
  const main = read("static/ws-main.js");
  const cad = read("static/cad-phone.js");
  assert.match(main, /function studioRoute\(\)/);
  assert.equal(main.includes("return !!b && !b.hidden"), false);
  assert.equal(main.includes("var ph = PHONE.matches"), false);
  assert.match(main, /def:\s*function \(\)/);
  assert.equal(cad.includes("var ph = PHONE.matches"), false);
  assert.match(cad, /def:\s*function \(\)/);
  assert.match(main, new RegExp(PHONE_Q.replace(/[()]/g, "\\$&")));
  assert.match(js, new RegExp(PHONE_Q.replace(/[()]/g, "\\$&")));
});

function installMedia(w, phoneOn) {
  const lists = [];
  const state = { phone: phoneOn };
  w.matchMedia = (q) => {
    const media = String(q);
    const mq = {
      media,
      matches: media.includes("max-width:820px") ? state.phone : media.includes("landscape") ? w.innerWidth > w.innerHeight : false,
      _fns: [],
      addEventListener(type, fn) { if (type === "change") this._fns.push(fn); },
      removeEventListener(type, fn) { this._fns = this._fns.filter((f) => f !== fn); },
      addListener(fn) { this._fns.push(fn); },
      removeListener(fn) { this._fns = this._fns.filter((f) => f !== fn); },
    };
    lists.push(mq);
    return mq;
  };
  w.setPhone = (on) => {
    state.phone = on;
    const rows = lists.filter((mq) => mq.media.includes("max-width:820px"));
    rows.forEach((mq) => { mq.matches = on; });
    rows.forEach((mq) => mq._fns.slice().forEach((fn) => fn({ matches: on, media: mq.media })));
  };
}

function boot(hash, phoneOn) {
  const { JSDOM } = require("/tmp/jsdom-batch2/node_modules/jsdom");
  const html = `<!DOCTYPE html><body>
    <main id="viewCreate">
      <aside class="controls" id="photoSettings"></aside>
      <section class="stage">
        <div id="vtools"><span id="litLightBox" hidden>light</span></div>
        <div id="result"></div>
        <section class="history" id="recentBuilds"></section>
      </section>
    </main>
  </body>`;
  const dom = new JSDOM(html, { url: "http://127.0.0.1/" + hash, pretendToBeVisual: true, runScripts: "dangerously" });
  const w = dom.window;
  w.innerWidth = 1280;
  w.innerHeight = 800;
  w.fetch = () => Promise.resolve({ ok: false, json: async () => null });
  if (typeof w.ResizeObserver !== "function") {
    w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  }
  w.visualViewport = {
    height: 800, width: 1280, offsetTop: 0, _fns: [],
    addEventListener(type, fn) { this._fns.push(fn); },
    removeEventListener(type, fn) { this._fns = this._fns.filter((f) => f !== fn); },
    dispatchEvent() { this._fns.slice().forEach((fn) => fn()); },
  };
  installMedia(w, phoneOn);
  let resizeAdds = 0, resizeRems = 0;
  const add = w.addEventListener.bind(w);
  const rem = w.removeEventListener.bind(w);
  w.addEventListener = (type, fn, opt) => { if (type === "resize") resizeAdds++; return add(type, fn, opt); };
  w.removeEventListener = (type, fn, opt) => { if (type === "resize") resizeRems++; return rem(type, fn, opt); };
  w.eval(read("static/wslayout.js"));
  w.eval(read("static/ws-main.js"));
  w.__resizeAdds = () => resizeAdds;
  w.__resizeRems = () => resizeRems;
  return w;
}

const settle = () => new Promise((r) => setTimeout(r, 0));

test("free rectangles stay out of obstacles", async () => {
  const w = boot("#studio", false);
  const box = { x: 0, y: 0, w: 100, h: 100 };
  const lower = w.ZWS.freeRects(box, [{ x: 0, y: 0, w: 100, h: 40 }]);
  assert.ok(lower.some((r) => r.y >= 39 && r.w > 90 && r.y + r.h >= 99), JSON.stringify(lower));
  assert.equal(lower.some((r) => r.y < 10 && r.h > 30), false);
  const sides = w.ZWS.freeRects(box, [{ x: 40, y: 0, w: 20, h: 100 }]);
  assert.ok(sides.some((r) => r.x < 5 && r.w > 30), JSON.stringify(sides));
  assert.ok(sides.some((r) => r.x > 55 && r.w > 30), JSON.stringify(sides));
  const column = w.ZWS.freeRects(box, [{ x: 0, y: 0, w: 40, h: 20 }, { x: 70, y: 0, w: 30, h: 50 }]);
  assert.ok(column.some((r) => r.x < 1 && r.w > 30 && r.y >= 19 && r.y < 25 && r.h > 70), JSON.stringify(column));
  w.ZWS.all.studio.destroy();
  await settle();
  w.close();
});

test("lithophane identity follows the route, not the light box", async () => {
  const w = boot("#lithophane", false);
  await settle();
  const st = w.ZWS.all.studio;
  assert.equal(w.document.querySelector("#litLightBox").hidden, true);
  assert.equal(st.setHidden("settings", true), true);
  const keys = Object.keys(w.localStorage);
  assert.ok(keys.some((k) => k.split(".")[3] === "litho"), keys.join(" "));
  assert.equal(keys.some((k) => k.split(".")[3] === "studio"), false);
  w.document.querySelector("#litLightBox").hidden = false;
  st.setHidden("history", true);
  const after = Object.keys(w.localStorage);
  assert.equal(after.some((k) => k.split(".")[3] === "studio"), false, after.join(" "));
  assert.equal(st.state().settings.hidden, true);
  w.location.hash = "#studio";
  w.dispatchEvent(new w.Event("hashchange"));
  assert.equal(st.state().settings.hidden, false);
  assert.equal(JSON.parse(w.localStorage.getItem("zeim.ws.guest.litho")).settings.hidden, true);
  w.location.hash = "#create";
  w.dispatchEvent(new w.Event("hashchange"));
  st.setHidden("view", true);
  const studioSaved = JSON.parse(w.localStorage.getItem("zeim.ws.guest.studio"));
  const lithoSaved = JSON.parse(w.localStorage.getItem("zeim.ws.guest.litho"));
  assert.equal(studioSaved.view.hidden, true);
  assert.equal(!!(lithoSaved.view && lithoSaved.view.hidden), false);
  w.ZWS.all.studio.destroy();
  await settle();
  w.close();
});

test("phone defaults apply on a breakpoint only when the layout was not customised", async () => {
  const fresh = boot("#studio", false);
  await settle();
  const st = fresh.ZWS.all.studio;
  assert.equal(st.state().settings.min, false);
  assert.equal(st.state().result.edge, "right");
  assert.equal(st.state().history.hidden, false);
  assert.equal(st.state().history.min, true);
  fresh.setPhone(true);
  assert.equal(st.state().settings.min, true);
  assert.equal(st.state().result.edge, "bottom");
  assert.equal(st.state().result.h, Math.round(fresh.innerHeight * 0.42));
  assert.equal(st.state().history.hidden, true);
  assert.equal(st.state().history.min, false);
  fresh.ZWS.all.studio.destroy();
  await settle();
  fresh.close();

  const saved = boot("#studio", false);
  await settle();
  const ws = saved.ZWS.all.studio;
  saved.document.querySelector("#zws-result .zws-grip").click();
  const edge = ws.state().result.edge;
  assert.notEqual(edge, "right");
  saved.setPhone(true);
  assert.equal(ws.state().result.edge, edge);
  assert.equal(ws.state().settings.min, false);
  ws.reset();
  assert.equal(ws.state().settings.min, true);
  assert.equal(ws.state().result.edge, "bottom");
  assert.equal(ws.state().result.userSize, false);
  assert.equal(saved.localStorage.getItem("zeim.ws.guest.studio"), null);
  assert.equal(saved.localStorage.getItem("zeim.ws.guest.studio.land"), null);
  assert.equal(saved.localStorage.getItem("zeim.ws.guest.studio.port"), null);
  saved.ZWS.all.studio.destroy();
  await settle();
  saved.close();
});

test("a phone keyboard reflow does not change which panels are open", async () => {
  const w = boot("#studio", false);
  await settle();
  const st = w.ZWS.all.studio;
  const snap = JSON.stringify(st.state());
  w.visualViewport.height = w.innerHeight - 320;
  w.visualViewport.dispatchEvent(new w.Event("resize"));
  w.setPhone(true);
  assert.equal(JSON.stringify(st.state()), snap);
  w.visualViewport.height = w.innerHeight;
  w.setPhone(false);
  assert.equal(st.state().settings.min, false);
  assert.equal(st.state().result.edge, "right");
  w.ZWS.all.studio.destroy();
  await settle();
  w.close();
});

test("orientation keeps the other orientation's dock and reset clears both", async () => {
  const w = boot("#studio", false);
  await settle();
  w.innerWidth = 1280;
  w.innerHeight = 800;
  const st = w.ZWS.all.studio;
  w.document.querySelector("#zws-result .zws-grip").click();
  const custom = st.state().result.edge;
  w.innerWidth = 400;
  w.innerHeight = 900;
  w.dispatchEvent(new w.Event("orientationchange"));
  assert.equal(st.state().result.edge, "right");
  assert.equal(JSON.parse(w.localStorage.getItem("zeim.ws.guest.studio.land")).result.edge, custom);
  st.reset();
  assert.equal(w.localStorage.getItem("zeim.ws.guest.studio.land"), null);
  assert.equal(w.localStorage.getItem("zeim.ws.guest.studio.port"), null);
  assert.equal(st.state().result.edge, "right");
  w.ZWS.all.studio.destroy();
  await settle();
  w.close();
});

test("destroy removes the resize listener", async () => {
  const w = boot("#studio", false);
  await settle();
  const root = w.document.querySelector("#viewCreate");
  assert.equal(root.classList.contains("zws"), true);
  const adds = w.__resizeAdds();
  assert.ok(adds >= 1);
  w.ZWS.all.studio.destroy();
  await settle();
  assert.equal(root.classList.contains("zws"), false);
  assert.equal(w.__resizeRems(), adds);
  w.dispatchEvent(new w.Event("resize"));
  await settle();
  assert.equal(root.classList.contains("zws"), false);
  w.close();
});

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

test("headless chrome: panels do not overlap, auto-hide, or ignore a user size", { timeout: 60000 }, async (t) => {
  if (!fs.existsSync("/usr/local/bin/google-chrome")) {
    t.skip("environment blocker: google-chrome is not installed");
    return;
  }
  const logs = [];
  const server = spawn("python3", ["-m", "http.server", "8931", "--bind", "127.0.0.1"], { cwd: root.pathname, stdio: ["ignore", "pipe", "pipe"] });
  listen(server, logs);
  const chrome = spawn("/usr/local/bin/google-chrome", [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--remote-debugging-port=9333", "--window-size=1280,800",
    "--user-data-dir=/tmp/chrome-layout-batch2",
    "http://127.0.0.1:8931/tests/fixtures/layout-batch2.html",
  ], { stdio: ["ignore", "pipe", "pipe"] });
  listen(chrome, logs);
  try {
    await waitFor(async () => {
      const r = await fetch("http://127.0.0.1:9333/json/list");
      if (!r.ok) return null;
      const pages = await r.json();
      return pages.find((p) => (p.url || "").includes("layout-batch2.html") && p.webSocketDebuggerUrl);
    }, 15000);
    const list = await (await fetch("http://127.0.0.1:9333/json/list")).json();
    const page = list.find((p) => (p.url || "").includes("layout-batch2.html"));
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
    }, 20000);
    assert.deepEqual(data.fails, [], (data.fails || []).join("\n") + "\n" + (data.notes || []).join("\n"));
    ws.close();
  } finally {
    chrome.kill("SIGKILL");
    server.kill("SIGKILL");
  }
});

test("headless chrome: route and phone defaults", { timeout: 60000 }, async (t) => {
  if (!fs.existsSync("/usr/local/bin/google-chrome")) {
    t.skip("environment blocker: google-chrome is not installed");
    return;
  }
  async function run(windowSize, hash) {
    const logs = [];
    const port = windowSize.startsWith("390") ? 8932 : 8933;
    const debug = windowSize.startsWith("390") ? 9334 : 9335;
    const server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1"], { cwd: root.pathname, stdio: ["ignore", "pipe", "pipe"] });
    listen(server, logs);
    const chrome = spawn("/usr/local/bin/google-chrome", [
      "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
      "--remote-debugging-port=" + debug, "--window-size=" + windowSize,
      "--user-data-dir=/tmp/chrome-layout-" + debug,
      "http://127.0.0.1:" + port + "/tests/fixtures/layout-batch2-main.html" + hash,
    ], { stdio: ["ignore", "pipe", "pipe"] });
    listen(chrome, logs);
    try {
      const page = await waitFor(async () => {
        const r = await fetch("http://127.0.0.1:" + debug + "/json/list");
        if (!r.ok) return null;
        const pages = await r.json();
        return pages.find((p) => (p.url || "").includes("layout-batch2-main.html") && p.webSocketDebuggerUrl) || null;
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
      }, 20000);
      ws.close();
      return data;
    } finally {
      chrome.kill("SIGKILL");
      server.kill("SIGKILL");
    }
  }
  const desk = await run("1280,800", "#lithophane");
  assert.equal(desk.phone, false, JSON.stringify(desk));
  assert.equal(desk.state.result.edge, "right");
  assert.equal(desk.state.settings.min, false);
  assert.ok(desk.extra.keys.every((k) => k.split(".")[3] === "litho"), desk.extra.keys.join(" "));
  assert.equal(desk.extra.settingsHidden, true);

  const phone = await run("390,844", "#studio");
  assert.equal(phone.phone, true, JSON.stringify(phone));
  assert.equal(phone.state.settings.min, true);
  assert.equal(phone.state.result.edge, "bottom");
  assert.equal(phone.state.history.hidden, true);
  assert.equal(phone.hash, "#studio");
});
