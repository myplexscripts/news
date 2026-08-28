const SHELL_CACHE = 'london-news-shell-v2';
const ASSET_CACHE = 'london-news-assets-v2';
const CACHE_PREFIX = 'london-news-';

function scopePath(path = '') {
  const base = new URL(self.registration.scope).pathname;
  return `${base}${path}`.replace(/\/+/g, '/');
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const urls = [
      scopePath(),
      scopePath('sections/'),
      scopePath('sources/'),
      scopePath('search/'),
      scopePath('latest/'),
      scopePath('settings/'),
      scopePath('manifest.webmanifest'),
      scopePath('smart-features.css')
    ];
    const cache = await caches.open(SHELL_CACHE);
    await Promise.all(urls.map((url) => cache.add(url).catch(() => null)));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, ASSET_CACHE]);
    const keys = await caches.keys();
    await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX) && !keep.has(key)).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

async function fetchNetwork(request, timeoutMs = 5000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(request, {
      signal: controller.signal,
      cache: request.mode === 'navigate' ? 'no-store' : 'no-cache'
    });
  } finally {
    clearTimeout(timer);
  }
}

async function networkFirst(request, cacheName, timeoutMs = 5000, fallbackToHome = false) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetchNetwork(request, timeoutMs);
    if (response.ok) cache.put(request, response.clone()).catch(() => {});
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    if (fallbackToHome) {
      const home = await caches.match(scopePath());
      if (home) return home;
    }
    return Response.error();
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSET_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone()).catch(() => {});
    return response;
  } catch {
    return Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Never let a feed payload become stale behind the service worker. The current
  // Astro site bakes news into HTML, but this guard keeps a future JSON endpoint
  // network-only too.
  if (/\/(?:data\/)?news\.json$/i.test(url.pathname)) {
    event.respondWith(fetch(event.request, { cache: 'no-store' }));
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request, SHELL_CACHE, 4500, true));
    return;
  }

  if (event.request.destination === 'image' || event.request.destination === 'font') {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  if (event.request.destination === 'style' || event.request.destination === 'script') {
    event.respondWith(networkFirst(event.request, ASSET_CACHE, 4500));
  }
});
