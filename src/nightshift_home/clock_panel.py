"""Native calendar and deliberately compact focus controls."""
from datetime import date
from gi.repository import Gtk, Atk


def css(widget, *names):
    for name in names:
        widget.get_style_context().add_class(name)
    return widget


def text(value, name=None, align=0):
    widget = Gtk.Label(label=value, xalign=align)
    return css(widget, name) if name else widget


class ClockPanel(Gtk.Box):
    def __init__(self, home):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.home = home
        self.refreshing = False
        css(self, 'home-card', 'calendar-panel')
        heading = Gtk.Box(spacing=8)
        heading.pack_start(text('Calendar & focus', 'card-title'), True, True, 0)
        today = css(Gtk.Button(label='Today'), 'text-button')
        today.get_accessible().set_name('Select today in the calendar')
        today.connect('clicked', self.go_today)
        heading.pack_end(today, False, False, 0)
        self.pack_start(heading, False, False, 0)
        self.calendar = Gtk.Calendar()
        self.calendar.get_accessible().set_name('Calendar. Use arrow keys to select a day.')
        self.calendar.set_display_options(Gtk.CalendarDisplayOptions.SHOW_HEADING | Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES)
        self.calendar.connect('month-changed', self.update_date)
        self.calendar.connect('day-selected', self.update_date)
        self.pack_start(self.calendar, False, False, 0)
        self.selected_date = text('', 'muted', .5)
        self.pack_start(self.selected_date, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 2)
        heading = Gtk.Box(spacing=8)
        heading.pack_start(text('FOCUS SESSION', 'eyebrow'), True, True, 0)
        self.status = text('', 'muted')
        self.status.get_accessible().set_role(Atk.Role.STATUSBAR)
        heading.pack_end(self.status, False, False, 0)
        self.pack_start(heading, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.presets = {}
        group = None
        for minutes in (25, 50):
            button = Gtk.RadioButton.new_with_label_from_widget(group, f'{minutes} min')
            group = button
            button.set_mode(False)
            css(button, 'duration-button')
            button.get_accessible().set_name(f'{minutes}-minute focus session')
            button.connect('clicked', lambda b, m=minutes: home.choose_focus_duration(m) if b.get_active() and not self.refreshing else None)
            row.pack_start(button, True, True, 0)
            self.presets[minutes] = button
        self.pack_start(row, False, False, 0)
        self.time = text('', 'timer-display', .5)
        self.time.get_accessible().set_name('Focus time remaining')
        self.pack_start(self.time, False, False, 0)
        self.progress = Gtk.ProgressBar()
        self.progress.get_accessible().set_name('Focus session progress')
        self.pack_start(self.progress, False, False, 0)
        row = Gtk.Box(spacing=8)
        self.primary = css(Gtk.Button(), 'primary-button')
        self.primary.connect('clicked', lambda *_: home.toggle_focus())
        row.pack_start(self.primary, True, True, 0)
        self.reset = css(Gtk.Button(label='Reset'), 'secondary-button')
        self.reset.connect('clicked', lambda *_: home.reset_focus())
        self.reset.get_accessible().set_name('Reset the focus timer')
        row.pack_end(self.reset, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.go_today()
        self.refresh()

    def go_today(self, *_):
        today = date.today()
        self.calendar.select_month(today.month - 1, today.year)
        self.calendar.select_day(today.day)

    def update_date(self, *_):
        year, month, day = self.calendar.get_date()
        today = date.today()
        self.calendar.clear_marks()
        if (year, month + 1) == (today.year, today.month):
            self.calendar.mark_day(today.day)
        if hasattr(self, 'selected_date') and day:
            self.selected_date.set_text(date(year, month + 1, day).strftime('%A, %d %B'))

    def refresh(self):
        self.refreshing = True
        timer = self.home.focus
        self.time.set_text(timer.display)
        self.status.set_text({'idle': 'Ready', 'running': 'In progress', 'paused': 'Paused', 'complete': 'Complete'}[timer.state])
        self.primary.set_label({'idle': 'Start focus', 'running': 'Pause', 'paused': 'Resume', 'complete': 'Start again'}[timer.state])
        self.primary.get_accessible().set_name(self.primary.get_label() + ' · focus timer')
        self.reset.set_sensitive(timer.state != 'idle')
        self.progress.set_fraction(1 - timer.seconds_left() / timer.duration)
        for minutes, button in self.presets.items():
            button.set_sensitive(timer.state in ('idle', 'complete'))
            if button.get_active() != (timer.duration == minutes * 60):
                button.set_active(timer.duration == minutes * 60)
        self.refreshing = False
