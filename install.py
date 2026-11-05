#!/usr/bin/env python3
"""Per-user, journaled installation. No sudo, downloads, or extension activation."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import tempfile

REPO = Path(__file__).resolve().parent
SOURCE = REPO / 'src/nightshift_home'
sys.path.insert(0, str(SOURCE))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(path):
    if path.is_symlink():
        return {'link': str(path.readlink())}
    if not path.exists():
        return None
    return {'data': base64.b64encode(path.read_bytes()).decode(),
            'mode': stat.S_IMODE(path.stat().st_mode)}


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.nightshift-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def restore(path, record):
    if record is None:
        path.unlink(missing_ok=True)
    elif 'link' in record:
        path.unlink(missing_ok=True)
        path.symlink_to(record['link'])
    else:
        atomic(path, base64.b64decode(record['data']), record['mode'])


def desktop_quote(value):
    # Desktop Entry Exec quoting is not shell quoting. Escape both layers.
    value = str(value).replace('\\', '\\\\\\\\').replace('"', '\\\\"')
    value = value.replace('`', '\\\\`').replace('$', '\\\\$').replace('%', '%%')
    return '"' + value + '"'


class Installer:
    def __init__(self, root, backend=None):
        self.root = Path(root).resolve()
        self.base = self.root / '.local/share/nightshift-home'
        self.journal = self.root / '.local/state/nightshift-desktop/install.json'
        self.backend = backend

    def settings_backend(self):
        if self.backend is None:
            from theme_apply import GioBackend
            self.backend = GioBackend()
        return self.backend

    def plan(self, desktop=False, autostart=False, palette=None):
        files = {}
        for path in SOURCE.rglob('*'):
            rel = path.relative_to(SOURCE)
            if not path.is_file() or path.is_symlink() or any(p in ('node_modules', '__pycache__', 'theme-output') for p in rel.parts):
                continue
            if path.suffix == '.pyc' or (len(rel.parts) == 1 and path.suffix not in ('.py', '.css', '.cjs', '.json')):
                continue
            if len(rel.parts) == 1 and path.suffix == '.json' and path.name not in ('default-layout.json', 'package.json', 'package-lock.json'):
                continue
            files[self.base / rel] = (path.read_bytes(), 0o644)
        for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
            if (REPO / name).is_file():
                files[self.base / name] = ((REPO / name).read_bytes(), 0o644)
        for name, script in [('nightshift-home', 'home.py'), ('midnight-terminal', 'terminal/terminal-launcher.py'),
                             ('midnight-settings', 'terminal/settings-launcher.py')]:
            wrapper = '#!/bin/sh\nexec /usr/bin/python3 ' + shlex.quote(str(self.base / script)) + ' "$@"\n'
            files[self.root / '.local/bin' / name] = (wrapper.encode(), 0o755)
        launch = '/usr/bin/python3 ' + desktop_quote(self.base / 'home.py')
        for name, title, args, icon in [('Home', 'Nightshift Home', '--manage', 'preferences-desktop'),
                                        ('Studio', 'Nightshift RGB Studio', '--theme', 'preferences-color'),
                                        ('Launcher', 'Nightshift Quick Launch', '--launcher', 'system-search'),
                                        ('Terminal', 'Nightshift Terminal', '', 'utilities-terminal'),
                                        ('Settings', 'Nightshift Settings', '', 'preferences-system')]:
            command = '/usr/bin/python3 ' + desktop_quote(self.base / 'terminal/terminal-launcher.py') if name == 'Terminal' else '/usr/bin/python3 ' + desktop_quote(self.base / 'terminal/settings-launcher.py') if name == 'Settings' else launch
            entry = f'[Desktop Entry]\nType=Application\nName={title}\nExec={command} {args}\nIcon={icon}\nTerminal=false\nCategories=Utility;\n'
            files[self.root / f'.local/share/applications/local.nightshift.{name}.desktop'] = (entry.encode(), 0o644)
        from data import DEFAULTS
        config = self.root / '.config/nightshift-home/config.json'
        if not config.exists():
            files[config] = (json.dumps({**DEFAULTS, 'autostart': autostart}, indent=2).encode(), 0o600)
        layout = self.root / '.config/nightshift-home/layout.json'
        if not layout.exists():
            files[layout] = ((SOURCE / 'default-layout.json').read_bytes(), 0o600)
        if autostart:
            entry = f'[Desktop Entry]\nType=Application\nName=Nightshift Home\nExec={launch}\nTerminal=false\nOnlyShowIn=GNOME;\nX-GNOME-Autostart-Delay=4\n'
            files[self.root / '.config/autostart/nightshift-home.desktop'] = (entry.encode(), 0o644)
        settings = []
        if desktop:
            from theme_apply import ThemeEngine
            from theme_palette import PRESETS
            backend = self.settings_backend()
            theme = ThemeEngine(self.root, SOURCE, backend).prepare(palette or PRESETS['Aurora glass'])
            files.update(theme['files'])
            settings.extend(theme['settings'])
            optional = [
                ('org.gnome.desktop.interface', 'color-scheme', 'prefer-dark', None),
                ('org.gnome.desktop.interface', 'enable-animations', True, None),
                ('org.gnome.shell.extensions.dash-to-dock', 'dock-position', 'BOTTOM', None),
                ('org.gnome.shell.extensions.dash-to-dock', 'extend-height', False, None),
                ('org.gnome.shell.extensions.dash-to-dock', 'dash-max-icon-size', 42, None),
                ('org.gnome.shell.extensions.dash-to-dock', 'show-show-apps-button', True, None),
            ]
            for entry in optional:
                if getattr(backend, 'supports', lambda *args: True)(entry[0], entry[1], entry[3]):
                    backend.check(entry)
                    settings.append(entry)
            # Keep existing user CSS intact after our appearance imports.
            for version, styles in [('3.0', ['terminal.css']), ('4.0', ['libadwaita.css'])]:
                path = self.root / f'.config/gtk-{version}/gtk.css'
                original = path.read_text() if path.exists() else ''
                marker = '/* Nightshift Desktop */'
                if marker not in original:
                    imports = '\n'.join('@import url("' + (self.root / '.local/share/desktop-styles/midnight-cyan' / style).as_uri() + '");' for style in styles)
                    files[path] = ((marker + '\n' + imports + '\n' + original).encode(), 0o644)
        return files, settings

    def install(self, files, settings):
        old = json.loads(self.journal.read_text()) if self.journal.exists() else {'files': {}, 'settings': [], 'status': 'ready'}
        if old['status'] != 'ready':
            raise RuntimeError('An interrupted operation was found. Run uninstall to restore its journal first.')
        journal = json.loads(json.dumps(old))
        previous, touched, applied = {}, [], []
        for path, (data, mode) in files.items():
            previous[path] = snapshot(path)
            key = str(path.relative_to(self.root))
            if key in old['files'] and path.exists() and sha(path.read_bytes()) != old['files'][key]['after']:
                # Preserve edits, including the user's latest RGB Studio palette.
                continue
            record = journal['files'].setdefault(key, {'before': previous[path]})
            record['after'] = sha(data)
            touched.append((path, data, mode))
        before_settings = []
        for schema, key, value, path in settings:
            backend = self.settings_backend()
            current = backend.get(schema, key, path)
            before_settings.append((schema, key, current, path))
            item = next((r for r in journal['settings'] if (r['schema'], r['key'], r['path']) == (schema, key, path)), None)
            if item is None:
                item = dict(schema=schema, key=key, path=path, before=current)
                journal['settings'].append(item)
            item['after'] = value
        journal['status'] = 'installing'
        atomic(self.journal, json.dumps(journal, indent=2).encode())
        try:
            for path, data, mode in touched:
                atomic(path, data, mode)
            for entry in settings:
                self.settings_backend().set(entry)
                applied.append(entry)
            if settings:
                self.settings_backend().sync()
            journal['status'] = 'ready'
            atomic(self.journal, json.dumps(journal, indent=2).encode())
        except Exception:
            for path, _, _ in reversed(touched):
                restore(path, previous[path])
            for entry in before_settings:
                self.settings_backend().set(entry)
            if settings:
                self.settings_backend().sync()
            atomic(self.journal, json.dumps(old, indent=2).encode())
            raise

    def uninstall(self):
        if not self.journal.exists():
            return []
        journal = json.loads(self.journal.read_text())
        retained = []
        for key, record in list(journal['files'].items()):
            path = self.root / key
            if not path.is_relative_to(self.root) or '..' in Path(key).parts:
                raise ValueError('Invalid installation journal path.')
            if path.is_file() and not path.is_symlink() and sha(path.read_bytes()) == record['after']:
                restore(path, record['before'])
                del journal['files'][key]
            elif not path.exists() and record['before'] is None:
                del journal['files'][key]
            else:
                retained.append(key)
        for entry in list(journal['settings']):
            backend = self.settings_backend()
            try:
                if backend.get(entry['schema'], entry['key'], entry['path']) == entry['after']:
                    backend.set((entry['schema'], entry['key'], entry['before'], entry['path']))
                journal['settings'].remove(entry)
            except RuntimeError:
                retained.append(entry['schema'] + ':' + entry['key'])
        if self.backend:
            self.backend.sync()
        if retained:
            journal['status'] = 'ready'
            atomic(self.journal, json.dumps(journal, indent=2).encode())
        else:
            self.journal.unlink()
        return retained


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--root', type=Path, default=Path.home(), help='target home directory (staging/tests)')
    parser.add_argument('--desktop', action='store_true', help='apply GTK, Shell, wallpaper, terminal and existing dock settings')
    parser.add_argument('--autostart', action='store_true', help='start widgets at GNOME login')
    parser.add_argument('--dry-run', action='store_true', help='show planned paths without changes')
    args = parser.parse_args()
    if args.root.resolve() != Path.home().resolve() and args.desktop and os.environ.get('GSETTINGS_BACKEND') != 'memory':
        parser.error('--desktop with a staging root requires GSETTINGS_BACKEND=memory')
    installer = Installer(args.root)
    if args.action == 'uninstall':
        if args.dry_run:
            print('Would restore installation journal:', installer.journal)
        else:
            retained = installer.uninstall()
            print('Restored unchanged installed files/settings. Personal data is preserved.')
            if retained:
                print('Kept later changes (journal retained):\n' + '\n'.join(retained))
        return
    files, settings = installer.plan(args.desktop, args.autostart)
    if args.dry_run:
        print('\n'.join(str(p) for p in files))
        print(f'{len(files)} files; {len(settings)} desktop settings; no extension activation.')
        return
    installer.install(files, settings)
    print('Installed. Start with:', installer.root / '.local/bin/nightshift-home')
    if args.desktop:
        print('Shell styling needs an enabled compatible User Themes extension. Log out/in if Shell does not reload.')


if __name__ == '__main__':
    main()
