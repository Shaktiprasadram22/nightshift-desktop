"""Brief interaction-only motion; honor the system and the app's reduced-motion setting."""
from gi.repository import Gtk


def allowed(reduced=False):
    settings = Gtk.Settings.get_default()
    return not reduced and settings is not None and settings.get_property('gtk-enable-animations')


def fade_in(window, reduced=False, duration=160):
    if not allowed(reduced):
        window.set_opacity(1)
        return
    window.set_opacity(.08)
    started = [None]

    def tick(widget, clock):
        if not widget.get_mapped():
            widget.set_opacity(1)
            return False
        now = clock.get_frame_time()
        if started[0] is None:
            started[0] = now
        fraction = min(1, (now - started[0]) / (duration * 1000))
        widget.set_opacity(.08 + .92 * (1 - (1 - fraction) ** 3))
        return fraction < 1

    window.add_tick_callback(tick)
