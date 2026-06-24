"""Replace remaining inline handlers in heavy templates."""
import os
import re

BASE = os.path.join(os.path.dirname(__file__), '..', 'templates')


def read(fname):
    with open(os.path.join(BASE, fname), encoding='utf-8') as f:
        return f.read()


def write(fname, content):
    with open(os.path.join(BASE, fname), 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  Saved: {fname}')


# ── project_detail.html ────────────────────────────────────────────────────
c = read('project_detail.html')
c = c.replace('onclick="confirmDelete()"', 'id="btn-confirm-delete"')
c = c.replace(
    'onkeydown="if(event.ctrlKey&&event.key===\'Enter\'){this.form.submit();}"',
    'id="comment-textarea"'
)
c = c.replace(
    'style="display:none" onchange="onAttachChange(this)"',
    'style="display:none" class="attach-file-input"'
)
c = c.replace(
    "onclick=\"document.getElementById('attachFileInput').click()\"",
    'data-action="trigger-file" data-target="attachFileInput"'
)
c = c.replace("onclick=\"setGanttView('Week',this)\"",  'data-action="gantt-view" data-val="Week"')
c = c.replace("onclick=\"setGanttView('Month',this)\"", 'data-action="gantt-view" data-val="Month"')
c = c.replace("onclick=\"setGanttView('Day',this)\"",   'data-action="gantt-view" data-val="Day"')
c = c.replace(
    'style="display:none" onchange="onOpeningFileChange(this)"',
    'style="display:none" id="openingFileInput"'
)
c = c.replace(
    "onclick=\"document.getElementById('openingFileInput').click()\"",
    'data-action="trigger-file" data-target="openingFileInput"'
)
c = c.replace('onclick="return confirmOpeningUpload()"', 'id="btn-opening-upload"')
write('project_detail.html', c)

# ── create_task.html ───────────────────────────────────────────────────────
c = read('create_task.html')
# HTML attrs
c = c.replace(
    "onchange=\"onStatusChange(this, {{ t.id }}, '{{ t.status }}')\"",
    'data-action="status-change" data-id="{{ t.id }}" data-status="{{ t.status }}"'
)
c = c.replace("onchange=\"previewPhotos(this)\"", 'id="photo-preview-input"')
c = c.replace('onclick="cancelComplete()"', 'id="btn-cancel-complete"')
c = c.replace('onclick="submitComplete()"', '')  # already has id="btnSubmitComplete"
# JS template literal handlers (inside backtick strings)
c = c.replace(
    "onchange=\"onStatusChange(this,${t.id},'${t.status}')\"",
    'data-action="status-change" data-id="${t.id}" data-status="${t.status}"'
)
c = c.replace(
    '`<button class="btn btn-sm btn-outline-secondary" onclick="window._taskPage=${page-1};applySearchAndPage()"><i class="bi bi-chevron-left"></i></button>`',
    '`<button class="btn btn-sm btn-outline-secondary" data-action="task-page" data-delta="-1"><i class="bi bi-chevron-left"></i></button>`'
)
c = c.replace(
    '`<button class="btn btn-sm btn-outline-secondary" onclick="window._taskPage=${page+1};applySearchAndPage()"><i class="bi bi-chevron-right"></i></button>`',
    '`<button class="btn btn-sm btn-outline-secondary" data-action="task-page" data-delta="1"><i class="bi bi-chevron-right"></i></button>`'
)
write('create_task.html', c)

# ── chat.html ──────────────────────────────────────────────────────────────
c = read('chat.html')
c = c.replace('onclick="clearPhoto()"', 'id="btn-clear-photo"')
c = c.replace('onclick="toggleEmoji()"', '')  # already has id="btnEmoji"
c = c.replace(
    "onclick=\"document.getElementById('photoInput').click()\"",
    'data-action="trigger-file" data-target="photoInput"'
)
c = c.replace("onchange=\"onPhotoSelected(this)\"", '')  # already has id="photoInput"
c = c.replace(
    'onkeydown="handleInputKey(event)" oninput="handleMentionInput(this)"',
    'id="chat-input-field"'
)
c = c.replace('onclick="sendMsg()"', 'id="btn-send-msg"')
c = c.replace("onclick=\"this.style.display='none'\"", 'id="lightbox"')
# JS string with inline onclick (dynamic bubble HTML)
c = c.replace(
    "bubbleContent += `<img src=\"${escHtml(m.photo)}\" class=\"chat-photo\" onclick=\"openLightbox('${escHtml(m.photo)}')\" alt=\"фото\">`;",
    "bubbleContent += `<img src=\"${escHtml(m.photo)}\" class=\"chat-photo\" data-action=\"open-lightbox\" data-url=\"${escHtml(m.photo)}\" alt=\"фото\">`;",
)
write('chat.html', c)

# ── login.html ─────────────────────────────────────────────────────────────
c = read('login.html')
c = c.replace("onclick=\"window.location.href='/login'\"", 'data-action="navigate" data-href="/login"')
c = c.replace("onclick=\"togglePass('pass','eye1')\"",   'data-action="toggle-pass" data-field="pass" data-eye="eye1"')
c = c.replace("oninput=\"checkStrength(this.value)\"",   'id="new-pass-strength"')
c = c.replace("onclick=\"togglePass('pass1','eye2')\"",  'data-action="toggle-pass" data-field="pass1" data-eye="eye2"')
c = c.replace("onclick=\"togglePass('pass2','eye3')\"",  'data-action="toggle-pass" data-field="pass2" data-eye="eye3"')
write('login.html', c)

# ── ai_chat.html ───────────────────────────────────────────────────────────
c = read('ai_chat.html')
c = c.replace('onclick="clearChat()"', 'id="btn-clear-chat"')
c = c.replace("onclick=\"sendQuick('Какие проекты просрочены или под угрозой срыва?')\"",  'data-action="quick-prompt" data-prompt="Какие проекты просрочены или под угрозой срыва?"')
c = c.replace("onclick=\"sendQuick('Дай полную сводку по всем активным проектам')\"",       'data-action="quick-prompt" data-prompt="Дай полную сводку по всем активным проектам"')
c = c.replace("onclick=\"sendQuick('Какие дедлайны на ближайшие 7 дней?')\"",              'data-action="quick-prompt" data-prompt="Какие дедлайны на ближайшие 7 дней?"')
c = c.replace("onclick=\"sendQuick('Кто из менеджеров перегружен и у кого критические сроки?')\"", 'data-action="quick-prompt" data-prompt="Кто из менеджеров перегружен и у кого критические сроки?"')
c = c.replace("onclick=\"sendQuick('Что нужно сделать в первую очередь сегодня?')\"",      'data-action="quick-prompt" data-prompt="Что нужно сделать в первую очередь сегодня?"')
c = c.replace('onkeydown="handleKey(event)"', 'id="ai-input"')
c = c.replace('onclick="sendMessage()"', '')  # already has id="send-btn"
write('ai_chat.html', c)

# ── managers.html ──────────────────────────────────────────────────────────
c = read('managers.html')
c = re.sub(
    r"onclick=\"showMgrTab\((\{\{ m\.id \}\}), '(recon|constr)'\)\"",
    lambda m: f'data-action="show-mgr-tab" data-id="{m.group(1)}" data-tab="{m.group(2)}"',
    c
)
c = re.sub(
    r"""onclick="openEmailModal\((\{\{ m\.id \}\}), '(\{\{ m\.name \}\})', '(\{\{ m\.email or '' \}\})'\)"\s*""",
    lambda m: f'data-action="open-email-modal" data-id="{m.group(1)}" data-name="{m.group(2)}" data-email="{m.group(3)}"',
    c
)
c = re.sub(
    r"onclick=\"closeMgrTab\((\{\{ m\.id \}\}), '(recon|constr)'\)\"",
    lambda m: f'data-action="close-mgr-tab" data-id="{m.group(1)}" data-tab="{m.group(2)}"',
    c
)
write('managers.html', c)

# ── opening.html ───────────────────────────────────────────────────────────
c = read('opening.html')
c = c.replace('oninput="filterTk(this.value)"', 'id="opening-tk-search"')
c = c.replace('onclick="selectTk(this)"', 'data-action="select-tk"')
c = c.replace(
    "onclick=\"document.getElementById('photoInput').click()\"",
    'data-action="trigger-file" data-target="photoInput"'
)
c = c.replace("onchange=\"startUpload(this.files)\"", '')  # already has id via context
c = c.replace('onclick="copyGalleryLink()"', '')  # already has id="copyLinkBtn"
c = c.replace('onsubmit="handleSendReport(this)"', 'id="send-report-form"')
c = c.replace('onclick="toggleFeatured({{ photo.id }})"', 'data-action="toggle-featured" data-id="{{ photo.id }}"')
c = c.replace('onclick="deletePhoto({{ photo.id }})"', 'data-action="delete-photo" data-id="{{ photo.id }}"')
# JS string handlers
c = c.replace(
    '`<button class="btn btn-sm rounded-circle p-1" onclick="toggleFeatured(${photoId})"',
    '`<button class="btn btn-sm rounded-circle p-1" data-action="toggle-featured" data-id="${photoId}"'
)
c = c.replace(
    '`<button class="btn btn-sm rounded-circle p-1" onclick="deletePhoto(${photoId})"',
    '`<button class="btn btn-sm rounded-circle p-1" data-action="delete-photo" data-id="${photoId}"'
)
write('opening.html', c)

# ── opening_gallery.html ───────────────────────────────────────────────────
c = read('opening_gallery.html')
c = c.replace('onclick="closeLightbox(event)"', 'id="lightbox" data-action="lb-close-if-self"')
c = c.replace('onclick="closeLightbox()"',       'data-action="lb-close"')
c = c.replace('onclick="lbPrev(event)"',         'data-action="lb-prev"')
c = c.replace('onclick="lbNext(event)"',         'data-action="lb-next"')
c = re.sub(
    r"onclick=\"openLb\('({{ purl }})', (\d+|\{\{ [^}]+ \}\})\)\"",
    lambda m: f'data-action="open-lb" data-url="{m.group(1)}" data-idx="{m.group(2)}"',
    c
)
write('opening_gallery.html', c)

# ── smr_schedule.html ──────────────────────────────────────────────────────
c = read('smr_schedule.html')
c = c.replace('onclick="openReportModal()"', 'id="btn-open-report-modal"')
c = re.sub(
    r"onclick=\"openConfirmModal\((\{\{ task\.id \}\}), '([^']*?)'",
    lambda m: f'data-action="open-confirm-modal" data-id="{m.group(1)}" data-name="{m.group(2)}"',
    c
)
c = c.replace('oninput="acSearchReport(this.value)"', 'id="ac-search-report"')
c = c.replace('onclick="sendReport()"', 'id="btn-send-report"')
c = c.replace('oninput="acSearch(1, this.value)"', 'id="ac-search-1"')
c = c.replace('oninput="acSearch(2, this.value)"', 'id="ac-search-2"')
c = c.replace('onclick="saveEmails()"', 'id="btn-save-emails"')
c = c.replace('onclick="sendConfirm()"', '')  # already has id="btnSendConfirm"
write('smr_schedule.html', c)

# ── adaptation_form.html ───────────────────────────────────────────────────
c = read('adaptation_form.html')
c = c.replace('onclick="confirmSend()"', 'data-action="confirm-send"')
c = re.sub(
    r'data-step="{{ snum }}" onclick="goStep\({{ snum }}\)"',
    'data-step="{{ snum }}" data-action="go-step"',
    c
)
c = c.replace('onchange="onAdaptPhotos(this)"', '')  # wire by id below
c = c.replace(
    "onclick=\"document.getElementById('adaptPhotoInput').click()\"",
    'data-action="trigger-file" data-target="adaptPhotoInput"'
)
c = c.replace('onclick="uploadAdaptPhotos()"', 'data-action="upload-adapt-photos"')
c = c.replace('onclick="stepPrev()" disabled', '')  # already has id="btnPrev"
c = c.replace('onclick="stepNext()"', '')           # already has id="btnNext"
# Mobile buttons at bottom (second set)
c = c.replace('onclick="stepPrev()" disabled>', '>')
c = c.replace('onclick="stepNext()">', '>')
c = c.replace('onclick="confirmSend()"', 'data-action="confirm-send"')
c = c.replace('onclick="closeTour()"', 'data-action="close-tour"')
write('adaptation_form.html', c)

# ── leader.html ────────────────────────────────────────────────────────────
c = read('leader.html')
c = c.replace("onclick=\"rcOverlay('overlayOpened')\"", 'data-action="rc-overlay" data-target="overlayOpened"')
c = c.replace("onclick=\"rcOverlay('overlayInWork')\"", 'data-action="rc-overlay" data-target="overlayInWork"')
c = re.sub(
    r"onclick=\"window\.location='/projects/(\{\{ p\.id \}\})'\"",
    lambda m: f'data-action="navigate" data-href="/projects/{m.group(1)}"',
    c
)
c = c.replace("onclick=\"if(event.target===this)rcClose('overlayOpened')\"", 'data-action="rc-close-if-self" data-target="overlayOpened"')
c = c.replace("onclick=\"rcClose('overlayOpened')\"", 'data-action="rc-close" data-target="overlayOpened"')
c = c.replace("onclick=\"if(event.target===this)rcClose('overlayInWork')\"", 'data-action="rc-close-if-self" data-target="overlayInWork"')
c = c.replace("onclick=\"rcClose('overlayInWork')\"", 'data-action="rc-close" data-target="overlayInWork"')
write('leader.html', c)

# ── smr_confirm.html ───────────────────────────────────────────────────────
c = read('smr_confirm.html')
# check what's there
remaining = re.findall(r' on(?:click|change|input|submit|keydown)="[^"]*"', c)
print(f'  smr_confirm.html remaining: {remaining}')
write('smr_confirm.html', c)

print('\nDone.')
