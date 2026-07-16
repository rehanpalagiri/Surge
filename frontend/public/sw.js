// CraftLint service worker
// Responsibilities:
//   1. Cache-first for immutable Next.js static assets (/_next/static/)
//   2. Network-first for everything else

const STATIC_CACHE = 'surge-static-v2';

// ─── Lifecycle ────────────────────────────────────────────────────────────────

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== STATIC_CACHE)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

// ─── Fetch ────────────────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-same-origin requests (Render API, etc.)
  if (url.origin !== self.location.origin) return;

  // Never cache local development chunks: Next dev uses stable filenames such
  // as app/layout.js, so cache-first can strand the browser on stale code.
  if (url.hostname === 'localhost' || url.hostname.startsWith('127.')) return;

  // Cache-first for Next.js static bundles (content-hashed, safe to cache forever)
  if (url.pathname.startsWith('/_next/static/')) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((res) => {
          const clone = res.clone();
          caches.open(STATIC_CACHE).then((c) => c.put(request, clone));
          return res;
        });
      })
    );
    return;
  }

  // Network-first for HTML/navigation — always serve fresh pages
  // (no respondWith → browser handles normally)
});
