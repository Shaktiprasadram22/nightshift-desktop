"""Google Photos Picker: explicit selection, PKCE, private local thumbnails.

No browser cookies or other apps' OAuth clients. Access tokens are ephemeral.
The Picker imports a selection; it does not subscribe to future library photos.
"""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import shutil
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, parse_qs, quote
from urllib.request import Request, urlopen
from data import HOME, write_json

ROOT = HOME/'.local/share/nightshift-home/photos'
INDEX = ROOT/'selection.json'
CLIENT = HOME/'.config/nightshift-home/google-photos-client.json'
SCOPE = 'https://www.googleapis.com/auth/photospicker.mediaitems.readonly'
API = 'https://photospicker.googleapis.com/v1/'

class PhotosError(Exception): pass

class Cancelled(PhotosError): pass

def selected_photos():
    try:
        items = json.loads(INDEX.read_text())['photos']
        return [v for v in items if Path(v['path']).is_relative_to(ROOT)
                and Path(v['path']).is_file()]
    except (OSError, ValueError, TypeError, KeyError): return []

def import_client(path):
    try:
        client = json.loads(Path(path).read_text())['installed']
        if not client.get('client_id', '').endswith('.apps.googleusercontent.com'):
            raise ValueError()
        if not client.get('client_secret'): raise ValueError()
    except (OSError, ValueError, TypeError, KeyError):
        raise PhotosError('Choose the JSON downloaded for a Google OAuth Desktop app.') from None
    write_json(CLIENT, {'installed': {'client_id':client['client_id'],
                                    'client_secret':client['client_secret']}})

def request_json(url, token=None, data=None, method=None, form=False):
    headers = {'Accept':'application/json'}
    if token: headers['Authorization'] = 'Bearer '+token
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urlencode(data) if form else json.dumps(data)).encode()
    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=20) as response:
            raw = response.read(2_000_000)
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        if exc.code in (401,403):
            raise PhotosError('Google access was denied. Check the Picker API and your test-user access, then reconnect.') from None
        raise PhotosError(f'Google Photos could not complete the request (HTTP {exc.code}). Try again.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise PhotosError('Google Photos is unavailable. Check your connection and try again.') from None

def authorize(open_url, status, cancel):
    try: client = json.loads(CLIENT.read_text())['installed']
    except (OSError, ValueError, KeyError): raise PhotosError('Import your Google Desktop app client first.') from None
    state = secrets.token_urlsafe(32); verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            parsed = urlsplit(self.path); query = parse_qs(parsed.query)
            valid = parsed.path == '/oauth/callback' and secrets.compare_digest(query.get('state',[''])[0],state)
            if not valid:
                self.send_response(400);self.end_headers();return
            result.update({k:v[0] for k,v in query.items()})
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.end_headers()
            self.wfile.write(b'<title>Nightshift Home</title><p>You can return to Nightshift Home.</p>')
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        server.timeout = .5
        redirect = f'http://127.0.0.1:{server.server_port}/oauth/callback'
        url = 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
            'client_id':client['client_id'],'redirect_uri':redirect,'response_type':'code',
            'scope':SCOPE,'state':state,'code_challenge':challenge,'code_challenge_method':'S256',
            'access_type':'online'})
        status('Sign in with Google in your browser.');open_url(url)
        deadline=time.monotonic()+480
        while not result and time.monotonic()<deadline:
            if cancel.is_set():raise Cancelled('Photo selection cancelled.')
            server.handle_request()
        if not result:raise PhotosError('Google sign-in timed out. Try again.')
        if 'code' not in result:raise PhotosError('Google sign-in was cancelled.')
    response=request_json('https://oauth2.googleapis.com/token',data={
        'client_id':client['client_id'],'client_secret':client['client_secret'],
        'code':result['code'],'code_verifier':verifier,'grant_type':'authorization_code',
        'redirect_uri':redirect},form=True)
    if not response.get('access_token'):raise PhotosError('Google did not grant photo access.')
    return response['access_token']

def select_photos(open_url, status, cancel):
    token=authorize(open_url,status,cancel);session=None;folder=None
    try:
        session=request_json(API+'sessions',token,{'pickingConfig':{'maxItemCount':'50'}})
        session_url=API+'sessions/'+quote(session['id'],safe='')
        picker=session['pickerUri']
        if urlsplit(picker).scheme!='https' or urlsplit(picker).hostname!='photos.google.com':
            raise PhotosError('Google returned an unexpected selection link.')
        open_url(picker);status('Choose up to 50 photos in Google Photos, then select Done.')
        deadline=time.monotonic()+600
        while not session.get('mediaItemsSet'):
            config=session.get('pollingConfig',{})
            interval=max(1,float(config.get('pollInterval','5s').removesuffix('s')))
            remaining=float(config.get('timeoutIn','600s').removesuffix('s'))
            deadline=min(deadline,time.monotonic()+remaining)
            if time.monotonic()+interval>deadline:raise PhotosError('Photo selection timed out. Try again.')
            if cancel.wait(interval):raise Cancelled('Photo selection cancelled.')
            session=request_json(session_url,token)
        items=[];page=''
        while True:
            query=urlencode({'sessionId':session['id'],'pageSize':100,'pageToken':page})
            response=request_json(API+'mediaItems?'+query,token)
            items.extend(i for i in response.get('mediaItems',[]) if i.get('type')=='PHOTO')
            page=response.get('nextPageToken','')
            if not page or len(items)>=50:break
        if not items:raise PhotosError('No photos selected. Choose still photos for the frame.')
        ROOT.mkdir(parents=True,exist_ok=True);ROOT.chmod(0o700)
        folder=ROOT/secrets.token_hex(12);folder.mkdir(mode=0o700)
        photos=[]
        for index,item in enumerate(items[:50]):
            if cancel.is_set():raise Cancelled('Photo selection cancelled.')
            status(f'Preparing photo {index+1} of {min(50,len(items))}…')
            url=item['mediaFile']['baseUrl']+'=w1280-h900'
            parsed=urlsplit(url)
            if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.googleusercontent.com'):
                raise PhotosError('Google returned an unexpected photo address.')
            request=Request(url,headers={'Authorization':'Bearer '+token})
            with urlopen(request,timeout=20) as response:content=response.read(12_000_001)
            if len(content)>12_000_000:raise PhotosError('A photo was too large. Select a smaller image.')
            path=folder/f'{index:03}.jpg';path.write_bytes(content);path.chmod(0o600)
            photos.append({'path':str(path),'selected_at':time.time()})
        # Commit the whole selection together so a failed refresh retains old photos.
        old=selected_photos();write_json(INDEX,{'photos':photos});folder=None
        for previous in {Path(p['path']).parent for p in old}:
            if previous.parent==ROOT:shutil.rmtree(previous,ignore_errors=True)
        return len(photos)
    except PhotosError:raise
    except (OSError,ValueError,KeyError,TypeError):
        raise PhotosError('The photos could not be downloaded. Your previous selection is unchanged.') from None
    finally:
        if folder:shutil.rmtree(folder,ignore_errors=True)
        if session:
            try:request_json(API+'sessions/'+quote(session['id'],safe=''),token,method='DELETE')
            except PhotosError:pass
        token=None

def show_setup(app):
    from gi.repository import Gtk,GLib
    if getattr(app,'photos_dialog',None):app.photos_dialog.present();return
    dialog=Gtk.Dialog(title='Connect Google Photos',transient_for=app.manager or app.window)
    app.photos_dialog=dialog;dialog.set_default_size(520,460)
    dialog.get_style_context().add_class('nightshift-manager')
    content=dialog.get_content_area();content.set_spacing(14);content.set_border_width(24)
    def text(value):
        item=Gtk.Label(label=value,xalign=0);item.set_line_wrap(True);item.set_max_width_chars(58)
        content.pack_start(item,False,False,0);return item
    title=text('Your photos, on your desktop');title.get_style_context().add_class('manager-title')
    text('Select photos from your Google account to rotate here. New library photos need a new selection.')
    text('One-time setup for this personal widget:\n'
         '1. Create a Google Cloud project and enable Google Photos Picker API.\n'
         '2. Configure Google Auth Platform for testing; add your Google account as a test user.\n'
         '3. Create an OAuth client of type Desktop app and download its JSON file.')
    row=Gtk.Box(spacing=8);content.pack_start(row,False,False,0)
    cloud=Gtk.Button(label='Open Google setup');row.pack_start(cloud,True,True,0)
    cloud.connect('clicked',lambda *_:app.open_url('https://console.cloud.google.com/apis/library/photospicker.googleapis.com'))
    load=Gtk.Button(label='Import client JSON…');row.pack_start(load,True,True,0)
    state=text('Client ready. Continue to choose your photos.' if CLIENT.exists() else 'Waiting for your Google Desktop app client.')
    action=Gtk.Button(label='Sign in & choose photos');action.set_sensitive(CLIENT.exists())
    content.pack_start(action,False,False,0)
    def import_file(*_):
        chooser=Gtk.FileChooserDialog(title='Google Desktop app client',transient_for=dialog,
            action=Gtk.FileChooserAction.OPEN)
        chooser.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Import',Gtk.ResponseType.OK)
        filt=Gtk.FileFilter();filt.set_name('Google client JSON');filt.add_pattern('*.json');chooser.add_filter(filt)
        if chooser.run()==Gtk.ResponseType.OK:
            try:import_client(chooser.get_filename());state.set_text('Client ready. Continue to choose your photos.');action.set_sensitive(True)
            except PhotosError as exc:state.set_text(str(exc))
        chooser.destroy()
    load.connect('clicked',import_file)
    cancel=threading.Event()
    def update_status(value):
        if app.photos_dialog is dialog:state.set_text(value)
        return False
    def finish(count,error):
        app.photos_busy=False
        if app.photos_dialog is dialog:
            load.set_sensitive(True);action.set_sensitive(True)
            state.set_text(error or f'{count} photos are ready on your desktop.')
        if count:app.photo_index=0;app.rotate_photo(False)
        return False
    def begin(*_):
        if app.photos_busy:return
        cancel.clear();app.photos_busy=True;load.set_sensitive(False);action.set_sensitive(False)
        def work():
            try:
                count=select_photos(lambda url:GLib.idle_add(app.open_url,url),
                    lambda value:GLib.idle_add(update_status,value),cancel);error=''
            except PhotosError as exc:count=0;error=str(exc)
            except Exception:count=0;error='Google Photos could not connect. Try again.'
            GLib.idle_add(finish,count,error)
        threading.Thread(target=work,name='photos-picker',daemon=True).start()
    action.connect('clicked',begin)
    dialog.add_button('Close',Gtk.ResponseType.CLOSE)
    dialog.connect('response',lambda *_:dialog.destroy())
    def close(*_):cancel.set();app.photos_dialog=None
    dialog.connect('destroy',close);dialog.show_all();dialog.present()
