"""Transparent, searchable AI learning with explicit saves to local documents."""
from datetime import datetime
import time
from gi.repository import Gtk, Pango, Atk, GLib
from clock_panel import css, text
from personal_widgets import transparent_scroller, focus_editor
import ai_feed


class AIPanel(Gtk.Box):
    def __init__(self, home):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.home = home
        self.tab, self.data, self.errors = 'latest', {}, {}
        self.busy, self.selecting = False, False
        self.saved, self.cards = set(), []
        self.notice, self.notice_source = '', 0
        css(self, 'personal-widget', 'ai-widget')
        header = Gtk.Box(spacing=8)
        header.pack_start(text('AI Learning', 'personal-title'), True, True, 0)
        self.refresh_button = home.small_button('view-refresh-symbolic', 'Refresh learning · checks every 5 minutes', lambda: home.refresh_ai(force=True))
        header.pack_end(self.refresh_button, False, False, 0)
        self.pack_start(header, False, False, 0)
        search_row = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry()
        self.search.set_width_chars(1)
        self.search.set_max_length(180)
        self.search.set_placeholder_text('Search learning: cost, caching, agents…')
        self.search.set_tooltip_text('Filter learning resources as you type. Web opens a broader AI search in Google.')
        self.search.get_accessible().set_name('Search AI learning resources')
        self.search.connect('button-press-event', focus_editor)
        self.search.connect('search-changed', self.search_changed)
        self.search.connect('activate', lambda *_: self.render())
        search_row.pack_start(self.search, True, True, 0)
        self.web_button = css(Gtk.Button(label='Web'), 'learning-action')
        self.web_button.set_tooltip_text('Search this AI topic on Google')
        self.web_button.get_accessible().set_name('Search this AI topic on Google in your browser')
        self.web_button.connect('clicked', lambda *_: home.open_url(ai_feed.web_search_url(self.search.get_text())))
        search_row.pack_end(self.web_button, False, False, 0)
        self.pack_start(search_row, False, False, 0)
        tabs = Gtk.Box(spacing=3)
        self.buttons = {}
        for name, title in [('latest', 'Latest'), ('cost', 'Cost'), ('latency', 'Latency'), ('build', 'Build')]:
            button = css(Gtk.ToggleButton(label=title), 'ai-tab')
            button.set_active(name == self.tab)
            button.get_accessible().set_name('Filter AI learning: ' + title)
            button.connect('clicked', lambda _b, n=name: self.select(n))
            tabs.pack_start(button, False, False, 0)
            self.buttons[name] = button
        self.pack_start(tabs, False, False, 0)
        self.items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        self.scroller = transparent_scroller(85)
        self.scroller.add(self.items)
        self.pack_start(self.scroller, True, True, 0)
        self.status = text('', 'personal-status')
        self.status.set_line_wrap(True)
        self.status.set_max_width_chars(1)
        self.status.set_lines(2)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.get_accessible().set_role(Atk.Role.STATUSBAR)
        self.pack_start(self.status, False, False, 0)
        self.connect('destroy', self.destroyed)
        self.render()

    def destroyed(self, *_):
        if self.notice_source:
            GLib.source_remove(self.notice_source)
            self.notice_source = 0

    def search_changed(self, *_):
        self.notice = ''
        self.scroller.get_vadjustment().set_value(0)
        self.render()

    def select(self, tab):
        if self.selecting or tab not in self.buttons:
            return
        self.selecting, self.tab, self.notice = True, tab, ''
        for name, button in self.buttons.items():
            button.set_active(name == tab)
        self.selecting = False
        self.scroller.get_vadjustment().set_value(0)
        self.render()

    def update(self, data, errors=None, busy=False):
        self.data, self.errors, self.busy = data, errors or {}, busy
        self.render()

    def save(self, item, destination, button):
        try:
            added = self.home.save_learning(item, destination)
        except (OSError, ValueError) as exc:
            self.notice = str(exc) if isinstance(exc, ValueError) else 'Could not save. Your existing text is safe; please retry.'
        else:
            self.saved.add((item['url'], destination))
            button.set_label('Added' if destination == 'todo' else 'Saved')
            button.set_sensitive(False)
            name = 'To-do' if destination == 'todo' else 'Notes'
            self.notice = ('Added to ' if added else 'Already in ') + name + ' · source link included'
        self.update_status()
        if self.notice_source:
            GLib.source_remove(self.notice_source)
        self.notice_source = GLib.timeout_add_seconds(8, self.clear_notice)

    def clear_notice(self):
        self.notice_source, self.notice = 0, ''
        self.update_status()
        return False

    def update_status(self):
        records = [value for key, value in self.data.items() if key in ai_feed.SOURCES]
        if self.busy:
            status = 'Checking for fresh learning…'
        elif self.errors:
            status = f'{len(self.errors)} source(s) offline · saved resources available'
        elif records:
            stamp = min(value['updated_at'] for value in records)
            date = datetime.fromtimestamp(stamp).strftime('%H:%M' if time.time() - stamp < 86400 else '%d %b, %H:%M')
            status = f'Checked {date} · every 5 min'
        else:
            status = 'Reference guides · refresh for recent articles'
        if self.search.get_text().strip():
            status = f'{len(self.cards)} matches · Web searches Google'
        self.status.set_text(self.notice or status)
        details = ['Publisher excerpts and dates. “Try” actions are suggested experiments; benefits depend on your workload.']
        for key, source in ai_feed.SOURCES.items():
            record = self.data.get(key)
            state = self.errors.get(key) or ('Checked ' + datetime.fromtimestamp(record['updated_at']).strftime('%d %b, %H:%M') if record else 'Not checked yet')
            details.append(source['name'] + ': ' + state)
        self.status.set_tooltip_text('\n'.join(details))
        self.refresh_button.set_sensitive(not self.busy)

    def render(self):
        top = self.get_toplevel()
        focus = top.get_focus() if isinstance(top, Gtk.Window) else None
        identity = getattr(focus, 'learning_key', None)
        position = self.scroller.get_vadjustment().get_value()
        for child in self.items.get_children():
            child.destroy()
        self.cards = []
        for item in ai_feed.select_items(self.data, self.tab, self.search.get_text()):
            card = css(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4), 'learning-card')
            link = css(Gtk.Button(), 'ai-article')
            link.learning_key = (item['url'], 'open')
            title = text(item['title'], 'ai-title')
            title.set_line_wrap(True)
            title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            title.set_lines(2)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.set_max_width_chars(1)
            link.add(title)
            link.set_tooltip_text(item['title'] + '\n' + item['url'] + '\nTry: ' + item['action'])
            link.get_accessible().set_name(item['title'] + '. Open source in browser.')
            link.connect('clicked', lambda _b, url=item['url']: self.home.open_url(url))
            card.pack_start(link, False, False, 0)
            excerpt = item.get('summary') or 'Try: ' + item['action']
            summary = text(excerpt, 'ai-description')
            summary.set_line_wrap(True)
            summary.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            summary.set_max_width_chars(1)
            summary.set_lines(2)
            summary.set_ellipsize(Pango.EllipsizeMode.END)
            summary.set_tooltip_text(excerpt)
            card.pack_start(summary, False, False, 0)
            row = Gtk.Box(spacing=5)
            date = datetime.fromtimestamp(item['published']).strftime('%d %b') if item.get('published') else 'Guide'
            caption = item['source'] + ' · ' + date
            meta = text(caption, 'personal-status')
            meta.set_max_width_chars(1)
            meta.set_ellipsize(Pango.EllipsizeMode.END)
            meta.set_tooltip_text(caption)
            row.pack_start(meta, True, True, 0)
            controls = {'open': link}
            for destination, label in [('todo', 'To-do'), ('notes', 'Notes')]:
                saved = (item['url'], destination) in self.saved
                action = css(Gtk.Button(label=('Added' if destination == 'todo' else 'Saved') if saved else label), 'learning-action')
                action.learning_key = (item['url'], destination)
                action.set_sensitive(not saved)
                action.get_accessible().set_name(('Add learning task to To-do: ' if destination == 'todo' else 'Append learning to Notes: ') + item['title'])
                action.set_tooltip_text(('Add task: ' + item['action']) if destination == 'todo' else 'Append the takeaway, suggested experiment, and source link to your existing notes')
                action.connect('clicked', lambda button, entry=item, dest=destination: self.save(entry, dest, button))
                row.pack_start(action, False, False, 0)
                controls[destination] = action
            card.pack_start(row, False, False, 0)
            self.items.pack_start(card, False, False, 0)
            self.cards.append({'item': item, 'widget': card, **controls})
            for control in controls.values():
                if identity == control.learning_key:
                    control.grab_focus()
        if not self.cards:
            empty = text('No matching resources here. Try another topic or use Web to search Google.', 'personal-placeholder')
            empty.set_line_wrap(True)
            empty.set_max_width_chars(1)
            self.items.pack_start(empty, False, False, 8)
        self.items.show_all()
        self.scroller.get_vadjustment().set_value(position)
        self.update_status()
