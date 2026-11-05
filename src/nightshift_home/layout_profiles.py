from paths import user_home
"""Optional widget presets, with private saves and recoverable transactions."""
import copy
import json
import math
import fcntl
from contextlib import contextmanager
from pathlib import Path
from layout import NAMES, MINIMUM, clamp_rect
from personal_store import private_write

TITLES = {'Coding': 'Tasks, notes, system and websites. Keep your saved positions.',
          'Focus': 'Clock, notes and tasks, with a quiet center.',
          'Chill': 'Clock and music, with Photos and your theme controls.'}


def visibility_key(name):
    return 'show_'+(name[5:] if name.startswith('icon-') else name.replace('-', '_'))


KEYS = {visibility_key(name) for name in NAMES}


def validate(value):
    if not isinstance(value, dict) or not isinstance(value.get('items'),dict) or not isinstance(value.get('visibility'),dict):
        raise ValueError('Invalid saved layout')
    for name, item in value['items'].items():
        if name not in NAMES or not isinstance(item,dict): raise ValueError('Invalid widget')
        rect, screen = item.get('rect',[]), item.get('screen',[])
        if (len(rect) != 4 or len(screen) != 2 or not all(type(n) in (int,float) and math.isfinite(n) for n in rect+screen)
                or min(screen) <= 0 or min(rect[2:]) <= 0): raise ValueError('Invalid widget size')
    if any(key not in KEYS or type(flag) is not bool for key,flag in value['visibility'].items()):
        raise ValueError('Invalid visibility')
    result = copy.deepcopy(value)
    result['visibility']['show_shortcuts'] = True
    return result


def snapshot(home):
    geo = home.screen_geometry(); screen = (geo.width, geo.height)
    return {'items': {name: {'rect': home.widget_rect(name), 'screen': list(screen)} for name in NAMES if name in home.windows},
            'visibility': {key: bool(home.config.get(key,True)) for key in KEYS}}


def built_in(name, current, screen):
    value = validate(current)
    groups = {'Coding': {'clock','notes','todo','system','cloudflare','icon-google','icon-handy','icon-theme','icon-github','icon-codex'},
              'Focus': {'clock','notes','todo'}, 'Chill': {'clock','music','icon-photos','icon-theme','icon-handy'}}
    visible = groups[name] | {'shortcuts'}
    value['visibility'] = {key: False for key in KEYS}
    for widget in visible: value['visibility'][visibility_key(widget)] = True
    if name == 'Coding': return value
    sw, sh = screen
    # On small displays stack the essentials; these presets remain manually editable.
    if sw < 1000 or sh < 760:
        for widget in ('icon-photos','icon-theme','icon-handy'):
            value['visibility'][visibility_key(widget)] = False
        if name == 'Focus':
            value['visibility']['show_notes'] = False
            geometry = {'clock': ((sw-300)//2,60,300,140), 'todo': ((sw-300)//2,220,300,min(340,sh-310))}
        else:
            geometry = {'clock': ((sw-300)//2,60,300,140), 'music': ((sw-360)//2,225,360,210)}
    else:
        geometry = {'clock': (sw//2-220, max(80,sh//7),440,175)}
        if name == 'Focus':
            geometry.update(notes=(max(40,sw//2-380),sh//2-55,340,260), todo=(sw//2+40,sh//2-55,340,340))
        else:
            geometry['music'] = (sw//2-240,sh//2-60,480,240)
            for index,widget in enumerate(('icon-photos','icon-theme','icon-handy')):
                geometry[widget] = (sw//2-142+index*100,sh//2+212,84,106)
    geometry['shortcuts'] = (sw-338,sh-66,314,40)
    for key,rect in geometry.items():
        value['items'][key] = {'rect':clamp_rect(rect,screen,MINIMUM[key]),'screen':list(screen)}
    return value


@contextmanager
def locked(directory):
    directory = Path(directory); directory.mkdir(parents=True,exist_ok=True)
    with (directory/'layout.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        yield


def _recover(directory):
    journal = directory/'layout-transaction.json'
    if not journal.exists(): return
    record = json.loads(journal.read_text())
    for name in ('config.json','layout.json','profiles.json'):
        value = record[name]
        if value is not None and not isinstance(value,dict): raise ValueError('Invalid layout recovery record')
    for name in ('config.json','layout.json','profiles.json'):
        if record[name] is None: (directory/name).unlink(missing_ok=True)
        else: private_write(directory/name,record[name])
    journal.unlink()


def recover(directory):
    directory = Path(directory)
    with locked(directory): _recover(directory)


def commit(directory, values):
    directory = Path(directory)
    if set(values) != {'config.json','layout.json','profiles.json'}: raise ValueError('Incomplete layout transaction')
    with locked(directory):
        _recover(directory)
        before = {name: json.loads((directory/name).read_text()) if (directory/name).exists() else None for name in values}
        journal = directory/'layout-transaction.json'
        private_write(journal,before)
        try:
            for name,value in values.items(): private_write(directory/name,value)
            journal.unlink()
        except OSError:
            _recover(directory)
            raise


class Profiles:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory/'profiles.json'
        self.data = {'profiles': {}, 'previous': None, 'replaced': None}
        self.error = ''
        try:
            recover(self.directory)
            if self.path.exists():
                saved = json.loads(self.path.read_text())
                self.data['profiles'] = {name:validate(value) for name,value in saved['profiles'].items() if name in TITLES}
                if saved.get('previous'): self.data['previous'] = validate(saved['previous'])
                if saved.get('replaced'):
                    name,value = saved['replaced']
                    if name not in TITLES: raise ValueError()
                    self.data['replaced'] = [name, validate(value) if value else None]
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            self.error = 'Saved layouts could not be read. The original files are preserved.'

    def save(self, name, current):
        if self.error: raise OSError(self.error)
        if name not in TITLES: raise ValueError('Unknown layout')
        value = copy.deepcopy(self.data)
        value['replaced'] = [name,value['profiles'].get(name)]
        value['profiles'][name] = validate(current)
        private_write(self.path,value)
        self.data = value

    def undo_save(self):
        if self.error: raise OSError(self.error)
        if not self.data['replaced']: return
        value = copy.deepcopy(self.data)
        name,old = value['replaced']
        if old: value['profiles'][name] = old
        else: value['profiles'].pop(name,None)
        value['replaced'] = None
        private_write(self.path,value); self.data = value

    def apply(self, home, name=None):
        if self.error: raise OSError(self.error)
        current = snapshot(home)
        geo = home.screen_geometry()
        target = self.data['previous'] if name is None else self.data['profiles'].get(name) or built_in(name,current,(geo.width,geo.height))
        if not target: return
        target = validate(target)
        config = dict(home.config); config.update(target['visibility'])
        saved = copy.deepcopy(self.data); saved['previous'] = current
        if home.notes_widget and not home.notes_widget.flush():
            raise OSError('Notes are still saving. Try applying the layout again.')
        commit(self.directory, {'config.json':config,'layout.json':target['items'],'profiles.json':saved})
        self.data = saved
        home.close_detail()
        if home.arranging: home.end_arrange()
        home.config, home.layout.items = config, target['items']
        home.apply_layout()
        for key in target['items']:
            if key in home.windows: home.place_widget(key,home.windows[key]._target_rect)
        if home.manager: home.manager.destroy()


def create_window(home, directory=None):
    from gi.repository import Gtk
    from clock_panel import css, text
    store = Profiles(directory or user_home()/'.config/nightshift-home')
    window = Gtk.ApplicationWindow(application=home,title='Saved desktop layouts')
    css(window,'nightshift-manager'); window.set_default_size(450,390); window.set_position(Gtk.WindowPosition.CENTER)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14); body.set_border_width(24)
    scroller = Gtk.ScrolledWindow(); scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroller.add(body);window.add(scroller)
    title = text('Your desktop, three ways','manager-title');title.set_line_wrap(True);title.set_max_width_chars(1)
    body.pack_start(title,False,False,0)
    note = text('Save widget positions, sizes and visibility. Your current layout stays in place until you click Apply.','muted')
    note.set_line_wrap(True);note.set_max_width_chars(45);body.pack_start(note,False,False,0)
    choice = Gtk.ComboBoxText()
    for name in TITLES: choice.append(name,name)
    choice.set_active(0);choice.get_accessible().set_name('Desktop layout')
    body.pack_start(choice,False,False,0)
    description = text('','muted');description.set_line_wrap(True);description.set_max_width_chars(42);body.pack_start(description,False,False,0)
    status = text(store.error,'personal-status');status.set_line_wrap(True);status.set_max_width_chars(42)
    apply = Gtk.Button(label='Apply layout');save = Gtk.Button(label='Save current desktop to this layout')
    restore = Gtk.Button(label='Restore previous desktop');undo = Gtk.Button(label='Undo last preset save')
    def refresh(*_):
        name = choice.get_active_id()
        description.set_text('Your saved widget positions and visibility.' if name in store.data['profiles'] else TITLES[name])
        restore.set_sensitive(bool(store.data['previous']) and not store.error)
        undo.set_sensitive(bool(store.data['replaced']) and not store.error)
    def action(callback, message):
        try: callback();status.set_text(message)
        except (OSError,ValueError) as exc: status.set_text(str(exc) or 'Could not save the layout. Try again.')
        refresh()
    choice.connect('changed',refresh)
    apply.connect('clicked',lambda *_:action(lambda:store.apply(home,choice.get_active_id()),choice.get_active_id()+' applied. Your previous desktop can be restored below.'))
    save.connect('clicked',lambda *_:action(lambda:store.save(choice.get_active_id(),snapshot(home)),'Current desktop saved as '+choice.get_active_id()+'.'))
    restore.connect('clicked',lambda *_:action(lambda:store.apply(home),'Previous desktop restored.'))
    undo.connect('clicked',lambda *_:action(store.undo_save,'Preset save undone.'))
    for button in (apply,save,restore,undo):
        button.get_child().set_line_wrap(True);button.get_child().set_max_width_chars(30)
        button.set_sensitive(not store.error); body.pack_start(button,False,False,0)
    body.pack_start(status,False,False,0);refresh()
    window.store = store
    window.choice,window.apply_button,window.restore_button = choice,apply,restore
    window.connect('key-press-event',lambda _w,event: (window.destroy() or True) if event.keyval == 65307 else False)
    return window
