// ── Date display ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const el = document.getElementById('js-date');
    if (el) {
        el.textContent = new Date().toLocaleDateString('ru-RU', {
            weekday: 'short', day: 'numeric', month: 'long', year: 'numeric'
        });
    }

    // Mobile sidebar
    const hamburger = document.getElementById('btn-hamburger');
    const sidebar = document.getElementById('sidebar');
    if (hamburger && sidebar) {
        hamburger.addEventListener('click', () => sidebar.classList.toggle('open'));
        document.addEventListener('click', e => {
            if (!sidebar.contains(e.target) && !hamburger.contains(e.target)) {
                sidebar.classList.remove('open');
            }
        });
    }

    // Notification button
    const btn = document.getElementById('btn-notif');
    if (btn) {
        const enabled = localStorage.getItem('notif_enabled') === 'true';
        if (enabled) btn.classList.add('active');
        btn.addEventListener('click', toggleNotifications);
    }

    // Check deadlines every 5 min; also once on load after 3s
    setTimeout(checkDeadlines, 3000);
    setInterval(checkDeadlines, 5 * 60 * 1000);
});

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
        if (badge) {
            if (total > 0) {
                badge.textContent = total;
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
            }
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

        if (data.urgent_projects.length > 0) {
            const msg = `🏗️ Проектов завершается в ближайшие 7 дней: ${data.urgent_projects.length}. ${data.urgent_projects.slice(0,2).map(p=>`«${p.name}» — ${p.days_left} д.`).join('; ')}`;
            showToast(msg, 'info', 8000);
            if (notifEnabled) sendBrowserNotif('Дедлайны проектов', `${data.urgent_projects.length} проектов завершаются скоро`);
        }

    } catch (_) {}
}
