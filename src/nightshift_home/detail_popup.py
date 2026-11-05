"""Native X11 detail popup, independent of the small desktop icon window."""
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib
from motion import fade_in


def popup_position(anchor, size, workarea, gap=12, margin=12, placement='below'):
    """Prefer below the icon; flip above and clamp to this monitor's workarea."""
    ax, ay, aw, ah = anchor
    width, height = size
    mx, my, mw, mh = workarea
    x = round(ax + aw / 2 - width / 2)
    y = ay + ah + gap
    if placement == 'beside' and ax + aw + gap * 2 + width <= mx + mw - margin:
        x, y = ax + aw + gap * 2, ay
    elif placement == 'beside' and ax - width - gap * 2 >= mx + margin:
        x, y = ax - width - gap * 2, ay
    elif y + height > my + mh - margin:
        y = ay - height - gap
    x = max(mx + margin, min(x, mx + mw - width - margin))
    y = max(my + margin, min(y, my + mh - height - margin))
    return int(x), int(y)


class DetailPopup(Gtk.Window):
    def __init__(self, title, dismiss, reduced_motion=False):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.dismiss = dismiss
        self.reduced_motion = reduced_motion
        self.placement = 'below'
        self.seat = None
        self.grab_status = 'not-open'
        self._closing = False
        self._gtk_grabbed = False
        self.anchor_rect = None
        self.workarea = None
        self.set_title(title)
        self.set_wmclass('nightshift-detail', 'gjs')
        self.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        context = self.get_style_context()
        context.add_class('nightshift-widget')
        context.add_class('detail-popup')
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.FOCUS_CHANGE_MASK |
                        Gdk.EventMask.TOUCH_MASK)
        self.connect('button-press-event', self._button_press)
        self.connect('touch-event', self._touch)
        self.connect('key-press-event', self._key_press)
        self.connect('focus-out-event', self._focus_out)
        self.connect('grab-broken-event', self._grab_broken)
        self.connect('delete-event', lambda *_: self._dismiss())
        self.connect('destroy', lambda *_: self.release_input())
        self.connect('map-event', self._mapped)

    def open_at(self, anchor, placement='below'):
        self.placement = placement
        toplevel = anchor.get_toplevel()
        translated = anchor.translate_coordinates(toplevel, 0, 0)
        # PyGObject may omit the boolean return annotation for this method.
        dx, dy = translated[-2:]
        tx, ty = toplevel.get_position()
        # Leave the icon label and the small footer controls unobscured.
        self.anchor_rect = (tx + dx, ty + dy, anchor.get_allocated_width(),
                            max(anchor.get_allocated_height(), toplevel.get_allocated_height() - dy))
        monitor = self.get_display().get_monitor_at_point(tx + dx, ty + dy)
        area = monitor.get_workarea()
        self.workarea = (area.x, area.y, area.width, area.height)
        width, height = self.fit_content(area.width, area.height)
        self.set_size_request(width, height)
        self.resize(width, height)
        self.move(*popup_position(self.anchor_rect, (width, height), self.workarea, placement=placement))
        self.show()
        fade_in(self, self.reduced_motion)
        # Check the realized size too; font scaling can change the request.
        GLib.idle_add(self._place_realized)

    def fit_content(self, available_width, available_height):
        content = self.get_child()
        content.show()
        width = min(max(400, content.get_preferred_width().minimum_width), available_width - 24)
        content.set_size_request(width, -1)
        natural = content.get_preferred_height_for_width(width).natural_height
        height = min(natural, available_height - 24)
        if natural > height:
            # Large accessibility text stays reachable instead of extending off screen.
            self.remove(content)
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scroller.set_size_request(width, height)
            scroller.add(content)
            self.add(scroller)
            scroller.show_all()
        return width, height

    def _place_realized(self):
        if not self._closing:
            self.move(*popup_position(self.anchor_rect, tuple(self.get_size()), self.workarea, placement=self.placement))
        return False

    def _mapped(self, *_):
        if self._closing:
            return False
        seat = self.get_display().get_default_seat()
        result = seat.grab(self.get_window(),
                           Gdk.SeatCapabilities.ALL_POINTING | Gdk.SeatCapabilities.KEYBOARD,
                           True, None, None, None, None)
        self.grab_status = result.value_nick
        if result != Gdk.GrabStatus.SUCCESS:
            GLib.idle_add(lambda: (self._dismiss(), False)[1])
            return False
        self.seat = seat
        self.grab_add()
        self._gtk_grabbed = True
        self.get_window().focus(Gdk.CURRENT_TIME)
        self.child_focus(Gtk.DirectionType.TAB_FORWARD)
        return False

    def _outside(self, x, y):
        px, py = self.get_position()
        width, height = self.get_size()
        return not (px <= x < px + width and py <= y < py + height)

    def _button_press(self, _widget, event):
        if self._outside(event.x_root, event.y_root):
            return self._dismiss()
        return False

    def _touch(self, _widget, event):
        if event.type == Gdk.EventType.TOUCH_BEGIN:
            _ok, x, y = event.get_root_coords()
            if self._outside(x, y):
                return self._dismiss()
        return False

    def _key_press(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            return self._dismiss()
        return False

    def _focus_out(self, *_):
        if self.seat:
            self._dismiss()
        return False

    def _grab_broken(self, *_):
        self._dismiss()
        return False

    def _dismiss(self):
        if not self._closing:
            self.dismiss(self)
        return True

    def release_input(self):
        self._closing = True
        if self._gtk_grabbed:
            self._gtk_grabbed = False
            self.grab_remove()
        if self.seat:
            seat, self.seat = self.seat, None
            seat.ungrab()
