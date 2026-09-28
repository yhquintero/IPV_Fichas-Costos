// IPV · Fichas y Costos — Service Worker (modo sin conexión)
// Autor: Ing. Yosvany Hernández Quintero
// · Recursos estáticos: stale-while-revalidate.
// · API: red primero; si no hay red se usa la última respuesta pública en caché.
// · Nunca se almacenan respuestas autenticadas ni el flujo de eventos en tiempo real.
const CACHE = 'ipv-fichas-costos-v10';
const STATIC = ['/', '/index.html', '/styles.css', '/app.js', '/enterprise.js', '/qr.js', '/license.js', '/ux.js', '/manifest.json', '/fonts/dm-sans.woff2', '/fonts/manrope.woff2'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/events') || url.pathname.startsWith('/api/auth') || url.pathname.startsWith('/api/license')) return;

  if (url.pathname.startsWith('/api/')) {
    const cacheable = !req.headers.has('Authorization');
    e.respondWith(fetch(req).then(res => {
      if (cacheable && res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return res;
    }).catch(async () => (cacheable && await caches.match(req)) || new Response(
      JSON.stringify({ error: 'Sin conexión con el servidor.' }),
      { status: 503, headers: { 'Content-Type': 'application/json; charset=utf-8' } })));
    return;
  }

  e.respondWith(caches.match(req).then(cached => {
    const network = fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => cached || (req.mode === 'navigate' ? caches.match('/index.html') : Response.error()));
    return cached || network;
  }));
});
