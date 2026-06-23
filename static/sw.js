/* Лента.PM — Service Worker v4 */
const CACHE_STATIC = 'lenta-static-v4';
const CACHE_PAGES  = 'lenta-pages-v4';
const CACHE_API    = 'lenta-api-v4';

const PRECACHE = [
    '/static/css/style.css',
    '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
    '/static/img/raccoon.png',
    '/static/vendor/bootstrap/bootstrap.bundle.min.js',
    '/static/vendor/bootstrap/bootstrap.min.css',
    '/static/js/app.js',
    '/static/js/offline-db.js',
];

// API маршруты с коротким TTL (5 мин)
const API_CACHE_ROUTES = [
    '/api/online',
    '/api/vpk/unread',
    '/api/chat/unread',
    '/api/notifications/construction',
    '/api/notifications/reconstruct',
];
const API_TTL = 5 * 60 * 1000;

// Данные проектов — долгий TTL (30 мин)
const PROJECTS_DATA_URL = '/api/projects/cache-data';
const PROJECTS_TTL = 30 * 60 * 1000;

self.addEventListener('install', e => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE_STATIC).then(c => c.addAll(PRECACHE).catch(() => {}))
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => ![CACHE_STATIC, CACHE_PAGES, CACHE_API].includes(k))
                    .map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    const req = e.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);

    // ── Статика: cache-first ──────────────────────────────────────────────────
    if (url.pathname.startsWith('/static/')) {
        e.respondWith(
            caches.open(CACHE_STATIC).then(async cache => {
                const hit = await cache.match(req);
                if (hit) return hit;
                const res = await fetch(req).catch(() => null);
                if (res && res.ok) cache.put(req, res.clone());
                return res;
            })
        );
        return;
    }

    // ── Данные проектов: network-first с длинным TTL ─────────────────────────
    if (url.pathname === PROJECTS_DATA_URL) {
        e.respondWith(networkFirstWithTTL(req, CACHE_API, PROJECTS_TTL));
        return;
    }

    // ── Прочие API: network-first с коротким TTL ─────────────────────────────
    if (url.pathname.startsWith('/api/')) {
        const shouldCache = API_CACHE_ROUTES.some(r => url.pathname.startsWith(r));
        if (shouldCache) {
            e.respondWith(networkFirstWithTTL(req, CACHE_API, API_TTL));
        }
        return;
    }

    // ── HTML-страницы: network-first, offline fallback ────────────────────────
    if (req.headers.get('accept')?.includes('text/html')) {
        e.respondWith(
            fetch(req).then(async res => {
                if (res.ok) {
                    const cache = await caches.open(CACHE_PAGES);
                    cache.put(req, res.clone());
                }
                return res;
            }).catch(async () => {
                const cache = await caches.open(CACHE_PAGES);
                const hit   = await cache.match(req);
                if (hit) return hit;
                const root = await caches.match('/');
                if (root) return root;
                return new Response(
                    '<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Офлайн</title>' +
                    '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="font-family:sans-serif;padding:32px;text-align:center">' +
                    '<h2>📵 Нет подключения</h2>' +
                    '<p>Страница недоступна в офлайн-режиме.</p>' +
                    '<a href="/" style="color:#3CB34A;font-weight:700">← На главную</a>' +
                    '</body></html>',
                    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                );
            })
        );
        return;
    }
});

async function networkFirstWithTTL(req, cacheName, ttl) {
    try {
        const res = await fetch(req);
        if (res.ok) {
            const cache = await caches.open(cacheName);
            const headers = new Headers(res.headers);
            headers.set('x-sw-cached-at', Date.now().toString());
            const timed = new Response(await res.clone().blob(), { status: res.status, headers });
            cache.put(req, timed);
        }
        return res;
    } catch (_) {
        const cache = await caches.open(cacheName);
        const hit   = await cache.match(req);
        if (!hit) return new Response(JSON.stringify({ offline: true, cached: false }),
            { headers: { 'Content-Type': 'application/json' } });
        const age = Date.now() - parseInt(hit.headers.get('x-sw-cached-at') || '0');
        if (age > ttl) return new Response(JSON.stringify({ offline: true, stale: true }),
            { headers: { 'Content-Type': 'application/json' } });
        return hit;
    }
}

/* ── Background Sync — проигрываем очередь при восстановлении сети ── */
self.addEventListener('sync', e => {
    if (e.tag === 'lenta-sync-queue') {
        e.waitUntil(flushSyncQueue());
    }
});

async function flushSyncQueue() {
    // Читаем очередь из IndexedDB
    const DB_NAME = 'lenta-offline-v1';
    const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, 1);
        req.onsuccess = e => resolve(e.target.result);
        req.onerror   = e => reject(e.target.error);
    }).catch(() => null);

    if (!db) return;

    const items = await new Promise((resolve, reject) => {
        const tx  = db.transaction('queue', 'readonly');
        const req = tx.objectStore('queue').getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror   = e => reject(e.target.error);
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
        } catch (_) {}
    }

    // Уведомляем все вкладки о завершении синхронизации
    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach(c => c.postMessage({ type: 'SYNC_COMPLETE' }));
}

/* ── Push уведомления ── */
self.addEventListener('push', e => {
    let data = { title: 'Лента.PM', body: 'Новое уведомление', url: '/' };
    try { data = { ...data, ...e.data.json() }; } catch {}
    e.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/img/raccoon.png',
            badge: '/static/img/raccoon.png',
            tag:  data.tag || 'lenta-notif',
            requireInteraction: data.urgent || false,
            data: { url: data.url },
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
