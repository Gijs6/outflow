const CACHE = "outflow-v2";
const STATIC = ["/static/styles/app.min.css", "/static/js/icons.js", "/static/vendor/htmx.min.js", "/static/images/icon-192.png", "/static/images/icon-512.png", "/static/favicon.svg", "/static/favicon.ico"];

self.addEventListener("install", (e) => {
    e.waitUntil(caches.open(CACHE).then((c) => c.addAll(STATIC)));
    self.skipWaiting();
});

self.addEventListener("activate", (e) => {
    e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
    self.clients.claim();
});

self.addEventListener("fetch", (e) => {
    const url = new URL(e.request.url);

    if (url.pathname.startsWith("/static/")) {
        e.respondWith(
            caches.match(e.request).then(
                (cached) =>
                    cached ||
                    fetch(e.request).then((res) => {
                        const clone = res.clone();
                        caches.open(CACHE).then((c) => c.put(e.request, clone));
                        return res;
                    })
            )
        );
        return;
    }

    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
