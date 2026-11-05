"""Small public HTTPS checks, independent of Cloudflare traffic analytics."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import subprocess
import threading
import time

from cloudflare_data import SITES
HOSTS = tuple(name for name, _ in SITES)
INTERVAL = 120


def check(host, runner=subprocess.run):
    if host not in HOSTS:
        raise ValueError('Unknown website')
    result = dict(state='unknown', code=0, milliseconds=None, checked_at=time.time())
    args = ['curl', '--silent', '--head', '--location', '--max-redirs', '3', '--proto', '=https',
            '--proto-redir', '=https', '--connect-timeout', '3', '--max-time', '8',
            '--output', '/dev/null', '--write-out', '%{json}', 'https://'+host+'/']
    try:
        response = runner(args, capture_output=True, text=True, timeout=10)
        data = json.loads(response.stdout)
        if data.get('http_code') in (405, 501):
            args.remove('--head')
            args[1:1] = ['--range', '0-0', '--max-filesize', '1048576']
            response = runner(args, capture_output=True, text=True, timeout=10)
            data = json.loads(response.stdout)
        code = int(data.get('http_code', 0))
        if response.returncode == 0 or (response.returncode == 63 and 200 <= code < 300):
            result.update(code=code, milliseconds=round(float(data.get('time_starttransfer', 0))*1000),
                          state='up' if 200 <= code < 400 else 'blocked' if code in (401,403) else 'error' if code >= 500 else 'warning')
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        pass
    return result


def description(value):
    if not value:
        return '○ Checking health…', 'Public HTTPS check every 2 minutes.'
    state, code = value['state'], value['code']
    name = dict(up='Up', blocked='Check blocked', error='HTTP error', warning='HTTP warning', unknown='Unreachable here')[state]
    suffix = f" · {value['milliseconds']} ms" if state == 'up' else f' · {code}' if code else ''
    stamp = datetime.fromtimestamp(value['checked_at']).strftime('%H:%M:%S')
    detail = f'Public HTTPS check from this computer at {stamp}. '
    detail += f'HTTP {code}. Time to response includes connection and TLS setup.' if code else 'A network, DNS, TLS, or timeout error occurred; this does not establish a global outage.'
    return ('● ' if state == 'up' else '○ ')+name+suffix, detail+' Checked every 2 minutes; separate from traffic totals.'


class HealthMonitor:
    def __init__(self, changed, checker=check):
        from gi.repository import GLib
        self.glib, self.changed, self.checker = GLib, changed, checker
        self.values, self.source, self.busy, self.active, self.generation = {}, 0, False, False, 0

    def start(self):
        if self.active:
            return
        self.active = True
        self.refresh()
        self.source = self.glib.timeout_add_seconds(INTERVAL, self.refresh)

    def stop(self):
        self.active = False
        self.generation += 1
        if self.source:
            self.glib.source_remove(self.source)
            self.source = 0

    def refresh(self):
        if not self.active or self.busy:
            return True
        self.busy = True
        generation = self.generation
        def work():
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    values = dict(zip(HOSTS, pool.map(self.checker, HOSTS)))
            except Exception:
                values = {host: dict(state='unknown', code=0, milliseconds=None, checked_at=time.time()) for host in HOSTS}
            def finish():
                self.busy = False
                if self.active and generation == self.generation:
                    self.values = values
                    self.changed(values)
                elif self.active:
                    self.refresh()
                return False
            self.glib.idle_add(finish)
        threading.Thread(target=work, daemon=True).start()
        return True
