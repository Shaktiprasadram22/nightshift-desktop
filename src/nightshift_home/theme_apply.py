"""Prepare coordinated theme changes, then commit with a private one-step undo."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
from data import HOME,BASE
from personal_store import private_write
from theme_palette import DEFAULT,validate,color,recolor,readable

ANSI=['#18243a','#f7768e','#9ece6a','#e0af68','#7aa2f7','#bb9af7','#58d8f2','#c0d2e6',
      '#728bad','#ff91a4','#b5e890','#f0cb8e','#9fbcff','#d2b6ff','#9beaff','#edf6ff']

def digest(data):return hashlib.sha256(data).hexdigest()
def snapshot(path):
    if path.is_symlink():return {'link':str(path.readlink()),'hash':digest(path.read_bytes())}
    if not path.exists():return None
    data=path.read_bytes();return {'data':base64.b64encode(data).decode(),'mode':stat.S_IMODE(path.stat().st_mode),'hash':digest(data)}
def put(path,data,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.rgb-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,mode);os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
def restore(path,previous):
    if previous is None:path.unlink(missing_ok=True)
    elif 'link' in previous:
        path.unlink(missing_ok=True);path.symlink_to(previous['link'])
    else:put(path,base64.b64decode(previous['data']),previous['mode'])

class GioBackend:
    def supports(self,schema,key,path=None):
        try:return self.setting(schema,path).props.settings_schema.has_key(key)
        except RuntimeError:return False

    def setting(self,schema,path=None):
        from gi.repository import Gio
        source=Gio.SettingsSchemaSource.get_default()
        if schema=='org.gnome.shell.extensions.dash-to-dock':
            folder=HOME/'.local/share/gnome-shell/extensions/dash-to-dock@micxgx.gmail.com/schemas'
            if folder.is_dir():source=Gio.SettingsSchemaSource.new_from_directory(str(folder),source,False)
        spec=source.lookup(schema,True)
        if not spec:
            for root in (HOME/'.local/share/gnome-shell/extensions',Path('/usr/share/gnome-shell/extensions')):
                for folder in sorted(root.glob('*/schemas')):
                    if not (folder/'gschemas.compiled').is_file():continue
                    candidate=Gio.SettingsSchemaSource.new_from_directory(str(folder),source,False)
                    spec=candidate.lookup(schema,True)
                    if spec:break
                if spec:break
        if not spec:raise RuntimeError('The desktop setting is unavailable: '+schema)
        return Gio.Settings.new_full(spec,None,path)
    def get(self,schema,key,path=None):return self.setting(schema,path).get_value(key).unpack()
    def check(self,entry):
        from gi.repository import GLib
        schema,key,value,path=entry;s=self.setting(schema,path)
        if not s.props.settings_schema.has_key(key) or not s.is_writable(key):raise RuntimeError('This desktop setting cannot be changed: '+key)
        spec=s.props.settings_schema.get_key(key);variant=GLib.Variant(spec.get_value_type().dup_string(),value)
        if not spec.range_check(variant):raise ValueError('Invalid setting: '+key)
    def set(self,entry):
        from gi.repository import GLib
        schema,key,value,path=entry;s=self.setting(schema,path);spec=s.props.settings_schema.get_key(key)
        if not s.set_value(key,GLib.Variant(spec.get_value_type().dup_string(),value)):raise OSError('Could not update '+key)
    def sync(self):
        from gi.repository import Gio
        Gio.Settings.sync()

class ThemeEngine:
    def __init__(self,root=HOME,base=BASE,backend=None):
        self.root=Path(root);self.base=Path(base);self.templates=self.base/'theme-templates'
        self.backend=backend or GioBackend();self.state=self.root/'.config/nightshift-home/theme.json'
        self.undo_path=self.root/'.config/nightshift-home/theme-undo.json'

    def settings_plan(self,palette,theme_name,wallpaper,icons):
        accent=readable(palette['primary']);p=palette;entries=[]
        supports=getattr(self.backend,'supports',lambda *args:True)
        def add(schema,values,path=None):
            entries.extend((schema,key,value,path) for key,value in values.items() if supports(schema,key,path))
        add('org.gnome.desktop.interface',{'gtk-theme':theme_name})
        if icons:add('org.gnome.desktop.interface',{'icon-theme':icons})
        add('org.gnome.desktop.background',{'picture-uri':wallpaper.as_uri(),'picture-uri-dark':wallpaper.as_uri()})
        add('org.gnome.shell.extensions.dash-to-dock',{'custom-theme-running-dots-color':accent,'custom-theme-running-dots-border-color':accent})
        add('org.gnome.shell.extensions.zorin-tiling-shell',{'window-border-color':accent})
        profile=self.backend.get('org.gnome.Terminal.ProfilesList','default') if supports('org.gnome.Terminal.ProfilesList','default') else ''
        path=f'/org/gnome/terminal/legacy/profiles:/:{profile}/'
        if profile:add('org.gnome.Terminal.Legacy.Profile',{
            'use-theme-colors':False,'background-color':color('#0b1423',p),'foreground-color':color('#d8e8f7',p),
            'cursor-colors-set':True,'cursor-background-color':accent,'cursor-foreground-color':color('#071520',p),
            'highlight-colors-set':True,'highlight-background-color':color('#234761',p),'highlight-foreground-color':color('#e3f5ff',p),
            'palette':[color(value,p) for value in ANSI]},path)
        # The shell reloads only after all of its assets are available.
        add('org.gnome.shell.extensions.user-theme',{'name':theme_name})
        for entry in entries:self.backend.check(entry)
        return entries

    def editor_file(self,target,entries,mode='apply'):
        source=target.read_bytes() if target.exists() else b'{}\n'
        with tempfile.TemporaryDirectory(prefix='nightshift-colors-') as temporary:
            temp=Path(temporary);(temp/'source.jsonc').write_bytes(source)
            payload={'source':str(temp/'source.jsonc'),'output':str(temp/'result.jsonc'),'journal':str(temp/'journal.json'),'mode':mode,'entries':entries}
            (temp/'payload.json').write_text(json.dumps(payload))
            result=subprocess.run(['node',str(self.base/'theme_editor.cjs'),str(temp/'payload.json')],capture_output=True,timeout=15)
            if result.returncode:raise ValueError('Could not read '+target.parent.parent.name+' settings. Fix its JSON syntax, or turn off editor matching.')
            return (temp/'result.jsonc').read_bytes(),json.loads((temp/'journal.json').read_text()),digest(source)

    def prepare(self,palette):
        palette=validate(palette)
        if not (self.templates/'theme/gtk-3.0/gtk.css').exists():raise OSError('The original theme template is missing.')
        supports=getattr(self.backend,'supports',lambda *args:True)
        current=self.backend.get('org.gnome.shell.extensions.user-theme','name') if supports('org.gnome.shell.extensions.user-theme','name') else ''
        theme_name='Nightshift-RGB-B' if current=='Nightshift-RGB-A' else 'Nightshift-RGB-A'
        files={};editor_journal={};watch={}
        for source in (self.templates/'theme').rglob('*'):
            if not source.is_file():continue
            relative=source.relative_to(self.templates/'theme');data=source.read_bytes()
            if source.suffix in ('.css','.svg','.xml','.xpm','.theme'):
                data=recolor(data.decode(),palette).encode()
            if relative.as_posix()=='gnome-shell/gnome-shell.css':
                overrides=self.base/'theme-shell-overrides.css'
                if overrides.is_file():data+=b'\n'+recolor(overrides.read_text(),palette).encode()
            for name in ('Midnight-Cyan',theme_name):files[self.root/'.themes'/name/relative]=(data,0o644)
        for name in ('libadwaita.css','terminal.css'):
            files[self.root/'.local/share/desktop-styles/midnight-cyan'/name]=(recolor((self.templates/name).read_text(),palette).encode(),0o644)
        from theme_assets import fallbacks
        for relative,data in fallbacks().items():
            if not (self.templates/'theme'/relative).exists():
                for name in ('Midnight-Cyan',theme_name):files[self.root/'.themes'/name/relative]=(data,0o644)
        files[self.root/'.config/nightshift-home/theme-widgets.css']=(recolor((self.base/'style.css').read_text(),palette).encode(),0o600)
        icons=None
        if (self.templates/'icons/index.theme').exists():
            icons=theme_name+'-Icons'
            for source in (self.templates/'icons').rglob('*'):
                if not source.is_file():continue
                data=source.read_bytes()
                if source.suffix=='.svg':data=recolor(data.decode(),palette).encode()
                files[self.root/'.local/share/icons'/icons/source.relative_to(self.templates/'icons')]=(data,0o644)
        wallpaper=self.root/'.local/share/nightshift-home/theme-output'/(theme_name+'.png')
        from aurora_art import render
        with tempfile.TemporaryDirectory(prefix='nightshift-wallpaper-') as temporary:
            path=Path(temporary)/'wallpaper.png';render(path,palette=palette);files[wallpaper]=(path.read_bytes(),0o644)
        if palette['editors']:
            entries=json.loads((self.templates/'editor-colors.json').read_text())
            entries=[{**entry,'value':recolor(entry['value'],palette)} for entry in entries]
            for app in ('Code','Cursor'):
                target=self.root/'.config'/app/'User/settings.json'
                if not target.parent.is_dir():continue
                data,journal,source_hash=self.editor_file(target,entries);files[target]=(data,0o600)
                editor_journal[str(target)]=journal;watch[str(target)]=source_hash
        state={'palette':palette,'theme_name':theme_name,'applied_at':time.time()}
        files[self.state]=(json.dumps(state,indent=2).encode(),0o600)
        return {'files':files,'settings':self.settings_plan(palette,theme_name,wallpaper,icons),'state':state,'editors':editor_journal,'watch':watch}

    def commit(self,plan):
        for path,expected in plan['watch'].items():
            target=Path(path);current=target.read_bytes() if target.exists() else b'{}\n'
            if digest(current)!=expected:raise RuntimeError('Editor settings changed while preparing. Press Apply to try again.')
        old={};changes={};settings=[]
        for path,(data,mode) in plan['files'].items():
            before=snapshot(path)
            if before and before['hash']==digest(data):continue
            old[str(path)]=before;changes[str(path)]={'before':before,'after':digest(data)}
        for schema,key,value,path in plan['settings']:
            settings.append({'schema':schema,'key':key,'path':path,'before':self.backend.get(schema,key,path),'after':value})
        touched=[];applied=[]
        try:
            for path,(data,mode) in plan['files'].items():
                if str(path) not in old:continue
                put(path,data,mode);touched.append(path)
            for entry in plan['settings']:self.backend.set(entry);applied.append(entry)
            self.backend.sync()
            private_write(self.undo_path,{'files':changes,'settings':settings,'editors':plan['editors']})
        except Exception:
            # A failed Apply must not leave half the palette active.
            for path in reversed(touched):restore(path,old[str(path)])
            for record in settings:
                self.backend.set((record['schema'],record['key'],record['before'],record['path']))
            self.backend.sync();raise
        return plan['state']

    def undo(self):
        try:journal=json.loads(self.undo_path.read_text())
        except (OSError,ValueError):raise ValueError('There is no previous Apply to undo.')
        # Validate before touching any files. Keep separately edited app settings.
        editor_files={}
        for path,entries in journal['editors'].items():
            editor_files[path]=self.editor_file(Path(path),entries,'undo')[0]
        for path,record in journal['files'].items():
            if path in editor_files:continue
            target=Path(path)
            if not target.exists() or digest(target.read_bytes())!=record['after']:
                raise ValueError('A theme file changed after the last Apply. Choose a preset to apply a new theme.')
        current={path:snapshot(Path(path)) for path in journal['files']}
        current_settings=[(r['schema'],r['key'],self.backend.get(r['schema'],r['key'],r['path']),r['path']) for r in journal['settings']]
        try:
            for path,record in journal['files'].items():
                if path in editor_files:put(Path(path),editor_files[path])
                else:restore(Path(path),record['before'])
            for entry in journal['settings']:
                if self.backend.get(entry['schema'],entry['key'],entry['path'])==entry['after']:
                    self.backend.set((entry['schema'],entry['key'],entry['before'],entry['path']))
            self.backend.sync();self.undo_path.unlink()
        except Exception:
            for path,record in current.items():restore(Path(path),record)
            for entry in current_settings:self.backend.set(entry)
            self.backend.sync();raise
        from theme_palette import load_state
        return load_state(self.state)
