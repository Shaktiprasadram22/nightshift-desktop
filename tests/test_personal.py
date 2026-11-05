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

class FeedTests(unittest.TestCase):
    RSS=b'<rss><channel><item><title>A &amp; B</title><link>https://huggingface.co/blog/example</link><pubDate>Wed, 04 Nov 2026 17:50:10 GMT</pubDate></item><item><title>Unsafe</title><link>javascript:alert(1)</link></item></channel></rss>'

    def test_rss_parsing_and_url_filter(self):
        result=ai_feed.parse_latest(self.RSS);self.assertEqual(len(result),1);self.assertEqual(result[0]['title'],'A & B')
        self.assertIsInstance(result[0]['published'],float)
        with self.assertRaises(ValueError):ai_feed.parse_latest(b'<!DOCTYPE x [<!ENTITY boom "x">]><rss/>')

    def test_tool_metadata_and_query(self):
        payload=json.dumps({'items':[{'full_name':'org/tool','html_url':'https://github.com/org/tool','stargazers_count':42,'description':'<b>AI</b> example'}, {'html_url':'https://other.example/x'}]}).encode()
        result=ai_feed.parse_tools(payload);self.assertEqual(result[0]['description'],'AI example');self.assertEqual(len(result),1)
        self.assertIn('created%3A%3E2026-09-06',ai_feed.tools_url(1793836800))

    def test_partial_failure_keeps_last_good_source(self):
        previous={'tools':{'items':[{'title':'old'}],'updated_at':123}}
        def fetch(url):
            if 'api.github' in url:raise HTTPError(url,429,'rate limited',{},None)
            return self.RSS
        result,errors=ai_feed.refresh(previous,fetch,now=456)
        self.assertEqual(result['tools'],previous['tools']);self.assertEqual(result['latest']['updated_at'],456)
        self.assertIn('rate limit',errors['tools']);self.assertNotIn('latest',errors)

    def test_empty_success_and_offline_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'feed.json';data={'latest':{'items':ai_feed.parse_latest(self.RSS),'updated_at':123}}
            ai_feed.save_cache(data,path);self.assertEqual(ai_feed.load_cache(path),data)
            result,errors=ai_feed.refresh(data,lambda _u:(_ for _ in ()).throw(OSError('offline')))
            self.assertEqual(result,data);self.assertEqual(set(errors),{'latest','tools'})
        self.assertEqual(ai_feed.parse_latest(b'<rss><channel/></rss>'),[])
        self.assertFalse(ai_feed.safe_url('https://github.com@evil.example/a','github.com'))

if __name__=='__main__':unittest.main()
