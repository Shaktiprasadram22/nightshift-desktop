import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import ai_feed
from personal_store import NotesStore,TodoStore
from layout import find_free_rect

class PersonalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_note_roundtrip_and_private_permissions(self):
        path=self.root/'notes.json';notes=NotesStore(path)
        notes.save('First line\nଓଡ଼ିଆ · a thought ✨')
        self.assertEqual(NotesStore(path).text,notes.text)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_failed_save_keeps_previous_document(self):
        path=self.root/'notes.json';notes=NotesStore(path);notes.save('Original')
        with patch('personal_store.os.replace',side_effect=OSError('full disk')):
            with self.assertRaises(OSError):notes.save('New text')
        self.assertEqual(notes.text,'Original');self.assertEqual(NotesStore(path).text,'Original')
        self.assertEqual(list(self.root.iterdir()),[path])

    def test_corrupt_data_is_preserved(self):
        for cls in (NotesStore,TodoStore):
            path=self.root/cls.__name__;path.write_text('broken')
            store=cls(path);self.assertFalse(store.loaded)
            with self.assertRaises(OSError):store.save('new') if cls is NotesStore else store.add('new')
            self.assertEqual(path.read_text(),'broken')

    def test_task_lifecycle_and_persistent_undo(self):
        path=self.root/'todo.json';todo=TodoStore(path)
        first=todo.add('  Read a guide  ');second=todo.add('Try an example')
        todo.update(first,done=True);todo.update(second,text='Build a small example');todo.clear_done()
        reloaded=TodoStore(path);self.assertEqual(len(reloaded.items),1);reloaded.undo()
        self.assertEqual(len(reloaded.items),2);self.assertTrue(reloaded.items[1]['done'])
        reloaded.remove(second);TodoStore(path).undo()
        self.assertEqual({i['id'] for i in TodoStore(path).items},{first,second})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_failed_task_write_does_not_change_state(self):
        todo=TodoStore(self.root/'todo.json');identifier=todo.add('Keep me')
        with patch('personal_store.private_write',side_effect=OSError()):
            with self.assertRaises(OSError):todo.update(identifier,done=True)
        self.assertFalse(todo.items[0]['done'])
        todo.remove(identifier);todo.update(identifier,done=True) # queued toggle after removal
        self.assertEqual(todo.items,[])

    def test_new_placement_respects_existing_widgets(self):
        occupied=[[140,100,360,400],[1437,102,440,175],[1495,354,356,412]]
        result=find_free_rect((140,130,360,260),occupied,(1920,1080),(280,200))
        x,y,w,h=result
        self.assertTrue(all(x+w<=a or a+c<=x or y+h<=b or b+d<=y for a,b,c,d in occupied))

if __name__=='__main__':unittest.main()
