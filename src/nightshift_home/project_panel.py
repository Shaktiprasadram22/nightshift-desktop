from paths import user_home
"""A compact project popup; repository work only runs when requested."""
from pathlib import Path
import json
import threading
from gi.repository import Gtk, GLib, Pango
from clock_panel import css, text
from launcher_catalog import discover_projects
from personal_store import private_write
import project_status


class ProjectWindow(Gtk.ApplicationWindow):
    def __init__(self, home, state_path=None, discover=True):
        super().__init__(application=home,title='Project status')
        self.home = home
        self.path = Path(state_path) if state_path else user_home()/'.config/nightshift-home/project.json'
        self.selected, self.serial, self.alive = None, 0, True
        self.saved, self.read_error = '', ''
        try:
            if self.path.exists():
                saved = json.loads(self.path.read_text())
                if not isinstance(saved.get('path'),str): raise ValueError()
                self.saved = saved['path']
        except (OSError,ValueError,TypeError,AttributeError): self.read_error = 'Saved project could not be read. The original file is preserved.'
        css(self,'nightshift-manager');self.set_default_size(470,390);self.set_position(Gtk.WindowPosition.CENTER)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);body.set_border_width(24)
        scroller = Gtk.ScrolledWindow();scroller.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroller.add(body);self.add(scroller)
        heading = Gtk.Box(spacing=12)
        title = text('Project status','manager-title');title.set_line_wrap(True);title.set_max_width_chars(1)
        heading.pack_start(title,True,True,0)
        self.refresh = home.small_button('view-refresh-symbolic','Refresh Git status',self.load_status);heading.pack_end(self.refresh,False,False,0);body.pack_start(heading,False,False,0)
        row = Gtk.Box(spacing=9)
        self.choice = Gtk.ComboBoxText();self.choice.set_hexpand(True);self.choice.get_accessible().set_name('Project folder')
        renderer = self.choice.get_cells()[0];renderer.set_property('ellipsize',Pango.EllipsizeMode.MIDDLE);renderer.set_property('width-chars',22)
        self.choice.connect('changed',self.choose);row.pack_start(self.choice,True,True,0)
        choose = home.small_button('folder-open-symbolic','Choose a project folder',self.browse);row.pack_end(choose,False,False,0);body.pack_start(row,False,False,0)
        self.folder = text('Choose a project folder','muted');self.folder.set_ellipsize(Pango.EllipsizeMode.MIDDLE);self.folder.set_max_width_chars(1);body.pack_start(self.folder,False,False,0)
        self.branch = text('Ready when you are','project-branch');self.branch.set_line_wrap(True);self.branch.set_max_width_chars(35);body.pack_start(self.branch,False,False,0)
        self.counts = text('Git branch and local changes appear here.','muted');self.counts.set_line_wrap(True);self.counts.set_max_width_chars(40);body.pack_start(self.counts,False,False,0)
        self.status = text(self.read_error or 'Checking local project folders…','personal-status');self.status.set_line_wrap(True);self.status.set_max_width_chars(42);body.pack_start(self.status,False,False,0)
        actions = Gtk.Box(spacing=12)
        self.editor = Gtk.Button(label='Open editor');self.terminal = Gtk.Button(label='Open terminal')
        for button,kind in ((self.editor,'editor'),(self.terminal,'terminal')):
            button.set_sensitive(False);button.connect('clicked',lambda _b,k=kind:self.launch(k));actions.pack_start(button,True,True,0)
        body.pack_start(actions,False,False,0)
        note = text('Local status only. Remote ahead/behind counts use your last Git fetch.','muted');note.set_line_wrap(True);note.set_max_width_chars(42);body.pack_start(note,False,False,0)
        self.connect('destroy',self.destroyed)
        self.connect('key-press-event',lambda _w,event:(self.destroy() or True) if event.keyval == 65307 else False)
        if discover:
            sessions = list(home.sessions)
            def work():
                projects = discover_projects(user_home(),sessions)
                if self.saved and Path(self.saved).is_dir(): projects.insert(0,Path(self.saved))
                GLib.idle_add(self.populate,projects)
            threading.Thread(target=work,daemon=True).start()

    def destroyed(self,*_): self.alive = False;self.serial += 1

    def populate(self,projects):
        if not self.alive: return False
        self.choice.remove_all();seen = set()
        for project in projects:
            path = str(project)
            if path in seen: continue
            seen.add(path);self.choice.append(path,project.name+' · '+str(project.parent).replace(str(user_home()),'~',1))
        if self.saved in seen: self.choice.set_active_id(self.saved)
        elif seen: self.choice.set_active(0)
        else: self.status.set_text(self.read_error or 'No projects found. Use the folder button to choose one.')
        return False

    def choose(self,*_):
        selected = self.choice.get_active_id()
        if not selected: return
        self.selected = Path(selected);self.folder.set_text(selected);self.folder.set_tooltip_text(selected)
        if not self.read_error:
            try: private_write(self.path,{'path':selected})
            except OSError: self.read_error = 'Could not remember this project. You can still use it now.'
        self.load_status()

    def browse(self):
        dialog = Gtk.FileChooserDialog(title='Choose a project folder',transient_for=self,action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Choose folder',Gtk.ResponseType.OK)
        if self.selected and self.selected.is_dir(): dialog.set_current_folder(str(self.selected))
        def response(widget,result):
            if result == Gtk.ResponseType.OK:
                path = widget.get_filename()
                if path:
                    self.choice.append(path,Path(path).name);self.choice.set_active_id(path)
            widget.destroy()
        dialog.connect('response',response);dialog.show_all()

    def load_status(self):
        if not self.selected: return
        self.serial += 1; serial,path = self.serial,self.selected
        self.refresh.set_sensitive(False);self.branch.set_text('Reading Git status…');self.counts.set_text('')
        for button in (self.editor,self.terminal): button.set_sensitive(path.is_dir())
        self.status.set_text('')
        def work():
            try: value,error = project_status.inspect(path),''
            except RuntimeError as exc: value,error = None,str(exc)
            def finish():
                if not self.alive or serial != self.serial: return False
                self.refresh.set_sensitive(True)
                if error:
                    self.branch.set_text('Status unavailable');self.status.set_text(error)
                else:
                    self.branch.set_text(value['branch'])
                    self.counts.set_text(f"{value['staged']} staged · {value['unstaged']} unstaged\n{value['untracked']} untracked entries · {value['conflicts']} conflicts")
                    remote = f" · ↑ {value['ahead']} ahead / ↓ {value['behind']} behind" if value['upstream'] else ''
                    self.status.set_text(self.read_error or ('Working tree clean' if not value['changed'] else f"{value['changed']} changed entries")+remote)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=work,daemon=True).start()

    def launch(self,kind):
        if not self.selected: return
        try: project_status.launch(self.selected,kind,self.home.config['project_editor'])
        except (OSError,RuntimeError) as exc: self.status.set_text(str(exc))
