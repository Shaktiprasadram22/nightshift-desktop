"""Read inbox headers via the Google account explicitly connected in GNOME.

Tokens remain in memory. No message bodies, email disk cache, SMTP, STORE,
EXPUNGE or read-state updates. This module is called only from a worker thread.
"""
import email
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
import imaplib
import re
import ssl
import time
from urllib.parse import quote

class MailError(Exception):
    def __init__(self, message, connect=False):
        super().__init__(message)
        self.connect = connect

def google_accounts():
    from gi.repository import Gio
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    objects = bus.call_sync('org.gnome.OnlineAccounts', '/org/gnome/OnlineAccounts',
        'org.freedesktop.DBus.ObjectManager', 'GetManagedObjects', None, None,
        Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
    accounts = []
    for path, interfaces in objects.items():
        account = interfaces.get('org.gnome.OnlineAccounts.Account', {})
        if account.get('ProviderType') == 'google':
            accounts.append({'path': path, 'email': account.get('Identity', ''),
                'enabled': not account.get('MailDisabled', True)
                    and 'org.gnome.OnlineAccounts.Mail' in interfaces})
    return bus, accounts

def parse_headers(response, account):
    """Parse literal IMAP headers; markup is never interpreted by GTK."""
    messages = []
    for item in response:
        if not isinstance(item, tuple) or len(item) < 2: continue
        header = email.message_from_bytes(item[1], policy=default)
        name, address = parseaddr(str(header.get('From', '')))
        message_id = str(header.get('Message-ID', '')).strip()
        url = 'https://mail.google.com/mail/u/' + quote(account, safe='') + '/'
        if message_id:
            url += '#search/' + quote('rfc822msgid:' + message_id, safe='')
        else: url += '#inbox'
        try: timestamp = parsedate_to_datetime(str(header.get('Date', ''))).timestamp()
        except (ValueError, TypeError, OverflowError): timestamp = None
        flag = re.search(rb'FLAGS \(([^)]*)\)', item[0])
        messages.append({'sender': (name or address or 'Unknown sender')[:180],
            'subject': str(header.get('Subject', '(No subject)'))[:500],
            'unread': bool(flag and b'\\Seen' not in flag[1]),
            'timestamp': timestamp, 'url': url})
    return list(reversed(messages))

def fetch_inbox(preferred=''):
    from gi.repository import Gio
    try: bus, accounts = google_accounts()
    except Exception:
        raise MailError('Open Online Accounts to connect Google.', True) from None
    if not accounts:
        raise MailError('Connect Google to see your inbox here.', True)
    if preferred:
        account = next((a for a in accounts if a['email'] == preferred), None)
        if not account: raise MailError('Reconnect your selected Google account.', True)
    elif len(accounts) == 1: account = accounts[0]
    else: raise MailError('Choose your Google account in widget settings.', True)
    if not account['enabled']:
        raise MailError('Enable Mail for Google in Online Accounts.', True)
    try:
        token, _expires = bus.call_sync('org.gnome.OnlineAccounts', account['path'],
            'org.gnome.OnlineAccounts.OAuth2Based', 'GetAccessToken', None, None,
            Gio.DBusCallFlags.NONE, 30000, None).unpack()
    except Exception:
        raise MailError('Sign in again under Online Accounts.', True) from None
    client = None
    try:
        client = imaplib.IMAP4_SSL('imap.gmail.com', 993,
            ssl_context=ssl.create_default_context(), timeout=12)
        auth = ('user=' + account['email'] + '\x01auth=Bearer ' + token + '\x01\x01').encode()
        # Gmail sends an error challenge on failure; finish it with an empty response.
        first = True
        def respond(_challenge):
            nonlocal first
            value = auth if first else b''
            first = False
            return value
        client.authenticate('XOAUTH2', respond)
        status, count = client.select('INBOX', readonly=True)
        if status != 'OK': raise MailError('Gmail could not open your inbox.')
        total = int(count[0])
        status, values = client.status('INBOX', '(UNSEEN)')
        match = re.search(rb'UNSEEN (\d+)', b' '.join(v for v in values if isinstance(v, bytes)))
        unread = int(match[1]) if status == 'OK' and match else None
        messages = []
        if total:
            status, response = client.fetch(f'{max(1, total-2)}:{total}',
                '(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])')
            if status != 'OK': raise MailError('Gmail could not load the latest messages.')
            messages = parse_headers(response, account['email'])
        return {'account': account['email'], 'unread': unread,
                'messages': messages, 'fetched_at': time.time()}
    except imaplib.IMAP4.error:
        raise MailError('Google mail access needs attention in Online Accounts.', True) from None
    except (OSError, ValueError):
        raise MailError('Gmail is offline. Retrying automatically.') from None
    finally:
        token = None
        if client:
            try: client.logout()
            except Exception: pass
