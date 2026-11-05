"""Saved desktop rectangles, pointer handles, and an equivalent keyboard editor."""
import copy
import json
import math
from data import HOME, write_json

PATH = HOME / '.config/nightshift-home/layout.json'
NAMES = {'clock':'Clock', 'icon-gmail':'Gmail', 'icon-photos':'Photos',
         'icon-github':'GitHub', 'icon-codex':'Codex', 'shortcuts':'Desktop controls',
         'cloudflare':'Cloudflare', 'notes':'Notes', 'todo':'To-do',
         'ai-feed':'AI Learning', 'icon-handy':'Handy', 'icon-theme':'RGB Studio', 'icon-google':'Google',
         'system':'System monitor', 'music':'YouTube Music'}
MINIMUM = {'clock':(240,140),'shortcuts':(260,40),'cloudflare':(320,210),
           'notes':(280,200),'todo':(280,300),'ai-feed':(320,320),'system':(300,210),'music':(280,195),
           **{name:(64,94) for name in NAMES if name.startswith('icon-')}}


def clamp_rect(rect, screen, minimum):
    sw,sh=screen;mw,mh=minimum
    x,y,w,h=(round(v) for v in rect)
    w=max(min(mw,sw-24),min(w,sw-24));h=max(min(mh,sh-72),min(h,sh-72))
    return [max(12,min(x,sw-w-12)),max(48,min(y,sh-h-12)),w,h]


def find_free_rect(preferred,occupied,screen,minimum,padding=12):
    """Place only new widgets in free space; never rewrite a user's rectangles."""
    px,py,pw,ph=clamp_rect(preferred,screen,minimum);sw,sh=screen
    best=None
    for width,height in [(pw,ph),(pw,minimum[1]),(minimum[0],ph),minimum]:
        xs={px,110,sw-width-24};ys={py,60,sh-height-24}
        for x,y,w,h in occupied:
            xs.update((x+w+24,x-width-24));ys.update((y+h+24,y-height-24))
        for x in xs:
            for y in ys:
                rect=clamp_rect((x,y,width,height),screen,minimum);x,y,width,height=rect
                overlaps=sum(max(0,min(x+width,ox+ow+padding)-max(x,ox-padding))*max(0,min(y+height,oy+oh+padding)-max(y,oy-padding)) for ox,oy,ow,oh in occupied)
                # Prefer full-size, nearby placement. If the screen is packed,
                # retain usable dimensions and minimize unavoidable overlap.
                score=(overlaps,(pw*ph-width*height)*3+(x-px)**2+(y-py)**2,x,y)
                if best is None or score<best[0]:best=(score,rect)
    return best[1]


class Layout:
    def __init__(self,path=PATH):
        self.path=path;self.items={};self.undo=None
        try:
            saved=json.loads(path.read_text())
            for key,item in saved.items():
                values=item['rect']+item['screen']
                if key in NAMES and len(item['rect'])==4 and len(item['screen'])==2 and all(isinstance(v,(float,int)) and math.isfinite(v) for v in values) and min(item['screen'])>0:
                    self.items[key]=item
        except (OSError,ValueError,TypeError,KeyError,AttributeError):pass

    def resolve(self,key,default,screen):
        item=self.items.get(key)
        if not item:return clamp_rect(default,screen,MINIMUM[key])
        x,y,w,h=item['rect'];ow,oh=item['screen'];sw,sh=screen
        w=min(w,sw-24);h=min(h,sh-72)
        # Preserve the relative placement when a monitor changes resolution.
        if [sw,sh]!=[ow,oh]:
            x=x/max(1,ow-item['rect'][2])*max(1,sw-w)
            y=y/max(1,oh-item['rect'][3])*max(1,sh-h)
        return clamp_rect((x,y,w,h),screen,MINIMUM[key])

    def save(self,key,rect,screen):
        self.items[key]={'rect':clamp_rect(rect,screen,MINIMUM[key]),'screen':list(screen)}
        write_json(self.path,self.items)

    def reset(self,key=None):
        self.undo=copy.deepcopy(self.items)
        if key:self.items.pop(key,None)
        else:self.items={}
        write_json(self.path,self.items)

    def restore(self):
        if self.undo is None:return
        self.items,self.undo=self.undo,None;write_json(self.path,self.items)


def widgets():
    # Data-only geometry tests do not need a graphical session.
    from gi.repository import Gtk,Gdk
    return Gtk,Gdk


class Handles:
    def __init__(self,home,name,window,content):
        Gtk,Gdk=widgets()
        self.home=home;self.name=name;self.window=window;self.start=None
        self.overlay=Gtk.Overlay();self.overlay.add(content)
        self.bar=Gtk.EventBox();self.bar.set_visible_window(True)
        self.bar.set_halign(Gtk.Align.FILL);self.bar.set_valign(Gtk.Align.START)
        self.bar.set_size_request(-1,26);self.bar.set_can_focus(True)
        self.bar.get_style_context().add_class('widget-dragbar')
        from gi.repository import Pango
        caption=Gtk.Label(label=NAMES[name]+'  ·  drag to move')
        caption.set_ellipsize(Pango.EllipsizeMode.END);caption.set_max_width_chars(1);self.bar.add(caption);caption.show()
        self.bar.get_accessible().set_name('Move '+NAMES[name]+'. Arrow keys move; Shift makes one-pixel adjustments.')
        self.grip=Gtk.EventBox();self.grip.set_visible_window(True);self.grip.set_can_focus(True)
        self.grip.set_halign(Gtk.Align.END);self.grip.set_valign(Gtk.Align.END)
        self.grip.set_size_request(28,28);self.grip.add(Gtk.Label(label='◢'));self.grip.get_child().show()
        self.grip.get_style_context().add_class('widget-resize-grip')
        self.grip.get_accessible().set_name('Resize '+NAMES[name]+'. Arrow keys adjust size.')
        for widget,resize in ((self.bar,False),(self.grip,True)):
            widget.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK)
            widget.connect('button-press-event',self.begin,resize)
            widget.connect('motion-notify-event',self.motion)
            widget.connect('button-release-event',self.end)
            widget.connect('key-press-event',self.key,resize)
            widget.connect('realize',lambda w,r=resize:w.get_window().set_cursor(Gdk.Cursor.new_from_name(w.get_display(),'se-resize' if r else 'move')))
            widget.set_no_show_all(True);self.overlay.add_overlay(widget)

    def set_editing(self,enabled):
        context=self.overlay.get_style_context()
        (context.add_class if enabled else context.remove_class)('widget-editing')
        for widget in (self.bar,self.grip):widget.set_visible(enabled)
        if not enabled and self.start:self.end(self.start['widget'],None)

    def begin(self,widget,event,resize):
        Gtk,Gdk=widgets()
        if event.button!=1 or not self.home.arranging:return False
        self.start=dict(pointer=(event.x_root,event.y_root),rect=self.home.widget_rect(self.name),resize=resize,widget=widget,last=None)
        widget.grab_focus();widget.grab_add()
        self.home.select_layout_widget(self.name)
        return True

    def motion(self,_widget,event):
        if not self.start:return False
        dx=event.x_root-self.start['pointer'][0];dy=event.y_root-self.start['pointer'][1]
        x,y,w,h=self.start['rect']
        rect=(x,y,w+dx,h+dy) if self.start['resize'] else (x+dx,y+dy,w,h)
        self.start['last']=self.home.place_widget(self.name,rect,save=False)
        return True

    def end(self,widget,event):
        if not self.start:return False
        last=self.start['last'];self.start['widget'].grab_remove();self.start=None
        if last:self.home.place_widget(self.name,last,save=True)
        return True

    def key(self,widget,event,resize):
        Gtk,Gdk=widgets()
        step=1 if event.state&Gdk.ModifierType.SHIFT_MASK else 10
        offsets={Gdk.KEY_Left:(-step,0),Gdk.KEY_Right:(step,0),Gdk.KEY_Up:(0,-step),Gdk.KEY_Down:(0,step)}
        if event.keyval not in offsets:return False
        # Super shortcuts remain the window manager's responsibility.
        if event.state&(Gdk.ModifierType.SUPER_MASK|Gdk.ModifierType.MOD4_MASK|Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.MOD1_MASK):return False
        x,y,w,h=self.home.widget_rect(self.name);dx,dy=offsets[event.keyval]
        self.home.place_widget(self.name,(x,y,w+dx,h+dy) if resize else (x+dx,y+dy,w,h),save=True)
        return True


def create_editor(home):
    Gtk,Gdk=widgets()
    window=Gtk.ApplicationWindow(application=home,title='Arrange desktop')
    window.set_wmclass('nightshift-layout','gjs');window.set_default_size(440,310)
    window.set_type_hint(Gdk.WindowTypeHint.DOCK);window.set_decorated(False)
    window.set_skip_taskbar_hint(True);window.set_skip_pager_hint(True)
    geo=home.screen_geometry();window.move(geo.x+100,geo.y+92)
    window.set_keep_above(True);window.get_style_context().add_class('nightshift-manager')
    content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);content.set_border_width(20);window.add(content)
    title=Gtk.Label(label='Make it yours',xalign=0);title.get_style_context().add_class('manager-title');content.pack_start(title,False,False,0)
    note=Gtk.Label(label='Drag a widget’s header to move it. Pull its lower-right corner to resize. Changes save automatically.',xalign=0)
    note.set_line_wrap(True);note.set_max_width_chars(40);content.pack_start(note,False,False,0)
    picker=Gtk.ComboBoxText()
    for key,name in NAMES.items():picker.append(key,name)
    picker.get_accessible().set_name('Widget to arrange');content.pack_start(picker,False,False,0)
    grid=Gtk.Grid(column_spacing=12,row_spacing=8);content.pack_start(grid,False,False,0)
    spins=[];updating=[False]
    for index,title in enumerate(('Left','Top','Width','Height')):
        label=Gtk.Label(label=title,xalign=0);spin=Gtk.SpinButton.new_with_range(0,10000,1)
        spin.get_accessible().set_name(title+' in pixels');grid.attach(label,(index%2)*2,index//2,1,1);grid.attach(spin,(index%2)*2+1,index//2,1,1)
        spins.append(spin)
    def refresh(*_):
        key=picker.get_active_id()
        if not key:return
        updating[0]=True
        for spin,value in zip(spins,home.widget_rect(key)):spin.set_value(value)
        updating[0]=False
    def changed(*_):
        if not updating[0] and picker.get_active_id():home.place_widget(picker.get_active_id(),[s.get_value_as_int() for s in spins],save=True)
    picker.connect('changed',refresh)
    for spin in spins:spin.connect('value-changed',changed)
    buttons=Gtk.Box(spacing=8)
    for title,callback in [('Reset selected',lambda:home.reset_layout(picker.get_active_id())),('Reset all',lambda:home.reset_layout()),('Undo reset',lambda:home.undo_layout())]:
        b=Gtk.Button(label=title);b.connect('clicked',lambda _b,c=callback:c());buttons.pack_start(b,True,True,0)
    content.pack_start(buttons,False,False,0)
    done=Gtk.Button(label='Done · lock layout');done.connect('clicked',lambda *_:home.end_arrange());content.pack_start(done,False,False,0)
    window.connect('delete-event',lambda *_:(home.end_arrange(),True)[1])
    window.connect('key-press-event',lambda _w,e:(home.end_arrange(),True)[1] if e.keyval==Gdk.KEY_Escape else False)
    window.layout_picker=picker;window.refresh_values=refresh;picker.set_active(0)
    return window
