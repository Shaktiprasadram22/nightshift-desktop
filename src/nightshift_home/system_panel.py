"""Transparent, responsive system telemetry using one two-second timer."""
from collections import deque
import cairo
from gi.repository import Gtk, GLib, Atk, Pango
from clock_panel import css, text
from personal_widgets import transparent_scroller
from system_stats import SystemSampler, SAMPLE_SECONDS, STORAGE_SECONDS
import theme_palette


class Meter(Gtk.DrawingArea):
    def __init__(self, color, history=False):
        super().__init__()
        self.color = color
        self.history = history
        self.values = []
        self.set_size_request(-1, 26)
        self.connect('draw', self.draw_meter)
        self.get_accessible().set_role(Atk.Role.IMAGE)
        self.get_accessible().set_name('Waiting for a reading')

    def update(self, values, description):
        self.values = list(values)
        self.get_accessible().set_name(description)
        self.set_tooltip_text(description)
        self.queue_draw()

    def draw_meter(self, _widget, cr):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        color = theme_palette.rgb(theme_palette.paint(self.color))
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if self.history:
            cr.set_source_rgba(*color, .18)
            cr.set_line_width(1)
            cr.move_to(1, height - 2); cr.line_to(width - 1, height - 2); cr.stroke()
            if self.values:
                cr.set_source_rgba(*color, .95)
                cr.set_line_width(1.6)
                for index, value in enumerate(self.values):
                    x = 1 + (30 - len(self.values) + index) * (width - 2) / 29
                    y = height - 2 - value / 100 * (height - 4)
                    (cr.move_to if index == 0 else cr.line_to)(x, y)
                cr.stroke()
                cr.arc(x, y, 1.7, 0, 6.283185); cr.fill()
        else:
            cr.set_source_rgba(*color, .22)
            cr.set_line_width(3)
            cr.move_to(2, height / 2); cr.line_to(width - 2, height / 2); cr.stroke()
            if self.values and self.values[-1] > 0:
                cr.set_source_rgba(*color, .9)
                cr.move_to(2, height / 2)
                cr.line_to(2 + (width - 4) * self.values[-1] / 100, height / 2)
                cr.stroke()
        return False


class Metric(Gtk.Box):
    def __init__(self, title, kind, color, detail):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        css(self, 'system-metric', 'system-' + kind)
        self.set_hexpand(True)
        self.title = text(title, 'system-label')
        self.value = text('—', 'system-value')
        self.detail = text(detail, 'system-detail')
        self.note = text('', 'system-note')
        for label in (self.title, self.value, self.detail, self.note):
            label.set_max_width_chars(1)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.meter = Meter(color, history=kind == 'cpu')
        for item in (self.title, self.value, self.detail, self.meter, self.note):
            self.pack_start(item, False, False, 0)


from network_stats import NetworkSampler, speed


class SystemPanel(Gtk.Box):
    def __init__(self, home, sampler=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.home = home
        self.sampler = sampler or SystemSampler()
        self.network_sampler = NetworkSampler()
        self.source = 0
        self.history = deque(maxlen=30)
        self.width = 624
        css(self, 'personal-widget', 'system-panel')
        header = Gtk.Box(spacing=10)
        title = text('System monitor', 'personal-title')
        title.set_max_width_chars(1); title.set_line_wrap(True)
        title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        header.pack_start(title, True, True, 0)
        self.live = text('LIVE', 'system-live')
        header.pack_start(self.live, False, False, 0)
        self.open_button = home.small_button('go-next-symbolic', 'Open System Monitor · processes and details', home.open_system_monitor)
        header.pack_end(self.open_button, False, False, 0)
        self.pack_start(header, False, False, 0)
        self.metrics = Gtk.Box(spacing=28)
        self.metrics.set_homogeneous(True)
        self.cpu = Metric('CPU', 'cpu', '#8ee7f6', 'Sampling…')
        self.memory = Metric('RAM', 'ram', '#c4b0f2', 'Reading memory…')
        self.storage = Metric('STORAGE · /', 'storage', '#ffbad9', 'Reading storage…')
        for metric in (self.cpu, self.memory, self.storage):
            self.metrics.pack_start(metric, True, True, 0)
        self.scroller = transparent_scroller(56)
        self.scroller.add(self.metrics)
        self.pack_start(self.scroller, True, True, 0)
        self.network = text('↓ —     ↑ —', 'network-speeds')
        self.network.set_max_width_chars(1); self.network.set_line_wrap(True)
        self.status = text(f'CPU / RAM · {SAMPLE_SECONDS}s     Storage · {STORAGE_SECONDS}s', 'personal-status')
        self.status.set_max_width_chars(1); self.status.set_line_wrap(True)
        self.footer = Gtk.Box(spacing=16)
        self.footer.pack_start(self.status, True, True, 0)
        self.footer.pack_end(self.network, True, True, 0)
        self.pack_start(self.footer, False, False, 0)
        self.connect('style-updated', lambda *_: self.set_geometry(self.width))
        self.connect('destroy', lambda *_: self.stop())

    def set_geometry(self, width, _height=None):
        self.width = width
        # Reflow for enlarged text too, not only for a narrow window.
        font_size = self.cpu.value.get_style_context().get_font(Gtk.StateFlags.NORMAL).get_size() / Pango.SCALE
        narrow = width < 560 * max(1, font_size / 26)
        orientation = Gtk.Orientation.VERTICAL if narrow else Gtk.Orientation.HORIZONTAL
        self.footer.set_orientation(orientation)
        self.footer.set_spacing(4 if narrow else 16)
        if self.metrics.get_orientation() != orientation:
            self.metrics.set_orientation(orientation)
            self.metrics.set_homogeneous(not narrow)
            self.metrics.set_spacing(20 if narrow else 28)

    def start(self):
        if self.source:
            return
        self.sampler.reset()
        self.network_sampler.reset()
        self.history.clear()
        self.refresh()
        self.source = GLib.timeout_add_seconds(SAMPLE_SECONDS, self.refresh)

    def stop(self):
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
        self.sampler.reset()
        self.network_sampler.reset()
        self.history.clear()

    def refresh(self):
        self.update(self.sampler.sample())
        net = self.network_sampler.sample()
        self.network.set_text('↓ '+speed(net['download'])+'     ↑ '+speed(net['upload']))
        message = net['state'] or 'Physical interfaces: '+', '.join(net['interfaces'])
        self.network.set_tooltip_text(message+'. Download / upload averaged over 2 seconds. Includes local network traffic; virtual and VPN interfaces are excluded to avoid counting traffic twice.')
        self.network.get_accessible().set_name('Download '+speed(net['download'])+', upload '+speed(net['upload'])+'. '+message)
        return True

    def update(self, reading):
        if reading.reset_history:
            self.history.clear()
        self.cpu.value.set_text('—' if reading.cpu is None else f'{reading.cpu:.1f}%')
        self.cpu.detail.set_text(reading.errors.get('cpu') or ('Sampling…' if reading.cpu is None else 'Across all cores'))
        self.cpu.note.set_text('Last 60 seconds')
        if reading.cpu is not None:
            self.history.append(reading.cpu)
        self.cpu.meter.update(self.history, 'CPU usage history, fixed scale from 0 to 100 percent, up to 60 seconds')
        self.cpu.value.get_accessible().set_name('CPU: ' + (f'{reading.cpu:.1f} percent across all cores' if reading.cpu is not None else self.cpu.detail.get_text()))
        for key, metric, usage in (('memory', self.memory, reading.memory), ('storage', self.storage, reading.storage)):
            if usage is None:
                metric.value.set_text('—')
                metric.detail.set_text(reading.errors.get(key, 'Reading…'))
                metric.note.set_text('Retrying automatically')
                metric.meter.update([], metric.detail.get_text())
            else:
                metric.value.set_text(f'{usage.percent:.1f}%')
                metric.detail.set_text(f'{usage.used / 2**30:.1f} / {usage.total / 2**30:.1f} GiB')
                metric.note.set_text(f'{usage.available / 2**30:.1f} GiB available')
                metric.meter.update([usage.percent], f'{metric.title.get_text()}: {usage.percent:.1f} percent used')
            metric.value.get_accessible().set_name(f'{metric.title.get_text()}: {metric.value.get_text()}, {metric.detail.get_text()}')
        self.memory.set_tooltip_text('Used RAM = total minus available memory. Reclaimable memory is included in available RAM.')
        self.storage.set_tooltip_text('Root filesystem (/), including your home folder on this system. Available space excludes filesystem-reserved blocks.')
        self.live.set_text('RETRYING' if reading.errors else 'LIVE')
        self.status.set_text(' · '.join(reading.errors.values()) + ' · retrying' if reading.errors else f'CPU / RAM · {SAMPLE_SECONDS}s     Storage · {STORAGE_SECONDS}s')
