"""A quiet four-site summary; details stay in a contextual panel."""
from datetime import datetime, timezone
from gi.repository import Gtk, Pango, Atk, GLib
from clock_panel import css, text
from cloudflare_data import SITES, normalize, compact, dashboard
from theme_palette import paint,rgb


class Sparkline(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()
        self.values = []
        self.set_size_request(84, 14)
        self.connect('draw', self.draw_chart)
        self.get_accessible().set_role(Atk.Role.IMAGE)
        self.get_accessible().set_name('Request trend in 15-minute intervals')

    def update(self, values):
        self.values = values
        self.queue_draw()

    def draw_chart(self, _widget, cr):
        if not self.values:return False
        width = self.get_allocated_width();height = self.get_allocated_height()
        maximum = max(1, max(self.values))
        step = (width - 4) / max(1, len(self.values) - 1)
        cr.set_source_rgba(*rgb(paint('#57d9f2')), .9);cr.set_line_width(1.5)
        for i, value in enumerate(self.values):
            x, y = 2 + step * i, height - 3 - (height - 6) * value / maximum
            cr.move_to(x, y) if not i else cr.line_to(x, y)
        cr.stroke()
        return False


class CloudflarePanel(Gtk.Box):
    def __init__(self, home):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.home = home
        from site_health import HealthMonitor
        self.health = HealthMonitor(self.update_health)
        self.connect('destroy', lambda *_: self.health.stop())
        css(self, 'cloudflare-panel')
        heading = Gtk.Box(spacing=8)
        title = text('Host requests', 'card-title')
        title.set_ellipsize(Pango.EllipsizeMode.END)
        heading.pack_start(title, True, True, 0)
        eyebrow=text('CLOUDFLARE / 24H', 'cf-eyebrow');eyebrow.set_ellipsize(Pango.EllipsizeMode.END)
        heading.pack_end(eyebrow, False, False, 0)
        heading.connect('size-allocate',self.reflow_details,title,eyebrow)
        self.pack_start(heading, False, False, 0)
        self.rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.fields = {}
        for name, _identifier in SITES:
            button = css(Gtk.Button(), 'cf-site')
            button.get_accessible().set_name('Cloudflare insights for ' + name)
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            first = Gtk.Box(spacing=12)
            domain = text(name, 'cf-domain');domain.set_ellipsize(Pango.EllipsizeMode.END)
            first.pack_start(domain, True, True, 0)
            requests = text('—', 'cf-requests');first.pack_end(requests, False, False, 0)
            content.pack_start(first, False, False, 0)
            second = Gtk.Box(spacing=10)
            health = text('○ Checking health…', 'cf-health')
            health.set_ellipsize(Pango.EllipsizeMode.END)
            detail = text('Waiting for metrics', 'cf-secondary');detail.set_xalign(1)
            detail.set_ellipsize(Pango.EllipsizeMode.END)
            second.pack_start(health, True, True, 0)
            second.pack_end(detail, True, True, 0)
            second.connect('size-allocate',self.reflow_details,health,detail)
            content.pack_start(second, False, False, 0)
            chart = Sparkline();chart.set_hexpand(True)
            content.pack_start(chart, False, False, 0)
            button.add(content)
            button.connect('clicked', lambda b, n=name: home.show_cloudflare_site(n, b))
            self.rows.pack_start(button, True, True, 0)
            self.fields[name] = dict(button=button, requests=requests, chart=chart, detail=detail, health=health)
        self.scroller=Gtk.ScrolledWindow();self.scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        self.scroller.set_min_content_height(80);self.scroller.set_propagate_natural_height(False)
        self.scroller.add(self.rows);self.pack_start(self.scroller, True, True, 0)
        footer = Gtk.Box(spacing=8)
        self.status = text('', 'cf-secondary');self.status.set_max_width_chars(1)
        self.status.set_line_wrap(True);self.status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        footer.pack_start(self.status, True, True, 0)
        self.refresh = home.small_button('view-refresh-symbolic', 'Refresh traffic and website health', lambda: (home.refresh_cloudflare(True), self.health.refresh()))
        self.connect_button = home.small_button('network-server-symbolic', 'Connect Cloudflare for automatic updates', home.connect_cloudflare)
        footer.pack_end(self.connect_button, False, False, 0)
        footer.pack_end(self.refresh, False, False, 0)
        self.pack_start(footer, False, False, 0)
        self.set_tooltip_text('Cloudflare request analytics, including automated traffic. Click a site for details.')

    def reflow_details(self, row, allocation, health, detail):
        # Measure unconstrained text; ellipsized label requisitions can otherwise
        # report their current allocation and prevent enlarged text from stacking.
        def natural(label):
            layout=label.create_pango_layout(label.get_text())
            layout.set_font_description(label.get_style_context().get_font(Gtk.StateFlags.NORMAL))
            layout.set_width(-1);layout.set_ellipsize(Pango.EllipsizeMode.NONE)
            return layout.get_pixel_size()[0]
        needed=natural(health)+natural(detail)+10
        stacked=allocation.width<needed
        orientation=Gtk.Orientation.VERTICAL if stacked else Gtk.Orientation.HORIZONTAL
        row._flow_target=(orientation,stacked)
        if row.get_orientation()!=orientation and not getattr(row,'_flow_pending',False):
            row._flow_pending=True
            def apply():
                row._flow_pending=False
                if row.get_parent() is None:return False
                target,vertical=row._flow_target
                row.set_orientation(target);row.set_spacing(2 if vertical else 10)
                detail.set_xalign(0 if vertical else 1)
                return False
            # Changing orientation during allocation can discard the resize;
            # defer it until the current GTK layout pass has finished.
            GLib.idle_add(apply)

    def update_health(self, values):
        from site_health import description
        for name, fields in self.fields.items():
            value = values.get(name)
            title, tooltip = description(value)
            fields['health'].set_text(title)
            fields['health'].set_tooltip_text(tooltip)
            fields['health'].get_accessible().set_name(name+' · '+title)
            context = fields['health'].get_style_context()
            for state in ('up','blocked','error','warning','unknown'):
                context.remove_class('health-'+state)
            if value: context.add_class('health-'+value['state'])

    def set_placement(self, placement):
        self.rows.set_orientation(Gtk.Orientation.HORIZONTAL if placement == 'bottom' else Gtk.Orientation.VERTICAL)
        self.rows.set_spacing(12 if placement == 'bottom' else 2)

    def geometry(self, width, height, preference):
        bottom=preference=='bottom' and width>=1400 and height>=860
        self.set_placement('bottom' if bottom else 'right')
        desired=min(1320,width-168) if bottom else 356
        minimum=self.get_preferred_width().minimum_width
        if bottom and minimum>width-100:
            bottom=False;self.set_placement('right');desired=356
            minimum=self.get_preferred_width().minimum_width
        panel_width=max(desired,minimum)
        chrome=self.get_preferred_height_for_width(panel_width).natural_height-self.scroller.get_preferred_height_for_width(panel_width-36).natural_height
        panel_height=chrome+max(80,self.rows.get_preferred_height_for_width(panel_width-36).natural_height)
        x=round((width-panel_width)/2) if bottom else width-panel_width-40
        return max(24,x),max(48,height-panel_height-52),panel_width,panel_height

    def update(self, record, error='', connected=False, busy=False, connecting=False):
        if not SITES:
            self.status.set_text('Add your account and hosts to sites.json, then restart Nightshift.')
            self.status.set_tooltip_text('Setup: ~/.config/nightshift-home/sites.json. See docs/INTEGRATIONS.md in the project.')
            self.refresh.set_sensitive(False)
            self.connect_button.set_sensitive(False)
            return
        for name, fields in self.fields.items():
            site = normalize(record, name)
            if site:
                fields['requests'].set_text(compact(site['requests']))
                cache = f"{site['cache_percent']:.0f}%" if site['cache_percent'] is not None else '—'
                fields['detail'].set_text(f"www {compact(site['www_requests'])} · 5xx {site['server_errors']}" if 'www_requests' in site else f"Cache {cache} · 5xx {site['server_errors']}")
                fields['chart'].update(site['hourly'])
                fields['button'].set_tooltip_text(f"{name}: {site['requests']:,} requests. Click for Cloudflare details.")
            else:
                fields['requests'].set_text('—');fields['detail'].set_text('Metrics unavailable')
                fields['chart'].update([])
        if record:
            local = datetime.fromtimestamp(record['fetched_at']).astimezone()
            stamp = local.strftime('%H:%M' if local.date()==datetime.now().astimezone().date() else '%d %b · %H:%M')
            message = ('Saved · ' if error or not connected else 'Updated · ') + stamp
            if record.get('kind')=='account-hosts-v2' and connected and not error:message+=' · every 5 min'
        else:message = 'Waiting for Cloudflare'
        if busy:message = 'Refreshing…'
        if connecting:message = 'Finish sign-in in your browser'
        elif not connected and record:message += ' · connect for updates'
        elif error:message += ' · refresh unavailable'
        self.status.set_text(message)
        self.status.set_tooltip_text(error or 'Rolling 24 hours, including the current hour. Account-level adaptive analytics; exact hostname totals, with www shown separately. Counts include bots and may be estimated by Cloudflare.')
        self.refresh.set_sensitive(not busy and not connecting)
        self.connect_button.set_visible(not connected or bool(error))
        # A pending sign-in must still be reopenable/cancellable.
        self.connect_button.set_sensitive(True)
        self.connect_button.set_tooltip_text('View sign-in progress or reopen Cloudflare' if connecting else 'Connect Cloudflare for automatic updates')


def site_detail(home, name):
    site = normalize(home.cloudflare, name)
    card = css(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14), 'home-card', 'cf-detail')
    card.pack_start(text(name, 'card-title'), False, False, 0)
    if home.cloudflare:
        start=datetime.fromisoformat(home.cloudflare['period']['start'].replace('Z','+00:00')).astimezone()
        end=datetime.fromisoformat(home.cloudflare['period']['end'].replace('Z','+00:00')).astimezone()
        card.pack_start(text(f'{start:%d %b, %H:%M} – {end:%d %b, %H:%M %Z}', 'tiny'),False,False,0)
    if not site:
        card.pack_start(text('Metrics are unavailable. Your saved data will return after the next successful refresh.', 'muted'), False, False, 0)
    else:
        metrics=[('This host', f"{site['requests']:,} requests")]
        if 'www_requests' in site:metrics.append(('www.'+name,f"{site['www_requests']:,} requests"))
        if site.get('unique_ips') is not None:metrics.append(('Unique IPs',f"{site['unique_ips']:,}"))
        metrics += [('Bandwidth · this host', f"{site['bytes']/1_000_000:.1f} MB"),
                             ('Cache HIT share', f"{site['cache_percent']:.1f}%" if site['cache_percent'] is not None else '—'),
                             ('Server errors · 5xx', str(site['server_errors'])),
                             ('Client errors · 4xx', str(site['client_errors'])), ('Not found · 404', str(site['not_found']))]
        for title,value in metrics:
            row = Gtk.Box(spacing=16);row.pack_start(text(title, 'muted'), True, True, 0)
            row.pack_end(text(value, 'cf-detail-value'), False, False, 0);card.pack_start(row, False, False, 0)
        note = text('Account traffic for the named host; www is separate. Counts include bots and use Cloudflare’s adaptive estimates. They are not human visitor counts.', 'tiny')
        note.set_line_wrap(True);note.set_max_width_chars(46);card.pack_start(note, False, False, 0)
    open_button = css(Gtk.Button(label='Open Cloudflare account ↗'), 'text-button')
    open_button.connect('clicked', lambda *_: home.open_url(dashboard(name)))
    card.pack_start(open_button, False, False, 0)
    return card
