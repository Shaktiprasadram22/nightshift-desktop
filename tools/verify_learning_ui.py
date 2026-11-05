#!/usr/bin/env python3
"""Offline GTK interaction/size checks; never uses the live desktop profile."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
profile=tempfile.TemporaryDirectory(prefix='nightshift-learning-ui-')
os.environ.update(NIGHTSHIFT_HOME=profile.name,GSETTINGS_BACKEND='memory',GIO_USE_VFS='local')
sys.path.insert(0,str(ROOT/'src/nightshift_home'))
from home import Home,Gtk,Gdk,cairo,style
from theme_palette import PRESETS,recolor,set_live
from aurora_art import draw
import ai_feed

Gtk.init([])
Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',True)
Gtk.Settings.get_default().set_property('gtk-enable-animations',False)
palette=PRESETS['Aurora glass'];set_live(palette)
provider=Gtk.CssProvider();provider.load_from_data(recolor((ROOT/'src/nightshift_home/style.css').read_text(),palette).encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)

def settle():
    deadline=time.monotonic()+.25
    while time.monotonic()<deadline:
        for _ in range(50):
            if not Gtk.events_pending():break
            Gtk.main_iteration_do(False)
        time.sleep(.005)

def window_for(widget,width,height,name):
    window=Gtk.OffscreenWindow();style(window,'nightshift-widget',name+'-window')
    window.set_app_paintable(True);window.set_size_request(width,height)
    window.add(widget);window.show_all();return window

home=Home();home.build_notes();home.build_todo()
notes,todo=home.notes_widget,home.todo_widget
notes.buffer.set_text('Existing note with unsaved typing.\n  Keep spacing  ')
original=todo.store.add('Keep this existing task');todo.render()
todo.rows[original]['stack'].set_visible_child_name('edit')
todo.rows[original]['edit'].set_text('My unfinished task edit')
todo.entry.set_text('Unsubmitted new task')
panel=home.build_ai();window=window_for(panel,624,320,'ai-feed');settle()
assert panel.cards
item=panel.cards[0]['item']
panel.cards[0]['notes'].clicked()
saved=json.loads(notes.store.path.read_text())['text']
assert saved.startswith('Existing note with unsaved typing.\n  Keep spacing  ')
assert item['url'] in saved and notes.buffer.get_text(notes.buffer.get_start_iter(),notes.buffer.get_end_iter(),True)==saved
assert not home.save_learning(item,'notes')
panel.cards[0]['todo'].clicked()
assert len(todo.store.items)==2 and todo.store.items[-1]['source_url']==item['url']
assert todo.rows[original]['edit'].get_text()=='My unfinished task edit'
assert todo.rows[original]['stack'].get_visible_child_name()=='edit'
assert todo.entry.get_text()=='Unsubmitted new task'
assert not home.save_learning(item,'todo')
# Saving never locks either button, including after refresh/filter re-rendering.
for destination, label in [('notes','Notes'),('todo','To-do')]:
    button=panel.cards[0][destination]
    assert button.get_sensitive() and button.get_label()==label
    button.clicked()
    assert panel.notice.startswith('Already in ')
assert json.loads(notes.store.path.read_text())['text']==saved
assert len(todo.store.items)==2
panel.render()
assert all(panel.cards[0][key].get_sensitive() for key in ('notes','todo'))
# Removing an item allows it to be saved again in the same app session.
notes.buffer.set_text('Keep this note after removing the learning entry.')
panel.cards[0]['notes'].clicked()
saved=json.loads(notes.store.path.read_text())['text']
assert saved.startswith('Keep this note after removing the learning entry.') and item['url'] in saved
assert panel.notice.startswith('Added to Notes')
todo.store.remove(todo.store.items[-1]['id'])
panel.cards[0]['todo'].clicked()
assert len(todo.store.items)==2 and todo.store.items[-1]['source_url']==item['url']
assert panel.notice.startswith('Added to To-do')
# Failed append must not lose the user's current in-memory buffer.
notes.buffer.set_text(saved+'\nMore unsaved typing')
before=notes.buffer.get_text(notes.buffer.get_start_iter(),notes.buffer.get_end_iter(),True)
with patch.object(notes.store,'save',side_effect=OSError('disk full')):
    try:home.save_learning(ai_feed.GUIDES[1],'notes')
    except OSError:pass
    else:raise AssertionError('Expected save failure')
assert notes.buffer.get_text(notes.buffer.get_start_iter(),notes.buffer.get_end_iter(),True)==before
notes.flush()
panel.search.set_text('cost');settle();assert panel.cards
panel.search.set_text('caching');settle();assert panel.cards
panel.search.set_text('cache');settle();assert panel.cards
panel.search.set_text('not-a-real-topic-xyz');settle();assert not panel.cards
opened=[];home.open_url=lambda url:opened.append(url)
panel.web_button.clicked();assert opened[-1].startswith('https://www.google.com/search?')
google=home.build_app_icon('google');home.app_buttons['google'].clicked()
assert opened[-1]=='https://www.google.com/'
assert google.get_accessible() is not None
panel.search.set_text('');panel.notice='';panel.select('cost');settle()
output=ROOT/'artifacts/learning-ui';output.mkdir(parents=True,exist_ok=True)
for width in (624,320):
    window.set_size_request(width,320);window.resize(width,320);settle()
    size=window.get_size();assert size.width==width and size.height==320,(width,size)
    assert panel.search.get_allocated_width()>=120
    for key in ('todo','notes'):
        button=panel.cards[0][key]
        pos=button.translate_coordinates(panel,0,0)
        assert pos is not None and pos[0]>=0 and pos[0]+button.get_allocated_width()<=width
        assert pos[1]+button.get_allocated_height()<=320,(width,key,pos,button.get_allocation())
    surface=cairo.ImageSurface(cairo.FORMAT_RGB24,width,320);context=cairo.Context(surface)
    draw(context,width,320,palette)
    layer=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,320);window.draw(cairo.Context(layer))
    context.set_source_surface(layer,0,0);context.paint()
    surface.write_to_png(str(output/f'learning-{width}.png'))
window.destroy();notes.destroy();todo.destroy();google.destroy();profile.cleanup()
print('GTK checks passed: reusable save buttons, duplicate prevention, re-save after deletion, notes and pending task edits preserved, search/web/Google actions work, 624×320 and 320×320 fit.')
