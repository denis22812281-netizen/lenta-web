/* Лента.PM — Service Worker v1 */
const CACHE = 'lenta-pm-v1';
const PRECACHE = [
    '/',
    '/static/css/style.css',
    '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
];

self.addEventListener('install', e => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE).then(c => c.addAll(PRECACHE).catch(() => {}))
    );
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', e => {
    if (e.request.method !== 'GET') return;
    if (e.request.url.includes('/api/')) return;
    e.respondWith(
        fetch(e.request)
            .then(r => {
                if (r && r.status === 200 && r.type === 'basic') {
                    const c = r.clone();
                    caches.open(CACHE).then(cache => cache.put(e.request, c));
                }
                return r;
            })
            .catch(() => caches.match(e.request))
    );
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
