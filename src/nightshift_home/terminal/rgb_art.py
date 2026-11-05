"""Original static neon artwork, rendered once rather than by a live wallpaper."""
from pathlib import Path
import cairo
import colorsys
import math
import random

def rgb(hexcode):
    return tuple(int(hexcode[i:i + 2], 16) / 255 for i in (1, 3, 5))

def wallpaper(path):
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 3840, 2160)
    c = cairo.Context(surface); c.scale(2, 2)
    bg = cairo.LinearGradient(0, 0, 1300, 1080)
    for pos, color in [(0, '#050810'), (.55, '#0a1022'), (1, '#100b25')]:
        bg.add_color_stop_rgb(pos, *rgb(color))
    c.set_source(bg); c.paint()
    for x, y, radius, color, alpha in [(1180, 410, 570, '#284dbe', .19), (1550, 565, 570, '#b728a4', .13), (620, 760, 600, '#059bbc', .10)]:
        glow = cairo.RadialGradient(x, y, 0, x, y, radius)
        glow.add_color_stop_rgba(0, *rgb(color), alpha)
        glow.add_color_stop_rgba(1, *rgb(color), 0)
        c.set_source(glow); c.paint()

    random.seed(47)
    for _ in range(110):
        x, y = random.uniform(40, 1880), random.uniform(70, 720)
        c.arc(x, y, random.uniform(.35, .85), 0, math.tau)
        c.set_source_rgba(.68, .8, 1, random.uniform(.12, .5)); c.fill()

    # Segmented spectral orbit, placed away from the left-hand workspace.
    cx, cy, radius = 1280, 423, 234
    orbit = cairo.LinearGradient(cx - radius, cy + radius, cx + radius, cy - radius)
    for pos, color in [(0, '#41e5ee'), (.35, '#6b8eff'), (.68, '#b277ff'), (1, '#ff5bc8')]:
        orbit.add_color_stop_rgb(pos, *rgb(color))
    for width, opacity in [(44, .012), (22, .026), (10, .07), (3, .55), (1, .95)]:
        c.push_group()
        c.arc(cx, cy, radius, -.92, 2.38)
        c.arc(cx, cy, radius, 2.47, math.tau - 1.03)
        c.set_source(orbit); c.set_line_width(width); c.stroke()
        c.pop_group_to_source(); c.paint_with_alpha(opacity)
    c.arc(cx, cy, radius + 12, .13, 1.58)
    c.set_source_rgba(.80, .39, .92, .26); c.set_line_width(.7); c.stroke()
    c.arc(cx, cy, radius - 13, 3.2, 4.22)
    c.set_source_rgba(.30, .85, 1, .26); c.stroke()

    # Crisp three-dimensional monolith with two illuminated faces.
    def poly(points, fill):
        c.move_to(*points[0])
        for p in points[1:]: c.line_to(*p)
        c.close_path()
        if isinstance(fill, str): c.set_source_rgb(*rgb(fill))
        else: c.set_source(fill)
        c.fill()
    points = [(970, 572), (1176, 350), (1392, 575), (1186, 798)]
    left = cairo.LinearGradient(970, 572, 1186, 798)
    left.add_color_stop_rgb(0, *rgb('#154966')); left.add_color_stop_rgb(1, *rgb('#0a152d'))
    right = cairo.LinearGradient(1176, 350, 1392, 575)
    right.add_color_stop_rgb(0, *rgb('#38274f')); right.add_color_stop_rgb(1, *rgb('#14132c'))
    poly([points[0], points[1], (1182, 575), points[3]], left)
    poly([points[1], points[2], points[3], (1182, 575)], right)
    poly([points[0], (1182, 575), points[3]], '#0b223b')
    edge = cairo.LinearGradient(970, 0, 1392, 0)
    edge.add_color_stop_rgb(0, *rgb('#4fe8f2')); edge.add_color_stop_rgb(.5, *rgb('#8495ff')); edge.add_color_stop_rgb(1, *rgb('#f776d8'))
    for width, alpha in [(17, .017), (7, .05), (2, .7), (.75, 1)]:
        c.push_group(); c.move_to(*points[0])
        for p in points[1:] + points[:1]: c.line_to(*p)
        c.move_to(*points[1]); c.line_to(1182, 575); c.line_to(*points[3])
        c.set_source(edge); c.set_line_width(width); c.stroke()
        c.pop_group_to_source(); c.paint_with_alpha(alpha)
    for i in range(1, 14):
        t = i / 14
        x, y = 970 + 206 * t, 572 - 222 * t
        c.move_to(x, y); c.line_to(1182 + 4 * (1 - t), 575 + 223 * (1 - t))
        c.set_source_rgba(.35, .78, .98, .055); c.set_line_width(.6); c.stroke()

    # Perspective ground: sparse illuminated circuits with plenty of dark space.
    horizon = 840
    floor = cairo.LinearGradient(0, horizon, 0, 1080)
    floor.add_color_stop_rgba(0, .01, .03, .08, 0)
    floor.add_color_stop_rgba(1, .015, .025, .055, .93)
    c.rectangle(0, horizon, 1920, 240); c.set_source(floor); c.fill()
    for endpoint in range(-1800, 3701, 260):
        c.move_to(1180 + (endpoint - 1180) * .12, horizon)
        c.line_to(endpoint, 1080)
        c.set_source_rgba(.26, .51, .77, .09); c.set_line_width(.7); c.stroke()
    for offset in [4, 11, 22, 39, 64, 102, 157, 235]:
        c.move_to(0, horizon + offset); c.line_to(1920, horizon + offset)
        c.set_source_rgba(.30, .44, .73, .095); c.set_line_width(.7); c.stroke()
    for points, color in [([(0, 1045), (392, 1045), (588, 941), (925, 941), (1122, 839)], '#3bdff2'), ([(1920, 1014), (1628, 1014), (1487, 936), (1300, 936), (1220, 839)], '#e96ddd')]:
        for width, alpha in [(18, .015), (7, .035), (1.3, .65)]:
            c.move_to(*points[0])
            for point in points[1:]: c.line_to(*point)
            c.set_source_rgba(*rgb(color), alpha); c.set_line_width(width); c.stroke()
    # Ground contact reflection, baked into the image.
    c.save(); c.translate(1184, 835); c.scale(150, 10)
    halo = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    halo.add_color_stop_rgba(0, .47, .55, 1, .22); halo.add_color_stop_rgba(1, .47, .55, 1, 0)
    c.arc(0, 0, 1, 0, math.tau); c.set_source(halo); c.fill(); c.restore()
    surface.write_to_png(str(path))

def chrome_assets(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, width, height, radius in [('rgb-panel.svg', 1900, 36, 14), ('rgb-dock.svg', 400, 74, 23), ('rgb-dock-vertical.svg', 74, 400, 23)]:
        direction = 'x1="0" y1="0" x2="0" y2="1"' if height > width else ''
        edge = f'M {width - 1.2} {radius + 4} V {height - radius - 4}' if height > width else f'M {radius + 4} {height - 1.2} H {width - radius - 4}'
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<defs><linearGradient id="surface" {direction}><stop stop-color="#071725"/><stop offset="0.5" stop-color="#10182d"/><stop offset="1" stop-color="#201229"/></linearGradient><linearGradient id="rgb" {direction}><stop stop-color="#45e3ee"/><stop offset="0.35" stop-color="#6c9cff"/><stop offset="0.7" stop-color="#b184ff"/><stop offset="1" stop-color="#ed6acb"/></linearGradient></defs>
<rect x="0.6" y="0.6" width="{width - 1.2}" height="{height - 1.2}" rx="{radius}" fill="url(#surface)" fill-opacity="0.96" stroke="url(#rgb)" stroke-opacity="0.62" stroke-width="1.2"/>
<path d="{edge}" fill="none" stroke="url(#rgb)" stroke-width="1.5" stroke-opacity="0.8"/>
</svg>'''
        (directory / name).write_text(svg)

if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    wallpaper(base / 'midnight-rgb-4k.png')
    chrome_assets(Path('rgb-assets'))
