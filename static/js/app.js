// ── CSRF: inject X-CSRFToken into every same-origin POST fetch ───────────────
(function () {
    const _fetch = window.fetch;
    window.fetch = function (input, init) {
        const method = ((init && init.method) || 'GET').toUpperCase();
        if (method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE') {
            const url = typeof input === 'string' ? input : (input.url || '');
            const isSameOrigin = !url.startsWith('http') || url.startsWith(location.origin);
            if (isSameOrigin) {
                const meta = document.querySelector('meta[name="csrf-token"]');
                if (meta) {
                    init = init || {};
                    init.headers = Object.assign({}, init.headers, {
                        'X-CSRFToken': meta.content,
                    });
                }
            }
        }
        return _fetch.call(this, input, init);
    };
})();

// ── Global image error handler (replaces all onerror= attrs, CSP compliance) ─
document.addEventListener('error', function(e) {
    const img = e.target;
    if (img.tagName !== 'IMG' || img.dataset.errHandled) return;
    img.dataset.errHandled = '1';
    if (img.dataset.fallback === 'hide') {
        img.style.display = 'none';
        const showId = img.dataset.showSibling;
        if (showId) { const el = document.getElementById(showId); if (el) el.style.display = ''; }
    } else if (img.dataset.fallback === 'show-next') {
        img.style.display = 'none';
        if (img.nextElementSibling) img.nextElementSibling.style.display = '';
    } else {
        const RACCOON = '/static/img/raccoon.png';
        if (img.src !== location.origin + RACCOON) img.src = RACCOON;
        else img.style.display = 'none';
    }
}, true);

// ── Navigation progress bar (npbar) ─────────────────────────────────────────
(function () {
    const bar = document.getElementById('npbar');
    if (!bar) return;

    // Complete bar on every page load
    bar.classList.add('loading');
    requestAnimationFrame(() => requestAnimationFrame(() => {
        bar.classList.remove('loading');
        bar.classList.add('done');
        setTimeout(() => bar.classList.add('hidden'), 450);
    }));

    // Show bar on navigation click (visible on current page while next page loads)
    document.addEventListener('click', (e) => {
        const a = e.target.closest('a[href]');
        if (!a) return;
        const href = a.getAttribute('href') || '';
        if (href.startsWith('#') || href.startsWith('javascript') ||
            href.startsWith('http') || href.startsWith('mailto') ||
            a.getAttribute('data-bs-toggle') || a.getAttribute('target') === '_blank') return;
        bar.classList.remove('hidden', 'done');
        bar.classList.add('loading');
    });
})();

// ── Skeleton loading ──────────────────────────────────────────────────────────
(function () {
    // Add skeleton rows to data-cards on load, remove after first render frame
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('.data-card').forEach(card => {
            if (!card.querySelector('table, .empty-state')) return;
            const sk = document.createElement('div');
            sk.className = 'sk-card-body';
            sk.style.display = 'none';
            sk.innerHTML = '<div class="sk-row w85"></div><div class="sk-row w70"></div><div class="sk-row w50"></div>';
            card.insertBefore(sk, card.querySelector('.table-responsive, .empty-state'));
        });
    });
})();

// ── Theme ────────────────────────────────────────────────────────────────────
function _applyThemeUI() {
    const dark  = document.getElementById('html-root').getAttribute('data-bs-theme') === 'dark';
    const icon  = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');
    if (icon)  icon.className  = dark ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    if (label) label.textContent = dark ? 'Светлая' : 'Тёмная';

    // Перекрашиваем Chart.js оси если charts на странице
    if (window.Chart) {
        const tickColor = dark ? '#94a3b8' : '#888';
        const gridColor = dark ? '#1e3a2f' : '#f0f0f0';
        Chart.defaults.color         = tickColor;
        Chart.defaults.borderColor   = gridColor;
        Chart.defaults.scale.grid.color = gridColor;
    }
}

function toggleTheme() {
    const root = document.getElementById('html-root');
    const next = root.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-bs-theme', next);
    localStorage.setItem('lenta_theme', next);
    _applyThemeUI();
}

function toggleNavSect(el) {
    const body = document.getElementById(el.dataset.target);
    if (!body) return;
    body.classList.toggle('collapsed');
    el.classList.toggle('open');
}

// ── Global data-action dispatcher ────────────────────────────────────────────
document.addEventListener('click', function(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const action = el.dataset.action;
    switch (action) {
        case 'nav-toggle':        toggleNavSect(el); break;
        case 'print':             window.print(); break;
        case 'reload':            location.reload(); break;
        case 'navigate':          window.location = el.dataset.href; break;
        case 'trigger-file':      { const t = document.getElementById(el.dataset.target); if (t) t.click(); break; }
        case 'stop-propagation':  e.stopPropagation(); break;
    }
});

// data-action="autosubmit" on <select> / <input> → submits parent form
document.addEventListener('change', function(e) {
    if (e.target.dataset.action === 'autosubmit') {
        const form = e.target.closest('form');
        if (form) form.submit();
    }
});

// data-confirm on <form> → native confirm dialog before submit
document.addEventListener('submit', function(e) {
    const msg = e.target.dataset.confirm;
    if (msg && !confirm(msg)) e.preventDefault();
});

// ── Date display + base.html event wiring ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    _applyThemeUI();
    const el = document.getElementById('js-date');
    if (el) {
        el.textContent = new Date().toLocaleDateString('ru-RU', {
            weekday: 'short', day: 'numeric', month: 'long', year: 'numeric'
        });
    }

    // Topbar buttons (base.html no longer uses inline handlers)
    const searchToggle = document.getElementById('btn-search-toggle');
    if (searchToggle) searchToggle.addEventListener('click', toggleSearchBar);

    const themeBtn = document.getElementById('btn-theme');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

    const notifBadge = document.getElementById('notif-badge');
    if (notifBadge) notifBadge.addEventListener('click', () => { window.location = '/deadlines'; });

    const searchOverlay = document.getElementById('search-overlay');
    if (searchOverlay) searchOverlay.addEventListener('click', closeSearchBar);

    const searchClose = document.getElementById('btn-search-close');
    if (searchClose) searchClose.addEventListener('click', closeSearchBar);

    const searchForm = document.getElementById('search-form');
    if (searchForm) searchForm.addEventListener('submit', closeSearchBar);

    // Mobile sidebar + backdrop
    const hamburger = document.getElementById('btn-hamburger');
    const sidebar   = document.getElementById('sidebar');
    const backdrop  = document.getElementById('sidebar-backdrop');

    function openSidebar()  {
        sidebar && sidebar.classList.add('open');
        backdrop && backdrop.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
    function closeSidebar() {
        sidebar && sidebar.classList.remove('open');
        backdrop && backdrop.classList.remove('show');
        document.body.style.overflow = '';
    }

    if (hamburger) hamburger.addEventListener('click', () =>
        sidebar && sidebar.classList.contains('open') ? closeSidebar() : openSidebar());
    if (backdrop)  backdrop.addEventListener('click', closeSidebar);

    const closeSidebarBtn = document.getElementById('btn-sidebar-close');
    if (closeSidebarBtn) closeSidebarBtn.addEventListener('click', closeSidebar);

    if (sidebar) {
        sidebar.querySelectorAll('.nav-item').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 992) closeSidebar();
            });
        });
    }

    // Notification button
    const btn = document.getElementById('btn-notif');
    if (btn) {
        if (localStorage.getItem('notif_enabled') === 'true') btn.classList.add('active');
        btn.addEventListener('click', toggleNotifications);
    }

    // Deadlines check
    setTimeout(checkDeadlines, 3000);
    setInterval(checkDeadlines, 5 * 60 * 1000);

    // Onboarding wizard
    _initOnboarding();
});

// ── Onboarding wizard ────────────────────────────────────────────────────────
function _initOnboarding() {
    const overlay = document.getElementById('onboard-overlay');
    if (!overlay) return;
    if (localStorage.getItem('lenta_welcome_v1')) return;

    let step = 0;
    const slides = overlay.querySelectorAll('.onboard-slide');
    const prog   = document.getElementById('onboard-prog');
    const dots   = overlay.querySelectorAll('.ob-dot');
    const nextBtn = document.getElementById('onboard-next');
    const skipBtn = document.getElementById('onboard-skip');

    function show(i) {
        slides.forEach((s, idx) => { s.style.display = idx === i ? '' : 'none'; });
        dots.forEach((d, idx) => {
            d.style.background = idx === i ? 'var(--lenta-green,#3CB34A)' : '#cbd5e1';
        });
        prog.style.width = ((i + 1) / slides.length * 100) + '%';
        nextBtn.textContent = i === slides.length - 1 ? 'Начать работу ✓' : 'Далее →';
    }

    function close() {
        localStorage.setItem('lenta_welcome_v1', '1');
        overlay.style.display = 'none';
    }

    nextBtn.addEventListener('click', () => {
        if (step < slides.length - 1) { step++; show(step); } else close();
    });
    skipBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

    // Помечаем сразу — чтобы крэш страницы не создавал бесконечный цикл
    localStorage.setItem('lenta_welcome_v1', '1');
    show(0);
    overlay.style.display = 'flex';
}

// ── Notification toggle ──────────────────────────────────────────────────────
async function toggleNotifications() {
    const btn = document.getElementById('btn-notif');
    if (!('Notification' in window)) {
        showToast('Ваш браузер не поддерживает уведомления', 'warning');
        return;
    }
    if (Notification.permission === 'denied') {
        showToast('Уведомления заблокированы в браузере. Разблокируйте в настройках сайта.', 'warning');
        return;
    }
    const perm = await Notification.requestPermission();
    if (perm === 'granted') {
        localStorage.setItem('notif_enabled', 'true');
        btn && btn.classList.add('active');
        showToast('Уведомления включены!', 'success');
        checkDeadlines(true);
    } else {
        localStorage.setItem('notif_enabled', 'false');
        btn && btn.classList.remove('active');
    }
}

// ── Sound (Web Audio API) ─────────────────────────────────────────────────────
function playSound(type = 'warn') {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        if (type === 'danger') {
            osc.type = 'square';
            osc.frequency.setValueAtTime(440, ctx.currentTime);
            osc.frequency.setValueAtTime(330, ctx.currentTime + 0.15);
            osc.frequency.setValueAtTime(440, ctx.currentTime + 0.3);
            gain.gain.setValueAtTime(0.2, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7);
            osc.start(); osc.stop(ctx.currentTime + 0.7);
        } else {
            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.1);
            gain.gain.setValueAtTime(0.25, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            osc.start(); osc.stop(ctx.currentTime + 0.4);
        }
    } catch (_) {}
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(msg, type = 'warning', duration = 7000) {
    const box = document.getElementById('toast-box');
    if (!box) return;
    const colors = { danger: '#dc3545', warning: '#fd7e14', success: '#198754', info: '#0dcaf0' };
    const icons  = { danger: 'bi-exclamation-triangle-fill', warning: 'bi-clock-fill',
                     success: 'bi-check-circle-fill', info: 'bi-info-circle-fill' };
    const div = document.createElement('div');
    div.className = 'toast show';
    div.style.cssText = `border-left:4px solid ${colors[type]||colors.warning};min-width:280px;max-width:360px;background:#fff;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.15)`;
    div.innerHTML = `
        <div class="toast-header border-0 pb-1">
            <i class="bi ${icons[type]||icons.warning} me-2" style="color:${colors[type]||colors.warning}"></i>
            <strong class="me-auto">Лента — Уведомление</strong>
            <small class="text-muted">${new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</small>
            <button type="button" class="btn-close ms-2" onclick="this.closest('.toast').remove()"></button>
        </div>
        <div class="toast-body pt-0 small">${msg}</div>`;
    box.appendChild(div);
    setTimeout(() => div.remove(), duration);
}

// ── Browser push notification ─────────────────────────────────────────────────
function sendBrowserNotif(title, body) {
    if (Notification.permission !== 'granted') return;
    try {
        new Notification(title, {
            body,
            icon: '/static/favicon.png',
            badge: '/static/favicon.png',
            tag: 'lenta-deadline',
        });
    } catch (_) {}
}

// ── Deadline checker ──────────────────────────────────────────────────────────
let _lastNotifDay = null;

async function checkDeadlines(force = false) {
    try {
        const res = await fetch('/api/deadlines/check');
        if (!res.ok) return;
        const data = await res.json();

        const total = data.overdue_tasks.length + data.urgent_tasks.length + data.urgent_projects.length;
        const badge = document.getElementById('notif-badge');
        const bnavNotif = document.getElementById('bnav-notif-badge');
        if (total > 0) {
            if (badge) { badge.textContent = total; badge.classList.remove('d-none'); }
            if (bnavNotif) { bnavNotif.textContent = total; bnavNotif.classList.add('show'); }
        } else {
            if (badge) { badge.classList.add('d-none'); }
            if (bnavNotif) { bnavNotif.classList.remove('show'); }
        }

        const today = new Date().toDateString();
        if (!force && _lastNotifDay === today) return;
        if (total === 0) return;
        _lastNotifDay = today;

        const notifEnabled = localStorage.getItem('notif_enabled') === 'true';

        if (data.overdue_tasks.length > 0) {
            playSound('danger');
            const msg = `❗ Просрочено задач: ${data.overdue_tasks.length}. ${data.overdue_tasks.slice(0,2).map(t=>`«${t.title}» (${t.assignee||'не назначено'})`).join('; ')}`;
            showToast(msg, 'danger', 10000);
            if (notifEnabled) sendBrowserNotif('Просроченные задачи!', `${data.overdue_tasks.length} задач просрочено`);
        }

        if (data.urgent_tasks.length > 0) {
            playSound('warn');
            const msg = `⚠️ Задач с дедлайном до 3 дней: ${data.urgent_tasks.length}. ${data.urgent_tasks.slice(0,2).map(t=>`«${t.title}» — ${t.days_left} д.`).join('; ')}`;
            showToast(msg, 'warning', 8000);
        }


    } catch (_) {}
}

// ── Button loading state ──────────────────────────────────────────────────────
function btnLoading(btn, loading) {
    if (loading) {
        btn.dataset._origText = btn.innerHTML;
        btn.classList.add('btn-loading');
        btn.disabled = true;
    } else {
        btn.innerHTML = btn.dataset._origText || btn.innerHTML;
        btn.classList.remove('btn-loading');
        btn.disabled = false;
    }
}

// Auto-disable submit buttons on form submit to prevent double-send
document.addEventListener('DOMContentLoaded', function () {
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (form.classList.contains('no-loading')) return;
        const btn = form.querySelector('[type="submit"]:not([data-no-loading])');
        if (btn) {
            // Restore after 8s as fallback if redirect doesn't happen
            setTimeout(() => btnLoading(btn, false), 8000);
            btnLoading(btn, true);
        }
    });
});

// ── Прогресс-индикатор для длинных форм ──────────────────────────────────────
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        var forms = [];
        document.querySelectorAll('form').forEach(function(form) {
            if (form.offsetHeight > 500 && !form.classList.contains('no-progress')) {
                forms.push(form);
            }
        });

        forms.forEach(function(form) {
            if (form._progressInited) return;
            form._progressInited = true;

            var bar = document.createElement('div');
            bar.className = 'form-progress-bar';
            var fill = document.createElement('div');
            fill.className = 'form-progress-fill';
            fill.style.width = '0%';
            bar.appendChild(fill);
            form.insertBefore(bar, form.firstChild);

            var fields = form.querySelectorAll(
                'input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select'
            );
            var total = fields.length;
            if (total === 0) return;

            function updateProgress() {
                var filled = 0;
                fields.forEach(function(f) {
                    if (f.type === 'checkbox' || f.type === 'radio') {
                        if (f.checked) filled++;
                    } else if ((f.value || '').trim() !== '') {
                        filled++;
                    }
                });
                var pct = Math.round((filled / total) * 100);
                fill.style.width = pct + '%';
                fill.style.background = pct < 40 ? '#ef4444' : pct < 80 ? '#f59e0b' : '#22c55e';
            }

            fields.forEach(function(f) {
                f.addEventListener('input', updateProgress);
                f.addEventListener('change', updateProgress);
            });
            updateProgress();
        });
    });
})();
