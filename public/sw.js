const SHELL_CACHE = 'london-news-shell-v7';
const ASSET_CACHE = 'london-news-assets-v7';
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
      scopePath('read-later/'),
      scopePath('latest/'),
      scopePath('settings/'),
      scopePath('manifest.webmanifest')
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
    if (self.registration.navigationPreload) {
      await self.registration.navigationPreload.enable().catch(() => {});
    }
    await self.clients.claim();
  })());
});

async function fetchNetwork(request, timeoutMs = 4000) {
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

async function navigationNetworkFirst(event, fallbackToHome = false) {
  const request = event.request;
  const cache = await caches.open(SHELL_CACHE);
  let timer;

  try {
    const response = await Promise.race([
      (async () => {
        const preloaded = await event.preloadResponse;
        return preloaded || fetchNetwork(request, 8000);
      })(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('navigation timeout')), 8000);
      })
    ]);

    clearTimeout(timer);
    if (response?.ok) cache.put(request, response.clone()).catch(() => {});
    return response;
  } catch {
    clearTimeout(timer);
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

async function assetNetworkFirst(request, timeoutMs = 1800) {
  const cache = await caches.open(ASSET_CACHE);
  try {
    const response = await fetchNetwork(request, timeoutMs);
    if (response?.ok) cache.put(request, response.clone()).catch(() => {});
    return response;
  } catch {
    return (await cache.match(request)) || Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  // Feed data is always network-only so a service worker can never hold the
  // timeline on an older refresh.
  if (/\/(?:data\/)?news\.json$/i.test(url.pathname)) {
    event.respondWith(fetch(event.request, { cache: 'no-store' }));
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(navigationNetworkFirst(event, true));
    return;
  }

  if (event.request.destination === 'image' || event.request.destination === 'font') {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  if (event.request.destination === 'style' || event.request.destination === 'script') {
    // Astro's hashed bundles are immutable by URL and safe to serve cache-first.
    // Stable public CSS/JS names must check the network first so layout changes
    // are visible on the first visit after a deploy instead of one refresh later.
    if (url.pathname.includes('/_astro/')) {
      event.respondWith(cacheFirst(event.request));
    } else {
      event.respondWith(assetNetworkFirst(event.request));
    }
  }
});
