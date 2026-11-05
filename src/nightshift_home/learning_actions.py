"""Plain-text learning exports. Existing notes and tasks remain intact."""
from datetime import datetime
from ai_feed import canonical_url, clean


def fields(item):
    url = canonical_url(item.get('url'))
    title = clean(item.get('title'), 220)
    action = clean(item.get('action'), 220)
    if not title or not action:
        raise ValueError('This learning item is incomplete; refresh and try again.')
    return url, title, action


def task_text(item):
    _, title, action = fields(item)
    return action + '\nGuide: ' + title


def append_note(existing, item):
    url, title, action = fields(item)
    source_line = 'Source: ' + url
    if source_line in existing.splitlines():
        return existing, False
    caption = clean(item.get('source'), 80)
    if item.get('published'):
        caption += ' · ' + datetime.fromtimestamp(item['published']).strftime('%d %b %Y')
    else:
        caption += ' · Reference guide'
    lines = ['AI Learning · ' + title, caption]
    summary = clean(item.get('summary'), 300)
    if summary:
        lines.append(summary)
    lines.extend(['Try: ' + action, source_line])
    separator = '' if not existing else '\n' if existing.endswith('\n') else '\n\n'
    return existing + separator + '\n'.join(lines), True
