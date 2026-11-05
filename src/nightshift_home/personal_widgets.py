"""Transparent notes and checklists, with local save and visible recovery states."""
from gi.repository import Gtk,Gdk,GLib,Pango,Atk
from clock_panel import css,text
from personal_store import NotesStore,TodoStore


def focus_editor(widget,event):
    if event.button==1:
        window=widget.get_toplevel().get_window()
        if window:window.focus(event.time)
        widget.grab_focus()
    return False


def transparent_scroller(minimum=70):
    scroller=Gtk.ScrolledWindow();scroller.set_policy(Gtk.PolicyType.EXTERNAL,Gtk.PolicyType.AUTOMATIC)
    scroller.set_min_content_width(1);scroller.set_propagate_natural_width(False)
    scroller.set_min_content_height(minimum);scroller.set_propagate_natural_height(False)
    return scroller


class NotesWidget(Gtk.Box):
    def __init__(self,home,store=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.home=home;self.store=store or NotesStore();self.pending=0;self.dirty=False
        css(self,'personal-widget','notes-widget')
        header=Gtk.Box(spacing=8);header.pack_start(text('Notes','personal-title'),True,True,0)
        self.save_button=home.small_button('document-save-symbolic','Save notes on this device',self.flush)
        header.pack_end(self.save_button,False,False,0);self.pack_start(header,False,False,0)
        self.editor=Gtk.TextView();self.editor.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.editor.set_left_margin(2);self.editor.set_right_margin(4);self.editor.set_pixels_above_lines(3);self.editor.set_pixels_below_lines(3)
        self.editor.get_accessible().set_name('Notes. Text saves automatically on this device.')
        self.editor.connect('button-press-event',focus_editor)
        self.editor.connect('focus-out-event',lambda *_:(self.flush(),False)[1])
        self.editor.set_editable(self.store.loaded)
        self.buffer=self.editor.get_buffer();self.buffer.set_text(self.store.text)
        self.scroller=transparent_scroller(70);self.scroller.add(self.editor)
        overlay=Gtk.Overlay();overlay.add(self.scroller)
        self.hint=text('An idea, a thought, something to remember…','personal-placeholder')
        self.hint.set_line_wrap(True);self.hint.set_max_width_chars(1);self.hint.set_halign(Gtk.Align.FILL);self.hint.set_valign(Gtk.Align.START)
        self.hint.set_no_show_all(True);overlay.add_overlay(self.hint);overlay.set_overlay_pass_through(self.hint,True)
        self.pack_start(overlay,True,True,0)
        self.status=text(self.store.error or 'Saved on this device','personal-status')
        self.status.set_line_wrap(True);self.status.set_max_width_chars(1);self.status.get_accessible().set_role(Atk.Role.STATUSBAR)
        self.pack_start(self.status,False,False,0)
        self.changed_handler=self.buffer.connect('changed',self.changed);self.hint.set_visible(not self.store.text)

    def append_learning(self,item):
        from learning_actions import append_note
        current=self.buffer.get_text(self.buffer.get_start_iter(),self.buffer.get_end_iter(),True)
        value,added=append_note(current,item)
        if not added:return False
        # Save the current editor buffer, including unsaved typing, in one write.
        # A failed save leaves both the buffer and its pending save untouched.
        self.store.save(value)
        if self.pending:GLib.source_remove(self.pending);self.pending=0
        cursor=self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()
        self.buffer.handler_block(self.changed_handler)
        try:
            self.buffer.set_text(value)
            self.buffer.place_cursor(self.buffer.get_iter_at_offset(cursor))
        finally:self.buffer.handler_unblock(self.changed_handler)
        self.dirty=False;self.hint.hide();self.status.set_text('Learning saved on this device')
        return True

    def changed(self,*_):
        self.dirty=True;self.hint.set_visible(self.buffer.get_char_count()==0);self.status.set_text('Saving…')
        if self.pending:GLib.source_remove(self.pending)
        self.pending=GLib.timeout_add(450,self.save_pending)

    def save_pending(self):
        self.pending=0;self.flush();return False

    def flush(self):
        if self.pending:GLib.source_remove(self.pending);self.pending=0
        if not self.dirty:return True
        value=self.buffer.get_text(self.buffer.get_start_iter(),self.buffer.get_end_iter(),True)
        try:self.store.save(value)
        except OSError:
            self.status.set_text('Not saved. Your text is still here; use Save to retry.');return False
        self.dirty=False;self.status.set_text('Saved on this device');return True


class TodoWidget(Gtk.Box):
    def __init__(self,home,store=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        self.home=home;self.store=store or TodoStore();self.rows={}
        css(self,'personal-widget','todo-widget')
        header=Gtk.Box(spacing=8);header.pack_start(text('To-do','personal-title'),True,True,0)
        self.count=text('','personal-meta');self.count.set_ellipsize(Pango.EllipsizeMode.END);header.pack_end(self.count,False,False,0);self.pack_start(header,False,False,0)
        addrow=Gtk.Box(spacing=6)
        self.entry=Gtk.Entry();self.entry.set_placeholder_text('Add a task…');self.entry.set_max_length(500);self.entry.set_width_chars(1)
        self.entry.get_accessible().set_name('New task. Press Enter to add.');self.entry.connect('activate',lambda *_:self.add_task());self.entry.connect('button-press-event',focus_editor)
        addrow.pack_start(self.entry,True,True,0)
        add=home.small_button('list-add-symbolic','Add task',self.add_task);addrow.pack_end(add,False,False,0)
        self.pack_start(addrow,False,False,0);addrow.set_sensitive(self.store.loaded)
        self.list=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        self.scroller=transparent_scroller(65);self.scroller.add(self.list);self.pack_start(self.scroller,True,True,0)
        footer=Gtk.Box(spacing=8)
        self.clear=css(Gtk.Button(label='Clear done'),'personal-link');self.clear.connect('clicked',lambda *_:self.act(self.store.clear_done))
        self.undo=css(Gtk.Button(label='Undo remove'),'personal-link');self.undo.connect('clicked',lambda *_:self.act(self.store.undo));self.undo.set_no_show_all(True)
        footer.pack_start(self.clear,False,False,0);footer.pack_end(self.undo,False,False,0);self.pack_start(footer,False,False,0)
        self.status=text(self.store.error or 'Saved on this device','personal-status');self.status.set_line_wrap(True);self.status.set_max_width_chars(1)
        self.status.get_accessible().set_role(Atk.Role.STATUSBAR);self.pack_start(self.status,False,False,0)
        self.render()

    def act(self,callback,*args,**kwargs):
        try:callback(*args,**kwargs)
        except (OSError,ValueError) as exc:
            self.status.set_text(str(exc) if isinstance(exc,ValueError) else 'Could not save that change. Your existing tasks are safe.');return False
        self.status.set_text('Saved on this device');self.render();return True

    def add_learning(self,item):
        from learning_actions import task_text
        before={entry['id'] for entry in self.store.items}
        identifier=self.store.add(task_text(item),source_url=item['url'])
        if identifier in before:return False
        edits={key:row['edit'].get_text() for key,row in self.rows.items() if row['stack'].get_visible_child_name()=='edit'}
        self.render()
        for key,value in edits.items():
            if key in self.rows:
                self.rows[key]['edit'].set_text(value);self.rows[key]['stack'].set_visible_child_name('edit')
        self.status.set_text('Learning task saved · source in its actions menu')
        return True

    def add_task(self):
        value=self.entry.get_text().strip()
        if not value:return
        try:self.store.add(value)
        except (OSError,ValueError) as exc:self.status.set_text(str(exc) if isinstance(exc,ValueError) else 'Could not save the task. Try again.');return
        self.entry.set_text('');self.status.set_text('Saved on this device');self.render();self.entry.grab_focus()

    def render(self):
        for child in self.list.get_children():child.destroy()
        self.rows={}
        if not self.store.items:
            empty=text('A clear list. Add your next small step.','personal-placeholder');empty.set_line_wrap(True);empty.set_max_width_chars(1)
            self.list.pack_start(empty,False,False,8)
        for item in self.store.items:self.build_row(item)
        remaining=sum(not i['done'] for i in self.store.items)
        self.count.set_text(f'{remaining} remaining' if self.store.items else '0 tasks')
        self.clear.set_sensitive(any(i['done'] for i in self.store.items));self.undo.set_visible(bool(self.store.undo_items))
        self.list.show_all()

    def build_row(self,item):
        identifier=item['id'];row=css(Gtk.Box(spacing=5),'todo-row')
        stack=Gtk.Stack();stack.set_transition_type(Gtk.StackTransitionType.NONE)
        check=Gtk.CheckButton();check.set_active(item['done']);check.set_hexpand(True)
        caption=text(item['text'],'task-done' if item['done'] else 'task-text')
        caption.set_line_wrap(True);caption.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR);caption.set_max_width_chars(1);caption.set_xalign(0)
        if item['done']:
            attrs=Pango.AttrList();attrs.insert(Pango.attr_strikethrough_new(True));caption.set_attributes(attrs)
        check.add(caption);check.get_accessible().set_name(item['text']);stack.add_named(check,'view')
        edit=Gtk.Entry();edit.set_text(item['text']);edit.set_max_length(500);edit.set_width_chars(1);edit.get_accessible().set_name('Edit task')
        edit.set_tooltip_text('Enter to save · Escape to cancel')
        edit.connect('button-press-event',focus_editor);stack.add_named(edit,'edit');stack.set_visible_child_name('view')
        row.pack_start(stack,True,True,0)
        def toggle(button):
            # Rebuild after the current signal, preserving the active control by ID.
            active=button.get_active()
            def commit():
                self.act(self.store.update,identifier,done=active)
                if identifier in self.rows:self.rows[identifier]['check'].grab_focus()
                return False
            GLib.idle_add(commit)
        check.connect('toggled',toggle)
        def start_edit(*_):
            stack.set_visible_child_name('edit');edit.grab_focus();edit.select_region(0,-1)
        edit.connect('activate',lambda *_:self.act(self.store.update,identifier,text=edit.get_text()))
        edit.connect('key-press-event',lambda _w,e:(stack.set_visible_child_name('view'),True)[1] if e.keyval==Gdk.KEY_Escape else False)
        menu=Gtk.Menu();edit_item=Gtk.MenuItem(label='Edit task');edit_item.connect('activate',start_edit);menu.append(edit_item)
        from ai_feed import safe_url
        if safe_url(item.get('source_url')):
            source=Gtk.MenuItem(label='Open learning source')
            source.connect('activate',lambda *_:self.home.open_url(item['source_url']));menu.append(source)
        delete=Gtk.MenuItem(label='Remove task');delete.connect('activate',lambda *_:self.act(self.store.remove,identifier));menu.append(delete);menu.show_all()
        actions=css(Gtk.MenuButton(),'icon-button');actions.add(Gtk.Image.new_from_icon_name('view-more-symbolic',Gtk.IconSize.BUTTON));actions.set_popup(menu)
        actions.get_accessible().set_name('Actions for '+item['text']);actions.set_valign(Gtk.Align.START);row.pack_end(actions,False,False,0)
        self.list.pack_start(row,False,False,0);self.rows[identifier]={'check':check,'edit':edit,'edit_action':edit_item,'stack':stack}
