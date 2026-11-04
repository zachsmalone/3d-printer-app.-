/* ZEIM offline cache (task 26). Static files only; pages and /api always go to the network.
   __VERSION__ is replaced by the server and changes on every deploy, so old caches are dropped. */
const CACHE = "zeim-static-__VERSION__";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
  await self.clients.claim();
})()));
self.addEventListener("fetch", e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== "GET" || u.origin !== location.origin) return;
  if (u.pathname.startsWith("/static/") && !u.pathname.endsWith(".html") && r.mode !== "navigate" && !r.headers.has("range")) {
    // Network first: a fresh copy whenever online; the cached copy only when the network fails.
    e.respondWith(fetch(r).then(res => {
      if (res.ok && res.type === "basic") { const c = res.clone(); caches.open(CACHE).then(x => x.put(r, c)); }
      return res;
    }).catch(() => caches.match(r).then(m => m || Response.error())));
    return;
  }
  if (r.mode === "navigate") {
    // Pages are never cached; offline gets a plain notice instead of an old page.
    e.respondWith(fetch(r).catch(() => new Response(
      '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline</title><p style="font:16px system-ui;padding:24px">You are offline. Reconnect and reload to keep going.</p>',
      { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } })));
  }
  // Everything else (/api, uploads, downloads) is left to the browser: no caching here.
});
