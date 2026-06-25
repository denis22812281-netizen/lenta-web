// Loaded after window.CHAT_CONF is set by the template
const PARTNER = window.CHAT_CONF.partner;
const MY_NAME = window.CHAT_CONF.myName;

// ── @mention система ────────────────────────────────────────────────────────
const MENTION_USERS = window.CHAT_CONF.users;
let _mentionActive = false;
let _mentionStart  = -1;
let _mentionIdx    = 0;
let _mentionList   = [];

function handleInputKey(e) {
    if (_mentionActive) {
        const drop = document.getElementById('mention-dropdown');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            _mentionIdx = Math.min(_mentionIdx + 1, _mentionList.length - 1);
            _renderMentionDropdown();
            return;
        }
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            _mentionIdx = Math.max(_mentionIdx - 1, 0);
            _renderMentionDropdown();
            return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
            if (_mentionList.length > 0) {
                e.preventDefault();
                _insertMention(_mentionList[_mentionIdx].name);
                return;
            }
        }
        if (e.key === 'Escape') {
            _closeMentionDropdown();
            return;
        }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMsg();
    }
}

function handleMentionInput(inp) {
    const val = inp.value;
    const pos = inp.selectionStart;
    let atIdx = -1;
    for (let i = pos - 1; i >= 0; i--) {
        if (val[i] === '@') { atIdx = i; break; }
        if (val[i] === ' ') break;
    }
    if (atIdx === -1) { _closeMentionDropdown(); return; }
    const query = val.slice(atIdx + 1, pos).toLowerCase();
    _mentionStart = atIdx;
    _mentionList  = MENTION_USERS.filter(u =>
        u.name.toLowerCase().includes(query) && u.name !== MY_NAME
    ).slice(0, 6);
    _mentionIdx   = 0;
    if (_mentionList.length) {
        _mentionActive = true;
        _renderMentionDropdown();
    } else {
        _closeMentionDropdown();
    }
}

function _renderMentionDropdown() {
    const drop = document.getElementById('mention-dropdown');
    drop.style.display = 'block';
    drop.innerHTML = _mentionList.map((u, i) => {
        const initials = u.name.trim().split(/\s+/).slice(0,2).map(w=>w[0]).join('');
        const src = u.photo ? (u.photo.startsWith('http') ? u.photo : '/static/' + u.photo) : '';
        return `<div class="mention-item${i === _mentionIdx ? ' selected' : ''}"
                     data-action="insert-mention" data-name="${u.name.replace(/"/g, '&quot;')}">
            <div class="mention-avatar">${src ? `<img src="${src}" style="width:100%;height:100%;object-fit:cover;border-radius:50%">` : initials}</div>
            <span>${u.name}</span>
        </div>`;
    }).join('');
}

function _closeMentionDropdown() {
    _mentionActive = false;
    _mentionStart  = -1;
    document.getElementById('mention-dropdown').style.display = 'none';
}

function _insertMention(name) {
    const inp = document.getElementById('msgInput');
    const val = inp.value;
    const pos = inp.selectionStart;
    const before = val.slice(0, _mentionStart);
    const after  = val.slice(pos);
    inp.value = before + '@' + name + ' ' + after;
    const newPos = before.length + name.length + 2;
    inp.setSelectionRange(newPos, newPos);
    inp.focus();
    _closeMentionDropdown();
}

// Подсветка @упоминаний
(function() {
    const names = MENTION_USERS.map(u => u.name)
        .sort((a, b) => b.length - a.length)
        .map(n => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    window._mentionRe = names.length
        ? new RegExp('@(' + names.join('|') + ')', 'g')
        : null;
})();

function highlightMentions(text, isMine) {
    if (!window._mentionRe) return text;
    const cls = isMine ? 'chat-mention-tag mine' : 'chat-mention-tag';
    return text.replace(window._mentionRe, function(m) {
        return '<span class="' + cls + '">' + m + '</span>';
    });
}
let lastId = 0;
let selectedFile = null;

// ── Emojis ────────────────────────────────────────────────────────────────────
const EMOJIS = [
    '😀','😁','😂','🤣','😊','😍','🥰','😎',
    '😅','😉','😋','🤩','🥳','😜','😏','🤔',
    '😢','😭','😡','🤬','😱','😨','🥺','😔',
    '👍','👎','👏','🙌','🤝','💪','🙏','👋',
    '❤️','🔥','⭐','✅','❌','⚠️','🎉','🚀',
    '📋','📅','📊','💼','🏗️','🔑','📌','🔔',
];

(function buildEmojiPicker() {
    const grid = document.getElementById('emojiGrid');
    if (!grid) return;
    EMOJIS.forEach(e => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'emoji-btn';
        btn.textContent = e;
        btn.onclick = () => insertEmoji(e);
        grid.appendChild(btn);
    });
})();

function toggleEmoji() {
    const p = document.getElementById('emojiPicker');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
}

function insertEmoji(e) {
    const inp = document.getElementById('msgInput');
    const pos = inp.selectionStart;
    inp.value = inp.value.slice(0, pos) + e + inp.value.slice(inp.selectionEnd);
    inp.selectionStart = inp.selectionEnd = pos + e.length;
    inp.focus();
    document.getElementById('emojiPicker').style.display = 'none';
}

document.addEventListener('click', e => {
    const picker = document.getElementById('emojiPicker');
    const btn = document.getElementById('btnEmoji');
    if (picker && btn && !picker.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        picker.style.display = 'none';
    }
});

// ── Photo ─────────────────────────────────────────────────────────────────────
function onPhotoSelected(input) {
    const file = input.files[0];
    if (!file) return;
    selectedFile = file;
    const preview = document.getElementById('photoPreview');
    const img = document.getElementById('photoPreviewImg');
    const name = document.getElementById('photoPreviewName');
    img.src = URL.createObjectURL(file);
    name.textContent = file.name;
    preview.style.display = 'flex';
}

function clearPhoto() {
    selectedFile = null;
    document.getElementById('photoInput').value = '';
    document.getElementById('photoPreview').style.display = 'none';
    document.getElementById('photoPreviewImg').src = '';
}

// ── Send ──────────────────────────────────────────────────────────────────────
async function sendMsg() {
    const inp = document.getElementById('msgInput');
    const text = inp.value.trim();
    if (!text && !selectedFile) return;
    inp.value = '';

    if (selectedFile) {
        const fd = new FormData();
        fd.append('file', selectedFile);
        fd.append('partner', PARTNER);
        fd.append('text', text);
        clearPhoto();
        try {
            const r = await fetch('/api/chat/send-photo', { method: 'POST', body: fd });
            const data = await r.json();
            if (data.id) {
                renderMessages([{id: data.id, sender: MY_NAME, text, photo: data.photo, time: data.time, mine: true}], false);
            }
        } catch(e) {}
    } else {
        try {
            const r = await fetch('/api/chat/send', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({text, partner: PARTNER}),
            });
            const data = await r.json();
            if (data.id) {
                renderMessages([{id: data.id, sender: MY_NAME, text, photo: '', time: data.time, mine: true}], false);
            }
        } catch(e) {}
    }
}

// ── Render ────────────────────────────────────────────────────────────────────
async function loadMessages() {
    try {
        const r = await fetch(`/api/chat/messages?partner=${encodeURIComponent(PARTNER)}&since_id=0`);
        const data = await r.json();
        lastId = 0;
        renderMessages(data.messages, true);
    } catch(e) {}
}

function playChatSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [[660, 0, 0.12], [880, 0.13, 0.12]].forEach(([freq, delay, dur]) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain); gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0, ctx.currentTime + delay);
            gain.gain.linearRampToValueAtTime(0.25, ctx.currentTime + delay + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + delay + dur);
            osc.start(ctx.currentTime + delay);
            osc.stop(ctx.currentTime + delay + dur);
        });
    } catch(e) {}
}

async function pollMessages() {
    try {
        const r = await fetch(`/api/chat/messages?partner=${encodeURIComponent(PARTNER)}&since_id=${lastId}`);
        const data = await r.json();
        if (data.messages && data.messages.length) {
            const hasIncoming = data.messages.some(m => m.sender !== MY_NAME);
            renderMessages(data.messages, false);
            if (hasIncoming) playChatSound();
        }
    } catch(e) {}
}

function renderMessages(msgs, clear) {
    const box = document.getElementById('chatMessages');
    if (clear) box.innerHTML = '';
    if (!msgs.length && clear) {
        box.innerHTML = '<div class="text-center text-muted small py-5"><i class="bi bi-chat-dots" style="font-size:2.5rem;display:block;margin-bottom:8px;opacity:.3"></i>Сообщений пока нет</div>';
        return;
    }
    msgs.forEach(m => {
        if (m.id > lastId) lastId = m.id;
        const div = document.createElement('div');
        div.className = 'chat-msg ' + (m.mine ? 'mine' : 'other');

        const senderHtml = (!m.mine && PARTNER === '')
            ? `<div class="chat-sender">${escHtml(m.sender)}</div>` : '';

        let bubbleContent = '';
        if (m.text) bubbleContent += highlightMentions(escHtml(m.text), m.mine);
        if (m.photo) {
            const isAudio = m.is_voice || /\.(webm|ogg|mp3|wav|m4a)(\?|$)/i.test(m.photo);
            if (isAudio) {
                const src = m.photo.startsWith('http') ? m.photo : `/static/${m.photo}`;
                bubbleContent += `<audio controls class="chat-audio" src="${escHtml(src)}"></audio>`;
            } else {
                bubbleContent += `<img src="${escHtml(m.photo)}" class="chat-photo" data-action="open-lightbox" data-url="${escHtml(m.photo)}" alt="фото">`;
            }
        }

        div.innerHTML = senderHtml +
            `<div class="chat-bubble">${bubbleContent}</div>` +
            `<div class="chat-meta">${m.time}</div>`;
        box.appendChild(div);
    });
    box.scrollTop = box.scrollHeight;
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}

function openLightbox(src) {
    const lb = document.getElementById('lightbox');
    document.getElementById('lightboxImg').src = src;
    lb.style.display = 'flex';
}

// ── Online status ─────────────────────────────────────────────────────────────
async function ping() {
    try { await fetch('/api/ping', { method: 'POST' }); } catch(e) {}
}

async function updateOnline() {
    try {
        const r = await fetch('/api/online');
        const data = await r.json();
        const online = new Set(data.online);
        document.querySelectorAll('[id^="dot-"]').forEach(dot => {
            const name = dot.id.replace('dot-', '').replace(/_/g, ' ');
            const statusEl = document.getElementById('status-' + dot.id.replace('dot-', ''));
            if (online.has(name)) {
                dot.classList.add('online');
                if (statusEl) { statusEl.textContent = '● В сети'; statusEl.className = 'text-success'; }
            } else {
                dot.classList.remove('online');
                if (statusEl) { statusEl.textContent = '● Не в сети'; statusEl.className = 'text-muted'; }
            }
        });
    } catch(e) {}
}

ping();
setInterval(ping, 30000);
setInterval(updateOnline, 15000);

loadMessages();

// ── WebSocket + polling fallback ──────────────────────────────────────────────
let ws = null;
let wsRetryTimer = null;
let pollTimer = null;

function startPollingFallback() {
    if (pollTimer) return;
    pollTimer = setInterval(pollMessages, 3000);
}

function stopPollingFallback() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function connectWS() {
    if (ws && ws.readyState === WebSocket.OPEN) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
        ws = new WebSocket(`${proto}//${location.host}/ws/chat?partner=${encodeURIComponent(PARTNER)}`);

        ws.onopen = function() {
            stopPollingFallback();
            if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null; }
            ws._ping = setInterval(() => { if (ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 25000);
        };

        ws.onmessage = function(e) {
            if (e.data === 'pong') return;
            try {
                const msg = JSON.parse(e.data);
                if (msg.id && msg.id > lastId) {
                    const incoming = msg.sender !== MY_NAME;
                    renderMessages([msg], false);
                    if (incoming) playChatSound();
                }
            } catch(_) {}
        };

        ws.onclose = function() {
            if (ws._ping) clearInterval(ws._ping);
            ws = null;
            startPollingFallback();
            wsRetryTimer = setTimeout(connectWS, 4000);
        };

        ws.onerror = function() {
            ws && ws.close();
        };
    } catch(_) {
        startPollingFallback();
    }
}

connectWS();

// ── Voice recording ──────────────────────────────────────────────────────────
let _mediaRecorder = null;
let _recChunks = [];
let _recTimer = null;
let _recSecs = 0;

async function startRecord() {
    if (_mediaRecorder) return;
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        _mediaRecorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/ogg' });
        _recChunks = [];
        _mediaRecorder.ondataavailable = e => { if (e.data.size) _recChunks.push(e.data); };
        _mediaRecorder.onstop = () => {
            stream.getTracks().forEach(t => t.stop());
            _sendVoice(new Blob(_recChunks, { type: _mediaRecorder.mimeType }));
        };
        _mediaRecorder.start(200);
        document.getElementById('btnMic').classList.add('recording');
        document.getElementById('voiceRecBar').classList.add('active');
        _recSecs = 0;
        _recTimer = setInterval(() => {
            _recSecs++;
            const m = Math.floor(_recSecs / 60), s = _recSecs % 60;
            document.getElementById('voiceRecTime').textContent = `${m}:${String(s).padStart(2,'0')}`;
        }, 1000);
    } catch(e) {
        alert('Нет доступа к микрофону');
    }
}

function stopRecord() {
    if (!_mediaRecorder || _mediaRecorder.state === 'inactive') return;
    _mediaRecorder.stop();
    _mediaRecorder = null;
    clearInterval(_recTimer);
    document.getElementById('btnMic').classList.remove('recording');
    document.getElementById('voiceRecBar').classList.remove('active');
}

async function _sendVoice(blob) {
    if (blob.size < 1000) return;
    const ext = blob.type.includes('ogg') ? '.ogg' : '.webm';
    const fd = new FormData();
    fd.append('file', blob, `voice${ext}`);
    fd.append('partner', PARTNER);
    try {
        const r = await fetch('/api/chat/send-voice', { method: 'POST', body: fd });
        const data = await r.json();
        if (data.id) {
            renderMessages([{ id: data.id, sender: MY_NAME, text: '', photo: data.photo, time: data.time, mine: true, is_voice: true }], false);
        }
    } catch(e) {}
}

// ── Mobile layout + event wiring ──────────────────────────────────────────────
(function() {
    if (window.innerWidth > 900) return;
    var chatWrap = document.querySelector('.chat-wrap');
    if (!chatWrap) return;

    chatWrap.style.cssText = '';
    var chatMain = chatWrap.querySelector('.chat-main');
    if (chatMain) chatMain.style.cssText = '';

    function _scrollBottom() {
        var msgs = document.getElementById('chatMessages');
        if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }
    _scrollBottom();
    if (window.visualViewport) window.visualViewport.addEventListener('resize', function() {
        setTimeout(_scrollBottom, 100);
    });

    var btnEmoji = document.getElementById('btnEmoji');
    if (btnEmoji) btnEmoji.addEventListener('click', toggleEmoji);
    var btnSend = document.getElementById('btn-send-msg');
    if (btnSend) btnSend.addEventListener('click', sendMsg);
    var clearPhotoBtn = document.getElementById('btn-clear-photo');
    if (clearPhotoBtn) clearPhotoBtn.addEventListener('click', clearPhoto);
    var chatInput = document.getElementById('chat-input-field');
    if (chatInput) {
        chatInput.addEventListener('keydown', handleInputKey);
        chatInput.addEventListener('input', function() { handleMentionInput(this); });
    }
    var photoInput = document.getElementById('photoInput');
    if (photoInput) photoInput.addEventListener('change', function() { onPhotoSelected(this); });
    var lightbox = document.getElementById('lightbox');
    if (lightbox) lightbox.addEventListener('click', function() { this.style.display = 'none'; });
    document.addEventListener('click', function(e) {
        var el = e.target.closest('[data-action="open-lightbox"]');
        if (el) openLightbox(el.dataset.url);
    });
    var mic = document.getElementById('btnMic');
    if (mic) {
        mic.addEventListener('pointerdown', startRecord);
        mic.addEventListener('pointerup', stopRecord);
        mic.addEventListener('touchstart', startRecord, { passive: true });
        mic.addEventListener('touchend', stopRecord);
    }
    document.addEventListener('mousedown', function(e) {
        var el = e.target.closest('[data-action="insert-mention"]');
        if (!el) return;
        e.preventDefault();
        _insertMention(el.dataset.name);
    });
})();
