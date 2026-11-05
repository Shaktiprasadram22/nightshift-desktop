"""A compact transparent YouTube Music shortcut and transport controls."""
from gi.repository import Gtk, Gio, Pango, GLib
from clock_panel import css, text
from personal_widgets import transparent_scroller
from music_data import MUSIC_URL, reopen_url, track, permitted, is_music, clean
from music_player import MusicPlayer
from music_progress import duration, seekable, stamp, track_key


class MusicPanel(Gtk.Box):
    def __init__(self, home, history=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.home = home
        self.progress_source = 0
        self.seek_source = 0
        self.seek_target = None
        css(self, 'personal-widget', 'music-panel')
        app = Gio.AppInfo.get_default_for_type('x-scheme-handler/https', False)
        browser = ((app.get_id() or '') + ' ' + app.get_name()).lower() if app else ''
        hint = next((n for n in ('chrome', 'chromium', 'brave', 'firefox') if n in browser), '')
        self.player = MusicPlayer(self.render, history, hint)
        header = Gtk.Box(spacing=9)
        image = Gtk.Image.new_from_icon_name('youtube-music', Gtk.IconSize.LARGE_TOOLBAR)
        header.pack_start(image, False, False, 0)
        title = text('YouTube Music', 'personal-title')
        title.set_max_width_chars(1); title.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_start(title, True, True, 0)
        self.open_button = home.small_button('go-next-symbolic', 'Open YouTube Music', self.open_music)
        header.pack_end(self.open_button, False, False, 0)
        self.pack_start(header, False, False, 0)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.title = text('', 'music-title')
        self.artist = text('', 'music-artist')
        for label in (self.title, self.artist):
            label.set_max_width_chars(1); label.set_ellipsize(Pango.EllipsizeMode.END)
            details.pack_start(label, False, False, 0)
        progress = Gtk.Box(spacing=9)
        self.elapsed = text('—:—', 'personal-status')
        self.total = text('—:—', 'personal-status')
        self.timeline = css(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1), 'music-progress')
        self.timeline.set_draw_value(False); self.timeline.set_hexpand(True)
        self.timeline.set_size_request(40, -1)
        self.timeline.get_accessible().set_name('Song position · seconds')
        self.timeline.connect('change-value', self.change_position)
        progress.pack_start(self.elapsed, False, False, 0)
        progress.pack_start(self.timeline, True, True, 0)
        progress.pack_start(self.total, False, False, 0)
        scroller = transparent_scroller(35); scroller.add(details)
        self.pack_start(scroller, True, True, 0)
        self.pack_start(progress, False, False, 0)
        controls = Gtk.Box(spacing=12)
        self.previous = home.small_button('media-skip-backward-symbolic', 'Previous song', lambda: self.player.action('Previous'))
        self.play = home.small_button('media-playback-start-symbolic', 'Open YouTube Music', self.play_clicked)
        self.next = home.small_button('media-skip-forward-symbolic', 'Next song', lambda: self.player.action('Next'))
        for button in (self.previous, self.play, self.next):
            css(button, 'music-control'); controls.pack_start(button, False, False, 0)
        self.choose_button = css(Gtk.MenuButton(), 'icon-button', 'music-control')
        self.choose_button.add(Gtk.Image.new_from_icon_name('view-more-symbolic', Gtk.IconSize.BUTTON))
        self.choose_button.set_tooltip_text('Choose music player or browser')
        self.choose_button.get_accessible().set_name('Choose music player or browser')
        self.menu = Gtk.Menu(); self.choose_button.set_popup(self.menu)
        self.menu.connect('show', self.fill_menu)
        controls.pack_end(self.choose_button, False, False, 0)
        self.pack_start(controls, False, False, 0)
        self.status = text('', 'personal-status')
        self.status.set_max_width_chars(1); self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.pack_start(self.status, False, False, 0)
        self.connect('destroy', self.destroyed)
        self.render()

    def destroyed(self, *_):
        self.player.stop()
        for source in (self.progress_source, self.seek_source):
            if source: GLib.source_remove(source)
        self.progress_source = self.seek_source = 0

    def change_position(self, _scale, _scroll, value):
        selected = self.player.selected
        if not selected or not seekable(selected['properties']): return True
        if self.seek_source: GLib.source_remove(self.seek_source)
        self.seek_target = ((selected['owner'], track_key(selected['properties'])), value)
        self.timeline.set_value(value); self.elapsed.set_text(stamp(value))
        # Coalesce dragging/key repeats; never queue a flood of player commands.
        def commit():
            self.seek_source = 0
            target, seconds = self.seek_target; self.seek_target = None
            self.player.seek(seconds, target)
            self.render_progress()
            return False
        self.seek_source = GLib.timeout_add(180, commit)
        return True

    def render_progress(self):
        selected = self.player.selected
        props = selected['properties'] if selected else {}
        length = duration(props)
        position = selected['progress'].position() if selected else None
        ready = length is not None and position is not None
        allowed = ready and seekable(props) and not self.player.busy
        self.timeline.set_sensitive(bool(allowed))
        self.timeline.set_tooltip_text('Seek within this song · drag or use arrow keys' if allowed else 'Playback progress · this player does not allow seeking' if ready else 'Timeline unavailable from this player')
        if not self.seek_source:
            self.timeline.set_range(0, length or 1)
            self.timeline.set_value(position if ready else 0)
            self.elapsed.set_text(stamp(position if ready else None)); self.total.set_text(stamp(length))
        return True

    def open_music(self, last=False):
        self.player.arm()
        value = self.player.history.value
        self.home.open_url(reopen_url(value) if last and value['title'] else MUSIC_URL)

    def play_clicked(self):
        if self.player.selected:
            props = self.player.selected['properties']
            self.player.action('Pause' if props.get('PlaybackStatus') == 'Playing' else 'Play')
        else:
            self.open_music(last=True)

    def fill_menu(self, *_):
        for child in self.menu.get_children(): child.destroy()
        choices = self.player.candidates()
        note = Gtk.MenuItem(label='Use a browser’s current media session'); note.set_sensitive(False); self.menu.append(note)
        for record in choices:
            title = track(record['properties'])['title']
            identity = clean(record['root'].get('Identity')) or 'Browser'
            item = Gtk.MenuItem(label=identity[:40] + (' · ' + title[:48] if title else ''))
            item.connect('activate', lambda _item, name=record['name']: self.player.choose(name))
            self.menu.append(item)
        if not choices:
            item = Gtk.MenuItem(label='Start a song in Music to connect'); item.set_sensitive(False); self.menu.append(item)
        self.menu.append(Gtk.SeparatorMenuItem())
        last = Gtk.MenuItem(label='Open last track in YouTube Music')
        last.set_sensitive(bool(self.player.history.value['title']))
        last.connect('activate', lambda *_: self.open_music(last=True)); self.menu.append(last)
        retry = Gtk.MenuItem(label='Check for players again')
        retry.connect('activate', lambda *_: (self.player.stop(), self.player.start())); self.menu.append(retry)
        self.menu.show_all()

    def render(self):
        selected = self.player.selected
        props = selected['properties'] if selected else {}
        value = track(props) if selected else self.player.history.value
        if not value['title'] and selected: value = {'title':'Track details unavailable','artist':'','url':''}
        self.title.set_text(value['title'] or 'Your music, one click away')
        self.artist.set_text(value['artist'] or ('Last played on this device' if value['title'] and not selected else 'Start a song in YouTube Music'))
        self.title.set_tooltip_text(value['title'] or 'Open YouTube Music and start a song')
        self.artist.set_tooltip_text(value['artist'] or None)
        playing = props.get('PlaybackStatus') == 'Playing'
        method = 'Pause' if playing else 'Play'
        self.play.get_child().set_from_icon_name('media-playback-pause-symbolic' if playing else 'media-playback-start-symbolic', Gtk.IconSize.BUTTON)
        action_name = method + ' song' if selected else ('Open last track in YouTube Music' if value['title'] else 'Open YouTube Music')
        self.play.set_tooltip_text(action_name); self.play.get_accessible().set_name(action_name)
        self.play.set_sensitive(not self.player.busy and (not selected or permitted(props, method)))
        for button, action in ((self.previous, 'Previous'), (self.next, 'Next')):
            allowed = bool(selected and not self.player.busy and permitted(props, action))
            button.set_sensitive(allowed)
            button.set_tooltip_text(action + ' song' if allowed else (action + ' is unavailable until the player provides a queue'))
        if self.player.error: status = self.player.error
        elif self.player.history.error: status = self.player.history.error
        elif selected:
            identity = clean(selected['root'].get('Identity')) or 'Music'
            status = ('Playing' if playing else 'Paused' if props.get('PlaybackStatus') == 'Paused' else 'Stopped') + ' · ' + identity
            if not is_music(selected['root'], props): status += ' current media'
        elif value['title']: status = 'Last played · open Music to continue'
        elif self.player.candidates(): status = 'Choose your browser from ··· to connect'
        else: status = 'Waiting for music playback'
        self.status.set_text(status)
        self.status.set_tooltip_text(status)
        self.render_progress()
        ticking = self.player.active and playing and selected and duration(props) and selected['progress'].position() is not None
        if ticking and not self.progress_source:
            self.progress_source = GLib.timeout_add_seconds(1, self.render_progress)
        elif not ticking and self.progress_source:
            GLib.source_remove(self.progress_source); self.progress_source = 0
