// Loaded after window.OPENING_CONF = { projectId: "..." } is set by the template

// ── Поиск по ТК ──────────────────────────────────────────────────────────────
function showTkDropdown() {
  document.getElementById('tkDropdown').classList.remove('d-none');
}

function filterTk(q) {
  const dd = document.getElementById('tkDropdown');
  dd.classList.remove('d-none');
  const lower = q.toLowerCase();
  let anyVisible = false;
  dd.querySelectorAll('.tk-option').forEach(el => {
    const match = el.dataset.search.includes(lower) || el.dataset.label.toLowerCase().includes(lower);
    el.style.display = match ? '' : 'none';
    if (match) anyVisible = true;
  });
}

function selectTk(el) {
  document.getElementById('tkSearch').value = el.dataset.label;
  document.getElementById('tkDropdown').classList.add('d-none');
  location.href = '/opening?project_id=' + el.dataset.id;
}

document.addEventListener('click', function(e) {
  const search = document.getElementById('tkSearch');
  const dd = document.getElementById('tkDropdown');
  if (search && dd && !search.contains(e.target) && !dd.contains(e.target)) {
    dd.classList.add('d-none');
  }
});

const PROJECT_ID = window.OPENING_CONF.projectId;

// ── Сжатие фото на клиенте (Canvas, max 1600px, quality 0.82) ────────────────
function compressImage(file, maxPx = 1600, quality = 0.82) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        let w = img.width, h = img.height;
        if (w > maxPx || h > maxPx) {
          if (w > h) { h = Math.round(h * maxPx / w); w = maxPx; }
          else       { w = Math.round(w * maxPx / h); h = maxPx; }
        }
        const canvas = document.createElement('canvas');
        canvas.width = w; canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob(resolve, 'image/jpeg', quality);
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  });
}

// ── AJAX загрузка по одному файлу ────────────────────────────────────────────
async function startUpload(files) {
  if (!files || !files.length || !PROJECT_ID) return;
  const wrap  = document.getElementById('progressWrap');
  const label = document.getElementById('progressLabel');
  const bar   = document.getElementById('progressBar');
  const pct   = document.getElementById('progressPct');
  const errEl = document.getElementById('progressError');

  wrap.classList.remove('d-none');
  errEl.classList.add('d-none');
  let done = 0, errors = 0;
  const total = files.length;

  for (let i = 0; i < total; i++) {
    label.textContent = `Загружаю ${i + 1} из ${total}...`;
    const p = Math.round((i / total) * 100);
    bar.style.width = p + '%';
    pct.textContent = p + '%';

    try {
      const blob = await compressImage(files[i]);
      const fd = new FormData();
      fd.append('project_id', PROJECT_ID);
      fd.append('photo', blob, `photo_${i}.jpg`);

      const resp = await fetch('/api/vpk/opening/upload-one', {method: 'POST', body: fd});
      const data = await resp.json();

      if (data.ok) {
        done++;
        addPhotoCard(data.photo_id, data.url);
        const hint = document.getElementById('emptyHint');
        if (hint) hint.style.display = 'none';
      } else {
        errors++;
      }
    } catch(e) {
      errors++;
    }
  }

  bar.style.width = '100%';
  pct.textContent = '100%';
  label.textContent = `Готово: ${done} фото загружено${errors ? ', ошибок: ' + errors : ''}`;
  label.style.color = errors ? '#dc2626' : '#16a34a';

  document.getElementById('photoInput').value = '';
}

// ── Добавить карточку фото в галерею без перезагрузки ────────────────────────
function addPhotoCard(photoId, url) {
  const grid = document.getElementById('photoGrid');
  if (!grid) return;
  const col = document.createElement('div');
  col.className = 'col-6 col-md-4 col-xl-3';
  col.id = 'photoCard' + photoId;
  col.innerHTML = `
    <div class="position-relative" style="border-radius:12px;overflow:hidden;
         aspect-ratio:1;background:#111;box-shadow:0 2px 8px rgba(0,0,0,.3)"
         id="photoFrame${photoId}">
      <img src="${url}" alt="Фото"
           style="width:100%;height:100%;object-fit:cover;display:block"
           loading="lazy" data-fallback="raccoon">
      <div class="position-absolute top-0 start-0 w-100 h-100 d-flex flex-column justify-content-between p-2"
           style="background:linear-gradient(to bottom,rgba(0,0,0,.5) 0%,transparent 40%,transparent 60%,rgba(0,0,0,.6) 100%)">
        <div class="d-flex justify-content-between align-items-start">
          <button class="btn btn-sm rounded-circle p-1" data-action="toggle-featured" data-id="${photoId}"
                  id="starBtn${photoId}"
                  style="width:32px;height:32px;line-height:1;background:rgba(0,0,0,.5);border:none;color:#fff">
            <i class="bi bi-star-fill" style="font-size:13px"></i>
          </button>
          <button class="btn btn-sm rounded-circle p-1" data-action="delete-photo" data-id="${photoId}"
                  style="width:28px;height:28px;line-height:1;background:rgba(220,38,38,.8);border:none;color:#fff">
            <i class="bi bi-trash3" style="font-size:11px"></i>
          </button>
        </div>
        <div style="font-size:10px;color:rgba(255,255,255,.8)" id="badge${photoId}"></div>
      </div>
    </div>`;
  grid.prepend(col);
}

// ── Toggle featured ───────────────────────────────────────────────────────────
async function toggleFeatured(photoId) {
  const btn   = document.getElementById('starBtn'   + photoId);
  const frame = document.getElementById('photoFrame'+ photoId);
  const badge = document.getElementById('badge'     + photoId);
  try {
    const resp = await fetch('/api/vpk/opening/' + photoId + '/feature', {method: 'POST'});
    const data = await resp.json();
    if (data.is_featured) {
      btn.style.background = 'rgba(255,210,0,.9)';
      btn.style.color = '#000';
      frame.style.boxShadow = '0 0 0 3px #FFD200';
      if (badge) badge.innerHTML = '<span style="background:#FFD200;color:#000;border-radius:4px;padding:1px 6px;font-weight:700;font-size:10px">⭐ ЛУЧШЕЕ</span>';
    } else {
      btn.style.background = 'rgba(0,0,0,.5)';
      btn.style.color = '#fff';
      frame.style.boxShadow = '0 2px 8px rgba(0,0,0,.3)';
      if (badge) badge.innerHTML = '';
    }
  } catch(e) { console.error(e); }
}

// ── Delete photo ──────────────────────────────────────────────────────────────
async function deletePhoto(photoId) {
  if (!confirm('Удалить фото?')) return;
  try {
    const resp = await fetch('/api/vpk/opening/' + photoId + '/delete', {method: 'POST'});
    const data = await resp.json();
    if (data.ok) {
      const card = document.getElementById('photoCard' + photoId);
      if (card) card.remove();
    }
  } catch(e) { console.error(e); }
}

// ── Drag & Drop ───────────────────────────────────────────────────────────────
function handleDrop(event) {
  event.preventDefault();
  document.getElementById('dropzone').classList.remove('drag-over');
  startUpload(event.dataTransfer.files);
}

// ── Копировать ссылку на галерею ──────────────────────────────────────────────
function copyGalleryLink() {
  if (!PROJECT_ID) return;
  const url = location.origin + '/opening/' + PROJECT_ID;
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.getElementById('copyLinkBtn');
    btn.innerHTML = '<i class="bi bi-check2 me-1"></i>Ссылка скопирована!';
    btn.classList.replace('btn-outline-secondary', 'btn-outline-success');
    setTimeout(() => {
      btn.innerHTML = '<i class="bi bi-link-45deg me-1"></i>Скопировать ссылку';
      btn.classList.replace('btn-outline-success', 'btn-outline-secondary');
    }, 2500);
  });
}

// ── Кнопка отправки — защита от двойного клика + спиннер ─────────────────────
function handleSendReport(form) {
  const btn = document.getElementById('sendReportBtn');
  const photos = document.querySelectorAll('#photoGrid [id^="photoCard"]');
  if (photos.length === 0) {
    alert('Сначала загрузите фото');
    return false;
  }
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Отправляю...';
}

(function() {
    var tkSearch = document.getElementById('opening-tk-search');
    if (tkSearch) {
        tkSearch.addEventListener('input', function() { filterTk(this.value); });
        tkSearch.addEventListener('focus', showTkDropdown);
    }
    var dropzone = document.getElementById('dropzone');
    if (dropzone) {
        dropzone.addEventListener('dragover', function(e) { e.preventDefault(); this.classList.add('drag-over'); });
        dropzone.addEventListener('dragleave', function() { this.classList.remove('drag-over'); });
        dropzone.addEventListener('drop', handleDrop);
    }
    document.addEventListener('mouseover', function(e) {
        var el = e.target.closest('.tk-option');
        if (el) el.style.background = 'rgba(60,179,74,.12)';
    });
    document.addEventListener('mouseout', function(e) {
        var el = e.target.closest('.tk-option');
        if (el) el.style.background = '';
    });
    var photoInput = document.getElementById('photoInput');
    if (photoInput) photoInput.addEventListener('change', function() { startUpload(this.files); });
    var sendReportForm = document.getElementById('send-report-form');
    if (sendReportForm) sendReportForm.addEventListener('submit', function(e) {
        e.preventDefault(); handleSendReport(this);
    });
    document.addEventListener('click', function(e) {
        var el = e.target.closest('[data-action]');
        if (!el) return;
        switch (el.dataset.action) {
            case 'select-tk':        selectTk(el); break;
            case 'toggle-featured':  toggleFeatured(parseInt(el.dataset.id)); break;
            case 'delete-photo':     deletePhoto(parseInt(el.dataset.id)); break;
        }
    });
})();
