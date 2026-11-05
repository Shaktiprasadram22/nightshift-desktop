#!/usr/bin/python3
from paths import user_home
"""A small native desktop home screen for the user's GNOME X11 session."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time

os.environ['GTK_THEME'] = 'Midnight-Cyan'
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gtk, Gdk, GdkX11, Gio, GLib, Pango, Atk, GdkPixbuf
import cairo
from data import (HOME, BASE, CONFIG, CACHE, load_config, write_json, fetch_github,
                  load_cache, contribution_summary, read_sessions, codex_command,
                  write_autostart, age_label, valid_login)

from google_mail import fetch_inbox, MailError
from detail_popup import DetailPopup
from focus_timer import FocusTimer
from clock_panel import ClockPanel
from motion import allowed as motion_allowed
from cloudflare_panel import CloudflarePanel, site_detail
import cloudflare_data
import cloudflare_oauth
from layout import Layout,Handles,MINIMUM,clamp_rect,create_editor,find_free_rect
from line_clock import LineClock
from personal_widgets import NotesWidget,TodoWidget
from ai_panel import AIPanel
from system_panel import SystemPanel
from music_panel import MusicPanel
import ai_feed
import theme_palette

URLS = {'gmail': 'https://mail.google.com/', 'photos': 'https://photos.google.com/', 'google': 'https://www.google.com/'}

def style(widget, *classes):
    for name in classes: widget.get_style_context().add_class(name)
    return widget

def label(text='', cls=None, align=0):
    item = Gtk.Label(label=text, xalign=align)
    if cls: style(item, cls)
    return item

def box(vertical=True, spacing=0):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL, spacing=spacing)

def accessible(widget, text):
    widget.get_accessible().set_name(text)
    widget.set_tooltip_text(text)
    return widget

def icon(name, size=24):
    path = HOME / '.local/share/icons/Papirus/64x64/apps' / (name + '.svg')
    if name == 'codex': path = BASE / 'icons/codex.svg'
    if name == 'theme': path = BASE / 'icons/theme.svg'
    if path.exists():
        from gi.repository import GdkPixbuf
        return Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), size, size, True))
    return Gtk.Image.new_from_icon_name(name, Gtk.IconSize.BUTTON)

class Heatmap(Gtk.DrawingArea):
    COLORS = ['#1c2d42', '#235b70', '#268c9e', '#40baca', '#76e0ef']
    LEVELS = {'NONE': 0, 'FIRST_QUARTILE': 1, 'SECOND_QUARTILE': 2, 'THIRD_QUARTILE': 3, 'FOURTH_QUARTILE': 4}
    def __init__(self):
        super().__init__()
        self.days = {}; self.cells = []
        self.set_size_request(-1, 62)
        self.set_has_tooltip(True)
        self.connect('draw', self.draw_chart)
        self.connect('query-tooltip', self.tooltip)
        self.get_accessible().set_role(Atk.Role.IMAGE)
        self.get_accessible().set_name('GitHub contribution calendar, last 26 weeks. Loading.')

    def update_days(self, days):
        self.days = days
        total = sum(d['contributionCount'] for k,d in days.items() if k >= datetime.now(timezone.utc).date() - timedelta(weeks=26))
        self.get_accessible().set_name(f'GitHub calendar. {total} contributions in the last 26 weeks; current streak and yearly total are shown above.')
        self.queue_draw()

    def draw_chart(self, _widget, cr):
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=(today.weekday()+1)%7, weeks=25)
        width = self.get_allocated_width()
        step = min(12.0, (width-18)/26)
        size = max(4.0, step-3)
        self.cells = []
        cr.select_font_face('sans-serif', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(8)
        cr.set_source_rgb(.60,.69,.79)
        for row, text in [(1,'M'),(3,'W'),(5,'F')]:
            cr.move_to(0, 6+row*8); cr.show_text(text)
        for week in range(26):
            for day in range(7):
                current = start + timedelta(weeks=week, days=day)
                item = self.days.get(current)
                level = self.LEVELS.get(item.get('contributionLevel','NONE'),0) if item else 0
                h = theme_palette.paint(self.COLORS[level])
                rgb = [int(h[i:i+2],16)/255 for i in (1,3,5)]
                cr.set_source_rgba(*rgb, .30 if current>today else 1)
                x,y = 18+week*step, day*8
                cr.rectangle(x,y,size,6);cr.fill()
                if current <= today: self.cells.append((x,y,size,6,current,item))
        return False

    def tooltip(self,_widget,x,y,keyboard,tooltip):
        if keyboard: return False
        for cx,cy,w,h,current,item in self.cells:
            if cx<=x<=cx+w and cy<=y<=cy+h:
                if not self.days: tooltip.set_text('Contribution data has not loaded yet.')
                else: tooltip.set_text(f"{current:%d %b %Y}: {item['contributionCount'] if item else 0} contributions")
                return True
        return False

class Home(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.nightshift.Home', flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        from layout_profiles import recover
        try: recover(CONFIG.parent)
        except (OSError,ValueError,KeyError,TypeError): pass  # Preserved for the layouts window to explain/retry.
        self.config = load_config()
        self.window = None; self.manager = None; self.windows = {}
        self.refresh_button=None
        self.detail_popover=None;self.detail_name=None;self.detail_content=None;self.app_buttons={}
        self.detail_host=None;self.detail_anchor=None;self.clock_panel=None;self.launcher_window=None
        self.focus_path=HOME/'.config/nightshift-home/focus.json'
        try:focus_saved=json.loads(self.focus_path.read_text())
        except (OSError,ValueError):focus_saved=None
        self.focus=FocusTimer(focus_saved);self.focus_source=0
        self.mail = None; self.mail_busy = False; self.mail_error = ''; self.mail_connect = True
        self.mail_attempt = 0; self.photos_busy = False; self.photo_index = 0; self.photo_stamp = None
        self.github = load_cache(self.config['github_username'])
        self.github_busy = False; self.github_error = ''; self.last_attempt = 0
        self.sessions = []; self.session_signature = None
        self.cloudflare=cloudflare_data.load_cache();self.cloudflare_busy=False;self.cloudflare_error=''
        self.cloudflare_attempt=0;self.cloudflare_connecting=False;self.cloudflare_cancel=threading.Event()
        self.cloudflare_dialog=None;self.cloudflare_url=None;self.cloudflare_generation=0
        self.layout=Layout();self.handles={};self.arranging=False;self.layout_editor=None
        self.notes_widget=None;self.todo_widget=None;self.ai_panel=None
        self.ai_data=ai_feed.load_cache();self.ai_busy=False;self.ai_errors={};self.ai_attempt=0
        self.theme_window=None;self.style_provider=None
        self.system_panel=None
        self.music_panel=None
        self.profiles_window=None;self.project_window=None
        self.held = False; self.testing = '--verify-ui' in sys.argv

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.style_provider=Gtk.CssProvider();self.reload_theme()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),self.style_provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        Gtk.Settings.get_default().connect('notify::gtk-enable-animations',lambda *_:self.apply_motion_preferences())

    def do_command_line(self, command):
        args = command.get_arguments()[1:]
        if '--quit' in args:
            return 0 if self.request_quit() else 1
        self.activate()
        if '--manage' in args: self.show_manager()
        if '--theme' in args:self.show_theme()
        if '--capture-theme' in args:
            self.show_theme();GLib.timeout_add(300,self.theme_window.capture)
        if '--reload-theme' in args:self.reload_theme()
        if '--photos' in args: self.connect_photos()
        if '--refresh' in args: self.refresh_all()
        if '--capture' in args: GLib.timeout_add(250,self.export_preview)
        if '--launcher' in args:self.show_launcher()
        if '--layouts' in args:self.show_profiles()
        if '--project' in args:self.show_project()
        if '--calendar' in args:self.toggle_clock()
        if '--arrange' in args:self.start_arrange()
        if '--lock-layout' in args:self.end_arrange()
        if '--cloudflare-connect' in args:self.connect_cloudflare()
        if '--cloudflare-restart' in args:self.connect_cloudflare(restart=True)
        if '--cloudflare-site' in args:
            index=args.index('--cloudflare-site')+1
            if index<len(args) and args[index] in self.cloudflare_panel.fields:
                self.show_cloudflare_site(args[index],self.cloudflare_panel.fields[args[index]]['button'])
        if '--workspace' in args:
            from workspaces import switch_workspace
            try:switch_workspace(int(args[args.index('--workspace')+1])-1)
            except (ValueError,IndexError,OSError,RuntimeError):return 1
        if '--detail' in args:
            index=args.index('--detail')+1
            if index<len(args) and args[index] in ('github','codex','gmail','photos'):self.toggle_detail(args[index],self.app_buttons[args[index]])
        if '--close-detail' in args:self.close_detail()
        return 0

    def do_activate(self):
        if self.window: return
        display=Gdk.Display.get_default()
        if not isinstance(display,GdkX11.X11Display):
            print('Nightshift Home desktop widgets require an X11 session.',file=sys.stderr)
            self.quit();return
        self.hold();self.held=True
        builders=[('clock',self.build_clock),('gmail',self.build_gmail),
                ('photos',self.build_photos),('github',self.build_github),
                ('codex',self.build_codex)]
        builders += [('icon-'+name,lambda n=name:self.build_app_icon(n)) for name in ('gmail','photos','github','codex','handy','theme','google')]
        builders += [('shortcuts',self.build_shortcuts),('cloudflare',self.build_cloudflare)]
        builders += [('notes',self.build_notes),('todo',self.build_todo),('ai-feed',self.build_ai),('system',self.build_system),('music',self.build_music)]
        for name,builder in builders:
            window=Gtk.ApplicationWindow(application=self,title='Nightshift · '+name.title())
            # Zorin excludes desktop hosts with this class from tiling/focus borders.
            window.set_wmclass('nightshift-'+name,'gjs')
            window.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            window.set_decorated(False);window.set_resizable(name in MINIMUM)
            window.set_skip_taskbar_hint(True);window.set_skip_pager_hint(True)
            window.set_keep_below(True);window.stick()
            window.set_focus_on_map(False);window.set_accept_focus(True)
            window.set_app_paintable(True)
            visual=window.get_screen().get_rgba_visual()
            if visual:window.set_visual(visual)
            style(window,'nightshift-widget',name+'-window')
            window.connect('draw',self.clear_background)
            content=builder()
            if name.startswith('icon-'):window.connect('size-allocate',content.scale_for_window)
            if name in MINIMUM:
                handles=Handles(self,name,window,content);self.handles[name]=handles;window.add(handles.overlay)
            else:window.add(content)
            self.windows[name]=window
            window.show_all()
            if name in self.handles:self.handles[name].set_editing(False)
        self.window=self.windows['clock']
        self.apply_layout()
        self.apply_motion_preferences()
        display.connect('monitor-added',lambda *_:self.apply_layout())
        display.connect('monitor-removed',lambda *_:self.apply_layout())
        self.clock_tick();self.tick();self.render_github();self.refresh_github();self.refresh_mail()
        self.sync_focus()
        self.render_cloudflare();self.refresh_cloudflare()
        self.ai_panel.update(self.ai_data);self.refresh_ai()
        GLib.timeout_add(300,lambda:self.rotate_photo(False) and False)
        GLib.timeout_add_seconds(30,self.tick)
        GLib.timeout_add_seconds(30,self.rotate_photo)
        GLib.timeout_add_seconds(cloudflare_data.REFRESH_SECONDS,self.cloudflare_tick)
        GLib.timeout_add_seconds(ai_feed.REFRESH_SECONDS,self.ai_tick)
        if self.testing: GLib.timeout_add(1500,self.verify_ui)

    def build_clock(self):
        clock=style(box(spacing=8),'clock-face')
        self.clock_date=label('','clock-date',.5)
        clock.pack_start(self.clock_date,False,False,0)
        self.clock_time=LineClock()
        clock.pack_start(self.clock_time,True,True,0)
        accent=style(box(False),'clock-accent');accent.set_size_request(54,2)
        accent.set_halign(Gtk.Align.CENTER);clock.pack_start(accent,False,False,0)
        self.clock_zone=label('','clock-zone',.5);clock.pack_start(self.clock_zone,False,False,0)
        self.clock_zone.set_ellipsize(Pango.EllipsizeMode.END);self.clock_zone.set_max_width_chars(1)
        self.clock_button=style(Gtk.Button(),'clock-button')
        self.clock_button.add(clock)
        accessible(self.clock_button,'Open calendar and focus timer')
        self.clock_button.connect('clicked',lambda *_:self.toggle_clock())
        return self.clock_button

    def build_app_icon(self,name):
        title={'gmail':'Gmail','photos':'Photos','github':'GitHub','codex':'Codex','handy':'Handy','theme':'Theme','google':'Google'}[name]
        column=box(spacing=9);column.set_valign(Gtk.Align.CENTER)
        from shortcut_glyphs import ShortcutGlyph
        image=ShortcutGlyph(name,30)
        image.get_accessible().set_role(Atk.Role.REDUNDANT_OBJECT)
        button=style(Gtk.Button(),'app-icon');button.set_halign(Gtk.Align.CENTER);button.add(image)
        if name in URLS:
            button.connect('clicked',lambda _b:self.open_url(URLS[name]));accessible(button,'Open '+title)
        elif name=='handy':
            button.connect('clicked',lambda *_:self.open_handy());accessible(button,'Open Handy · voice typing uses Ctrl + Alt + Space')
        elif name=='theme':
            button.connect('clicked',lambda *_:self.show_theme());accessible(button,'Open RGB Studio · adjust the desktop theme')
        else:
            button.connect('clicked',lambda b:self.toggle_detail(name,b));accessible(button,'Show '+title+' details')
        column.pack_start(button,False,False,0);column.pack_start(label(title,'app-label',.5),False,False,0)
        self.app_buttons[name]=button
        provider=Gtk.CssProvider();button.get_style_context().add_provider(provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+5)
        previous=[None]
        def scale(_widget,allocation):
            factor=max(.65,min(2.5,(allocation.width-12)/68,(allocation.height-26)/70))
            size=round(30*factor);padding=round(15*factor)
            if size==previous[0]:return
            previous[0]=size
            provider.load_from_data(f'button.app-icon {{ min-width:0; min-height:0; padding:{padding}px; border-radius:{round(19*factor)}px; }}'.encode())
            image.set_pixel_size(size)
        column.scale_for_window=scale
        return column

    def build_notes(self):
        self.notes_widget=NotesWidget(self);return self.notes_widget

    def build_todo(self):
        self.todo_widget=TodoWidget(self);return self.todo_widget

    def build_ai(self):
        self.ai_panel=AIPanel(self);return self.ai_panel

    def build_system(self):
        self.system_panel=SystemPanel(self);return self.system_panel

    def build_music(self):
        self.music_panel=MusicPanel(self);return self.music_panel

    def open_system_monitor(self):
        try:
            launcher=Gio.DesktopAppInfo.new('org.gnome.SystemMonitor.desktop') or Gio.DesktopAppInfo.new('gnome-system-monitor.desktop')
            if not launcher:raise OSError('System Monitor launcher missing')
            context=Gdk.Display.get_default().get_app_launch_context()
            context.unsetenv('GTK_THEME');context.unsetenv('FONTCONFIG_FILE')
            launcher.launch([],context)
        except (GLib.Error,OSError):self.show_message('System Monitor could not open. The desktop readings will keep updating.')

    def request_quit(self):
        if self.theme_window and self.theme_window.busy:
            self.show_message('Wait for the theme update to finish before closing.');return False
        if self.notes_widget and not self.notes_widget.flush():
            self.show_message('Your latest notes could not be saved. Use Save in Notes to retry before closing.');return False
        self.cloudflare_cancel.set()
        if self.arranging:self.end_arrange()
        self.quit();return True

    def reload_theme(self):
        state=theme_palette.load_state();palette=state['palette'] if state.get('applied_at') else None
        theme_palette.set_live(palette)
        source=(BASE/'style.css').read_text()
        if palette:source=theme_palette.recolor(source,palette)
        if self.style_provider:self.style_provider.load_from_data(source.encode())
        os.environ['GTK_THEME']=state.get('theme_name','Midnight-Cyan')
        Gtk.Settings.get_default().set_property('gtk-theme-name',os.environ['GTK_THEME'])
        for window in self.windows.values():window.queue_draw()

    def show_theme(self):
        self.close_detail()
        if self.theme_window:self.theme_window.present();return
        from theme_studio import ThemeStudio
        self.theme_window=ThemeStudio(self)
        self.theme_window.connect('destroy',lambda *_:setattr(self,'theme_window',None))
        self.theme_window.show_all();self.theme_window.present();self.apply_motion_preferences(self.theme_window)

    def do_shutdown(self):
        if self.notes_widget:self.notes_widget.flush()
        if self.system_panel:self.system_panel.stop()
        if self.music_panel:self.music_panel.player.stop()
        if hasattr(self,'cloudflare_panel'):self.cloudflare_panel.health.stop()
        Gtk.Application.do_shutdown(self)

    def open_handy(self):
        self.close_detail()
        try:
            launcher=Gio.DesktopAppInfo.new('handy.desktop')
            if not launcher:raise OSError('Handy launcher missing')
            context=Gdk.Display.get_default().get_app_launch_context()
            context.unsetenv('GTK_THEME');context.unsetenv('FONTCONFIG_FILE')
            launcher.launch([],context)
        except (GLib.Error,OSError):self.show_message('Handy could not open. Check its application launcher.')

    def ai_tick(self):
        self.refresh_ai();return True

    def save_learning(self,item,destination):
        if destination=='notes':return self.notes_widget.append_learning(item)
        if destination=='todo':return self.todo_widget.add_learning(item)
        raise ValueError('Choose Notes or To-do.')

    def refresh_ai(self,force=False):
        if self.ai_busy or not self.config['show_ai_feed']:return
        now=time.time()
        if not force and now-self.ai_attempt<ai_feed.REFRESH_SECONDS:return
        if not force and all(now-self.ai_data.get(key,{}).get('updated_at',0)<ai_feed.REFRESH_SECONDS for key in ai_feed.SOURCES):return
        self.ai_attempt=now;self.ai_busy=True;self.ai_panel.update(self.ai_data,self.ai_errors,True)
        previous=self.ai_data
        def work():
            value,errors=ai_feed.refresh(previous)
            try:ai_feed.save_cache(value)
            except OSError:
                for key in ai_feed.SOURCES:errors.setdefault(key,'Could not save this update for offline use.')
            GLib.idle_add(self.finish_ai,value,errors)
        threading.Thread(target=work,daemon=True,name='nightshift-ai-feed').start()

    def finish_ai(self,value,errors):
        self.ai_data=value;self.ai_errors=errors;self.ai_busy=False
        self.ai_panel.update(value,errors);return False

    def build_shortcuts(self):
        content=style(box(spacing=0),'launchpad');content.set_valign(Gtk.Align.CENTER)
        footer=box(False,9);footer.set_halign(Gtk.Align.CENTER)
        self.launcher_button=self.small_button('system-search-symbolic','Search projects, apps, and sessions · Super + K',self.show_launcher)
        footer.pack_start(self.launcher_button,False,False,0)
        self.profiles_button=self.small_button('view-grid-symbolic','Saved layouts · Coding, Focus, Chill',self.show_profiles)
        footer.pack_start(self.profiles_button,False,False,0)
        self.project_button=self.small_button('folder-symbolic','Project status · Git, editor and terminal',self.show_project)
        footer.pack_start(self.project_button,False,False,0)
        footer.pack_start(self.small_button('preferences-system-symbolic','Manage desktop widgets',self.show_manager),False,False,0)
        footer.pack_start(self.small_button('transform-move-symbolic','Arrange desktop widgets',self.start_arrange),False,False,0)
        content.pack_start(footer,False,False,0)
        return content

    def show_profiles(self):
        self.close_detail()
        if self.profiles_window:self.profiles_window.present();return
        from layout_profiles import create_window
        self.profiles_window=create_window(self)
        self.profiles_window.connect('destroy',lambda *_:setattr(self,'profiles_window',None))
        self.profiles_window.show_all();self.profiles_window.present();self.apply_motion_preferences(self.profiles_window)

    def show_project(self):
        self.close_detail()
        if self.project_window:self.project_window.present();self.project_window.load_status();return
        from project_panel import ProjectWindow
        self.project_window=ProjectWindow(self)
        self.project_window.connect('destroy',lambda *_:setattr(self,'project_window',None))
        self.project_window.show_all();self.project_window.present();self.apply_motion_preferences(self.project_window)

    def toggle_detail(self,name,anchor):
        same=self.detail_name==name
        self.close_detail()
        if same:return
        host=self.windows[name];content=host.get_child()
        host.remove(content)
        popover=DetailPopup(name.title()+' details',self.restore_detail,self.config['reduced_motion'])
        popover.add(content)
        self.detail_popover=popover;self.detail_name=name;self.detail_content=content
        self.detail_host=host;self.detail_anchor=anchor
        self.apply_motion_preferences(popover)
        content.show_all()
        self.mail_action.set_visible(self.mail_connect)
        self.mail_status.set_visible(bool(self.mail))
        self.photo_stack.show()
        from google_photos import selected_photos
        self.photo_next.set_visible(bool(selected_photos()))
        popover.open_at(anchor)
        GLib.timeout_add(300,self.capture_detail)
        if name=='gmail':self.refresh_mail()
        elif name=='github':self.refresh_github()
        elif name=='codex':self.refresh_sessions()
        elif name=='photos':self.rotate_photo(False)

    def restore_detail(self,popover):
        if popover is not self.detail_popover:return
        content=self.detail_content;host=self.detail_host;anchor=self.detail_anchor
        self.detail_popover=None;self.detail_name=None;self.detail_content=None
        self.detail_host=None;self.detail_anchor=None;self.clock_panel=None
        popover.release_input()
        content.get_parent().remove(content)
        if host:
            host.add(content);content.set_size_request(-1,-1)
        else:content.destroy()
        popover.destroy()
        if anchor and anchor.get_mapped():anchor.grab_focus()
        write_json(BASE/'popup-state.json',{'open':False})

    def close_detail(self):
        if self.detail_popover:self.restore_detail(self.detail_popover)

    def toggle_clock(self):
        same=self.detail_name=='calendar'
        self.close_detail()
        if same:return
        self.clock_panel=ClockPanel(self)
        popup=DetailPopup('Calendar & focus',self.restore_detail,self.config['reduced_motion'])
        popup.add(self.clock_panel)
        self.detail_popover=popup;self.detail_name='calendar';self.detail_content=self.clock_panel
        self.detail_host=None;self.detail_anchor=self.clock_button
        self.apply_motion_preferences(popup)
        self.clock_panel.show_all()
        popup.open_at(self.clock_button,placement='beside')
        GLib.timeout_add(300,self.capture_detail)

    def show_launcher(self):
        self.close_detail()
        if self.launcher_window is None:
            from launcher import Launcher
            self.launcher_window=Launcher(self)
        if self.launcher_window.get_visible():self.launcher_window.dismiss()
        else:self.launcher_window.open()

    def screen_geometry(self):
        display=Gdk.Display.get_default();monitor=display.get_primary_monitor() or display.get_monitor(0)
        return monitor.get_geometry()

    def widget_rect(self,name):
        window=self.windows[name];geo=self.screen_geometry();x,y=window.get_position();w,h=window.get_size()
        return [x-geo.x,y-geo.y,w,h]

    def place_widget(self,name,rect,save=False):
        geo=self.screen_geometry();rect=clamp_rect(rect,(geo.width,geo.height),MINIMUM[name])
        x,y,width,height=rect;window=self.windows[name]
        if name=='cloudflare':self.cloudflare_panel.set_placement('bottom' if width>=1100 else 'right')
        if name=='system':self.system_panel.set_geometry(width,height)
        if name.startswith('icon-'):
            allocation=Gdk.Rectangle();allocation.width=width;allocation.height=height
            window.get_child().get_child().scale_for_window(window,allocation)
        window.set_size_request(width,height);window.resize(width,height);window.move(geo.x+x,geo.y+y)
        # X11 can process a resize before its reduced minimum-size hints arrive.
        # Coalesce one follow-up after the current GTK frame, only while resizing.
        window._target_rect=tuple(rect)
        if getattr(window,'_resize_source',0):GLib.source_remove(window._resize_source)
        def settle_size():
            window._resize_source=0
            if window.get_realized() and getattr(window,'_target_rect',None)==tuple(rect):
                window.resize(width,height);window.move(geo.x+x,geo.y+y)
            return False
        window._resize_source=GLib.timeout_add(75,settle_size)
        if save:self.layout.save(name,rect,(geo.width,geo.height))
        if self.layout_editor:GLib.idle_add(lambda:(self.layout_editor.refresh_values() if self.layout_editor else None,False)[1])
        return rect

    def save_widget(self,name):
        geo=self.screen_geometry();self.layout.save(name,self.widget_rect(name),(geo.width,geo.height))
        if self.layout_editor:self.layout_editor.refresh_values()

    def select_layout_widget(self,name):
        if self.layout_editor:self.layout_editor.layout_picker.set_active_id(name)

    def start_arrange(self):
        self.close_detail()
        if self.layout_editor:self.layout_editor.present();return
        from workspaces import show_desktop
        try:self.layout_old_desktop=subprocess.check_output(['xprop','-root','_NET_SHOWING_DESKTOP'],text=True).strip().endswith('= 1')
        except (OSError,subprocess.SubprocessError):self.layout_old_desktop=True
        show_desktop(True)
        self.arranging=True
        for handle in self.handles.values():handle.set_editing(True)
        self.layout_editor=create_editor(self);self.layout_editor.show_all();self.layout_editor.present()

    def end_arrange(self):
        self.arranging=False
        for handle in self.handles.values():handle.set_editing(False)
        if self.layout_editor:
            window=self.layout_editor;self.layout_editor=None;window.destroy()
        from workspaces import show_desktop
        show_desktop(getattr(self,'layout_old_desktop',True))

    def reset_layout(self,key=None):
        self.layout.reset(key);self.apply_layout()
        if self.layout_editor:self.layout_editor.refresh_values()

    def undo_layout(self):
        self.layout.restore();self.apply_layout()
        if self.layout_editor:self.layout_editor.refresh_values()

    def build_cloudflare(self):
        self.cloudflare_panel=CloudflarePanel(self)
        return self.cloudflare_panel

    def show_cloudflare_site(self,name,anchor):
        same=self.detail_name=='cloudflare:'+name
        self.close_detail()
        if same:return
        content=site_detail(self,name)
        popup=DetailPopup(name+' · Cloudflare',self.restore_detail,self.config['reduced_motion'])
        popup.add(content)
        self.detail_popover=popup;self.detail_name='cloudflare:'+name;self.detail_content=content
        self.detail_host=None;self.detail_anchor=anchor
        self.apply_motion_preferences(popup);content.show_all()
        popup.open_at(anchor,placement='beside')
        GLib.timeout_add(300,self.capture_detail)

    def render_cloudflare(self):
        self.cloudflare_panel.update(self.cloudflare,self.cloudflare_error,
            cloudflare_oauth.connected(),self.cloudflare_busy,self.cloudflare_connecting)
        if self.cloudflare_dialog:self.cloudflare_dialog.refresh()

    def cloudflare_tick(self):
        self.refresh_cloudflare()
        self.render_cloudflare()
        return True

    def refresh_cloudflare(self,force=False):
        if self.cloudflare_busy or not self.config['show_cloudflare']:return
        if not cloudflare_oauth.connected():
            if force:self.connect_cloudflare()
            return
        if not force and time.time()-self.cloudflare_attempt<cloudflare_data.REFRESH_SECONDS-20:return
        self.cloudflare_busy=True;self.cloudflare_attempt=time.time();self.render_cloudflare()
        def work():
            try:value=cloudflare_data.fetch();error=''
            except Exception as exc:value=None;error=str(exc)
            GLib.idle_add(self.finish_cloudflare,value,error)
        threading.Thread(target=work,name='cloudflare-refresh',daemon=True).start()

    def finish_cloudflare(self,value,error):
        self.cloudflare_busy=False;self.cloudflare_error=error
        if value:self.cloudflare=value
        self.render_cloudflare()
        return False

    def connect_cloudflare(self,restart=False):
        if not cloudflare_data.SITES:
            self.show_message('Configure your account and hosts in ~/.config/nightshift-home/sites.json, then restart Nightshift. See the integration setup guide in the project.')
            return
        from cloudflare_connection import ConnectionWindow
        self.close_detail()
        if self.cloudflare_dialog:self.cloudflare_dialog.present()
        else:
            self.cloudflare_dialog=ConnectionWindow(self);self.cloudflare_dialog.show_all();self.cloudflare_dialog.refresh();self.cloudflare_dialog.present()
        if restart or (not self.cloudflare_connecting and not cloudflare_oauth.connected()):self.start_cloudflare_connection()

    def start_cloudflare_connection(self):
        self.cloudflare_cancel.set();self.cloudflare_cancel=threading.Event()
        cancelled=self.cloudflare_cancel;self.cloudflare_generation+=1;generation=self.cloudflare_generation
        self.close_detail();self.cloudflare_connecting=True;self.cloudflare_error=''
        self.cloudflare_url=None;self.render_cloudflare()
        def open_consent(url):
            def ready():
                if generation!=self.cloudflare_generation:return False
                self.cloudflare_url=url;self.render_cloudflare();self.open_cloudflare_consent();return False
            GLib.idle_add(ready)
        def work():
            try:cloudflare_oauth.authorize(open_consent,cancelled);error=''
            except Exception as exc:error=str(exc)
            GLib.idle_add(self.finish_cloudflare_connection,error,generation)
        threading.Thread(target=work,name='cloudflare-connect',daemon=True).start()

    def open_cloudflare_consent(self):
        if not self.cloudflare_url:return
        try:
            browser=shutil.which('google-chrome') or shutil.which('google-chrome-stable')
            if browser:subprocess.Popen([browser,'--new-window',self.cloudflare_url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            else:
                chrome=Gio.DesktopAppInfo.new('com.google.Chrome.desktop')
                if not chrome:raise OSError('Chrome is unavailable')
                context=Gio.AppLaunchContext()
                for name in ('FONTCONFIG_FILE','GTK_THEME','GTK_MODULES','GTK3_MODULES'):context.unsetenv(name)
                chrome.launch_uris([self.cloudflare_url],context)
        except (OSError,GLib.Error):self.open_url(self.cloudflare_url)

    def cancel_cloudflare_connection(self):
        self.cloudflare_cancel.set();self.cloudflare_generation+=1
        self.cloudflare_connecting=False;self.cloudflare_url=None;self.cloudflare_error='Sign-in cancelled. You can start again at any time.';self.render_cloudflare()

    def finish_cloudflare_connection(self,error,generation):
        if generation!=self.cloudflare_generation:return False
        self.cloudflare_connecting=False;self.cloudflare_error=error
        self.cloudflare_url=None
        self.render_cloudflare()
        if not error:self.refresh_cloudflare(True)
        return False

    def apply_motion_preferences(self,extra=None):
        reduced=not motion_allowed(self.config['reduced_motion'])
        windows=list(self.windows.values())+[self.manager,self.detail_popover,self.launcher_window,extra]
        for window in windows:
            if window:
                context=window.get_style_context()
                (context.add_class if reduced else context.remove_class)('reduce-motion')
        if hasattr(self,'photo_stack'):self.photo_stack.set_transition_duration(0 if reduced else 160)

    def choose_focus_duration(self,minutes):
        if self.focus.select(minutes):self.sync_focus(save=True)

    def toggle_focus(self):
        if self.focus.state=='running':self.focus.pause()
        else:self.focus.start()
        self.sync_focus(save=True)

    def reset_focus(self):
        self.focus.reset();self.sync_focus(save=True)

    def sync_focus(self,save=False):
        if self.focus.tick():
            save=True
            notification=Gio.Notification.new('Focus complete')
            notification.set_body(f'Your {self.focus.duration//60}-minute session is finished. Time for a break.')
            notification.set_icon(Gio.ThemedIcon.new('alarm-symbolic'))
            self.send_notification('focus-complete',notification)
        if save:write_json(self.focus_path,self.focus.snapshot())
        if self.clock_panel:self.clock_panel.refresh()
        self.update_clock_caption()
        if self.focus.state=='running' and not self.focus_source:
            self.focus_source=GLib.timeout_add_seconds(1,self.focus_tick)
        elif self.focus.state!='running' and self.focus_source:
            GLib.source_remove(self.focus_source);self.focus_source=0

    def focus_tick(self):
        self.focus_source=0
        self.sync_focus()
        return False

    def update_clock_caption(self):
        name=self.config.get('display_name','')
        context=self.clock_zone.get_style_context()
        if name and self.focus.state=='idle':context.add_class('clock-personalized')
        else:context.remove_class('clock-personalized')
        if self.focus.state=='running':caption='FOCUS   /   '+self.focus.display
        elif self.focus.state=='paused':caption='PAUSED   /   '+self.focus.display
        elif self.focus.state=='complete':caption='FOCUS COMPLETE   /   TAKE A BREAK'
        else:caption='LOCAL TIME   /   '+datetime.now().astimezone().tzname()
        details=(name+' · ' if name else '')+caption
        if name:caption=name+'   /   '+(datetime.now().astimezone().tzname() if self.focus.state=='idle' else caption)
        self.clock_zone.set_text(caption)
        self.clock_zone.set_tooltip_text(details)

    def set_display_name(self,value):
        value=' '.join(value.split())[:24]
        updated={**self.config,'display_name':value}
        write_json(CONFIG,updated)
        self.config=updated
        self.update_clock_caption()
        return value

    def capture_detail(self):
        # Keep inbox content in memory; only nonprivate UI previews are exported.
        if not self.detail_popover or self.detail_name in ('gmail','photos'):return False
        widget=self.detail_popover;allocation=widget.get_allocation()
        write_json(BASE/'popup-state.json',{'open':True,'name':self.detail_name,
            'position':list(widget.get_position()),'size':list(widget.get_size()),
            'workarea':list(widget.workarea),'anchor':list(widget.anchor_rect),
            'grab':widget.grab_status,'xid':widget.get_window().get_xid(),
            'native_popup':widget.get_window_type()==Gtk.WindowType.POPUP,
            'mapped':widget.get_mapped()})
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,allocation.width,allocation.height)
        widget.draw(cairo.Context(surface));surface.write_to_png(str(BASE/'detail-preview.png'))
        return False

    def card_header(self,card,name,ico,action):
        row=box(False,8);row.pack_start(icon(ico,23),False,False,0)
        row.pack_start(label(name,'card-title'),True,True,0)
        row.pack_end(self.small_button('go-next-symbolic','Open '+name,action),False,False,0)
        card.pack_start(row,False,False,0)

    def build_gmail(self):
        card=style(box(spacing=8),'home-card','gmail-card')
        row=box(False,8);row.pack_start(icon('gmail',20),False,False,0)
        row.pack_start(label('Gmail','card-title'),True,True,0)
        self.unread=label('—','mail-count');accessible(self.unread,'Unread messages in inbox')
        row.pack_end(self.small_button('go-next-symbolic','Open Gmail',lambda:self.open_url(URLS['gmail'])),False,False,0)
        row.pack_end(self.unread,False,False,0);card.pack_start(row,False,False,0)
        self.mail_list=box(spacing=5);card.pack_start(self.mail_list,False,False,0)
        self.mail_status=label('Checking Google connection…','tiny')
        self.mail_status.set_ellipsize(Pango.EllipsizeMode.END);self.mail_status.set_max_width_chars(38)
        card.pack_start(self.mail_status,False,False,0)
        self.mail_action=style(Gtk.Button(label='Connect Google'),'text-button')
        self.mail_action.set_halign(Gtk.Align.START)
        accessible(self.mail_action,'Connect Google for inbox previews')
        self.mail_action.connect('clicked',lambda *_:self.open_accounts())
        card.pack_start(self.mail_action,False,False,0)
        return card

    def build_photos(self):
        card=style(box(spacing=12),'home-card','photos-card')
        self.card_header(card,'Google Photos','google-photos',lambda:self.open_url(URLS['photos']))
        self.photo_stack=Gtk.Stack();self.photo_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.photo_stack.set_transition_duration(250)
        self.photo_stack.set_size_request(-1,120)
        empty=style(box(spacing=9),'photo-empty');empty.set_valign(Gtk.Align.CENTER)
        empty.pack_start(icon('google-photos',42),False,False,0)
        empty.pack_start(label('Your moments, here','photo-title',.5),False,False,0)
        hint=label('Choose photos from your Google library.','muted',.5)
        hint.set_line_wrap(True);hint.set_max_width_chars(34);empty.pack_start(hint,False,False,0)
        self.photo_stack.add_named(empty,'empty')
        for name in ['a','b']:
            image=Gtk.Image();self.photo_stack.add_named(image,name)
        card.pack_start(self.photo_stack,True,True,0)
        self.photo_status=label('Choose photos to start your frame.','tiny')
        self.photo_status.set_line_wrap(True);self.photo_status.set_max_width_chars(40)
        card.pack_start(self.photo_status,False,False,0)
        row=box(False,8)
        self.photo_action=style(Gtk.Button(label='Choose photos'),'text-button')
        self.photo_action.connect('clicked',lambda *_:self.connect_photos())
        accessible(self.photo_action,'Choose photos from Google Photos')
        row.pack_start(self.photo_action,True,True,0)
        self.photo_next=self.small_button('go-next-symbolic','Next photo',lambda:self.rotate_photo(True))
        row.pack_end(self.photo_next,False,False,0)
        card.pack_start(row,False,False,0)
        self.rotate_photo()
        return card

    def clear_background(self,_widget,cr):
        cr.save();cr.set_operator(cairo.OPERATOR_SOURCE);cr.set_source_rgba(0,0,0,0);cr.paint();cr.restore()
        return False

    def small_button(self,name,title,callback):
        button=style(Gtk.Button(),'icon-button')
        button.set_valign(Gtk.Align.CENTER)
        button.add(Gtk.Image.new_from_icon_name(name,Gtk.IconSize.BUTTON))
        button.connect('clicked',lambda *_:callback())
        return accessible(button,title)

    def build_github(self):
        card=style(box(spacing=7),'home-card','github-card')
        row=box(False,8);row.pack_start(icon('github',23),False,False,0)
        row.pack_start(label('GitHub','card-title'),True,True,0)
        row.pack_end(self.small_button('go-next-symbolic','Open GitHub profile',self.open_github),False,False,0)
        card.pack_start(row,False,False,0)
        self.github_user=label('@'+self.config['github_username'],'muted');self.github_user.set_ellipsize(Pango.EllipsizeMode.END)
        # Profile identity is available on the header tooltip; keep desktop text sparse.
        row.set_tooltip_text('@'+self.config['github_username'])
        metrics=box(False,16)
        left=box(False,6);right=box(False,6);self.streak=label('—','streak');self.total=label('—','metric')
        left.pack_start(self.streak,False,False,0);left.pack_start(label('day streak','metric-label'),False,False,0)
        right.pack_start(self.total,False,False,0);right.pack_start(label('past year','metric-label'),False,False,0)
        metrics.pack_start(left,True,True,0);metrics.pack_start(right,True,True,0)
        accessible(metrics,"Consecutive GitHub contribution days. An empty current UTC day preserves yesterday's streak.")
        card.pack_start(metrics,False,False,0)
        self.heatmap=Heatmap();card.pack_start(self.heatmap,False,False,0)
        self.github_status=label('Loading GitHub activity…','tiny')
        self.github_status.set_line_wrap(True);self.github_status.set_max_width_chars(44)
        card.pack_start(self.github_status,False,False,0)
        return card

    def build_codex(self):
        card=style(box(spacing=8),'home-card','codex-card')
        row=box(False,8);row.pack_start(icon('codex',23),False,False,0)
        row.pack_start(label('Codex','card-title'),True,True,0)
        picker=style(Gtk.Button(label='All sessions ↗'),'text-button')
        picker.connect('clicked',lambda *_:self.open_codex());accessible(picker,'Open the Codex session picker')
        row.pack_end(picker,False,False,0);card.pack_start(row,False,False,0)

        self.session_list=box(spacing=6);card.pack_start(self.session_list,False,False,0)
        self.session_note=label('Latest saved session','tiny')
        card.pack_start(self.session_note,False,False,0)
        return card

    def apply_layout(self,dimensions=None):
        if not self.window:return
        display=Gdk.Display.get_default();monitor=display.get_primary_monitor() or display.get_monitor(0)
        geometry=monitor.get_geometry();w,h=dimensions or (geometry.width,geometry.height)
        compact=w<1550 or h<920
        clock_width=440;clock_height=175 if not compact else 160
        clock_y=80 if compact else 102
        icon_y=clock_y+clock_height+36
        positions={'clock':(w-480,clock_y,clock_width,clock_height),
                   'shortcuts':(w-360,h-66,300,40)}
        for index,name in enumerate(('gmail','photos','github','codex')):
            positions['icon-'+name]=(w-392+index*86,icon_y,84,106)
        self.windows['cloudflare'].set_size_request(-1,-1)
        positions['cloudflare']=self.cloudflare_panel.geometry(w,h,self.config['cloudflare_placement'])
        if self.config['cloudflare_placement']=='right':
            cx,cy,cw,ch=positions['cloudflare'];cy=icon_y+126
            positions['cloudflare']=(cx,cy,cw,min(ch,h-cy-88))
        resolved={name:self.layout.resolve(name,rect,(w,h)) for name,rect in positions.items()}
        occupied=list(resolved.values())
        # Existing custom positions win, including custom positions for new panels.
        additions={'notes':(110 if compact else 140,80 if compact else 130,300 if compact else 360,220 if compact else 260),
                   'todo':(110 if compact else 140,340 if compact else 460,300 if compact else 360,340),
                   'ai-feed':(450 if compact else 640,80 if compact else 160,410 if compact else 440,570)}
        ax,ay,aw,ah=self.layout.resolve('ai-feed',additions['ai-feed'],(w,h))
        additions['system']=(ax,ay+ah+32,max(560,aw),230)
        sx,sy,sw,sh=self.layout.resolve('system',additions['system'],(w,h))
        additions['music']=(sx,sy+sh+24,420,210)
        gx,gy,_,_=resolved['icon-gmail'];additions['icon-google']=(gx-94,gy,84,106)
        additions['icon-handy']=(gx-188,gy,84,106)
        additions['icon-theme']=(gx-282,gy,84,106)
        for name,preferred in additions.items():
            if name in self.layout.items:
                resolved[name]=self.layout.resolve(name,preferred,(w,h));occupied.append(resolved[name])
        for name,preferred in additions.items():
            if name not in resolved:
                resolved[name]=find_free_rect(preferred,occupied,(w,h),MINIMUM[name],padding=0 if name.startswith('icon-') else 12);occupied.append(resolved[name])
        for name,window in self.windows.items():
            context=window.get_style_context()
            (context.add_class if compact else context.remove_class)('compact')
            if name not in resolved:
                window.hide()
                if not self.config['show_'+name] and self.detail_name==name:self.close_detail()
                continue
            x,y,width,height=resolved[name]
            if name=='cloudflare':self.cloudflare_panel.set_placement('bottom' if width>=1100 else 'right')
            if name=='system':self.system_panel.set_geometry(width,height)
            if name.startswith('icon-'):
                allocation=Gdk.Rectangle();allocation.width=width;allocation.height=height
                window.get_child().get_child().scale_for_window(window,allocation)
            window.set_size_request(width,height);window.resize(width,height)
            window._target_rect=(x,y,width,height)
            window.move(geometry.x+x,geometry.y+y)
            visible=self.config['show_'+name[5:]] and self.config['show_shortcuts'] if name.startswith('icon-') else self.config['show_'+name.replace('-','_')]
            window.set_visible(visible)
            if name=='system':
                (self.system_panel.start if visible else self.system_panel.stop)()
            if name=='music':
                (self.music_panel.player.start if visible else self.music_panel.player.stop)()
            if name=='cloudflare':
                (self.cloudflare_panel.health.start if visible else self.cloudflare_panel.health.stop)()
        if self.detail_name and ((self.detail_name.startswith('cloudflare:') and not self.config['show_cloudflare'])
                or (self.detail_name in self.app_buttons and not self.config['show_shortcuts'])):self.close_detail()

    def clock_tick(self):
        now=datetime.now().astimezone()
        value=now.strftime('%H:%M')
        if self.clock_time.get_text()!=value:self.clock_time.set_text(value)
        self.clock_date.set_text(now.strftime('%A  /  %d %B').upper())
        self.update_clock_caption()
        GLib.timeout_add(max(50,60010-now.second*1000-now.microsecond//1000),self.clock_tick)
        return False

    def tick(self):
        if self.config['show_gmail']: self.refresh_mail()
        if self.config['show_codex']:self.refresh_sessions()
        if self.config['show_github']:
            self.render_github();self.refresh_github()
        return True

    def refresh_sessions(self):
        self.sessions=read_sessions(3)
        signature=json.dumps([(s['id'],s['title'],age_label(s['updated_at'])) for s in self.sessions])+str(self.config['show_session_titles'])
        if signature==self.session_signature:return
        self.session_signature=signature
        for child in self.session_list.get_children():child.destroy()
        if not self.sessions:
            empty=label('Open Codex to find your saved sessions.','muted');empty.set_line_wrap(True)
            self.session_list.pack_start(empty,True,True,0)
        for index,session in enumerate(self.sessions[:1]):
            button=style(Gtk.Button(),'session');content=box(spacing=3)
            title=session['title'] if self.config['show_session_titles'] else f'Saved session {index+1}'
            text=label(title,'session-title');text.set_ellipsize(Pango.EllipsizeMode.END);text.set_max_width_chars(24)
            project='Home' if Path(session['cwd'])==HOME else Path(session['cwd']).name
            subtitle=label(f'{project}  ·  {age_label(session["updated_at"])}','session-subtitle')
            subtitle.set_ellipsize(Pango.EllipsizeMode.END);subtitle.set_max_width_chars(28)
            content.pack_start(text,False,False,0);content.pack_start(subtitle,False,False,0)
            button.add(content);button.connect('clicked',lambda _b,s=session:self.open_codex(s))
            accessible(button,'Resume '+title);self.session_list.pack_start(button,False,False,0)
        self.session_list.show_all()

    def render_github(self):
        self.github_user.set_text('@'+self.config['github_username'])
        if self.github:
            try:
                summary=contribution_summary(self.github)
                self.streak.set_text(str(summary['streak'])+('+' if summary['lower_bound'] else ''))
                self.total.set_text(f"{summary['total']:,}")
                stamp=self.github.get('fetched_at',0)
                if getattr(self,'chart_stamp',None)!=stamp:
                    self.heatmap.update_days(summary['days']);self.chart_stamp=stamp
                message=f'Updated {age_label(stamp)}'
                if self.github_error:message='Offline / unavailable · saved '+age_label(stamp)
                self.github_status.set_text(message)
                self.github_status.set_tooltip_text(self.github_error or 'Updates every 30 minutes. Streak uses UTC calendar dates; an unfinished empty day keeps yesterday’s streak.')
                return
            except (KeyError,ValueError,TypeError):self.github=None
        self.streak.set_text('—');self.total.set_text('—');self.heatmap.update_days({})
        self.github_status.set_text(self.github_error or 'Loading GitHub activity…')

    def refresh_github(self,force=False):
        if not self.config['show_github'] or self.github_busy:return
        now=time.time();stamp=(self.github or {}).get('fetched_at',0)
        if not force and (now-stamp<1800 or now-self.last_attempt<300):return
        self.github_busy=True;self.last_attempt=now
        if self.refresh_button:self.refresh_button.set_sensitive(False)
        login=self.config['github_username']
        def work():
            try:value=fetch_github(login);error=''
            except Exception as exc:value=None;error=str(exc)
            GLib.idle_add(self.finish_github,login,value,error)
        threading.Thread(target=work,name='github-refresh',daemon=True).start()

    def finish_github(self,login,value,error):
        self.github_busy=False
        if self.refresh_button:self.refresh_button.set_sensitive(True)
        if login!=self.config['github_username']:self.refresh_github(force=True);return False
        self.github_error=error
        if value:
            self.github=value
            try:write_json(CACHE,value)
            except OSError:self.github_error='Could not save the local activity cache.'
        self.render_github();return False

    def refresh_all(self):
        self.refresh_sessions();self.refresh_github(force=True);self.refresh_mail(force=True)
        self.refresh_cloudflare(force=cloudflare_oauth.connected())
        self.refresh_ai(force=True)

    def open_accounts(self):
        self.close_detail()
        subprocess.Popen([str(HOME/'.local/bin/midnight-settings'),'online-accounts'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

    def refresh_mail(self,force=False):
        if not force and self.detail_name!='gmail':return
        if self.mail_busy or not self.config['show_gmail']:return
        if not force and time.time()-self.mail_attempt<60:return
        self.mail_busy=True;self.mail_attempt=time.time()
        account=self.config['gmail_account']
        def work():
            try:value=fetch_inbox(account);error='';connect=False
            except MailError as exc:value=None;error=str(exc);connect=exc.connect
            except Exception:value=None;error='Gmail could not refresh. Try again shortly.';connect=False
            GLib.idle_add(self.finish_mail,value,error,connect,account)
        threading.Thread(target=work,name='gmail-refresh',daemon=True).start()

    def finish_mail(self,value,error,connect,account=None):
        self.mail_busy=False;self.mail_error=error;self.mail_connect=connect
        if account is not None and account!=self.config['gmail_account']:
            self.refresh_mail(force=True);return False
        if value:self.mail=value
        if connect:self.mail=None
        self.unread.set_text(str(self.mail['unread']) if self.mail and self.mail['unread'] is not None else '—')
        for child in self.mail_list.get_children():child.destroy()
        if self.mail:
            for message in self.mail['messages'][:2]:
                button=style(Gtk.Button(),'mail-row');content=box(spacing=3)
                sender=label(('●  ' if message['unread'] else '')+message['sender'],'mail-sender')
                sender.set_ellipsize(Pango.EllipsizeMode.END);sender.set_max_width_chars(32)
                subject=label(message['subject'],'muted');subject.set_ellipsize(Pango.EllipsizeMode.END)
                subject.set_max_width_chars(38)
                content.pack_start(sender,False,False,0);content.pack_start(subject,False,False,0)
                button.add(content);button.connect('clicked',lambda _b,m=message:self.open_url(m['url']))
                accessible(button,message['sender']+': '+message['subject'])
                self.mail_list.pack_start(button,False,False,0)
            if not self.mail['messages']:
                self.mail_list.pack_start(label('Your inbox is empty.','muted'),True,True,0)
            status=error or 'Updated '+age_label(self.mail['fetched_at'])
            self.mail_status.set_text(status)
            self.mail_status.set_tooltip_text(self.mail['account'])
        else:
            note=label('Sign-in needs attention.' if connect else 'Checking your inbox…','muted')
            note.set_tooltip_text(error)
            note.set_line_wrap(True);note.set_max_width_chars(32)
            self.mail_list.pack_start(note,True,True,0)
            self.mail_status.set_text('')
        self.mail_status.set_visible(bool(self.mail))
        self.mail_action.set_visible(connect);self.mail_list.show_all()
        self.apply_layout()
        return False

    def rotate_photo(self,advance=True):
        from google_photos import selected_photos
        photos=selected_photos()
        if not photos:return True
        if not self.photo_stack.get_visible():self.photo_stack.show();self.apply_layout()
        if advance:self.photo_index=(self.photo_index+1)%len(photos)
        item=photos[self.photo_index%len(photos)]
        try:
            available=max(220,self.photo_stack.get_allocated_width())
            height=max(172,min(220,self.photo_stack.get_allocated_height()))
            stamp=(item['path'],Path(item['path']).stat().st_mtime,available,height)
            if stamp==self.photo_stamp:return True
            self.photo_stamp=stamp
            pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(item['path'],available,height,True)
            pixbuf=pixbuf.apply_embedded_orientation()
            target='b' if self.photo_stack.get_visible_child_name()=='a' else 'a'
            self.photo_stack.get_child_by_name(target).set_from_pixbuf(pixbuf)
            self.photo_stack.set_visible_child_name(target)
            self.photo_status.set_text(f"Google Photos · {self.photo_index%len(photos)+1} / {len(photos)}")
            self.photo_action.set_label('Change selected photos')
        except (GLib.Error,OSError):self.photo_status.set_text('This photo could not load. Choose photos again.')
        return True

    def connect_photos(self):
        self.close_detail()
        from google_photos import show_setup
        show_setup(self)

    def export_preview(self):
        monitor=Gdk.Display.get_default().get_primary_monitor();geo=monitor.get_geometry()
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,geo.width,geo.height);cr=cairo.Context(surface)
        wallpaper=Path(GLib.filename_from_uri(Gio.Settings.new('org.gnome.desktop.background').get_string('picture-uri'))[0])
        pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(wallpaper),geo.width,geo.height,False)
        Gdk.cairo_set_source_pixbuf(cr,pixbuf,0,0);cr.paint()
        for name,window in self.windows.items():
            if not window.get_visible():continue
            window.check_resize()
            x,y=window.get_position();width,height=window.get_size()
            tile=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
            window.draw(cairo.Context(tile))
            if name in ('notes','todo'):
                # Exports must not persist the user's private notes or task text.
                private=cairo.Context(tile);private.set_operator(cairo.OPERATOR_CLEAR);private.paint();private.set_operator(cairo.OPERATOR_OVER)
                private.set_source_rgb(.82,.90,.96);private.set_font_size(13)
                private.move_to(18,38);private.show_text(('Notes' if name=='notes' else 'To-do')+' · content hidden in export')
            if name=='gmail' and self.mail:
                private=cairo.Context(tile);private.set_source_rgb(.035,.065,.105);private.paint()
                private.set_source_rgb(.82,.90,.96);private.set_font_size(13)
                private.move_to(20,40);private.show_text('Gmail connected · preview hidden in export')
            cr.set_source_surface(tile,x-geo.x,y-geo.y);cr.paint()
        surface.write_to_png(str(BASE/'desktop-preview.png'))

    def open_url(self,url):
        self.close_detail()
        try:Gio.AppInfo.launch_default_for_uri(url,None)
        except GLib.Error:self.show_message('Could not open the browser. Check your default browser setting.')

    def open_github(self):self.open_url('https://github.com/'+self.config['github_username'])

    def open_codex(self,session=None):
        self.close_detail()
        try:subprocess.Popen(codex_command(session),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except (OSError,ValueError):self.show_message('Codex could not open. Check that your terminal and Codex CLI are available.')

    def show_message(self,message):
        dialog=Gtk.MessageDialog(transient_for=self.manager or self.window,modal=True,message_type=Gtk.MessageType.INFO,buttons=Gtk.ButtonsType.OK,text=message)
        dialog.connect('response',lambda w,_r:w.destroy());dialog.show_all()

    def save(self):
        write_json(CONFIG,self.config)
        write_autostart(self.config['autostart'])
        self.apply_layout();self.refresh_sessions()
        self.apply_motion_preferences()

    def show_manager(self):
        self.close_detail()
        if self.manager:self.manager.present();return
        self.manager=Gtk.ApplicationWindow(application=self,title='Manage Nightshift Home')
        self.manager.set_wmclass('nightshift-home-manager','NightshiftHome')
        self.manager.set_default_size(480,550);self.manager.set_position(Gtk.WindowPosition.CENTER)
        style(self.manager,'nightshift-manager')
        def manager_closed(*_):
            self.manager=None;self.refresh_button=None
        self.manager.connect('destroy',manager_closed)
        scrolled=Gtk.ScrolledWindow();scrolled.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.manager.add(scrolled)
        content=box(spacing=16);content.set_border_width(24);scrolled.add(content)
        content.pack_start(label('Your desktop','manager-title'),False,False,0)
        content.pack_start(label('Google apps open in your browser. GitHub and Codex open a panel.','muted'),False,False,0)
        name_row=box(False,8);name_row.pack_start(label('Display name'),False,False,0)
        name_entry=Gtk.Entry();name_entry.set_max_length(24);name_entry.set_width_chars(12)
        name_entry.set_text(self.config.get('display_name',''));name_entry.set_placeholder_text('Your name')
        accessible(name_entry,'Desktop display name');name_row.pack_start(name_entry,True,True,0)
        name_save=Gtk.Button(label='Save');accessible(name_save,'Save desktop display name')
        def save_name(*_):
            try:name_entry.set_text(self.set_display_name(name_entry.get_text()))
            except OSError:self.show_message('Your display name could not be saved. Please retry.')
        name_save.connect('clicked',save_name);name_entry.connect('activate',save_name)
        name_row.pack_end(name_save,False,False,0);content.pack_start(name_row,False,False,0)
        content.pack_start(label('WIDGETS','manager-section'),False,False,0)
        theme_button=Gtk.Button(label='RGB Studio · adjust theme colors')
        theme_button.connect('clicked',lambda *_:self.show_theme());content.pack_start(theme_button,False,False,0)
        arrange=Gtk.Button(label='Arrange desktop · move and resize')
        arrange.connect('clicked',lambda *_:self.start_arrange());content.pack_start(arrange,False,False,0)
        profiles=Gtk.Button(label='Saved layouts · Coding, Focus, Chill')
        profiles.connect('clicked',lambda *_:self.show_profiles());content.pack_start(profiles,False,False,0)
        project=Gtk.Button(label='Project status · Git, editor and terminal')
        project.connect('clicked',lambda *_:self.show_project());content.pack_start(project,False,False,0)
        for title,key in [('Clock and date','show_clock'),('Notes','show_notes'),('To-do list','show_todo'),('AI Learning','show_ai_feed'),('System monitor · CPU, RAM, storage','show_system'),('YouTube Music player','show_music'),('Google shortcut','show_google'),('Handy shortcut','show_handy'),('RGB Studio shortcut','show_theme'),('App icons','show_shortcuts'),('Cloudflare site insights','show_cloudflare'),('GitHub activity','show_github'),('Gmail inbox','show_gmail'),('Google Photos frame','show_photos'),('Recent Codex sessions','show_codex'),('Show Codex session names','show_session_titles'),('Reduce motion','reduced_motion'),('Start when I log in','autostart')]:
            row=box(False,12);row.pack_start(label(title),True,True,0)
            toggle=Gtk.Switch();toggle.set_active(self.config[key]);accessible(toggle,title)
            toggle.connect('notify::active',lambda w,_p,k=key:self.set_option(k,w.get_active()))
            row.pack_end(toggle,False,False,0);content.pack_start(row,False,False,0)
        cf_row=box(False,12);cf_row.pack_start(label('Website panel position'),True,True,0)
        cf_position=Gtk.ComboBoxText();cf_position.append('right','Lower right');cf_position.append('bottom','Along the bottom')
        cf_position.set_active_id(self.config['cloudflare_placement']);accessible(cf_position,'Cloudflare panel position')
        cf_position.connect('changed',lambda w:self.set_option('cloudflare_placement',w.get_active_id() or 'right'))
        cf_row.pack_end(cf_position,False,False,0);content.pack_start(cf_row,False,False,0)
        content.pack_start(label('QUICK LAUNCH','manager-section'),False,False,0)
        editor_row=box(False,12);editor_row.pack_start(label('Open projects with'),True,True,0)
        editor=Gtk.ComboBoxText();editor.append('code','VS Code');editor.append('cursor','Cursor')
        editor.set_active_id(self.config['project_editor']);accessible(editor,'Editor for project folders')
        editor.connect('changed',lambda w:self.set_option('project_editor',w.get_active_id() or 'code'))
        editor_row.pack_end(editor,False,False,0);content.pack_start(editor_row,False,False,0)
        controls=box(False,8)
        quick=Gtk.Button(label='Quick launch · Super + K');quick.connect('clicked',lambda *_:self.show_launcher())
        refresh=Gtk.Button(label='Refresh widgets');refresh.connect('clicked',lambda *_:self.refresh_all())
        self.refresh_button=refresh;refresh.set_sensitive(not self.github_busy)
        controls.pack_start(quick,True,True,0);controls.pack_end(refresh,False,False,0);content.pack_start(controls,False,False,0)
        hint=label('Workspaces: Coding, Research, Personal. Switch with Super + Alt + 1 / 2 / 3.','muted')
        hint.set_line_wrap(True);hint.set_max_width_chars(48);content.pack_start(hint,False,False,0)
        content.pack_start(label('CONNECTIONS','manager-section'),False,False,0)
        cloudflare=Gtk.Button(label='Cloudflare · connect read-only analytics')
        cloudflare.connect('clicked',lambda *_:self.connect_cloudflare());content.pack_start(cloudflare,False,False,0)
        google=Gtk.Button(label='Google account · enable Mail')
        google.connect('clicked',lambda *_:self.open_accounts());content.pack_start(google,False,False,0)
        account_row=box(False,12);account_row.pack_start(label('Inbox account'),True,True,0)
        account_choice=Gtk.ComboBoxText();account_choice.append('','Connected Google account')
        account_choice.set_active(0);accessible(account_choice,'Google account used for inbox previews')
        account_row.pack_end(account_choice,False,False,0);content.pack_start(account_row,False,False,0)
        manager=self.manager
        def load_accounts():
            from google_mail import google_accounts
            try:_bus,accounts=google_accounts()
            except Exception:accounts=[]
            def show_accounts():
                if self.manager is not manager:return False
                for account in accounts:account_choice.append(account['email'],account['email'])
                account_choice.set_active_id(self.config['gmail_account'])
                account_choice.connect('changed',lambda w:self.select_mail_account(w.get_active_id() or ''))
                return False
            GLib.idle_add(show_accounts)
        threading.Thread(target=load_accounts,daemon=True).start()
        photos=Gtk.Button(label='Choose photos from Google Photos')
        photos.connect('clicked',lambda *_:self.connect_photos());content.pack_start(photos,False,False,0)
        content.pack_start(label('GITHUB ACCOUNT','manager-section'),False,False,0)
        account_row=box(False,8);entry=Gtk.Entry();entry.set_text(self.config['github_username']);entry.set_placeholder_text('GitHub username')
        accessible(entry,'GitHub username');account_row.pack_start(entry,True,True,0)
        apply=Gtk.Button(label='Update');account_row.pack_end(apply,False,False,0)
        error=label('','status-error');error.set_line_wrap(True)
        def update_account(*_):
            login=entry.get_text().strip()
            if not valid_login(login):error.set_text('Enter a valid GitHub username.');return
            error.set_text('');self.config['github_username']=login;self.github=load_cache(login)
            self.github_error='';self.chart_stamp=None;self.last_attempt=0;self.save();self.render_github();self.refresh_github(force=True)
        apply.connect('clicked',update_account);entry.connect('activate',update_account)
        content.pack_start(account_row,False,False,0);content.pack_start(error,False,False,0)
        note=label('Gmail checks every minute. Selected Google photos rotate every 30 seconds. GitHub refreshes every 30 minutes. Codex shows recent saved sessions.','muted')
        note.set_line_wrap(True);note.set_max_width_chars(48);content.pack_start(note,False,False,0)
        controls=box(False,8)
        stop=Gtk.Button(label='Hide until next launch');stop.connect('clicked',lambda *_:self.request_quit())
        close=Gtk.Button(label='Done');close.connect('clicked',lambda *_:self.manager.destroy())
        controls.pack_start(stop,False,False,0);controls.pack_end(close,False,False,0);content.pack_start(controls,False,False,0)
        self.manager.show_all();self.manager.present()
        self.apply_motion_preferences(self.manager)

    def set_option(self,key,value):
        if key=='cloudflare_placement':self.layout.reset('cloudflare')
        self.config[key]=value;self.save()
        if key=='show_session_titles' and self.launcher_window:
            self.launcher_window.loaded_at=0;self.launcher_window.catalog=[]
            self.launcher_window.render()
            if self.launcher_window.get_visible():self.launcher_window.load()
        if key=='show_github' and value:self.render_github();self.refresh_github()
        if key=='show_gmail' and value:self.refresh_mail(force=True)
        if key=='show_cloudflare' and value:self.refresh_cloudflare()
        if key=='show_ai_feed' and value:self.refresh_ai()
        if key=='show_notes' and not value and self.notes_widget:self.notes_widget.flush()

    def select_mail_account(self,account):
        self.config['gmail_account']=account;self.mail=None;self.save();self.refresh_mail(force=True)

    def verify_ui(self):
        buttons=[]
        def walk(widget):
            if isinstance(widget,Gtk.Button):buttons.append(widget)
            if isinstance(widget,Gtk.Container):
                for child in widget.get_children():walk(child)
        for window in self.windows.values():walk(window)
        report={'window_type':self.window.get_type_hint().value_nick,
                'buttons':len(buttons),'all_buttons_have_accessible_names':all(b.get_accessible().get_name() for b in buttons),
                'can_traverse_with_keyboard':all(w.child_focus(Gtk.DirectionType.TAB_FORWARD) for n,w in self.windows.items() if n!='clock' and w.get_visible()),
                'saved_sessions':len(self.sessions),'github_cached':bool(self.github),
                'geometry':{n:{'position':list(w.get_position()),'size':list(w.get_size()),'visible':w.get_visible()} for n,w in self.windows.items()},
                'scrollbars':sum(isinstance(c,Gtk.ScrolledWindow) for w in self.windows.values() for c in w.get_children()),'display_backend':type(Gdk.Display.get_default()).__name__}
        write_json(BASE/'ui-check.json',report)
        self.export_preview()
        return False

if __name__=='__main__':
    app=Home();raise SystemExit(app.run(sys.argv))
