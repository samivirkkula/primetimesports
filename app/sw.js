// Network first, cached copy when offline. Bump VERSION when app files change.
const VERSION = "ruutuaikataulu-24";
const SHELL = ["./", "index.html", "app.css?v=24", "app.js?v=24", "manifest.webmanifest", "icons/icon-192.png", "fonts/archivo.woff"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  // Calendar files go straight to the network: iOS hands them to the calendar preview, which fails via a SW response.
  if (new URL(e.request.url).pathname.endsWith(".ics")) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok || res.type === "opaque") {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(e.request, copy));
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
