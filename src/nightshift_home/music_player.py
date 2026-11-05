"""Event-driven MPRIS controller. Only an identified or linked player is controlled."""
import time
from gi.repository import Gio, GLib
from music_data import LastTrack, track, is_music, is_browser, permitted, fingerprint
from music_progress import Progress, MISSING, track_key, metadata, duration, seekable

PREFIX = 'org.mpris.MediaPlayer2.'
PATH = '/org/mpris/MediaPlayer2'
ROOT = 'org.mpris.MediaPlayer2'
PLAYER = ROOT + '.Player'
PROPS = 'org.freedesktop.DBus.Properties'


class MusicPlayer:
    def __init__(self, changed, history=None, browser_hint=''):
        self.changed = changed
        self.history = history or LastTrack()
        self.browser_hint = browser_hint
        self.bus = None
        self.bus_id = None
        self.records = {}
        self.selected = None
        self.linked_owner = None
        self.subscriptions = []
        self.active = False
        self.generation = 0
        self.busy = False
        self.error = ''
        self.cancel = None
        self.armed_until = 0
        self.baseline = {}

    def start(self):
        if self.active:
            return
        self.active = True
        self.generation += 1
        generation = self.generation
        self.cancel = Gio.Cancellable()
        self.changed()
        def connected(_source, result):
            try:
                bus = Gio.bus_get_finish(result)
            except GLib.Error:
                if self.active and generation == self.generation:
                    self.error = 'Media connection unavailable · retry from the player menu'
                    self.changed()
                return
            if not self.active or generation != self.generation:
                return
            self.bus = bus
            self.error = ''
            self.subscriptions = [
                bus.signal_subscribe('org.freedesktop.DBus', 'org.freedesktop.DBus', 'NameOwnerChanged', '/org/freedesktop/DBus', None, Gio.DBusSignalFlags.NONE, self.owner_changed),
                bus.signal_subscribe(None, PROPS, 'PropertiesChanged', PATH, PLAYER, Gio.DBusSignalFlags.NONE, self.properties_changed),
                bus.signal_subscribe(None, PLAYER, 'Seeked', PATH, None, Gio.DBusSignalFlags.NONE, self.seeked),
            ]
            def names(value, error):
                if error:
                    self.error = 'Could not discover players · retry from the player menu'
                    self.changed()
                else:
                    for name in value[0]:
                        if name.startswith(PREFIX): self.add(name)
                    self.update()
            self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'ListNames', None, '(as)', names)
            def identity(value, error):
                if not error:
                    self.bus_id = value[0]
                    self.update()
            self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'GetId', None, '(s)', identity)
        Gio.bus_get(Gio.BusType.SESSION, self.cancel, connected)

    def stop(self):
        self.active = False
        self.generation += 1
        if self.cancel: self.cancel.cancel()
        if self.bus:
            for identifier in self.subscriptions: self.bus.signal_unsubscribe(identifier)
        self.subscriptions = []
        self.records = {}
        self.selected = None
        self.bus = None
        self.busy = False
        self.changed()

    def call(self, destination, path, interface, method, parameters, reply_type, callback):
        if not self.bus:
            callback(None, 'Media connection unavailable')
            return
        generation = self.generation
        def done(connection, result):
            try:
                value, error = connection.call_finish(result).unpack(), None
            except GLib.Error as exc:
                value, error = None, exc.message
            if self.active and generation == self.generation:
                callback(value, error)
        self.bus.call(destination, path, interface, method, parameters, GLib.VariantType.new(reply_type),
                      Gio.DBusCallFlags.NO_AUTO_START, 2500, self.cancel, done)

    def add(self, name, owner=None):
        if not name.startswith(PREFIX) or len(self.records) >= 32:
            return
        if owner is None:
            def resolved(value, error):
                if not error and name not in self.records: self.add(name, value[0])
            self.call('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'GetNameOwner', GLib.Variant('(s)', (name,)), '(s)', resolved)
            return
        record = {'name': name, 'owner': owner, 'root': {}, 'properties': {}, 'progress': Progress(), 'revision': 0, 'position_request': 0}
        self.records[name] = record
        self.read(record, ROOT, 'root')
        self.read(record, PLAYER, 'properties')

    def read(self, record, interface, key):
        revision = record['revision']
        def loaded(value, error):
            if self.records.get(record['name']) is not record: return
            if key == 'properties' and revision != record['revision']:
                self.read(record, interface, key)
                return
            if error:
                self.records.pop(record['name'], None)
            else:
                record[key] = value[0]
                if key == 'properties':
                    record['progress'].sync(record[key], record[key].get('Position', MISSING))
            self.update()
        self.call(record['owner'], PATH, PROPS, 'GetAll', GLib.Variant('(s)', (interface,)), '(a{sv})', loaded)

    def owner_changed(self, _bus, _sender, _path, _interface, _signal, parameters):
        name, old, new = parameters.unpack()
        if not name.startswith(PREFIX): return
        self.records.pop(name, None)
        if old == self.linked_owner: self.linked_owner = None
        if new: self.add(name, new)
        self.update()

    def properties_changed(self, _bus, sender, _path, _interface, _signal, parameters):
        interface, changed, invalidated = parameters.unpack()
        if interface != PLAYER: return
        for record in list(self.records.values()):
            if record['owner'] != sender: continue
            record['properties'].update(changed)
            for key in invalidated: record['properties'].pop(key, None)
            record['revision'] += 1
            record['progress'].sync(record['properties'], changed.get('Position', MISSING))
            if invalidated: self.read(record, PLAYER, 'properties')
            elif any(key in changed for key in ('Metadata', 'PlaybackStatus', 'Rate')):
                self.read_position(record)
        self.update()

    def read_position(self, record):
        record['position_request'] += 1
        request, key = record['position_request'], track_key(record['properties'])
        def loaded(value, error):
            if (self.records.get(record['name']) is not record or request != record['position_request']
                    or key != track_key(record['properties'])): return
            record['progress'].sync(record['properties'], value[0] if not error else None)
            self.changed()
        self.call(record['owner'], PATH, PROPS, 'Get', GLib.Variant('(ss)', (PLAYER, 'Position')), '(v)', loaded)

    def seeked(self, _bus, sender, _path, _interface, _signal, parameters):
        for record in self.records.values():
            if record['owner'] == sender:
                record['position_request'] += 1
                record['progress'].sync(record['properties'], parameters.unpack()[0])
        self.changed()

    def seek(self, seconds, expected=None):
        record = self.selected
        if (self.busy or not record or not seekable(record['properties']) or record['progress'].position() is None
                or expected is not None and expected != (record['owner'], track_key(record['properties']))): return False
        import math
        if not isinstance(seconds,(int,float)) or not math.isfinite(seconds): return False
        position = int(max(0,min(seconds,duration(record['properties'])))*1e6)
        self.busy = True; self.error = ''; self.changed()
        def finished(_value, error):
            self.busy = False
            if error: self.error = 'Seeking unavailable · try the player in Music'
            if self.records.get(record['name']) is record: self.read_position(record)
            self.changed()
        self.call(record['owner'], PATH, PLAYER, 'SetPosition', GLib.Variant('(ox)', (metadata(record['properties'])['mpris:trackid'], position)), '()', finished)
        return True

    @staticmethod
    def signature(record):
        props = record['properties']
        value = track(props)
        return value['title'], value['artist'], props.get('PlaybackStatus')

    def arm(self):
        # Opening Music explicitly links the next new/changed playback session
        # from the default browser. Never attach an already-playing unrelated tab.
        self.armed_until = time.monotonic() + 120
        self.baseline = {r['owner']: self.signature(r) for r in self.records.values()}
        self.error = ''

    def candidates(self):
        return [r for r in self.records.values() if r['root'] and (is_music(r['root'], r['properties']) or is_browser(r['root'], r['name']))]

    def choose(self, name):
        record = self.records.get(name)
        if record not in self.candidates(): return
        self.linked_owner = record['owner']
        self.armed_until = 0
        self.error = ''
        self.update()

    def update(self):
        choices = self.candidates()
        # Reconnect only the explicitly linked owner on the same login bus and
        # the same track. A browser's unrelated tab or a new login cannot match.
        connection = self.history.connection
        if not self.linked_owner and connection and self.bus_id == connection['bus']:
            for record in choices:
                if (record['owner'] == connection['owner'] and record['name'] == connection['name']
                        and fingerprint(track(record['properties'])) == connection['track']):
                    self.linked_owner = record['owner']
                    break
        if self.armed_until > time.monotonic():
            for record in choices:
                metadata=record['properties'].get('Metadata',{})
                raw_url=metadata.get('xesam:url') if isinstance(metadata,dict) else None
                if raw_url and not track(record['properties'])['url']:
                    continue
                if (is_browser(record['root'], record['name'], self.browser_hint)
                    and record['properties'].get('PlaybackStatus') == 'Playing'
                    and track(record['properties'])['title']
                    and self.baseline.get(record['owner']) != self.signature(record)):
                    self.linked_owner = record['owner']
                    self.armed_until = 0
                    break
        linked = [r for r in choices if r['owner'] == self.linked_owner]
        identified = [r for r in choices if is_music(r['root'], r['properties'])]
        eligible = linked or identified
        eligible.sort(key=lambda r: (r['properties'].get('PlaybackStatus') != 'Playing', r is not self.selected, r['name']))
        self.selected = eligible[0] if eligible else None
        if self.selected:
            value = track(self.selected['properties'])
            connection = None
            if self.linked_owner == self.selected['owner'] and self.bus_id:
                connection = dict(bus=self.bus_id,owner=self.selected['owner'],name=self.selected['name'],track=fingerprint(value))
            self.history.remember(value,connection)
        self.changed()

    def action(self, method):
        record = self.selected
        if self.busy or not record or not permitted(record['properties'], method): return False
        self.busy = True
        self.error = ''
        self.changed()
        def finished(_value, error):
            self.busy = False
            if error: self.error = 'Player unavailable · open Music or choose its browser again'
            if self.records.get(record['name']) is record: self.read(record, PLAYER, 'properties')
            self.changed()
        self.call(record['owner'], PATH, PLAYER, method, None, '()', finished)
        return True
