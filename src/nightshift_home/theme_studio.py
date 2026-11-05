"""Native RGB Studio: a local preview, explicit Apply, and one-step Undo."""
import threading
from gi.repository import Gtk,Gdk,GLib,Atk,Pango
import cairo
from clock_panel import css,text
from data import BASE
from theme_palette import DEFAULT,PRESETS,load_state,validate,hex_color,rgb,hex_rgb,readable,color,recolor
from theme_apply import ThemeEngine
from aurora_art import draw as wallpaper

class Preview(Gtk.DrawingArea):
    def __init__(self,palette):
        super().__init__();self.palette=palette.copy();self.set_size_request(1,145)
        self.get_accessible().set_role(Atk.Role.IMAGE);self.get_accessible().set_name('Theme preview: wallpaper, clock, windows and terminal')
        self.connect('draw',self.draw_preview)
    def update(self,palette):self.palette=palette.copy();self.queue_draw()
    def draw_preview(self,_widget,cr):
        width,height=self.get_allocated_width(),self.get_allocated_height();p=self.palette
        wallpaper(cr,width,height,p);cr.save();scale=min(width/760,height/145)
        cr.translate((width-760*scale)/2,(height-145*scale)/2);cr.scale(scale,scale)
        def fill(value):cr.set_source_rgb(*rgb(value))
        accent=readable(p['primary']);secondary=readable(p['secondary']);highlight=readable(p['highlight'])
        cr.set_line_width(2)
        gradient=cairo.LinearGradient(0,0,760,0)
        for stop,value in [(0,accent),(.5,secondary),(1,highlight)]:gradient.add_color_stop_rgb(stop,*rgb(value))
        cr.set_source(gradient);cr.rectangle(16,9,728,2);cr.fill()
        cr.select_font_face('Inter',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_NORMAL)
        def caption(value,x,y,size=12,tint='#d8e8f7'):
            fill(tint);cr.set_font_size(size);cr.move_to(x,y);cr.show_text(value)
        from line_clock import LineClock
        fill(color('#e0f7ff',p));cr.save();cr.translate(558,28);cr.scale(.46,.46)
        cr.set_line_width(1.5);cr.set_line_cap(cairo.LINE_CAP_ROUND);cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for index,char in enumerate('1234'):
            cr.save();cr.translate(index*75+(12 if index>1 else 0),0);LineClock.digit(cr,char);cr.restore()
        for y in (35,67):cr.move_to(149,y);cr.line_to(149,y+2);cr.stroke()
        cr.restore();caption('THURSDAY / YOUR DESKTOP',560,94,8)
        caption('Notes',30,34,13,accent);caption('Make something worth keeping.',30,57,11)
        caption('To-do',30,88,13,secondary)
        fill(secondary);cr.rectangle(31,106,10,10);cr.stroke();caption('Build the next idea',50,116,11)
        fill(color('#0b1423',p));cr.rectangle(292,28,236,94);cr.fill()
        fill(accent);cr.rectangle(292,28,236,2);cr.fill()
        caption('Terminal',305,44,10);caption('~/projects',305,66,12,secondary)
        caption('$ make something',305,88,12,accent);caption('ready to build',305,110,10)
        for index,value in enumerate((accent,secondary,highlight)):
            fill(value);cr.arc(575+index*37,118,7,0,6.284);cr.fill()
        cr.restore();return False

class ThemeStudio(Gtk.ApplicationWindow):
    def __init__(self,home,engine=None):
        super().__init__(application=home,title='RGB Studio · Desktop theme')
        self.home=home;self.engine=engine or ThemeEngine();self.current=load_state(self.engine.state)
        self.palette=self.current['palette'].copy();self.selected='primary';self.updating=False;self.busy=False;self.valid=True
        css(self,'nightshift-manager','rgb-studio')
        geometry=home.screen_geometry();self.set_default_size(min(880,geometry.width-100),min(710,geometry.height-110));self.set_size_request(510,420)
        provider=Gtk.CssProvider();self.provider=provider;self.chrome()
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+15)
        self.connect('delete-event',self.close_requested);self.connect('key-press-event',self.key)
        self.connect('destroy',lambda *_:Gtk.StyleContext.remove_provider_for_screen(self.get_screen(),provider))
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);outer.set_border_width(20);self.add(outer)
        header=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        header.pack_start(text('RGB Studio','studio-title'),False,False,0)
        subtitle=text('Match your desktop, widgets and terminal.','studio-muted');subtitle.set_line_wrap(True);header.pack_start(subtitle,False,False,0)
        outer.pack_start(header,False,False,0)
        scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_overlay_scrolling(False);outer.pack_start(scroll,True,True,0)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);scroll.add(body)
        self.preview=Preview(self.palette);body.pack_start(self.preview,False,False,0)
        presetrow=Gtk.Box(spacing=12);presetrow.pack_start(text('Palette','studio-label'),False,False,0)
        self.presets=Gtk.ComboBoxText();self.presets.append('custom','Custom colors')
        for name in PRESETS:self.presets.append(name,name)
        self.presets.get_accessible().set_name('Theme preset');self.presets.connect('changed',self.preset_changed)
        presetrow.pack_start(self.presets,True,True,0);body.pack_start(presetrow,False,False,0)
        swatches=Gtk.Box(spacing=10);self.swatches={};self.chips={}
        for key,title in [('primary','Primary'),('secondary','Secondary'),('highlight','Highlight')]:
            button=css(Gtk.ToggleButton(),'studio-swatch');button.set_hexpand(True)
            column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
            chip=Gtk.DrawingArea();chip.set_size_request(1,7);chip.connect('draw',self.draw_swatch,key)
            column.pack_start(chip,False,False,0);column.pack_start(text(title,align=.5),False,False,0);button.add(column)
            button.connect('clicked',lambda _w,k=key:self.select(k));button.get_accessible().set_name('Edit '+title+' color')
            swatches.pack_start(button,True,True,0);self.swatches[key]=button;self.chips[key]=chip
        body.pack_start(swatches,False,False,0)
        flow=Gtk.FlowBox();flow.set_selection_mode(Gtk.SelectionMode.NONE);flow.set_min_children_per_line(1);flow.set_max_children_per_line(2)
        flow.set_column_spacing(22);flow.set_row_spacing(16);flow.set_homogeneous(True);body.pack_start(flow,False,False,0)
        channels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9);channels.set_size_request(275,-1)
        self.channel_title=text('PRIMARY / RGB','studio-label');channels.pack_start(self.channel_title,False,False,0)
        self.scales=[];self.spins=[]
        for index,name in enumerate(('Red','Green','Blue')):
            row=Gtk.Box(spacing=8);title=text(name);title.set_width_chars(5);row.pack_start(title,False,False,0)
            adjustment=Gtk.Adjustment(value=0,lower=0,upper=255,step_increment=1,page_increment=10,page_size=0)
            scale=Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,adjustment=adjustment);scale.set_draw_value(False);scale.set_hexpand(True)
            spin=Gtk.SpinButton(adjustment=adjustment,climb_rate=1,digits=0);spin.set_width_chars(3)
            scale.get_accessible().set_name(name+' channel, 0 to 255');spin.get_accessible().set_name(name+' numeric value')
            title.set_mnemonic_widget(spin);adjustment.connect('value-changed',lambda *_:self.channels_changed())
            row.pack_start(scale,True,True,0);row.pack_end(spin,False,False,0);channels.pack_start(row,False,False,0);self.scales.append(scale);self.spins.append(spin)
        hexrow=Gtk.Box(spacing=8);hexlabel=text('Hex');hexrow.pack_start(hexlabel,False,False,0)
        self.hex=Gtk.Entry();self.hex.set_width_chars(8);self.hex.set_max_length(7);self.hex.get_accessible().set_name('Hex color, six digits after #')
        self.hex.connect('changed',self.hex_changed);hexlabel.set_mnemonic_widget(self.hex);hexrow.pack_start(self.hex,True,True,0)
        self.picker=Gtk.ColorButton();self.picker.set_use_alpha(False);self.picker.set_title('Choose an RGB color');self.picker.get_accessible().set_name('Open color picker')
        self.picker.connect('color-set',self.picker_changed);hexrow.pack_end(self.picker,False,False,0);channels.pack_start(hexrow,False,False,0);flow.add(channels)
        atmosphere=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9);atmosphere.set_size_request(275,-1)
        atmosphere.pack_start(text('ATMOSPHERE','studio-label'),False,False,0);self.levels={}
        for key,title in [('darkness','Background darkness'),('glow','Wallpaper glow')]:
            row=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2);label=text(title);row.pack_start(label,False,False,0)
            scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1);scale.set_digits(0);scale.set_value_pos(Gtk.PositionType.RIGHT)
            scale.get_accessible().set_name(title+', 0 to 100');label.set_mnemonic_widget(scale);scale.connect('value-changed',lambda w,k=key:self.level_changed(k,w.get_value()))
            row.pack_start(scale,False,False,0);atmosphere.pack_start(row,False,False,0);self.levels[key]=scale
        self.editors=Gtk.CheckButton(label='Also match VS Code and Cursor');self.editors.get_child().set_line_wrap(True);self.editors.get_child().set_max_width_chars(1)
        self.editors.connect('toggled',self.editors_changed);atmosphere.pack_start(self.editors,False,False,0);flow.add(atmosphere)
        note=text('Applies to wallpaper, widgets, dock, window accents, folders, Settings and terminal. Text stays readable. Reopen Settings and some apps to refresh their colors.','studio-muted')
        note.set_line_wrap(True);note.set_max_width_chars(1);body.pack_start(note,False,False,0)
        self.status=text('Preview only · choose your colors, then Apply.','studio-status');self.status.set_line_wrap(True);self.status.set_max_width_chars(1)
        self.status.get_accessible().set_role(Atk.Role.STATUSBAR);outer.pack_start(self.status,False,False,0)
        footer=Gtk.Box(spacing=10)
        self.undo_button=Gtk.Button(label='Undo last Apply');self.undo_button.connect('clicked',lambda *_:self.undo());footer.pack_start(self.undo_button,False,False,0)
        self.apply_button=css(Gtk.Button(label='Apply theme'),'studio-apply');self.apply_button.connect('clicked',lambda *_:self.apply());footer.pack_end(self.apply_button,False,False,0)
        outer.pack_start(footer,False,False,0);self.body=body;self.sync()

    def draw_swatch(self,widget,cr,key):
        cr.set_source_rgb(*rgb(self.palette[key]));cr.rectangle(0,0,widget.get_allocated_width(),widget.get_allocated_height());cr.fill();return False
    def chrome(self):
        source=(BASE/'theme-studio.css').read_text()
        if self.current.get('applied_at'):source=recolor(source,self.current['palette'])
        self.provider.load_from_data(source.encode())
    def select(self,key):
        if self.updating or self.busy:return
        self.selected=key;self.sync()
    def sync(self):
        self.updating=True
        for key,button in self.swatches.items():button.set_active(key==self.selected);self.chips[key].queue_draw()
        name=next((name for name,palette in PRESETS.items() if palette==self.palette),'custom');self.presets.set_active_id(name)
        self.channel_title.set_text(self.selected.upper()+' / RGB')
        for spin,value in zip(self.spins,rgb(self.palette[self.selected])):spin.set_value(round(value*255))
        self.hex.set_text(self.palette[self.selected].upper());rgba=Gdk.RGBA();rgba.parse(self.palette[self.selected]);self.picker.set_rgba(rgba)
        for key,scale in self.levels.items():scale.set_value(self.palette[key])
        self.editors.set_active(self.palette['editors']);self.updating=False;self.valid=True
        self.preview.update(self.palette);self.buttons()
    def buttons(self):
        self.apply_button.set_sensitive(self.valid and not self.busy);self.undo_button.set_sensitive(self.engine.undo_path.exists() and not self.busy)
        self.body.set_sensitive(not self.busy)
    def changed(self):
        self.sync();self.status.set_text('Preview only · Apply to use these colors everywhere.')
    def preset_changed(self,widget):
        if self.updating:return
        name=widget.get_active_id()
        if name in PRESETS:self.palette=PRESETS[name].copy();self.changed()
    def channels_changed(self):
        if self.updating:return
        self.palette[self.selected]=hex_rgb(tuple(spin.get_value()/255 for spin in self.spins));self.changed()
    def hex_changed(self,entry):
        if self.updating:return
        try:value=hex_color(entry.get_text())
        except ValueError:
            self.valid=False;self.status.set_text('Enter # followed by six hex digits, such as #58D8F2.');self.buttons();return
        self.palette[self.selected]=value;cursor=entry.get_position();self.changed();entry.set_position(cursor)
    def picker_changed(self,widget):
        value=widget.get_rgba();self.palette[self.selected]=hex_rgb((value.red,value.green,value.blue));self.changed()
    def level_changed(self,key,value):
        if self.updating:return
        self.palette[key]=round(value);self.changed()
    def editors_changed(self,widget):
        if not self.updating:self.palette['editors']=widget.get_active();self.changed()
    def apply(self):
        if self.busy or not self.valid:return
        palette=validate(self.palette);self.run(lambda:self.engine.commit(self.engine.prepare(palette)),'Applying your palette…')
    def undo(self):
        if not self.busy:self.run(self.engine.undo,'Restoring the previous theme…',undo=True)
    def run(self,operation,message,undo=False):
        self.busy=True;self.buttons();self.status.set_text(message)
        def worker():
            try:result=operation();error=None
            except Exception as exc:result=None;error=str(exc)
            GLib.idle_add(self.finished,result,error,undo)
        threading.Thread(target=worker,daemon=True,name='rgb-studio-apply').start()
    def finished(self,result,error,undo):
        self.busy=False
        if error:self.status.set_text('Could not apply: '+error);self.buttons();return False
        self.current=result;self.palette=result['palette'].copy();self.home.reload_theme();self.chrome();self.sync()
        self.status.set_text('Previous theme restored.' if undo else 'Theme applied. Reopen Settings and some apps for their updated colors.');return False
    def close_requested(self,*_):return self.busy
    def capture(self):
        width,height=self.get_size();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
        self.draw(cairo.Context(surface));surface.write_to_png(str(BASE/'rgb-studio-live.png'));return False
    def key(self,_widget,event):
        if event.keyval==Gdk.KEY_Escape:
            if not self.busy:self.close()
            return True
        if event.keyval==Gdk.KEY_Return and event.state&Gdk.ModifierType.CONTROL_MASK:self.apply();return True
        return False
