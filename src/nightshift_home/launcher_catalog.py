"""Bounded local project/app/session discovery and literal search; no shell evaluation."""
from pathlib import Path
import os
import unicodedata

MARKERS = ('.git', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'pom.xml', 'CMakeLists.txt')
SKIP = {'node_modules', 'venv', 'env', 'target', 'build', 'dist', 'vendor', '__pycache__'}


def discover_projects(home, sessions=(), limit=150):
    home = Path(home)
    found = {}

    def add(path):
        try:
            path = Path(path).resolve()
            if path == home or not path.is_relative_to(home) or not path.is_dir():
                return
            if any(part.startswith('.') for part in path.relative_to(home).parts):
                return
            found[str(path)] = path
        except (OSError, ValueError):
            pass

    for session in sessions:
        add(session['cwd'])
    # Only inspect immediate home folders and two levels in explicit project roots.
    queue = [(home, 1)]
    queue.extend((home / name, 3) for name in ('Projects', 'projects', 'Developer', 'dev', 'Documents'))
    visited = set()
    inspected = 0
    while queue and inspected < 600 and len(found) < limit:
        folder, depth = queue.pop(0)
        if folder in visited or not folder.is_dir() or folder.is_symlink():
            continue
        visited.add(folder)
        try:
            children = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for path in children:
            if inspected >= 600 or len(found) >= limit:
                break
            if path.name.startswith('.') or path.name in SKIP or path.is_symlink() or not path.is_dir():
                continue
            inspected += 1
            if any((path / marker).exists() for marker in MARKERS):
                add(path)
            elif depth > 1:
                queue.append((path, depth - 1))
    return list(found.values())


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold())
                   if not unicodedata.combining(c))


def search_items(items, query='', category='all', limit=60):
    tokens = normalize(query).split()
    scored = []
    for order, item in enumerate(items):
        if category != 'all' and item['kind'] != category:
            continue
        title = normalize(item['title'])
        corpus = title + ' ' + normalize(item.get('subtitle', '')) + ' ' + normalize(item.get('keywords', ''))
        if not all(token in corpus for token in tokens):
            continue
        score = sum(0 if title == t else 1 if title.startswith(t) else 3 if t in title else 8 for t in tokens)
        scored.append((score, order, item))
    scored.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in scored[:limit]], len(scored)


def build_catalog(show_titles=True):
    from gi.repository import Gio
    from data import HOME, read_sessions, age_label
    sessions = read_sessions(24)
    session_items = [dict(key='session:' + s['id'], kind='session',
                          title=s['title'] if show_titles else f'Saved session {i + 1}',
                          subtitle=f"{Path(s['cwd']).name or 'Home'} · {age_label(s['updated_at'])}",
                          keywords='codex resume', payload=s, icon='utilities-terminal-symbolic')
                     for i, s in enumerate(sessions)]
    projects = [dict(key='project:' + str(p), kind='project', title=p.name,
                     subtitle='~/' + str(p.relative_to(HOME)), keywords='folder code project',
                     payload=str(p), icon='folder-symbolic')
                for p in discover_projects(HOME, sessions)]
    apps = []
    for app in Gio.AppInfo.get_all():
        if not app.should_show() or not app.get_id():
            continue
        apps.append(dict(key='app:' + app.get_id(), kind='app', title=app.get_display_name(),
                         subtitle=app.get_description() or 'Application',
                         keywords=app.get_executable() or '', payload=app.get_id(),
                         icon=app.get_icon().to_string() if app.get_icon() else 'application-x-executable-symbolic'))
    favorites = ['org.gnome.Terminal.desktop', 'code.desktop', 'cursor.desktop', 'brave-browser.desktop', 'org.gnome.Nautilus.desktop']
    apps.sort(key=lambda a: (favorites.index(a['payload']) if a['payload'] in favorites else 99, a['title'].casefold()))
    # A balanced initial list makes every category discoverable before searching.
    return session_items[:2] + projects[:3] + apps[:4] + session_items[2:] + projects[3:] + apps[4:]
