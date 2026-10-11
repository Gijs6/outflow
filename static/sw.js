const CACHE = "outflow-v6";
const STATIC = ["/static/styles/app.min.css", "/static/vendor/htmx.min.js", "/static/icons/icon-192.png", "/static/icons/icon-512.png", "/static/favicon.svg", "/static/favicon.ico"];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)));
    self.skipWaiting();
});

self.addEventListener("activate", (e) => {
    e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
    self.clients.claim();
});

self.addEventListener("fetch", (e) => {
    if (e.request.method !== "GET") return;
    const url = new URL(e.request.url);
    if (url.origin !== location.origin) return;

    e.respondWith(
        fetch(e.request)
            .then((res) => {
                if (res.ok && url.pathname.startsWith("/static/")) {
                    const clone = res.clone();
                    caches.open(CACHE).then((c) => c.put(e.request, clone));
                }
                return res;
            })
            .catch(() => caches.match(e.request))
    );
});
