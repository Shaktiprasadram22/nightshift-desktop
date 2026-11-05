#!/usr/bin/env python3
"""Render actual GTK widgets offscreen using only synthetic, offline data.

Run under a private D-Bus session and an X display (Xvfb works). No desktop
windows are shown and no real account, media player, or session is queried.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT / 'docs/images/desktop.png')
args = parser.parse_args()
profile = tempfile.TemporaryDirectory(prefix='nightshift-demo-')
os.environ['NIGHTSHIFT_HOME'] = profile.name
os.environ['GSETTINGS_BACKEND'] = 'memory'
os.environ['GIO_USE_VFS'] = 'local'
os.environ['GTK_THEME'] = 'Adwaita:dark'
sys.path.insert(0, str(ROOT / 'src/nightshift_home'))
config = Path(profile.name) / '.config/nightshift-home'
config.mkdir(parents=True)
(config / 'sites.json').write_text(json.dumps({'account_id': '0'*32, 'hosts': ['example.com', 'example.net', 'example.org', 'example.test']}))
(config / 'notes.json').write_text(json.dumps({'text': 'Make room for good ideas.\n\nBuild something useful.\nKeep the desktop quiet.\nLeave a little space to think.'}))
(config / 'todos.json').write_text(json.dumps({'items': [
    {'id': '1', 'text': 'Sketch the next idea', 'done': True},
    {'id': '2', 'text': 'Build a small prototype', 'done': False},
    {'id': '3', 'text': 'Share what you learned', 'done': False}]}))
from home import Home, Gtk, Gdk, GLib, cairo, style
from theme_palette import PRESETS, recolor, set_live
from aurora_art import draw
from system_stats import Usage, Snapshot

Gtk.init([])
Gtk.Settings.get_default().set_property('gtk-theme-name', 'Adwaita')
Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
Gtk.Settings.get_default().set_property('gtk-enable-animations', False)
palette = PRESETS['Aurora glass']
set_live(palette)
provider = Gtk.CssProvider()
provider.load_from_data(recolor((ROOT / 'src/nightshift_home/style.css').read_text(), palette).encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
home = Home()
tiles = []


def tile(name, widget, rect):
    x, y, width, height = rect
    window = Gtk.OffscreenWindow()
    style(window, 'nightshift-widget', name + '-window')
    window.set_app_paintable(True)
    window.set_default_size(width, height)
    window.set_size_request(width, height)
    window.add(widget)
    window.show_all()
    tiles.append((window, x, y, width, height))
    return widget


tile('clock', home.build_clock(), (1431, 129, 440, 175))
home.clock_date.set_text('THURSDAY, 5 NOVEMBER')
home.clock_time.set_text('22:48')
home.clock_zone.set_text('A little space to focus')
tile('notes', home.build_notes(), (140, 130, 360, 260))
tile('todo', home.build_todo(), (142, 424, 360, 340))
ai = tile('ai-feed', home.build_ai(), (664, 113, 624, 320))
ai.select('learn')
system = tile('system', home.build_system(), (664, 465, 624, 230))
system.set_geometry(624, 230)
system.update(Snapshot(5.9, Usage(16*2**30, 6*2**30, 10*2**30), Usage(512*2**30, 184*2**30, 328*2**30), {}))
system.live.set_text('DEMO')
system.status.set_text('Sample readings · CPU / RAM / storage')
cf = tile('cloudflare', home.build_cloudflare(), (1495, 354, 356, 412))
for i, (host, fields) in enumerate(cf.fields.items()):
    fields['requests'].set_text(['8.56k', '3.07k', '2.26k', '916'][i])
    fields['detail'].set_text(['Cache 42% · 5xx 0', 'Cache 70% · 5xx 0', 'Cache 18% · 5xx 0', 'Cache 52% · 5xx 0'][i])
    fields['health'].set_text('● Up · demo')
    fields['chart'].update([4, 7, 5, 8, 6, 10, 5, 7, 21, 6, 7, 9, 5, 7, 32, 8, 5, 9, 12, 7])
cf.status.set_text('Sample data · 24-hour host traffic')
music = tile('music', home.build_music(), (731, 734, 502, 195))
music.title.set_text('Midnight coding session')
music.artist.set_text('Your soundtrack, your space')
music.status.set_text('Demo · connect your browser to play')
for name, x, y in [('gmail',1517,808),('codex',1604,808),('photos',1687,808),('github',1771,808),('theme',145,799),('handy',255,799)]:
    tile('icon-'+name, home.build_app_icon(name), (x,y,84,106))
tile('shortcuts', home.build_shortcuts(), (1532,927,314,73))

# Let GTK finish allocations and text layout without registering desktop windows.
deadline = time.monotonic() + .5
while time.monotonic() < deadline:
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    time.sleep(.01)
surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 1920, 1080)
context = cairo.Context(surface)
draw(context, 1920, 1080, palette)
for window, x, y, width, height in tiles:
    window.check_resize()
    actual = window.get_size()
    if actual.width > width + 2 or actual.height > height + 2:
        raise RuntimeError(f'Widget does not fit its layout: {actual}, expected {width}×{height}')
    layer = cairo.ImageSurface(cairo.FORMAT_ARGB32, actual.width, actual.height)
    window.draw(cairo.Context(layer))
    context.set_source_surface(layer, x, y)
    context.paint()
context.set_source_rgba(.75, .85, .92, .7)
context.select_font_face('sans-serif')
context.set_font_size(12)
context.move_to(142, 1020)
context.show_text('NIGHTSHIFT DESKTOP   /   SAMPLE DATA')
args.output.parent.mkdir(parents=True, exist_ok=True)
surface.write_to_png(str(args.output))
for window, *_ in tiles:
    window.destroy()
profile.cleanup()
print('Rendered offline GTK preview:', args.output)
