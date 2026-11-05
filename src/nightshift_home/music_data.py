from paths import user_home
"""Validated local music history and MPRIS source selection."""
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
import json
import re
from personal_store import private_write

MUSIC_URL = 'https://music.youtube.com/'
LAST_PATH = user_home() / '.config/nightshift-home/music-last-track.json'


def clean(value, limit=300):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def music_url(value):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or parsed.hostname != 'music.youtube.com' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return ''
        video = parse_qs(parsed.query).get('v', [''])[0]
        if parsed.path == '/watch' and re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
            return MUSIC_URL + 'watch?' + urlencode({'v': video})
        return MUSIC_URL
    except ValueError:
        return ''


def track(properties):
    metadata = properties.get('Metadata', {})
    if not isinstance(metadata, dict):
        metadata = {}
    artists = metadata.get('xesam:artist', [])
    if isinstance(artists, str):
        artists = [artists]
    if not isinstance(artists, (list, tuple)):
        artists = []
    return {'title': clean(metadata.get('xesam:title')), 'artist': clean(', '.join(clean(a) for a in artists[:6] if clean(a))),
            'url': music_url(metadata.get('xesam:url'))}


def is_music(root, properties):
    identity = re.sub(r'[^a-z]', '', str(root.get('Identity', '')).lower())
    desktop = re.sub(r'[^a-z]', '', str(root.get('DesktopEntry', '')).lower())
    return 'youtubemusic' in identity or 'youtubemusic' in desktop or bool(track(properties)['url'])


def is_browser(root, name='', hint=''):
    value = ' '.join((str(root.get('Identity', '')), str(root.get('DesktopEntry', '')), name)).lower()
    if hint in ('chrome', 'chromium'):
        return any(n in value for n in ('chrome', 'chromium')) and not any(n in value for n in ('brave', 'firefox'))
    return hint in value if hint else any(n in value for n in ('chrome', 'chromium', 'brave', 'firefox'))


def permitted(properties, action):
    if properties.get('CanControl') is not True:
        return False
    key = {'Previous': 'CanGoPrevious', 'Next': 'CanGoNext', 'Play': 'CanPlay', 'Pause': 'CanPause'}.get(action)
    return bool(key and properties.get(key) is True)


def reopen_url(last):
    direct = music_url(last.get('url'))
    if direct and direct != MUSIC_URL:
        return direct
    query = clean(' '.join((last.get('title', ''), last.get('artist', ''))), 600)
    return MUSIC_URL + 'search?' + urlencode({'q': query}) if query else MUSIC_URL


class LastTrack:
    def __init__(self, path=LAST_PATH):
        self.path = Path(path)
        self.value = {'title': '', 'artist': '', 'url': ''}
        self.connection = None
        self.error = ''
        self.loaded = True
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict) or any(not isinstance(data.get(key, ''), str) for key in self.value):
                raise ValueError('Invalid last track')
            self.value = {'title': clean(data.get('title')), 'artist': clean(data.get('artist')), 'url': music_url(data.get('url'))}
            connection = data.get('connection')
            if isinstance(connection,dict) and set(connection) == {'bus','owner','name','track'} and all(isinstance(value,str) and len(value)<300 for value in connection.values()):
                self.connection = connection
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            self.loaded = False
            self.error = 'Last track could not be read'

    def remember(self, value, connection=None):
        if not value['title'] or value == self.value and connection == self.connection:
            return
        if not self.loaded:
            return
        try:
            private_write(self.path, {**value,'connection':connection})
            self.value = value.copy()
            self.connection = connection.copy() if connection else None
            self.error = ''
        except OSError:
            self.error = 'Could not save the last track'


def fingerprint(value):
    import hashlib
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
