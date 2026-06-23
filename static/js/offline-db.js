/* Лента.PM — IndexedDB offline storage + sync queue */
(function () {
    const DB_NAME    = 'lenta-offline-v1';
    const DB_VERSION = 1;

    function _open() {
        return new Promise(function (resolve, reject) {
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (e) {
                const db = e.target.result;
                // Key-value хранилище для кэша данных
                if (!db.objectStoreNames.contains('kv')) {
                    db.createObjectStore('kv', { keyPath: 'k' });
                }
                // Очередь несинхронизированных запросов
                if (!db.objectStoreNames.contains('queue')) {
                    db.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
                }
            };
            req.onsuccess  = function (e) { resolve(e.target.result); };
            req.onerror    = function (e) { reject(e.target.error); };
        });
    }

    window.OfflineDB = {
        // ── KV store ─────────────────────────────────────────────────────────
        set: async function (key, value) {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx = db.transaction('kv', 'readwrite');
                tx.objectStore('kv').put({ k: key, v: value, t: Date.now() });
                tx.oncomplete = resolve;
                tx.onerror = function (e) { reject(e.target.error); };
            });
        },

        get: async function (key) {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx  = db.transaction('kv', 'readonly');
                const req = tx.objectStore('kv').get(key);
                req.onsuccess = function () {
                    resolve(req.result ? { value: req.result.v, savedAt: req.result.t } : null);
                };
                req.onerror = function (e) { reject(e.target.error); };
            });
        },

        // ── Sync queue ────────────────────────────────────────────────────────
        queueAdd: async function (item) {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx  = db.transaction('queue', 'readwrite');
                const req = tx.objectStore('queue').add(
                    Object.assign({}, item, { ts: Date.now(), retries: 0 })
                );
                req.onsuccess = function () { resolve(req.result); };
                req.onerror   = function (e) { reject(e.target.error); };
            });
        },

        queueAll: async function () {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx  = db.transaction('queue', 'readonly');
                const req = tx.objectStore('queue').getAll();
                req.onsuccess = function () { resolve(req.result || []); };
                req.onerror   = function (e) { reject(e.target.error); };
            });
        },

        queueDelete: async function (id) {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx = db.transaction('queue', 'readwrite');
                tx.objectStore('queue').delete(id);
                tx.oncomplete = resolve;
                tx.onerror    = function (e) { reject(e.target.error); };
            });
        },

        queueCount: async function () {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx  = db.transaction('queue', 'readonly');
                const req = tx.objectStore('queue').count();
                req.onsuccess = function () { resolve(req.result); };
                req.onerror   = function (e) { reject(e.target.error); };
            });
        },

        queueClear: async function () {
            const db = await _open();
            return new Promise(function (resolve, reject) {
                const tx = db.transaction('queue', 'readwrite');
                tx.objectStore('queue').clear();
                tx.oncomplete = resolve;
                tx.onerror    = function (e) { reject(e.target.error); };
            });
        },
    };
})();
