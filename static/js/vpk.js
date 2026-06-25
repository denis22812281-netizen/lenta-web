// Loaded after window.VPK_CONF is set by the template:
// { totalCriteria: N, precheckTotal: N, precheckIds: [...] }

// ── Предосмотр: TK-автодополнитель ──────────────────────────────────────────
const preProjects = (() => {
    const el = document.getElementById('preProjectsData');
    return el ? JSON.parse(el.textContent) : [];
})();
let preFiltered = [], preIdx = -1;

function preTkSearch(val) {
    const q = val.trim();
    document.getElementById('preTkClearBtn').style.display = q ? '' : 'none';
    if (!q) { hidePre(); return; }
    preFiltered = preProjects.filter(p => String(p.tk).includes(q));
    renderPreDropdown();
}
function renderPreDropdown() {
    const ul = document.getElementById('preTkDropdown');
    ul.innerHTML = '';
    preIdx = -1;
    if (!preFiltered.length) { ul.style.display = 'none'; return; }
    preFiltered.slice(0, 8).forEach((p, i) => {
        const li = document.createElement('li');
        li.className = 'list-group-item list-group-item-action d-flex justify-content-between';
        li.innerHTML = `<span><b>ТК ${p.tk}</b> — ${p.addr}</span><small class="text-muted">${p.mgr}</small>`;
        li.onclick = () => selectPreProject(p);
        ul.appendChild(li);
    });
    ul.style.display = '';
}
function preTkKeydown(e) {
    const ul = document.getElementById('preTkDropdown');
    const items = ul.querySelectorAll('li');
    if (e.key === 'ArrowDown') { preIdx = Math.min(preIdx + 1, items.length - 1); highlightPre(items); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { preIdx = Math.max(preIdx - 1, 0); highlightPre(items); e.preventDefault(); }
    else if (e.key === 'Enter' && preIdx >= 0) { items[preIdx].click(); e.preventDefault(); }
    else if (e.key === 'Escape') { hidePre(); }
}
function highlightPre(items) { items.forEach((li, i) => li.classList.toggle('active', i === preIdx)); }
function selectPreProject(p) {
    document.getElementById('preProjectId').value = p.id;
    document.getElementById('preTkInput').value = p.tk;
    document.getElementById('preSelectedTkLabel').textContent = `ТК ${p.tk} — ${p.addr}`;
    document.getElementById('preSelectedTkMgr').textContent = p.mgr + (p.vpk_date ? ` · ВПК: ${p.vpk_date}` : '');
    document.getElementById('preSelectedTk').classList.remove('d-none');
    hidePre();
    document.getElementById('preTkClearBtn').style.display = '';
}
function hidePre() { document.getElementById('preTkDropdown') && (document.getElementById('preTkDropdown').style.display = 'none'); }
function preTkClear() {
    document.getElementById('preTkInput').value = '';
    document.getElementById('preProjectId').value = '';
    document.getElementById('preSelectedTk').classList.add('d-none');
    document.getElementById('preTkClearBtn').style.display = 'none';
    hidePre();
}
document.addEventListener('click', e => {
    const inp = document.getElementById('preTkInput');
    const dd  = document.getElementById('preTkDropdown');
    if (dd && inp && !inp.contains(e.target) && !dd.contains(e.target)) hidePre();
});

// ── Предосмотр: состояние критериев ─────────────────────────────────────────
const preState = {};

function setPrecheck(id, val) {
    preState[id] = val;
    const row     = document.getElementById(`pre-row-${id}`);
    const cbox    = document.getElementById(`pre-cbox-${id}`);
    const btnYes  = document.getElementById(`pre-btn-yes-${id}`);
    const btnNo   = document.getElementById(`pre-btn-no-${id}`);
    const btnSkip = document.getElementById(`pre-btn-skip-${id}`);
    if (row) {
        row.classList.toggle('done', val === 'done');
        row.classList.toggle('no',   val === 'not_done');
    }
    if (cbox) cbox.style.display = val === 'not_done' ? '' : 'none';
    if (btnYes)  btnYes.classList.toggle('active',  val === 'done');
    if (btnNo)   btnNo.classList.toggle('active',   val === 'not_done');
    if (btnSkip) btnSkip.classList.toggle('active', val === 'not_checked');
    const fld = document.getElementById('precheckJson');
    if (fld) fld.value = JSON.stringify(preState);
    updatePreCounters();
}

function updatePreCounters() {
    const vals  = Object.values(preState);
    const done  = vals.filter(v => v === 'done').length;
    const bad   = vals.filter(v => v === 'not_done').length;
    const total = window.VPK_CONF.precheckTotal;
    const okEl   = document.getElementById('pre-ok-count');
    const failEl = document.getElementById('pre-fail-count');
    const skipEl = document.getElementById('pre-skip-count');
    if (okEl)   okEl.textContent   = `✅ ${done}`;
    if (failEl) failEl.textContent = `❌ ${bad}`;
    if (skipEl) skipEl.textContent = `— ${total - done - bad}`;
}

function preCheckAll(val) {
    window.VPK_CONF.precheckIds.forEach(id => setPrecheck(id, val));
}

function onPrePhoto(id, input) {
    const span = document.getElementById(`pre-photo-name-${id}`);
    if (span) span.textContent = input.files[0] ? input.files[0].name : '';
}

function preConfirmSubmit() {
    const pid = document.getElementById('preProjectId') && document.getElementById('preProjectId').value;
    const tk  = document.getElementById('preTkInput') && document.getElementById('preTkInput').value.trim();
    if (!pid && !tk) { alert('Введите номер ТК'); return false; }
    const anyMarked = Object.values(preState).some(v => v !== 'not_checked');
    if (!anyMarked) if (!confirm('Ни один критерий не отмечен. Отправить?')) return false;
    return true;
}

// ── ВПК 1/2 ─────────────────────────────────────────────────────────────────
const totalCriteria = window.VPK_CONF.totalCriteria;
let checkedCount = 0;
let dropdownIndex = -1;

const PROJECTS = JSON.parse(document.getElementById('projectsData')?.textContent || '[]');

function setCriterion(id, isDone) {
    const cb  = document.getElementById('c_' + id);
    const row = document.getElementById('row-' + id);
    const cbox = document.getElementById('cbox-' + id);
    const btnYes = document.getElementById('btn-yes-' + id);
    const btnNo  = document.getElementById('btn-no-'  + id);
    cb.checked = isDone;
    row.classList.toggle('done', isDone);
    row.classList.toggle('no',  !isDone);
    btnYes.classList.toggle('active',  isDone);
    btnNo.classList.toggle('active',  !isDone);
    if (cbox) cbox.style.display = isDone ? 'none' : 'block';
    updateProgress();
}

function onCriterionPhoto(id, input) {
    const file = input.files[0];
    const nameEl = document.getElementById('photo-name-' + id);
    if (nameEl) nameEl.textContent = file ? file.name : '';
}

function saveComment(id) {
    const cbox = document.getElementById('cbox-' + id);
    const saved = document.getElementById('saved-' + id);
    if (!saved) {
        const tag = document.createElement('span');
        tag.id = 'saved-' + id;
        tag.className = 'badge bg-success ms-2 small';
        tag.textContent = '✓ Сохранено';
        if (cbox) cbox.appendChild(tag);
    }
}

function updateProgress() {
    const count = document.querySelectorAll('.vpk-check:checked').length;
    const pct = totalCriteria > 0 ? Math.round(count / totalCriteria * 100) : 0;
    const bar = document.getElementById('progressBar');
    const txt = document.getElementById('progressText');
    const pctEl = document.getElementById('progressPct');
    if (bar) bar.style.width = pct + '%';
    if (txt) txt.textContent = 'Выполнено: ' + count + ' / ' + totalCriteria;
    if (pctEl) pctEl.textContent = pct + '%';
}

function checkAll(val) {
    document.querySelectorAll('.vpk-check').forEach(cb => {
        const id = parseInt(cb.id.replace('c_', ''));
        if (val) {
            setCriterion(id, true);
        } else {
            resetCriterion(id);
        }
    });
}

function resetCriterion(id) {
    const cb  = document.getElementById('c_' + id);
    const row = document.getElementById('row-' + id);
    const cbox = document.getElementById('cbox-' + id);
    const btnYes = document.getElementById('btn-yes-' + id);
    const btnNo  = document.getElementById('btn-no-'  + id);
    if (cb) cb.checked = false;
    if (row) { row.classList.remove('done'); row.classList.remove('no'); }
    if (btnYes) btnYes.classList.remove('active');
    if (btnNo)  btnNo.classList.remove('active');
    if (cbox)   cbox.style.display = 'none';
    updateProgress();
}

// ── TK autocomplete ──────────────────────────────────────────────
function tkSearch(query) {
    const q = query.trim().toLowerCase();
    const dd = document.getElementById('tkDropdown');
    const clearBtn = document.getElementById('tkClearBtn');
    if (clearBtn) clearBtn.style.display = q ? '' : 'none';
    if (!dd) return;
    if (!q) { dd.style.display = 'none'; return; }

    const matches = PROJECTS.filter(p =>
        p.tk.toLowerCase().includes(q) ||
        p.addr.toLowerCase().includes(q)
    ).slice(0, 12);

    if (!matches.length) {
        dd.innerHTML = '<li class="list-group-item text-muted small py-2 px-3">Не найдено</li>';
        dd.style.display = 'block';
        dropdownIndex = -1;
        return;
    }

    dd.innerHTML = matches.map((p, i) =>
        `<li class="list-group-item list-group-item-action py-2 px-3 tk-option" data-i="${i}" style="cursor:pointer"
             data-action="tk-select" data-id="${p.id}" data-tk="${p.tk.replace(/"/g,'&quot;')}" data-addr="${(p.addr||'').replace(/"/g,'&quot;')}" data-mgr="${(p.mgr||'').replace(/"/g,'&quot;')}">
            <span class="fw-bold me-2">ТК ${p.tk}</span>
            <span class="text-muted small">${p.addr ? p.addr.substring(0,50) : ''}</span>
            ${p.mgr ? `<span class="badge bg-secondary ms-1 small">${p.mgr}</span>` : ''}
        </li>`
    ).join('');
    dd.style.display = 'block';
    dropdownIndex = -1;
}

function tkKeydown(e) {
    const dd = document.getElementById('tkDropdown');
    if (!dd) return;
    const items = dd.querySelectorAll('.tk-option');
    if (!items.length) return;
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        dropdownIndex = Math.min(dropdownIndex + 1, items.length - 1);
        items.forEach((el, i) => el.classList.toggle('active', i === dropdownIndex));
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        dropdownIndex = Math.max(dropdownIndex - 1, 0);
        items.forEach((el, i) => el.classList.toggle('active', i === dropdownIndex));
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (dropdownIndex >= 0 && items[dropdownIndex]) items[dropdownIndex].dispatchEvent(new MouseEvent('mousedown'));
    } else if (e.key === 'Escape') {
        dd.style.display = 'none';
    }
}

function tkSelect(id, tk, addr, mgr) {
    document.getElementById('projectId').value = id;
    document.getElementById('tkInput').value = 'ТК ' + tk;
    document.getElementById('tkDropdown').style.display = 'none';
    document.getElementById('tkClearBtn').style.display = '';
    const box = document.getElementById('selectedTk');
    document.getElementById('selectedTkLabel').textContent = 'ТК ' + tk + (addr ? ' — ' + addr.substring(0, 60) : '');
    document.getElementById('selectedTkMgr').textContent = mgr ? 'Менеджер: ' + mgr : '';
    box.classList.remove('d-none');
}

function tkClear() {
    document.getElementById('projectId').value = '';
    document.getElementById('tkInput').value = '';
    document.getElementById('tkDropdown').style.display = 'none';
    document.getElementById('tkClearBtn').style.display = 'none';
    document.getElementById('selectedTk').classList.add('d-none');
    document.getElementById('tkInput').focus();
}

document.addEventListener('click', e => {
    const dd = document.getElementById('tkDropdown');
    if (dd && !e.target.closest('.position-relative')) dd.style.display = 'none';
});

function confirmSubmit() {
    if (!document.getElementById('projectId').value) {
        alert('Выберите объект из списка');
        document.getElementById('tkInput').focus();
        return false;
    }
    return confirm('Отправить отчёт? Уведомление получат Гаврин Игорь и Месмер Денис.');
}

async function markRead(reportId) {
    try {
        await fetch('/vpk/reports/' + reportId + '/read', { method: 'POST' });
    } catch(e) {}
}

// ── Event delegation ─────────────────────────────────────────────────────────
(function() {
    var ti = document.getElementById('tkInput');
    if (ti) { ti.addEventListener('input', function() { tkSearch(this.value); }); ti.addEventListener('keydown', tkKeydown); }
    var tc = document.getElementById('tkClearBtn');
    if (tc) tc.addEventListener('click', tkClear);
    var pi = document.getElementById('preTkInput');
    if (pi) { pi.addEventListener('input', function() { preTkSearch(this.value); }); pi.addEventListener('keydown', preTkKeydown); }
    var pc = document.getElementById('preTkClearBtn');
    if (pc) pc.addEventListener('click', preTkClear);
    var vs = document.getElementById('vpk-submit-btn');
    if (vs) vs.addEventListener('click', function(e) { if (!confirmSubmit()) e.preventDefault(); });
    var ps = document.getElementById('vpk-pre-submit-btn');
    if (ps) ps.addEventListener('click', function(e) { if (!preConfirmSubmit()) e.preventDefault(); });

    document.addEventListener('click', function(e) {
        var el = e.target.closest('[data-action]');
        if (!el) return;
        switch (el.dataset.action) {
            case 'vpk-check-all':       checkAll(el.dataset.val === 'true'); break;
            case 'trigger-file':        document.getElementById(el.dataset.target) && document.getElementById(el.dataset.target).click(); break;
            case 'vpk-save-comment':    saveComment(parseInt(el.dataset.cid)); break;
            case 'vpk-set-criterion':   setCriterion(parseInt(el.dataset.cid), el.dataset.val === 'true'); break;
            case 'vpk-pre-check-all':   preCheckAll(el.dataset.val); break;
            case 'vpk-set-precheck':    setPrecheck(parseInt(el.dataset.cid), el.dataset.val); break;
            case 'vpk-mark-read':       markRead(parseInt(el.dataset.rid)); break;
        }
    });
    document.addEventListener('mousedown', function(e) {
        var el = e.target.closest('[data-action="tk-select"]');
        if (!el) return;
        e.preventDefault();
        tkSelect(el.dataset.id, el.dataset.tk, el.dataset.addr, el.dataset.mgr);
    });
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('vpk-photo-input'))     onCriterionPhoto(parseInt(e.target.dataset.cid), e.target);
        if (e.target.classList.contains('vpk-pre-photo-input')) onPrePhoto(parseInt(e.target.dataset.cid), e.target);
    });
})();
