"""A separate, read-only desktop OAuth client for Cloudflare's official MCP.

PKCE and a loopback callback keep authorization in the browser. This module does
not read or share Codex credentials. Tokens are private to this desktop widget.
"""
import base64
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from data import HOME

ORIGIN = 'https://mcp.cloudflare.com'
RESOURCE = ORIGIN + '/mcp'
SCOPES = 'offline_access user:read account:read analytics.read'
TOKEN_FILE = HOME / '.config/nightshift-home/cloudflare-oauth.json'
LOCK = threading.RLock()


class ConnectionError(RuntimeError):
    pass


def read_tokens():
    try:
        value = json.loads(TOKEN_FILE.read_text())
        if (isinstance(value.get('access_token'),str) and value['access_token']
                and isinstance(value.get('client_id'),str) and value['client_id']
                and isinstance(value.get('expires_at'),(int,float))):
            return value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {}


def connected():
    value = read_tokens()
    return bool(value and (value.get('refresh_token') or value.get('expires_at', 0) > time.time()))


def save_tokens(value):
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.cloudflare-', dir=TOKEN_FILE.parent)
    try:
        # mkstemp creates the file with mode 0600, before any token is written.
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream)
        os.replace(temporary, TOKEN_FILE)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def decode_response(raw, content_type='application/json', request_id=None):
    if 'text/event-stream' not in content_type:
        return json.loads(raw)
    # Streamable HTTP may return one or more SSE messages, including notices.
    for block in raw.replace('\r\n', '\n').split('\n\n'):
        payload = '\n'.join(line[5:].lstrip() for line in block.splitlines() if line.startswith('data:'))
        if not payload:continue
        value = json.loads(payload)
        if request_id is None or value.get('id') == request_id:return value
    raise ConnectionError('Cloudflare returned no analytics response. Try again shortly.')


def request(url, payload=None, headers=None, form=False, request_id=None):
    if urlparse(url).scheme != 'https' or urlparse(url).netloc != 'mcp.cloudflare.com':
        raise ConnectionError('The Cloudflare connection endpoint is not trusted.')
    fields = {'User-Agent': 'Nightshift-Desktop/1.0', 'Accept': 'application/json'}
    fields.update(headers or {})
    data = None
    if payload is not None:
        data = (urlencode(payload) if form else json.dumps(payload)).encode()
        fields['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    try:
        with urlopen(Request(url, data=data, headers=fields), timeout=25) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:raise ConnectionError('Cloudflare returned too much data. Saved figures are still shown.')
            return (decode_response(raw.decode(), response.headers.get('Content-Type', ''), request_id) if raw else {}), dict(response.headers)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise ConnectionError('Cloudflare authorization needs attention. Reconnect with Analytics read access.') from None
        if exc.code == 429:raise ConnectionError('Cloudflare is rate limiting requests. The widget will try again later.') from None
        raise ConnectionError(f'Cloudflare could not refresh (HTTP {exc.code}). Saved figures are still shown.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ConnectionError('Cloudflare is unreachable. Saved figures are still shown.') from None


def merge_tokens(response, previous):
    if not response.get('access_token'):raise ConnectionError('Cloudflare did not finish sign-in. Try connecting again.')
    return {**previous, **{k: response[k] for k in ('access_token', 'refresh_token', 'scope', 'token_type') if k in response},
            'expires_at': time.time() + float(response.get('expires_in', 3600))}


def access_token():
    with LOCK:
        value = read_tokens()
        if not value:raise ConnectionError('Connect Cloudflare to enable automatic updates.')
        if value.get('expires_at', 0) < time.time() + 90:
            if not value.get('refresh_token'):raise ConnectionError('Cloudflare sign-in has expired. Connect again to resume updates.')
            response, _ = request(ORIGIN + '/token', {
                'grant_type': 'refresh_token', 'refresh_token': value['refresh_token'],
                'client_id': value['client_id'], 'resource': RESOURCE}, form=True)
            value = merge_tokens(response, value)
            save_tokens(value)
        return value['access_token']


def authorize(open_browser, cancelled=None):
    """Runs in a worker thread. open_browser receives only the consent URL."""
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args):pass  # Authorization codes never enter logs.
        def do_GET(self):
            parsed = urlparse(self.path)
            values = parse_qs(parsed.query)
            valid = (parsed.path == '/callback' and secrets.compare_digest(values.get('state', [''])[0], state)
                     and values.get('iss', [ORIGIN])[0] == ORIGIN)
            if not valid:
                self.send_error(400, 'Invalid sign-in callback');return
            if values.get('error'):
                result['error'] = 'Cloudflare sign-in was cancelled. Saved figures are still available.'
                message = 'Connection cancelled. You can return to your desktop.'
            elif values.get('code'):
                result['code'] = values['code'][0]
                message = 'Authorization received. You can return to your desktop while Nightshift verifies the connection.'
            else:
                self.send_error(400, 'Missing authorization code');return
            body = ('<!doctype html><meta charset="utf-8"><title>Nightshift · Cloudflare</title>'
                    '<style>body{background:#0c1728;color:#e1ecfa;font:18px system-ui;max-width:620px;margin:15vh auto;padding:24px}h1{color:#58d8f2}</style>'
                    '<h1>Nightshift Home</h1><p>' + message + '</p>').encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server = HTTPServer(('127.0.0.1', 0), Callback)
    server.timeout = .5
    redirect = f'http://127.0.0.1:{server.server_port}/callback'
    try:
        metadata, _ = request(ORIGIN + '/.well-known/oauth-authorization-server')
        if not set(SCOPES.split()).issubset(metadata.get('scopes_supported', [])):
            raise ConnectionError('The Cloudflare server does not offer the requested read-only analytics connection.')
        registration, _ = request(metadata['registration_endpoint'], {
            'client_name': 'Nightshift Home · Read-only site insights',
            'redirect_uris': [redirect], 'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'], 'token_endpoint_auth_method': 'none', 'scope': SCOPES})
        client_id = registration['client_id']
        authorization = metadata['authorization_endpoint']
        if authorization != ORIGIN + '/authorize':raise ConnectionError('The Cloudflare consent endpoint changed. Connection stopped.')
        open_browser(authorization + '?' + urlencode({
            'client_id': client_id, 'redirect_uri': redirect, 'response_type': 'code',
            'scope': SCOPES, 'state': state, 'code_challenge': challenge,
            'code_challenge_method': 'S256', 'resource': RESOURCE}))
        deadline = time.monotonic() + 600
        while not result and time.monotonic() < deadline and not (cancelled and cancelled.is_set()):
            server.handle_request()
        if cancelled and cancelled.is_set():raise ConnectionError('Cloudflare sign-in was cancelled.')
        if result.get('error'):raise ConnectionError(result['error'])
        if not result.get('code'):raise ConnectionError('Cloudflare sign-in did not finish. Click Connect to try again.')
        response, _ = request(metadata['token_endpoint'], {
            'grant_type': 'authorization_code', 'code': result['code'], 'redirect_uri': redirect,
            'client_id': client_id, 'code_verifier': verifier, 'resource': RESOURCE}, form=True)
        if cancelled and cancelled.is_set():raise ConnectionError('Cloudflare sign-in was cancelled.')
        with LOCK:save_tokens(merge_tokens(response, {'client_id': client_id}))
    finally:
        server.server_close()


def execute(code, account):
    headers = {'Authorization': 'Bearer ' + access_token(), 'Accept': 'application/json, text/event-stream'}
    response, metadata = request(RESOURCE, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                   'clientInfo': {'name': 'nightshift-home', 'version': '1.0'}}}, headers, request_id=1)
    if response.get('error'):raise ConnectionError('Cloudflare could not start an analytics connection.')
    headers['MCP-Protocol-Version'] = response.get('result', {}).get('protocolVersion', '2025-03-26')
    session = next((v for k, v in metadata.items() if k.lower() == 'mcp-session-id'), None)
    if session:headers['Mcp-Session-Id'] = session
    request(RESOURCE, {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, headers)
    response, _ = request(RESOURCE, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
        'params': {'name': 'execute', 'arguments': {'account_id': account, 'code': code, 'truncate': False}}}, headers, request_id=2)
    result = response.get('result', {})
    if response.get('error') or result.get('isError'):
        raise ConnectionError('Cloudflare could not read these sites. Reconnect with Analytics read access.')
    value = result.get('structuredContent')
    if isinstance(value, dict) and ('data' in value or 'errors' in value):return value
    for item in result.get('content', []):
        if item.get('type') == 'text':
            try:return json.loads(item['text'])
            except ValueError:continue
    raise ConnectionError('Cloudflare returned an incomplete analytics response. Saved figures are still shown.')
