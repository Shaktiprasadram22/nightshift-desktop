"""A transparent, scalable name with the desktop's existing arrange controls."""
import cairo
import gi
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Pango, PangoCairo, Atk
from theme_palette import paint, rgb


class NameWidget(Gtk.Button):
    def __init__(self, value, arrange):
        super().__init__()
        self.get_style_context().add_class('name-widget')
        self.drawing = Gtk.DrawingArea()
        self.drawing.set_size_request(1, 1)
        self.drawing.get_accessible().set_role(Atk.Role.REDUNDANT_OBJECT)
        self.drawing.connect('draw', self.draw_name)
        self.add(self.drawing)
        self.connect('clicked', lambda *_: arrange())
        self.set_text(value)

    def set_text(self, value):
        self.value = value or 'Your name'
        self.get_accessible().set_name('Move and resize ' + self.value)
        self.set_tooltip_text(self.value + '\nClick to move or resize. Change the text in Home settings → Display name.')
        self.drawing.queue_draw()

    def draw_name(self, widget, cr):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        parent = self.get_parent()
        editing = parent is not None and parent.get_style_context().has_class('widget-editing')
        left, right, top, bottom = (14, 42, 32, 8) if editing else (14, 14, 12, 12)
        available_width, available_height = max(1, width - left - right), max(1, height - top - bottom)
        layout = widget.create_pango_layout(self.value)
        font = Pango.FontDescription()
        font.set_family('Michroma, Inter, Noto Sans')
        font.set_absolute_size(100 * Pango.SCALE)
        layout.set_font_description(font)
        layout.set_single_paragraph_mode(True)
        attributes = Pango.AttrList()
        attributes.insert(Pango.attr_letter_spacing_new(5 * Pango.SCALE))
        layout.set_attributes(attributes)
        ink, _ = layout.get_pixel_extents()
        if ink.width <= 0 or ink.height <= 0:
            return False
        scale = min(available_width / ink.width, available_height / ink.height)
        # Long names keep readable lettering instead of shrinking indefinitely.
        if scale < .14:
            scale = .14
            layout.set_width(int(available_width / scale * Pango.SCALE))
            layout.set_ellipsize(Pango.EllipsizeMode.END)
            ink, _ = layout.get_pixel_extents()
        cr.save()
        cr.translate(left + (available_width - ink.width * scale) / 2 - ink.x * scale,
                     top + (available_height - ink.height * scale) / 2 - ink.y * scale)
        cr.scale(scale, scale)
        cr.set_source_rgb(*rgb(paint('#8ee7f6')))
        cr.set_line_width(1.25 / scale)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        PangoCairo.layout_path(cr, layout)
        cr.stroke()
        cr.restore()
        return False
