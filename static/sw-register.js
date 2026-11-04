/* Registers the offline cache worker (static files only). Safe to fail: the site works without it. */
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  addEventListener("load", () => navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => { }));
}
