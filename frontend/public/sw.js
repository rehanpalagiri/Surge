// Surge service worker
// Responsibilities:
//   1. Intercept Web Share Target POST to /share, store the video, redirect to /share page
//   2. Cache-first for immutable Next.js static assets (/_next/static/)
//   3. Network-first for everything else

const STATIC_CACHE = 'surge-static-v1';
const SHARE_CACHE  = 'surge-share-v1';
const SHARE_KEY    = '/pending-share';

// ─── Lifecycle ────────────────────────────────────────────────────────────────

self.addEventListener('install', () => {
  // Activate immediately — don't wait for old tabs to close
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k !== STATIC_CACHE && k !== SHARE_CACHE)
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

  // 1. Web Share Target: browser POSTs the shared file here
  if (url.pathname === '/share' && request.method === 'POST') {
    event.respondWith(handleShareTarget(request));
    return;
  }

  // 2. Skip non-same-origin requests (Render API, Gemini, etc.)
  if (url.origin !== self.location.origin) return;

  // 3. Cache-first for Next.js static bundles (content-hashed, safe to cache forever)
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

  // 4. Network-first for HTML/navigation — always serve fresh pages
  // (no respondWith → browser handles normally)
});

// ─── Share target handler ─────────────────────────────────────────────────────

async function handleShareTarget(request) {
  try {
    const formData = await request.formData();
    const video = formData.get('video');

    if (video instanceof File && video.size > 0) {
      const cache = await caches.open(SHARE_CACHE);
      // Store the raw file bytes with metadata in headers so the /share page can reconstruct a File
      await cache.put(
        SHARE_KEY,
        new Response(video, {
          headers: {
            'Content-Type': video.type || 'video/mp4',
            'X-File-Name': encodeURIComponent(video.name || 'shared-video.mp4'),
            'X-Timestamp': String(Date.now()),
          },
        })
      );
    }
  } catch (err) {
    console.error('[Surge SW] Share target error:', err);
  }

  // Redirect the browser to the share page (GET)
  return Response.redirect('/share', 303);
}
