"""A quiet static RGB backdrop with light kept at the edges."""
from pathlib import Path
import cairo,math

def render(path,palette=None):
    surface=cairo.ImageSurface(cairo.FORMAT_RGB24,3840,2160)
    draw(cairo.Context(surface),3840,2160,palette)
    surface.write_to_png(str(path))

def draw(cr,width,height,palette=None):
    from theme_palette import rgb,hex_rgb,color as map_color
    cr.save();cr.scale(width/1920,height/1080)
    def mapped(values):return rgb(map_color(hex_rgb(values),palette)) if palette else values
    glow_factor=palette['glow']/60 if palette else 1
    bg=cairo.LinearGradient(0,0,1920,1080)
    bg.add_color_stop_rgb(0,*mapped((.018,.030,.065)));bg.add_color_stop_rgb(.5,*mapped((.032,.044,.085)));bg.add_color_stop_rgb(1,*mapped((.046,.025,.080)))
    cr.set_source(bg);cr.paint()
    for x,y,radius,color,strength in [(1740,150,650,(.31,.14,.68),.16),(60,1000,750,(.01,.46,.61),.12),(1880,1000,450,(.7,.15,.45),.05)]:
        glow=cairo.RadialGradient(x,y,0,x,y,radius)
        glow.add_color_stop_rgba(0,*mapped(color),strength*glow_factor);glow.add_color_stop_rgba(1,*mapped(color),0)
        cr.set_source(glow);cr.paint()
    def ribbon(points,colors):
        gradient=cairo.LinearGradient(*points[0],*points[-1])
        for i,color in enumerate(colors):gradient.add_color_stop_rgb(i/(len(colors)-1),*mapped(color))
        for width,alpha in [(35,.008),(16,.018),(5,.07),(1,.58)]:
            cr.move_to(*points[0]);cr.curve_to(*points[1],*points[2],*points[3])
            cr.set_line_width(width);cr.set_source(gradient);cr.push_group();cr.stroke();cr.pop_group_to_source();cr.paint_with_alpha(min(1,alpha*glow_factor))
    for delta in [0,12,32]:
        ribbon([(1340+delta,-60),(1650+delta,85),(1820+delta,165),(2000+delta,530)],[(.34,.50,.95),(.65,.33,.82),(.84,.28,.59)])
    for delta in [0,13]:
        ribbon([(-70,510+delta),(80,845+delta),(250,995+delta),(665,1160+delta)],[(.13,.38,.55),(.25,.78,.85),(.34,.48,.81)])
    cr.restore()

if __name__=='__main__':render(Path(__file__).with_name('midnight-aurora-4k.png'))
