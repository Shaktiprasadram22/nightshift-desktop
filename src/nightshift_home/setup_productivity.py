from paths import user_home
"""Install/restore the launcher shortcut and three named workspaces, with a change journal."""
from pathlib import Path
import json
import shlex
import subprocess
import sys
from gi.repository import Gio, GLib

BASE = Path(__file__).resolve().parent
JOURNAL = user_home() / '.config/nightshift-home/productivity-settings.json'
LAUNCHER = shlex.quote(str(user_home() / '.local/bin/nightshift-home'))
CUSTOM_PATH = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/nightshift-launcher/'
CUSTOM_SCHEMA = 'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding'


def settings(schema, path=None):
    return Gio.Settings.new_with_path(schema, path) if path else Gio.Settings.new(schema)


def desired():
    wm = settings('org.gnome.desktop.wm.preferences')
    # Keep any additional user workspaces if this installer is run again later.
    existing = int(subprocess.check_output(['xprop', '-root', '_NET_NUMBER_OF_DESKTOPS'], text=True).strip().split('=')[-1])
    count = max(3, existing)
    old_names = list(wm.get_strv('workspace-names'))
    names = ['Coding', 'Research', 'Personal'] + [old_names[i] if i < len(old_names) else f'Workspace {i+1}' for i in range(3, count)]
    result = [('org.gnome.mutter', 'dynamic-workspaces', False, None),
              ('org.gnome.desktop.wm.preferences', 'num-workspaces', count, None),
              ('org.gnome.desktop.wm.preferences', 'workspace-names', names, None)]
    for index in range(1, 4):
        key = f'switch-to-workspace-{index}'
        values = list(settings('org.gnome.desktop.wm.keybindings').get_strv(key))
        binding = f'<Super><Alt>{index}'
        if binding not in values:
            values.append(binding)
        result.append(('org.gnome.desktop.wm.keybindings', key, values, None))
    for key, value in [('name', 'Nightshift Quick launch'), ('command', LAUNCHER + ' --launcher'), ('binding', '<Super>k')]:
        result.append((CUSTOM_SCHEMA, key, value, CUSTOM_PATH))
    media = settings('org.gnome.settings-daemon.plugins.media-keys')
    paths = list(media.get_strv('custom-keybindings'))
    if CUSTOM_PATH not in paths:
        paths.append(CUSTOM_PATH)
    result.append(('org.gnome.settings-daemon.plugins.media-keys', 'custom-keybindings', paths, None))
    return result


def apply():
    changes = desired()
    journal = json.loads(JOURNAL.read_text()) if JOURNAL.exists() else []
    for schema, key, value, path in changes:
        s = settings(schema, path)
        spec = s.props.settings_schema.get_key(key)
        variant = GLib.Variant(spec.get_value_type().dup_string(), value)
        if not spec.range_check(variant) or not s.is_writable(key):
            raise RuntimeError(f'Cannot set {schema} {key}')
        entry = next((e for e in journal if (e['schema'], e['key'], e['path']) == (schema, key, path)), None)
        if entry is None:
            old = s.get_user_value(key)
            entry = dict(schema=schema, key=key, path=path, old=old.print_(True) if old is not None else None)
            journal.append(entry)
        entry['applied'] = variant.print_(True)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(journal, indent=2));JOURNAL.chmod(0o600)
    for schema, key, value, path in changes:
        s = settings(schema, path)
        s.set_value(key, GLib.Variant(s.props.settings_schema.get_key(key).get_value_type().dup_string(), value))
    Gio.Settings.sync()
    print('Super+K: launcher. Super+Alt+1/2/3: Coding, Research, Personal.')


def restore():
    if JOURNAL.exists():
        for entry in reversed(json.loads(JOURNAL.read_text())):
            s = settings(entry['schema'], entry['path'])
            if entry['key'] == 'custom-keybindings':
                s.set_strv(entry['key'], [p for p in s.get_strv(entry['key']) if p != CUSTOM_PATH])
            elif s.get_value(entry['key']).print_(True) == entry['applied']:
                if entry['old'] is None:
                    s.reset(entry['key'])
                else:
                    s.set_value(entry['key'], GLib.Variant.parse(None, entry['old'], None, None))
        Gio.Settings.sync()
    JOURNAL.unlink(missing_ok=True)
    print('Restored the workspace and shortcut settings changed by this helper.')


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('apply', 'restore'):
        raise SystemExit('Use apply or restore.')
    globals()[sys.argv[1]]()
