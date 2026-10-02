const SHELL_CACHE = 'forest-city-news-shell-v4';
const ASSET_CACHE = 'forest-city-news-assets-v4';
const IMAGE_CACHE = 'forest-city-news-images-v4';
// Replaced with the generated application asset list during the build.
const PRECACHE_ASSETS = [];
const DATA_CACHE = 'forest-city-news-data-v4';
const CACHE_PREFIXES = ['forest-city-news-', 'london-news-'];

function scopePath(path = '') {
  const base = new URL(self.registration.scope).pathname;
  return `${base}${path}`.replace(/\/+/g, '/');
}

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    const urls = [
      scopePath(),
      scopePath('sections/'),
      scopePath('search/'),
      scopePath('read-later/'),
      scopePath('settings/'),
      scopePath('data/app-feed.json'),
      scopePath('manifest.webmanifest')
    ];
    await Promise.all(urls.map((url) => cache.add(url).catch(() => null)));
    const assets = await caches.open(ASSET_CACHE);
    await Promise.all(PRECACHE_ASSETS.map((path) => assets.add(scopePath(path))));
    const data = await caches.open(DATA_CACHE);
    await data.add(scopePath('data/app-feed.json')).catch(() => null);
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, ASSET_CACHE, IMAGE_CACHE, DATA_CACHE]);
    const keys = await caches.keys();
    await Promise.all(keys
      .filter((key) => CACHE_PREFIXES.some((prefix) => key.startsWith(prefix)) && !keep.has(key))
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

async function putBounded(cache, request, response, limit, protectedPaths = []) {
  await cache.put(request, response.clone());
  const keys = await cache.keys();
  const disposable = keys.filter((key) => !protectedPaths.includes(new URL(key.url).pathname));
  if (keys.length > limit) await Promise.all(disposable.slice(0, keys.length - limit).map((key) => cache.delete(key)));
}

async function networkFirst(request, cacheName, fallbackRequest) {
  const cache = await caches.open(cacheName);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(request, { cache: 'no-store', signal: controller.signal });
    if (!response.ok) {
      const cached = await cache.match(request);
      if (cached) return cached;
      return response;
    }
    await putBounded(cache, request, response, cacheName === DATA_CACHE ? 100 : 40, [scopePath(), scopePath('data/app-feed.json')]).catch(() => {});
    return response;
  } catch {
    return (await cache.match(request))
      || (fallbackRequest ? await cache.match(fallbackRequest) : null)
      || Response.error();
  } finally {
    clearTimeout(timer);
  }
}

async function cacheFirst(request, cacheName = ASSET_CACHE) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response?.ok) await putBounded(cache, request, response, cacheName === IMAGE_CACHE ? 240 : 160, PRECACHE_ASSETS.map((path) => scopePath(path))).catch(() => {});
    return response;
  } catch {
    return Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;

  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request, SHELL_CACHE, scopePath()));
    return;
  }

  if (/\/data\/app-feed\.json$/i.test(url.pathname) || /\/data\/stories\/.+\.json$/i.test(url.pathname)) {
    event.respondWith(networkFirst(event.request, DATA_CACHE));
    return;
  }

  if (url.pathname.includes('/_app/immutable/')) {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  if (event.request.destination === 'image') {
    event.respondWith(cacheFirst(event.request, IMAGE_CACHE));
    return;
  }

  if (event.request.destination === 'font') {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  if (event.request.destination === 'style' || event.request.destination === 'script') {
    event.respondWith(networkFirst(event.request, ASSET_CACHE));
  }
});
