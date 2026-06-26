/* Лента.PM — Service Worker v5 */
const VERSION      = 'v5';
const CACHE_STATIC = `lenta-static-${VERSION}`;
const CACHE_API    = `lenta-api-${VERSION}`;

// Статика с версионными строками — кэшируем навсегда
const PRECACHE = [
    '/static/css/style.css?v=20260625',
    '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
    '/static/img/raccoon.png',
    '/static/vendor/bootstrap/bootstrap.bundle.min.js',
    '/static/vendor/bootstrap/bootstrap.min.css',
    '/static/js/app.js?v=20260625',
];

const API_CACHE_ROUTES = [
    '/api/online',
    '/api/vpk/unread',
    '/api/chat/unread',
    '/api/notifications/construction',
    '/api/notifications/reconstruct',
];
const API_TTL      = 5  * 60 * 1000;
const PROJECTS_TTL = 30 * 60 * 1000;

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', e => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE_STATIC)
            .then(c => c.addAll(PRECACHE).catch(() => {}))
    );
});

// ── Activate: удаляем старые кэши, захватываем клиентов, перезагружаем ───────
self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys()
            .then(keys => Promise.all(
                keys.filter(k => k !== CACHE_STATIC && k !== CACHE_API)
                    .map(k => caches.delete(k))
            ))
            .then(() => self.clients.claim())
            .then(() => self.clients.matchAll({ type: 'window' }))
            .then(clientList => {
                // Force-reload every open tab once so pages that were stuck on
                // ERR_FAILED (caused by the old broken SW) recover immediately
                // without requiring the user to manually refresh.
                // This fires only once — when this SW version first activates.
                clientList.forEach(c => c.navigate(c.url).catch(() => {}));
            })
    );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', e => {
    const req = e.request;
    if (req.method !== 'GET') return;

    let url;
    try { url = new URL(req.url); } catch { return; }

    // Только наш домен
    if (url.origin !== self.location.origin) return;

    // ── 1. Статика: cache-first (URL содержит версию) ────────────────────────
    if (url.pathname.startsWith('/static/')) {
        e.respondWith(staticFirst(req));
        return;
    }

    // ── 2. HTML-страницы: ВСЕГДА network-first, НЕ кэшируем ─────────────────
    //    (они динамические, user-specific, с Cache-Control: no-store)
    if (req.headers.get('accept')?.includes('text/html')) {
        e.respondWith(htmlNetworkFirst(req));
        return;
    }

    // ── 3. API с TTL-кэшем ───────────────────────────────────────────────────
    if (url.pathname === '/api/projects/cache-data') {
        e.respondWith(networkFirstWithTTL(req, PROJECTS_TTL));
        return;
    }
    if (API_CACHE_ROUTES.some(r => url.pathname.startsWith(r))) {
        e.respondWith(networkFirstWithTTL(req, API_TTL));
        return;
    }
});

async function staticFirst(req) {
    try {
        const cache = await caches.open(CACHE_STATIC);
        const hit   = await cache.match(req);
        if (hit) return hit;
        const res = await fetch(req);
        if (res && res.ok) cache.put(req, res.clone());
        return res;
    } catch {
        const cache = await caches.open(CACHE_STATIC);
        return await cache.match(req) || new Response('', { status: 503 });
    }
}

async function htmlNetworkFirst(req) {
    try {
        return await fetch(req);
    } catch {
        // Офлайн: показываем заглушку
        return new Response(
            '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">' +
            '<meta name="viewport" content="width=device-width,initial-scale=1">' +
            '<title>Офлайн — Лента.PM</title>' +
            '<style>body{font-family:sans-serif;text-align:center;padding:48px 24px;background:#0f172a;color:#e2e8f0}' +
            'h2{color:#3CB34A}a{color:#3CB34A;font-weight:700}</style></head>' +
            '<body><h2>📵 Нет подключения</h2>' +
            '<p>Проверьте интернет и обновите страницу.</p>' +
            '<a href="/">← На главную</a></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
    }
}

async function networkFirstWithTTL(req, ttl) {
    try {
        const res = await fetch(req);
        if (res.ok) {
            const cache   = await caches.open(CACHE_API);
            const headers = new Headers(res.headers);
            headers.set('x-sw-cached-at', Date.now().toString());
            const timed   = new Response(await res.clone().blob(), { status: res.status, headers });
            cache.put(req, timed);
        }
        return res;
    } catch {
        const cache = await caches.open(CACHE_API);
        const hit   = await cache.match(req);
        if (!hit) return new Response(JSON.stringify({ offline: true, cached: false }),
            { headers: { 'Content-Type': 'application/json' } });
        const age = Date.now() - parseInt(hit.headers.get('x-sw-cached-at') || '0');
        if (age > ttl) return new Response(JSON.stringify({ offline: true, stale: true }),
            { headers: { 'Content-Type': 'application/json' } });
        return hit;
    }
}

// ── Version ping (для авто-детекта старого SW на странице) ───────────────────
self.addEventListener('message', e => {
    if (e.data?.type === 'GET_VERSION') {
        (e.source || e.ports?.[0])?.postMessage?.({ type: 'SW_VERSION', version: VERSION });
    }
});

// ── Background Sync ───────────────────────────────────────────────────────────
self.addEventListener('sync', e => {
    if (e.tag === 'lenta-sync-queue') e.waitUntil(flushSyncQueue());
});

async function flushSyncQueue() {
    const db = await new Promise((res, rej) => {
        const r = indexedDB.open('lenta-offline-v1', 1);
        r.onsuccess = e => res(e.target.result);
        r.onerror   = e => rej(e.target.error);
    }).catch(() => null);
    if (!db) return;

    const items = await new Promise((res, rej) => {
        const tx  = db.transaction('queue', 'readonly');
        const r   = tx.objectStore('queue').getAll();
        r.onsuccess = () => res(r.result || []);
        r.onerror   = e => rej(e.target.error);
    }).catch(() => []);

    for (const item of items) {
        try {
            const res = await fetch(item.url, {
                method:  item.method || 'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(item.body),
            });
            if (res.ok) {
                await new Promise((resolve, reject) => {
                    const tx = db.transaction('queue', 'readwrite');
                    tx.objectStore('queue').delete(item.id);
                    tx.oncomplete = resolve;
                    tx.onerror    = e => reject(e.target.error);
                });
            }
        } catch {}
    }

    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach(c => c.postMessage({ type: 'SYNC_COMPLETE' }));
}

// ── Push уведомления ──────────────────────────────────────────────────────────
self.addEventListener('push', e => {
    let data = { title: 'Лента.PM', body: 'Новое уведомление', url: '/' };
    try { data = { ...data, ...e.data.json() }; } catch {}
    e.waitUntil(
        self.registration.showNotification(data.title, {
            body:                data.body,
            icon:                '/static/img/raccoon.png',
            badge:               '/static/img/raccoon.png',
            tag:                 data.tag || 'lenta-notif',
            requireInteraction:  data.urgent || false,
            data:                { url: data.url },
        })
    );
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    const url = e.notification.data?.url || '/';
    e.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
            for (const c of list) {
                if (c.url === url && 'focus' in c) return c.focus();
            }
            return clients.openWindow(url);
        })
    );
});
