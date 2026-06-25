// Loaded after window.SMR_CONF = { projId: N } is set by the template
// ── Автодополнение контактов ──────────────────────────────────────────────────
let _acTimer = null;

async function acSearch(slot, q) {
    clearTimeout(_acTimer);
    const drop  = document.getElementById(`acDrop${slot}`);
    const email = document.getElementById(`confirmEmail${slot}`);
    if (!q || q.length < 1) {
        drop.style.display = 'none';
        email.value = '';
        return;
    }
    _acTimer = setTimeout(async () => {
        const res  = await fetch(`/api/smr/contacts?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        drop.innerHTML = '';
        if (!data.contacts.length) {
            drop.innerHTML = `<div class="smr-ac-empty">Не найдено. <a href="/smr/contacts" target="_blank" class="text-success">Добавить</a></div>`;
        } else {
            data.contacts.forEach(c => {
                const div = document.createElement('div');
                div.className = 'smr-ac-item';
                div.innerHTML = `<div class="smr-ac-name">${escHtmlAc(c.name)}</div>
                    <div class="smr-ac-sub">
                      <span class="smr-ac-email">${escHtmlAc(c.email)}</span>
                      ${c.position ? ' · ' + escHtmlAc(c.position) : ''}
                    </div>`;
                div.addEventListener('mousedown', e => {
                    e.preventDefault();
                    document.getElementById(`acName${slot}`).value  = c.name;
                    document.getElementById(`confirmEmail${slot}`).value = c.email;
                    drop.style.display = 'none';
                });
                drop.appendChild(div);
            });
        }
        drop.style.display = 'block';
    }, 200);
}

function escHtmlAc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

document.addEventListener('click', e => {
    ['acDrop1','acDrop2'].forEach(id => {
        const d = document.getElementById(id);
        if (d) d.style.display = 'none';
    });
});

// ── Автодополнение для модала отчёта ────────────────────────────────────────
async function acSearchReport(q) {
    clearTimeout(_acTimer);
    const drop = document.getElementById('reportAcDrop');
    if (!q || q.length < 1) { drop.style.display='none'; return; }
    _acTimer = setTimeout(async () => {
        const res  = await fetch(`/api/smr/contacts?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        drop.innerHTML = '';
        if (!data.contacts.length) {
            drop.innerHTML = `<div class="smr-ac-empty">Не найдено</div>`;
        } else {
            data.contacts.forEach(c => {
                const div = document.createElement('div');
                div.className = 'smr-ac-item';
                div.innerHTML = `<div class="smr-ac-name">${escHtmlAc(c.name)}</div>
                    <div class="smr-ac-sub smr-ac-email">${escHtmlAc(c.email)}</div>`;
                div.addEventListener('mousedown', e => {
                    e.preventDefault();
                    document.getElementById('reportAcName').value = c.name;
                    document.getElementById('reportEmail').value  = c.email;
                    drop.style.display = 'none';
                });
                drop.appendChild(div);
            });
        }
        drop.style.display = 'block';
    }, 200);
}

function openReportModal() {
    document.getElementById('reportAcName').value = '';
    document.getElementById('reportEmail').value  = '';
    document.getElementById('reportResult').innerHTML = '';
    document.getElementById('reportAcDrop').style.display = 'none';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalReport')).show();
}

async function sendReport() {
    const email = document.getElementById('reportEmail').value.trim();
    const res   = document.getElementById('reportResult');
    if (!email) { res.innerHTML = '<span class="text-danger">Укажите email</span>'; return; }
    res.innerHTML = '<span class="text-muted"><i class="bi bi-hourglass-split me-1"></i>Отправляю...</span>';
    const r    = await fetch(`/api/smr/${window.SMR_CONF.projId}/send-report`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({email})
    });
    const data = await r.json();
    if (data.ok) {
        res.innerHTML = `<span class="text-success"><i class="bi bi-check-circle me-1"></i>Отправлено на ${data.sent_to}</span>`;
    } else {
        res.innerHTML = `<span class="text-danger">${data.error || 'Ошибка отправки'}</span>`;
    }
}

let _confirmTaskId = null;
let _confirmIsMilestone = false;

function openConfirmModal(taskId, taskName, email1, email2, isMilestone) {
    _confirmTaskId = taskId;
    _confirmIsMilestone = isMilestone;
    document.getElementById('confirmTaskName').textContent = taskName;
    document.getElementById('confirmEmail1').value = email1 || '';
    document.getElementById('confirmEmail2').value = email2 || '';
    document.getElementById('acName1').value = email1 ? '(выбрано)' : '';
    document.getElementById('acName2').value = email2 ? '(выбрано)' : '';
    document.getElementById('acDrop1').style.display = 'none';
    document.getElementById('acDrop2').style.display = 'none';
    document.getElementById('confirmResult').innerHTML = '';
    const hint = document.getElementById('confirmHint');
    const btn  = document.getElementById('btnSendConfirm');
    hint.textContent = isMilestone
        ? 'Ключевая веха — можно запросить подтверждение по email.'
        : 'При смене статуса на "Выполнено" — письмо уйдёт автоматически.';
    btn.style.display = isMilestone ? '' : 'none';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('modalConfirm')).show();
}

async function saveEmails() {
    const e1 = document.getElementById('confirmEmail1').value.trim();
    const e2 = document.getElementById('confirmEmail2').value.trim();
    if (!e1) {
        document.getElementById('confirmResult').innerHTML =
            '<span class="text-danger">Выберите получателя из списка</span>';
        return;
    }
    await fetch(`/api/smr/task/${_confirmTaskId}/emails`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email1:e1, email2:e2})
    });
    document.getElementById('confirmResult').innerHTML =
        '<span class="text-success"><i class="bi bi-check-circle me-1"></i>Сохранено</span>';
    const btn = document.querySelector(`[data-action="open-confirm-modal"][data-id="${_confirmTaskId}"]`);
    if (btn) {
        btn.classList.add('smr-email-set');
        btn.innerHTML = '<i class="bi bi-envelope-check"></i>';
    }
}

async function sendConfirm() {
    const e1 = document.getElementById('confirmEmail1').value.trim();
    const e2 = document.getElementById('confirmEmail2').value.trim();
    const res = document.getElementById('confirmResult');
    if (!e1) { res.innerHTML = '<span class="text-danger">Введите хотя бы один email</span>'; return; }
    await fetch(`/api/smr/task/${_confirmTaskId}/emails`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({email1:e1, email2:e2})
    });
    const r    = await fetch(`/api/smr/task/${_confirmTaskId}/send-confirm`, {
        method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
    });
    const data = await r.json();
    res.innerHTML = data.ok
        ? `<span class="text-success"><i class="bi bi-check-circle me-1"></i>Отправлено: ${data.sent.join(', ')}</span>`
        : '<span class="text-danger">Ошибка отправки</span>';
}

document.querySelectorAll('.smr-status-select').forEach(sel => {
    sel.addEventListener('change', async function() {
        const taskId = this.dataset.taskId;
        const status = this.value;
        await fetch(`/api/smr/task/${taskId}/status`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body:JSON.stringify({status})
        });
        const colors = {
            'Выполнено':'#16a34a','В работе':'#2563eb',
            'Просрочено':'#dc2626','Запланировано':'#2d3748'
        };
        this.style.borderColor = colors[status] || '#2d3748';
    });
});

document.addEventListener('DOMContentLoaded', function() {
    var btnOpenReport = document.getElementById('btn-open-report-modal');
    if (btnOpenReport) btnOpenReport.addEventListener('click', openReportModal);
    var btnSendReport = document.getElementById('btn-send-report');
    if (btnSendReport) btnSendReport.addEventListener('click', sendReport);
    var acSearch1 = document.getElementById('acName1');
    if (acSearch1) acSearch1.addEventListener('input', function() { acSearch(1, this.value); });
    var acSearch2 = document.getElementById('acName2');
    if (acSearch2) acSearch2.addEventListener('input', function() { acSearch(2, this.value); });
    var acReport = document.getElementById('reportAcName');
    if (acReport) acReport.addEventListener('input', function() { acSearchReport(this.value); });
    var btnSaveEmails = document.getElementById('btn-save-emails');
    if (btnSaveEmails) btnSaveEmails.addEventListener('click', saveEmails);
    var btnSendConfirm = document.getElementById('btnSendConfirm');
    if (btnSendConfirm) btnSendConfirm.addEventListener('click', sendConfirm);
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action="open-confirm-modal"]');
        if (!btn) return;
        openConfirmModal(
            parseInt(btn.dataset.id),
            btn.dataset.name || '',
            btn.dataset.email1 || '',
            btn.dataset.email2 || '',
            btn.dataset.milestone === 'true'
        );
    });
});
