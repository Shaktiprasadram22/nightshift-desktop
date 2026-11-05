"""Small native line icons, inheriting the button's RGB and focus colors."""
import math
import cairo
from gi.repository import Gtk


class ShortcutGlyph(Gtk.DrawingArea):
    def __init__(self, name, size=30):
        super().__init__()
        self.name = name
        self.set_pixel_size(size)
        self.connect('draw', self.draw_glyph)

    def set_pixel_size(self, size):
        self.set_size_request(size, size)

    def draw_glyph(self, _widget, cr):
        parent = self.get_parent() or self
        color = parent.get_style_context().get_color(parent.get_state_flags())
        cr.save()
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        width, height = self.get_allocated_width(), self.get_allocated_height()
        scale = min(width, height) / 24
        cr.translate((width-24*scale)/2, (height-24*scale)/2)
        cr.scale(scale, scale)
        cr.set_line_width(1.6)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

        def line(*points):
            cr.move_to(*points[0])
            for point in points[1:]: cr.line_to(*point)
            cr.stroke()

        def circle(x,y,r):
            cr.new_sub_path();cr.arc(x,y,r,0,2*math.pi);cr.stroke()

        def rounded(x,y,w,h,r):
            cr.new_sub_path()
            for cx,cy,a in ((x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)):
                cr.arc(cx,cy,r,a,a+math.pi/2)
            cr.close_path();cr.stroke()

        if self.name == 'google':
            cr.arc(12,12,8,math.pi/4,2*math.pi-math.pi/4);cr.stroke()
            cr.move_to(12,12);cr.line_to(20,12);cr.curve_to(20,14.5,19,16.5,17.65,17.65);cr.stroke()
        elif self.name == 'gmail':
            rounded(3.5,5.5,17,13,2)
            line((4.5,7),(12,13),(19.5,7))
            line((4.5,17),(9.5,13));line((19.5,17),(14.5,13))
        elif self.name == 'photos':
            cr.translate(12,12)
            for _ in range(4):
                cr.move_to(0,0);cr.line_to(0,-8)
                cr.curve_to(2.21,-8,4,-6.21,4,-4)
                cr.line_to(4,0);cr.close_path();cr.stroke()
                cr.rotate(math.pi/2)
        elif self.name == 'github':
            circle(7,5,2);circle(7,19,2);circle(17,6,2)
            line((7,7),(7,17))
            cr.move_to(17,8);cr.line_to(17,10);cr.curve_to(17,12.76,14.76,15,12,15);cr.line_to(7,15);cr.stroke()
        elif self.name == 'codex':
            line((7,6),(2,12),(7,18));line((17,6),(22,12),(17,18));line((14,4),(10,20))
        elif self.name == 'handy':
            rounded(9,3,6,12,3)
            cr.move_to(6,10);cr.line_to(6,12);cr.curve_to(6,15.31,8.69,18,12,18)
            cr.curve_to(15.31,18,18,15.31,18,12);cr.line_to(18,10);cr.stroke()
            line((12,18),(12,21));line((9,21),(15,21))
        elif self.name == 'theme':
            for x,y in ((5,9),(12,15),(19,8)):
                line((x,3),(x,y-2));line((x,y+2),(x,21));circle(x,y,2)
        cr.restore()
        return False
