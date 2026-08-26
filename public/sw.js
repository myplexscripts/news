const CACHE = 'london-news-shell-v1';
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const base = new URL(self.registration.scope).pathname;
    const urls = [base, `${base}sections/`, `${base}sources/`, `${base}search/`, `${base}latest/`, `${base}manifest.webmanifest`];
    const cache = await caches.open(CACHE);
    await Promise.all(urls.map(url => cache.add(url).catch(() => null)));
    self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== location.origin) return;
  event.respondWith((async () => {
    try {
      const response = await fetch(event.request);
      if (response.ok && (event.request.destination === 'document' || event.request.destination === 'style' || event.request.destination === 'script')) {
        const cache = await caches.open(CACHE);
        cache.put(event.request, response.clone()).catch(() => {});
      }
      return response;
    } catch {
      return (await caches.match(event.request)) || (await caches.match(new URL(self.registration.scope).pathname));
    }
  })());
});
