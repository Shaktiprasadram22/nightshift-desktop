import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from install import Installer
from sites_config import load_sites
from test_theme import FakeBackend


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='nightshift install ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.backend = FakeBackend()
        self.installer = Installer(self.root, self.backend)

    def test_install_twice_and_uninstall_restore_existing_files(self):
        wrapper = self.root / '.local/bin/nightshift-home'
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text('previous launcher\n')
        notes = self.root / '.config/nightshift-home/notes.json'
        notes.parent.mkdir(parents=True)
        notes.write_text('{"text":"keep my notes"}')
        files, settings = self.installer.plan(autostart=True)
        self.installer.install(files, settings)
        self.assertIn('home.py', wrapper.read_text())
        self.assertEqual(wrapper.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.installer.journal.stat().st_mode & 0o777, 0o600)
        self.installer.install(*self.installer.plan(autostart=True))
        self.assertEqual(self.installer.uninstall(), [])
        self.assertEqual(wrapper.read_text(), 'previous launcher\n')
        self.assertIn('keep my notes', notes.read_text())
        self.assertFalse(self.installer.journal.exists())

    def test_uninstall_retains_later_user_edits(self):
        self.installer.install(*self.installer.plan())
        config = self.root / '.config/nightshift-home/config.json'
        config.write_text('{"github_username":"octocat"}')
        retained = self.installer.uninstall()
        self.assertIn('.config/nightshift-home/config.json', retained)
        self.assertIn('octocat', config.read_text())

    def test_failed_desktop_apply_restores_files_and_settings(self):
        previous = self.root / '.config/gtk-4.0/gtk.css'
        previous.parent.mkdir(parents=True)
        previous.write_text('/* existing CSS */\n')
        plan = self.installer.plan(desktop=True)
        self.backend.fail_once = 'dock-position'
        with self.assertRaises(OSError):
            self.installer.install(*plan)
        self.assertEqual(previous.read_text(), '/* existing CSS */\n')
        self.assertFalse((self.root / '.local/bin/nightshift-home').exists())
        self.assertEqual(self.backend.get('org.gnome.shell.extensions.user-theme', 'name'), 'Midnight-Cyan')

    def test_desktop_restore_and_optional_extensions(self):
        self.backend.supports = lambda schema, key, path=None: '.extensions.' not in schema
        files, settings = self.installer.plan(desktop=True)
        self.assertFalse(any('.extensions.' in row[0] for row in settings))
        self.assertFalse(any('keybinding' in row[0] or row[1] == 'disable-user-extensions' for row in settings))
        self.installer.install(files, settings)
        self.assertTrue((self.root / '.themes/Midnight-Cyan/gtk-3.0/gtk.css').exists())
        self.assertEqual(self.installer.uninstall(), [])

    def test_public_source_contains_no_runtime_state(self):
        files, _ = self.installer.plan()
        forbidden = {'cloudflare-initial.json', 'cloudflare-token.json', 'notes.json', 'todos.json', 'music-last-track.json', 'google-photos-client.json'}
        self.assertFalse(forbidden.intersection(p.name for p in files))
        config = json.loads(files[self.root / '.config/nightshift-home/config.json'][0])
        self.assertEqual(config['github_username'], '')
        self.assertFalse(config['show_cloudflare'])
        self.assertFalse(config['show_session_titles'])

    def test_desktop_entries_parse_when_home_has_spaces_and_special_characters(self):
        from gi.repository import Gio
        root = self.root / 'a $quoted% home'
        installer = Installer(root)
        installer.install(*installer.plan(autostart=True))
        for entry in root.rglob('*.desktop'):
            app = Gio.DesktopAppInfo.new_from_filename(str(entry))
            self.assertIsNotNone(app, str(entry))
            self.assertEqual(app.get_executable(), '/usr/bin/python3')


class SiteConfigurationTests(unittest.TestCase):
    def test_explicit_hosts_and_no_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sites.json'
            self.assertEqual(load_sites(path), ('', []))
            path.write_text(json.dumps({'account_id': 'a'*32, 'hosts': ['example.com', 'example.net']}))
            self.assertEqual(load_sites(path)[1], [('example.com', 'example.com'), ('example.net', 'example.net')])
            for host in ['https://example.com', '127.0.0.1', 'a.local', 'example.com:8080', 'a/b', '*.example.com']:
                path.write_text(json.dumps({'account_id': 'a'*32, 'hosts': [host]}))
                with self.assertRaises(ValueError):
                    load_sites(path)
