"""MPRIS position math: local extrapolation, never a per-second D-Bus poll."""
import math
import re
import time

MISSING = object()


def metadata(props):
    data = props.get('Metadata', {})
    return data if isinstance(data, dict) else {}


def duration(props):
    value = metadata(props).get('mpris:length')
    return value/1e6 if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and 0 < value < 2**63 else None


def track_key(props):
    data = metadata(props)
    return str(data.get('mpris:trackid', '')), str(data.get('xesam:title', '')), str(data.get('xesam:artist', ''))


def seekable(props):
    identifier = metadata(props).get('mpris:trackid', '')
    return bool(props.get('CanControl') is True and props.get('CanSeek') is True and duration(props)
                and isinstance(identifier, str) and re.fullmatch(r'(?:/[A-Za-z0-9_]+)+', identifier)
                and identifier != '/org/mpris/MediaPlayer2/TrackList/NoTrack')


def stamp(seconds):
    if seconds is None:
        return '—:—'
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f'{minutes}:{seconds:02}'


class Progress:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.at = clock()
        self.seconds, self.length, self.key = None, None, None
        self.playing, self.rate = False, 1.0

    def position(self):
        if self.seconds is None:
            return None
        value = self.seconds + (max(0, self.clock()-self.at)*self.rate if self.playing else 0)
        return max(0, min(value, self.length)) if self.length else max(0, value)

    def sync(self, props, microseconds=MISSING):
        value, key = self.position(), track_key(props)
        if key != self.key:
            value = None
        if microseconds is not MISSING:
            value = microseconds/1e6 if isinstance(microseconds, (float,int)) and not isinstance(microseconds,bool) and math.isfinite(microseconds) and microseconds >= 0 else None
        self.seconds, self.key, self.at, self.length = value, key, self.clock(), duration(props)
        self.playing = props.get('PlaybackStatus') == 'Playing'
        rate = props.get('Rate', 1.0)
        self.rate = rate if isinstance(rate,(int,float)) and math.isfinite(rate) and 0 < rate <= 16 else 1.0
