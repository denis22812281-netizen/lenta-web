"""Bulk-replace common inline event handler patterns across all templates."""
import os
import re

tdir = os.path.join(os.path.dirname(__file__), '..', 'templates')
changed = []

for fname in sorted(os.listdir(tdir)):
    if not fname.endswith('.html'):
        continue
    path = os.path.join(tdir, fname)
    with open(path, encoding='utf-8') as f:
        content = f.read()
    orig = content

    # onsubmit="return confirm('message')" → data-confirm="message"
    content = re.sub(
        r'''onsubmit="return confirm\('([^']*?)'\)"''',
        lambda m: 'data-confirm="' + m.group(1) + '"',
        content
    )
    # onsubmit="return confirm("message")" (double quotes inside)
    content = re.sub(
        r'''onsubmit="return confirm\(&quot;([^&]*?)&quot;\)"''',
        lambda m: 'data-confirm="' + m.group(1) + '"',
        content
    )

    # onclick="window.print()"
    content = content.replace('onclick="window.print()"', 'data-action="print"')

    # onclick="location.reload()" or onclick='location.reload()'
    content = content.replace('onclick="location.reload()"', 'data-action="reload"')
    content = content.replace("onclick='location.reload()'", 'data-action="reload"')

    # onchange="this.form.submit()"
    content = content.replace('onchange="this.form.submit()"', 'data-action="autosubmit"')

    if content != orig:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        changed.append(fname)

print('Changed files:', changed)
print('Total:', len(changed))
