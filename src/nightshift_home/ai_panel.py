"""A quiet, transparent reading list with clear sources and freshness."""
from datetime import datetime
import time
from gi.repository import Gtk,Pango,Atk
from clock_panel import css,text
from personal_widgets import transparent_scroller
import ai_feed

class AIPanel(Gtk.Box):
    def __init__(self,home):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=13)
        self.home=home;self.tab='latest';self.data={};self.errors={};self.busy=False;self.selecting=False
        css(self,'personal-widget','ai-widget')
        header=Gtk.Box(spacing=8);header.pack_start(text('AI pulse','personal-title'),True,True,0)
        kicker=text('DISCOVER / BUILD','personal-meta');kicker.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_end(kicker,False,False,0);self.pack_start(header,False,False,0)
        tabs=Gtk.Box(spacing=4);self.buttons={}
        for name,title in [('latest','Latest'),('tools','Tools'),('learn','Learn')]:
            button=css(Gtk.ToggleButton(label=title),'ai-tab');button.set_active(name==self.tab)
            button.get_accessible().set_name('AI '+title)
            button.connect('clicked',lambda _b,n=name:self.select(n));tabs.pack_start(button,False,False,0);self.buttons[name]=button
        self.pack_start(tabs,False,False,0)
        self.scope=text('','personal-meta');self.scope.set_line_wrap(True);self.scope.set_max_width_chars(1);self.pack_start(self.scope,False,False,0)
        self.items=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
        self.scroller=transparent_scroller(60);self.scroller.add(self.items);self.pack_start(self.scroller,True,True,0)
        footer=Gtk.Box(spacing=8)
        self.status=text('','personal-status');self.status.set_line_wrap(True);self.status.set_max_width_chars(1);self.status.get_accessible().set_role(Atk.Role.STATUSBAR)
        footer.pack_start(self.status,True,True,0)
        self.refresh_button=home.small_button('view-refresh-symbolic','Refresh AI sources · automatic refresh every 15 minutes',lambda:home.refresh_ai(force=True))
        footer.pack_end(self.refresh_button,False,False,0);self.pack_start(footer,False,False,0)
        self.render()

    def select(self,tab):
        if self.selecting:return
        self.selecting=True
        self.tab=tab
        for name,button in self.buttons.items():button.set_active(name==tab)
        self.selecting=False
        self.scroller.get_vadjustment().set_value(0);self.render()

    def update(self,data,errors=None,busy=False):
        self.data=data;self.errors=errors or {};self.busy=busy;self.render()

    def render(self):
        # Network refreshes do not remove a focused article button mid-navigation.
        focus=self.get_toplevel().get_focus() if isinstance(self.get_toplevel(),Gtk.Window) else None
        focused_url=getattr(focus,'feed_url',None)
        for child in self.items.get_children():child.destroy()
        source=self.data.get(self.tab,{})
        items=ai_feed.LEARN if self.tab=='learn' else source.get('items',[])
        self.scope.set_text({'latest':'New posts from Hugging Face','tools':'Recent LLM repos · last 60 days · sorted by stars','learn':'Learning library · official, self-paced guides'}[self.tab])
        for item in items:
            button=css(Gtk.Button(),'ai-article');button.feed_url=item['url']
            button.set_tooltip_text(item['title']+'\n'+item['url']);button.get_accessible().set_name(item['title']+'. Open in browser.')
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            title=text(item['title'],'ai-title');title.set_line_wrap(True);title.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            title.set_ellipsize(Pango.EllipsizeMode.END);title.set_lines(2);title.set_max_width_chars(1);body.pack_start(title,False,False,0)
            if self.tab=='tools' and item.get('description'):
                description=text(item['description'],'ai-description');description.set_line_wrap(True);description.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                description.set_max_width_chars(1);description.set_lines(2);description.set_ellipsize(Pango.EllipsizeMode.END);body.pack_start(description,False,False,0)
            if self.tab=='latest':
                try:stamp=datetime.fromtimestamp(item['published']).strftime('%d %b') if item.get('published') else ''
                except (TypeError,ValueError,OverflowError,OSError):stamp=''
                caption='Hugging Face'+(' · '+stamp if stamp else '')
            elif self.tab=='tools':caption=f"GitHub · {item.get('stars',0):,} stars"
            else:caption=item['description']
            meta=text(caption,'personal-status');meta.set_line_wrap(True);meta.set_max_width_chars(1);meta.set_lines(2);meta.set_ellipsize(Pango.EllipsizeMode.END)
            body.pack_start(meta,False,False,0);button.add(body);button.connect('clicked',lambda _b,u=item['url']:self.home.open_url(u))
            self.items.pack_start(button,False,False,0)
            if focused_url==item['url']:button.grab_focus()
        if not items:
            message='Checking for new stories…' if self.busy else ('No results yet. Use refresh to try again.' if self.tab in self.data else 'Connect to the internet, then refresh to load stories.')
            empty=text(message,'personal-placeholder');empty.set_line_wrap(True);empty.set_max_width_chars(1);self.items.pack_start(empty,False,False,12)
        stamp=source.get('updated_at')
        if self.tab=='learn':status='Choose a guide to open in your browser'
        elif self.busy:status='Refreshing…'
        elif self.errors.get(self.tab):status=(datetime.fromtimestamp(stamp).strftime('Saved %d %b, %H:%M · ') if stamp else '')+self.errors[self.tab]
        elif stamp:
            status=datetime.fromtimestamp(stamp).strftime('Updated %H:%M' if time.time()-stamp<86400 else 'Saved %d %b, %H:%M')+' · every 15 min'
        else:status='Updates every 15 min'
        self.status.set_text(status);self.status.set_tooltip_text(self.errors.get(self.tab) or 'Public source updates are checked every 15 minutes; this is not a live stream.')
        self.refresh_button.set_sensitive(not self.busy);self.items.show_all()
