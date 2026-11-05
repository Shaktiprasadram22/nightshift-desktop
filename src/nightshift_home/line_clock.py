"""A scalable monoline clock: rounded, single-stroke geometric numerals."""
import cairo
from gi.repository import Gtk,Atk
from theme_palette import paint,rgb


class LineClock(Gtk.DrawingArea):
    def __init__(self):
        super().__init__();self.value='00:00'
        self.set_size_request(180,76);self.set_hexpand(True);self.set_vexpand(True)
        self.get_accessible().set_role(Atk.Role.IMAGE)
        self.get_accessible().set_name('Local time 00:00')
        self.connect('draw',self.draw_time)

    def set_text(self,value):
        if value==self.value:return
        self.value=value;self.get_accessible().set_name('Local time '+value);self.queue_draw()

    def get_text(self):return self.value

    def draw_time(self,_widget,cr):
        width,height=self.get_allocated_width(),self.get_allocated_height()
        scale=min((width-12)/310,(height-10)/100)
        if scale<=0:return False
        cr.translate((width-310*scale)/2,(height-100*scale)/2);cr.scale(scale,scale)
        cr.set_source_rgb(*rgb(paint('#e0f7ff')));cr.set_line_width(1.35)
        cr.set_line_cap(cairo.LINE_CAP_ROUND);cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for index,char in enumerate(self.value):
            x=[0,74,148,162,236][index];cr.save();cr.translate(x,0)
            if char==':':
                for y in (35,67):cr.move_to(0,y);cr.line_to(0,y+2);cr.stroke()
            else:self.digit(cr,char)
            cr.restore()
        return False

    @staticmethod
    def digit(cr,char):
        # All glyphs share a 60×96 box, a uniform stroke, and rounded terminals.
        if char=='0':
            cr.move_to(16,2);cr.line_to(44,2);cr.curve_to(58,2,60,8,60,18);cr.line_to(60,80)
            cr.curve_to(60,92,56,98,44,98);cr.line_to(16,98);cr.curve_to(4,98,0,92,0,80)
            cr.line_to(0,18);cr.curve_to(0,8,2,2,16,2)
        elif char=='1':cr.move_to(18,17);cr.line_to(35,2);cr.line_to(35,98)
        elif char=='2':
            cr.move_to(0,18);cr.curve_to(0,6,6,2,18,2);cr.line_to(42,2);cr.curve_to(56,2,60,8,60,20)
            cr.line_to(60,32);cr.curve_to(60,41,55,46,45,51);cr.line_to(14,68);cr.curve_to(3,74,0,80,0,90);cr.line_to(0,98);cr.line_to(60,98)
        elif char=='3':
            cr.move_to(0,2);cr.line_to(42,2);cr.curve_to(58,2,60,10,60,24);cr.line_to(60,30);cr.curve_to(60,43,55,50,40,50);cr.line_to(23,50)
            cr.move_to(40,50);cr.curve_to(55,50,60,57,60,70);cr.line_to(60,76);cr.curve_to(60,91,55,98,42,98);cr.line_to(0,98)
        elif char=='4':
            cr.move_to(4,2);cr.line_to(0,60);cr.line_to(60,60);cr.move_to(48,2);cr.line_to(48,98)
        elif char=='5':
            cr.move_to(60,2);cr.line_to(0,2);cr.line_to(0,49);cr.line_to(42,49);cr.curve_to(56,49,60,56,60,69)
            cr.line_to(60,78);cr.curve_to(60,92,54,98,42,98);cr.line_to(0,98)
        elif char=='6':
            cr.move_to(58,2);cr.line_to(20,2);cr.curve_to(5,2,0,9,0,23);cr.line_to(0,78);cr.curve_to(0,93,6,98,20,98)
            cr.line_to(40,98);cr.curve_to(54,98,60,93,60,78);cr.line_to(60,68);cr.curve_to(60,54,54,49,40,49);cr.line_to(0,49)
        elif char=='7':cr.move_to(0,2);cr.line_to(60,2);cr.line_to(21,98)
        elif char=='8':
            cr.move_to(17,50);cr.curve_to(4,50,0,42,0,28);cr.line_to(0,22);cr.curve_to(0,7,5,2,20,2)
            cr.line_to(40,2);cr.curve_to(55,2,60,7,60,22);cr.line_to(60,28);cr.curve_to(60,42,56,50,43,50);cr.close_path()
            cr.move_to(17,50);cr.curve_to(4,50,0,58,0,72);cr.line_to(0,78);cr.curve_to(0,93,5,98,20,98)
            cr.line_to(40,98);cr.curve_to(55,98,60,93,60,78);cr.line_to(60,72);cr.curve_to(60,58,56,50,43,50)
        elif char=='9':
            cr.move_to(2,98);cr.line_to(40,98);cr.curve_to(55,98,60,91,60,77);cr.line_to(60,22);cr.curve_to(60,7,54,2,40,2)
            cr.line_to(20,2);cr.curve_to(6,2,0,7,0,22);cr.line_to(0,32);cr.curve_to(0,46,6,51,20,51);cr.line_to(60,51)
        cr.stroke()
