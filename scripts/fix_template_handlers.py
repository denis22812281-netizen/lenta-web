"""Per-template targeted replacements for remaining inline handlers."""
import os

BASE = os.path.join(os.path.dirname(__file__), '..', 'templates')


def patch(fname, replacements):
    path = os.path.join(BASE, fname)
    with open(path, encoding='utf-8') as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f'  WARN: not found in {fname}: {old[:60]!r}')
        content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Patched: {fname}')


# reconstruction.html
patch('reconstruction.html', [
    ('onclick="document.getElementById(\'search\').focus()"',
     'data-action="focus-search"'),
    ('onclick="setOnlyProblems(true)"', 'data-action="set-only-problems" data-val="true"'),
    # second occurrence
    ('onclick="setOnlyProblems(true)"', 'data-action="set-only-problems" data-val="true"'),
    ('onclick="toggleRisk(this)"', 'data-action="toggle-risk"'),
    ('oninput="filterTable(this.value)"', 'id="search-input-recon"'),
    ('onchange="setOnlyProblems(this.checked)"', 'data-action="set-problems-checkbox"'),
    ("onclick=\"switchView('table')\"", 'data-action="switch-view" data-val="table"'),
    ("onclick=\"switchView('cards')\"", 'data-action="switch-view" data-val="cards"'),
    ('onclick="toggleCard(this.parentElement)"', 'data-action="toggle-card"'),
    ('onclick="manualRefresh()" title="Нажмите для обновления"',
     'id="btn-manual-refresh" title="Нажмите для обновления"'),
])

# section_projects.html
patch('section_projects.html', [
    ('onclick="applyBulk()"', 'data-action="apply-bulk"'),
    ('onclick="clearSelection()"', 'data-action="clear-selection"'),
    ('onchange="toggleAll(this)"', 'data-action="toggle-all"'),
    ('onchange="updateBulkBar()"', 'data-action="update-bulk-bar"'),
])

# projects.html — sortable th headers
patch('projects.html', [
    ('onclick="sortTable(0)"', 'data-action="sort-table" data-col="0"'),
    ('onclick="sortTable(1)"', 'data-action="sort-table" data-col="1"'),
    ('onclick="sortTable(2)"', 'data-action="sort-table" data-col="2"'),
    ('onclick="sortTable(3)"', 'data-action="sort-table" data-col="3"'),
    ('onclick="sortTable(7)"', 'data-action="sort-table" data-col="7"'),
    ('onclick="sortTable(8)"', 'data-action="sort-table" data-col="8"'),
])

# adaptation_list.html
patch('adaptation_list.html', [
    ('onclick="event.stopPropagation()"', 'data-action="stop-propagation"'),
    ('onclick="event.stopPropagation()"', 'data-action="stop-propagation"'),
])

# reports.html
patch('reports.html', [
    ("onclick=\"openPhoto('{{ media_url(item.photo_path) }}')\"",
     "data-action=\"open-photo\" data-url=\"{{ media_url(item.photo_path) }}\""),
    ('onclick="this.style.display=\'none\'"', 'id="lightbox-overlay"'),
])

# account_2fa.html
patch('account_2fa.html', [
    ('onclick="copySecret()"', 'id="btn-copy-secret"'),
])

# admin_users.html
patch('admin_users.html', [
    ("onclick=\"return confirm('Сбросить пароль?')\"",
     'data-confirm-inline="Сбросить пароль?"'),
    ("onclick=\"confirmDelete({{ wl.id }}, '{{ wl.display_name }}'\")",
     'data-action="confirm-delete-user" data-id="{{ wl.id }}" data-name="{{ wl.display_name }}"'),
])

# admin_vpk_criteria.html
patch('admin_vpk_criteria.html', [
    ("onclick=\"editCrit({{ c.id }}, '{{ c.name|replace(\"'\", \"\\\\'\") }}')\"",
     'data-action="edit-crit" data-id="{{ c.id }}" data-name="{{ c.name|replace(\'"\', \'&quot;\') }}"'),
])

# smr_contacts.html
patch('smr_contacts.html', [
    ('oninput="filterContacts(this.value)"', 'id="contacts-search"'),
])

# index.html
patch('index.html', [
    ("onclick=\"window.location='/tasks'\"",
     'data-action="navigate" data-href="/tasks"'),
])

# kanban.html
patch('kanban.html', [
    ('onclick="event.stopPropagation()"', 'data-action="stop-propagation"'),
])

# map.html
patch('map.html', [
    ('onclick="closeDetail()"', 'id="btn-close-detail"'),
])

# deadlines.html (print already handled by bulk script, check onchange)
patch('deadlines.html', [])  # should be clean after bulk script

print('\nDone.')
