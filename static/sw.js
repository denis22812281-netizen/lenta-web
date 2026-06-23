/* Лента.PM — Service Worker v3 */
const CACHE_STATIC  = 'lenta-static-v3';
const CACHE_PAGES   = 'lenta-pages-v3';
const CACHE_API     = 'lenta-api-v3';

// Статика — кэшируем при установке
const PRECACHE = [
    '/static/css/style.css',
    '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
    '/static/img/raccoon.png',
    '/static/vendor/bootstrap/bootstrap.bundle.min.js',
    '/static/vendor/bootstrap/bootstrap.min.css',
];

// API-маршруты для offline-кэша (только GET, TTL 5 минут)
const CACHE_API_ROUTES = [
    '/api/online',
    '/api/notifications/construction',
    '/api/notifications/reconstruct',
    '/api/vpk/unread',
    '/api/chat/unread',
];

const API_TTL_MS = 5 * 60 * 1000; // 5 мин

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

    // 1. Статика — cache-first
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

    // 2. API — network-first с offline-fallback (только разрешённые роуты)
    if (url.pathname.startsWith('/api/')) {
        const shouldCache = CACHE_API_ROUTES.some(r => url.pathname.startsWith(r));
        if (!shouldCache) return;
        e.respondWith(
            fetch(req).then(async res => {
                if (res.ok) {
                    const cache = await caches.open(CACHE_API);
                    const r = res.clone();
                    // Добавляем timestamp в заголовок для TTL
                    const headers = new Headers(r.headers);
                    headers.set('x-sw-cached-at', Date.now().toString());
                    const timed = new Response(await r.blob(), { headers });
                    cache.put(req, timed);
                }
                return res;
            }).catch(async () => {
                const cache = await caches.open(CACHE_API);
                const hit = await cache.match(req);
                if (!hit) return new Response(JSON.stringify({ offline: true }), {
                    headers: { 'Content-Type': 'application/json' }
                });
                const cachedAt = parseInt(hit.headers.get('x-sw-cached-at') || '0');
                if (Date.now() - cachedAt > API_TTL_MS) {
                    return new Response(JSON.stringify({ offline: true }), {
                        headers: { 'Content-Type': 'application/json' }
                    });
                }
                return hit;
            })
        );
        return;
    }

    // 3. HTML-страницы — network-first, fallback на кэш
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
                const hit = await cache.match(req);
                if (hit) return hit;
                // Если нет кэша — отдаём главную страницу
                return caches.match('/') || new Response(
                    '<h2>Нет подключения</h2><p>Страница недоступна в офлайн-режиме. <a href="/">На главную</a></p>',
                    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                );
            })
        );
        return;
    }
});

/* ── Push уведомления ── */
self.addEventListener('push', e => {
    let data = { title: 'Лента.PM', body: 'Новое уведомление', url: '/' };
    try { data = { ...data, ...e.data.json() }; } catch {}
    e.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/static/img/raccoon.png',
            badge: '/static/img/raccoon.png',
            tag: data.tag || 'lenta-notif',
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
