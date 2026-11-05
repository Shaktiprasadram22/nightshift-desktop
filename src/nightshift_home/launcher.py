"""An on-demand, keyboard-first launcher for local projects, apps, and saved sessions."""
from pathlib import Path
import shutil
import subprocess
import threading
import time
from gi.repository import Gtk, Gdk, Gio, GLib, Pango, Atk
from clock_panel import css, text
from launcher_catalog import build_catalog, search_items
from motion import fade_in
from workspaces import NAMES, switch_workspace


class Launcher(Gtk.ApplicationWindow):
    def __init__(self, home):
        super().__init__(application=home, title='Nightshift · Quick launch')
        self.home = home
        self.catalog = []
        self.loaded_at = 0
        self.loading = False
        self.category = 'all'
        self.matches = []
        self.filtering = False
        self.set_wmclass('nightshift-launcher', 'gjs')
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        css(self, 'nightshift-widget', 'nightshift-launcher')
        self.connect('delete-event', lambda *_: self.dismiss())
        self.connect('key-press-event', self.key_press)
        self.connect('focus-out-event', lambda *_: self.dismiss())
        content = css(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16), 'launcher-content')
        self.add(content)
        title = Gtk.Box(spacing=12)
        title.pack_start(text('Quick launch', 'launcher-title'), True, True, 0)
        title.pack_end(text('SUPER + K', 'eyebrow'), False, False, 0)
        content.pack_start(title, False, False, 0)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Search projects, apps, or sessions…')
        self.search.get_accessible().set_name('Search projects, apps, and saved Codex sessions')
        self.search.connect('search-changed', lambda *_: self.render())
        self.search.connect('activate', lambda *_: self.activate_selected())
        content.pack_start(self.search, False, False, 0)
        filters = Gtk.Box(spacing=6)
        self.filters = {}
        for value, name in [('all', 'All'), ('project', 'Projects'), ('app', 'Apps'), ('session', 'Sessions')]:
            button = css(Gtk.ToggleButton(label=name), 'filter-button')
            button.get_accessible().set_name('Show ' + name.lower())
            button.connect('clicked', lambda _b, v=value: self.set_category(v))
            filters.pack_start(button, False, False, 0)
            self.filters[value] = button
        content.pack_start(filters, False, False, 0)
        self.results = Gtk.ListBox()
        self.results.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.results.set_activate_on_single_click(True)
        self.results.get_accessible().set_name('Search results')
        self.results.connect('row-activated', lambda _list, row: self.activate_item(row.item))
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.add(self.results)
        self.empty = text('Loading local projects and apps…', 'muted', .5)
        self.empty.set_line_wrap(True)
        self.empty.set_max_width_chars(48)
        self.results.set_placeholder(self.empty)
        content.pack_start(self.scroller, True, True, 0)
        self.status = text('', 'tiny')
        self.status.get_accessible().set_role(Atk.Role.STATUSBAR)
        content.pack_start(self.status, False, False, 0)
        content.pack_start(Gtk.Separator(), False, False, 0)
        row = Gtk.Box(spacing=8)
        for index, name in enumerate(NAMES):
            button = css(Gtk.Button(label=f'{index + 1:02}  {name}'), 'workspace-button')
            button.set_tooltip_text(f'Switch to {name} · Super + Alt + {index + 1}')
            button.get_accessible().set_name(f'Switch to {name} workspace')
            button.connect('clicked', lambda _b, i=index: self.workspace(i))
            row.pack_start(button, True, True, 0)
        content.pack_start(row, False, False, 0)
        content.pack_start(text('↑ ↓  select     Enter  open     Esc  close', 'tiny', .5), False, False, 0)
        self.set_category('all')

    def open(self):
        display = self.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        width = min(640, area.width - 48)
        height = min(650, area.height - 60)
        # Let the window allocate the remaining height, including at larger text sizes.
        self.scroller.set_min_content_height(128)
        self.set_default_size(width, height)
        self.resize(width, height)
        self.move(area.x + (area.width - width) // 2, area.y + max(24, (area.height - height) // 3))
        self.search.set_text('')
        self.set_category('all')
        self.home.apply_motion_preferences(self)
        self.show_all()
        self.present()
        self.search.grab_focus()
        fade_in(self, self.home.config['reduced_motion'])
        if time.monotonic() - self.loaded_at > 30:
            self.load()

    def dismiss(self):
        self.hide()
        return True

    def load(self):
        if self.loading:
            return
        self.loading = True
        self.status.set_text('Loading local projects and apps…')
        show_titles = self.home.config['show_session_titles']

        def work():
            try:
                result, error = build_catalog(show_titles), None
            except Exception:
                result, error = [], 'Could not read local items. Close and reopen to try again.'
            GLib.idle_add(self.loaded, result, error, show_titles)

        threading.Thread(target=work, name='launcher-index', daemon=True).start()

    def loaded(self, result, error, show_titles=None):
        self.loading = False
        if show_titles is not None and show_titles != self.home.config['show_session_titles']:
            self.catalog = []
            self.loaded_at = 0
            self.load()
            return False
        if not error:
            self.catalog = result
            self.loaded_at = time.monotonic()
        self.render()
        if error:
            self.status.set_text(error)
        return False

    def set_category(self, category):
        if self.filtering:
            return
        self.filtering = True
        self.category = category
        for key, button in self.filters.items():
            button.set_active(key == category)
        self.filtering = False
        self.render()

    def render(self):
        if not hasattr(self, 'results'):
            return
        for row in self.results.get_children():
            row.destroy()
        self.matches, total = search_items(self.catalog, self.search.get_text(), self.category)
        for item in self.matches:
            row = Gtk.ListBoxRow()
            row.item = item
            css(row, 'launcher-result')
            content = Gtk.Box(spacing=12)
            try:
                ico = Gtk.Image.new_from_gicon(Gio.Icon.new_for_string(item['icon']), Gtk.IconSize.DND)
                ico.set_pixel_size(26)
            except GLib.Error:
                ico = Gtk.Image.new_from_icon_name('application-x-executable-symbolic', Gtk.IconSize.DND)
            content.pack_start(ico, False, False, 0)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            title = text(item['title'], 'result-title')
            subtitle = text(item['subtitle'], 'muted')
            for label in (title, subtitle):
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.set_max_width_chars(48)
                labels.pack_start(label, False, False, 0)
            content.pack_start(labels, True, True, 0)
            content.pack_end(text(item['kind'].title(), 'tiny'), False, False, 0)
            row.add(content)
            row.get_accessible().set_name(item['title'] + ', ' + item['kind'] + ', ' + item['subtitle'])
            row.set_tooltip_text(item['title'] + '\n' + item['subtitle'])
            self.results.add(row)
        self.empty.set_text('Loading local projects and apps…' if self.loading and not self.catalog
                            else 'No matches.\nTry a project name, app, or saved session.')
        self.empty.show()
        self.results.show_all()
        self.results.select_row(self.results.get_row_at_index(0))
        self.scroller.get_vadjustment().set_value(0)
        prefix = f'Showing {len(self.matches)} of {total}' if total > len(self.matches) else str(total)
        self.status.set_text(prefix + (' result' if total == 1 else ' results') if total
                             else 'Loading local items…' if self.loading else 'No matches. Try a different name.')

    def key_press(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            return self.dismiss()
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down) and self.matches:
            current = self.results.get_selected_row()
            index = current.get_index() if current else 0
            index = max(0, min(len(self.matches) - 1, index + (1 if event.keyval == Gdk.KEY_Down else -1)))
            row = self.results.get_row_at_index(index)
            self.results.select_row(row)
            allocation = row.get_allocation()
            self.scroller.get_vadjustment().clamp_page(allocation.y, allocation.y + allocation.height)
            return True
        return False

    def activate_selected(self):
        row = self.results.get_selected_row()
        if row:
            self.activate_item(row.item)

    def activate_item(self, item):
        try:
            if item['kind'] == 'session':
                self.dismiss()
                self.home.open_codex(item['payload'])
            elif item['kind'] == 'project':
                path = Path(item['payload'])
                if not path.is_dir():
                    raise RuntimeError('That project folder has moved. Reopen the launcher to refresh.')
                editor = shutil.which(self.home.config['project_editor'])
                if not editor:
                    raise RuntimeError('Choose an installed project editor in Nightshift settings.')
                subprocess.Popen([editor, '--new-window', str(path)], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
                self.dismiss()
            elif item['kind'] == 'app':
                app = Gio.DesktopAppInfo.new(item['payload'])
                if not app:
                    raise RuntimeError('That app is no longer available. Reopen the launcher to refresh.')
                app.launch([], self.get_display().get_app_launch_context())
                self.dismiss()
        except (OSError, GLib.Error, RuntimeError) as exc:
            self.status.set_text(str(exc))

    def workspace(self, index):
        try:
            switch_workspace(index)
            self.dismiss()
        except (OSError, RuntimeError) as exc:
            self.status.set_text(str(exc))
