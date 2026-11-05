"""A recoverable sign-in window; browser consent remains with the user."""
from gi.repository import Gtk,Gdk,Atk
from clock_panel import css,text
import cloudflare_oauth


class ConnectionWindow(Gtk.ApplicationWindow):
    def __init__(self,home):
        super().__init__(application=home,title='Connect Cloudflare · Nightshift')
        self.home=home;self.set_wmclass('nightshift-cloudflare-login','gjs')
        self.set_default_size(470,330);self.set_position(Gtk.WindowPosition.CENTER)
        css(self,'nightshift-manager')
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);body.set_border_width(24);self.add(body)
        body.pack_start(text('Cloudflare insights','manager-title'),False,False,0)
        note=text('Connect once to refresh your four sites every 5 minutes. Analytics cover a rolling 24 hours, including the current hour and automated traffic.','muted')
        note.set_line_wrap(True);note.set_max_width_chars(48);body.pack_start(note,False,False,0)
        self.status=text('Preparing sign-in…','card-title');self.status.set_line_wrap(True);self.status.set_max_width_chars(46)
        self.status.get_accessible().set_role(Atk.Role.STATUSBAR);body.pack_start(self.status,False,False,0)
        self.explanation=text('','muted');self.explanation.set_line_wrap(True);self.explanation.set_max_width_chars(48)
        body.pack_start(self.explanation,False,False,0)
        self.open=Gtk.Button(label='Open sign-in page');self.open.connect('clicked',lambda *_:home.open_cloudflare_consent())
        body.pack_start(self.open,False,False,0)
        row=Gtk.Box(spacing=8)
        self.retry=Gtk.Button(label='Start sign-in again');self.retry.connect('clicked',lambda *_:home.start_cloudflare_connection())
        self.cancel=Gtk.Button(label='Cancel sign-in');self.cancel.connect('clicked',lambda *_:home.cancel_cloudflare_connection())
        row.pack_start(self.retry,True,True,0);row.pack_start(self.cancel,True,True,0);body.pack_start(row,False,False,0)
        close=Gtk.Button(label='Close');close.connect('clicked',lambda *_:self.destroy());body.pack_start(close,False,False,0)
        self.connect('destroy',lambda *_:setattr(home,'cloudflare_dialog',None))
        self.connect('key-press-event',lambda _w,e:(self.destroy(),True)[1] if e.keyval==Gdk.KEY_Escape else False)

    def refresh(self):
        home=self.home;connected=cloudflare_oauth.connected()
        if home.cloudflare_connecting:
            message='Finish the read-only consent in your browser.' if home.cloudflare_url else 'Preparing your Cloudflare sign-in…'
        elif home.cloudflare_error:message=home.cloudflare_error
        elif connected:message='Connected · refreshing analytics…' if home.cloudflare_busy else 'Connected to Cloudflare.'
        else:message='Not connected. Your saved snapshot is still available.'
        self.status.set_text(message)
        self.explanation.set_text('If the browser page is hidden or was closed, open it again below. No write permissions are requested.' if home.cloudflare_connecting else 'Start again if sign-in expired. You can close this window while analytics refresh.')
        self.open.set_sensitive(bool(home.cloudflare_url) and home.cloudflare_connecting)
        self.cancel.set_sensitive(home.cloudflare_connecting)
        self.retry.set_sensitive(not home.cloudflare_busy)
