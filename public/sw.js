/* FarmIntel service worker.
 *
 * Strategy
 *   - App shell + built assets: cache-first, refreshed in the background.
 *   - Mandi price API (GET): stale-while-revalidate, so the last known real
 *     price is shown offline with an "offline" banner instead of an error.
 *   - Everything else: network, falling back to the shell when offline.
 *
 * No secrets and no personalised responses are cached: only public price
 * endpoints (which the backend serves without authentication).
 */

const VERSION = 'agrosmart-v1';
const SHELL_CACHE = `${VERSION}-shell`;
const API_CACHE = `${VERSION}-api`;

const SHELL_ASSETS = ['/', '/index.html', '/manifest.webmanifest', '/logo.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).catch(() => undefined),
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

const isPriceApi = (url) =>
  url.pathname.startsWith('/market/') ||
  /\/market\/(price|history|coverage|status)/.test(url.pathname);

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  // Never cache auth or chat traffic.
  if (url.pathname.startsWith('/chat') || url.pathname.includes('/auth/')) return;

  if (isPriceApi(url)) {
    event.respondWith(
      caches.open(API_CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        const network = fetch(request)
          .then((res) => {
            if (res.ok) cache.put(request, res.clone());
            return res;
          })
          .catch(() => null);
        const fresh = await network;
        if (fresh) return fresh;
        if (cached) {
          const headers = new Headers(cached.headers);
          headers.set('x-agrosmart-offline', '1');
          return new Response(await cached.blob(), { status: 200, headers });
        }
        return new Response(
          JSON.stringify({
            commodity: '',
            price: null,
            source: 'unavailable',
            detail: 'You are offline and no cached price exists yet.',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }),
    );
    return;
  }

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL_CACHE).then((c) => c.put('/index.html', copy)).catch(() => undefined);
          return res;
        })
        .catch(() => caches.match('/index.html').then((r) => r || Response.error())),
    );
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(SHELL_CACHE).then((c) => c.put(request, copy)).catch(() => undefined);
            }
            return res;
          })
          .catch(() => cached);
        return cached || network;
      }),
    );
  }
});

self.addEventListener('message', (event) => {
  if (event.data === 'skip-waiting') self.skipWaiting();
});
