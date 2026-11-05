from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from music_data import LastTrack, music_url, reopen_url, track, is_music, is_browser, permitted, fingerprint


class MusicTests(unittest.TestCase):
    def test_only_music_links_are_used_and_parameters_are_minimized(self):
        self.assertEqual(music_url('https://music.youtube.com/watch?v=abcdefghijk&list=secret&tracking=abc'), 'https://music.youtube.com/watch?v=abcdefghijk')
        for url in ('https://music.youtube.com.evil.test/watch?v=abcdefghijk', 'javascript:alert(1)', 'file:///etc/passwd', 'https://user:pass@music.youtube.com/watch?v=abcdefghijk', 'https://music.youtube.com:444/watch?v=abcdefghijk', None):
            self.assertEqual(music_url(url), '')
        self.assertTrue(reopen_url({'title':'A & B','artist':'A singer','url':''}).startswith('https://music.youtube.com/search?q=A+%26+B'))

    def test_metadata_is_plain_bounded_text_and_missing_values_are_safe(self):
        value=track({'Metadata':{'xesam:title':' A\n song ','xesam:artist':['One','Two'],'xesam:url':'https://music.youtube.com/watch?v=abcdefghijk'}})
        self.assertEqual(value['title'],'A song');self.assertEqual(value['artist'],'One, Two')
        self.assertEqual(track({'Metadata':None}),{'title':'','artist':'','url':''})
        self.assertFalse(is_music({'Identity':'Google Chrome'}, {'Metadata':{'xesam:url':'https://www.youtube.com/watch?v=abcdefghijk'}}))
        self.assertTrue(is_music({'Identity':'YouTube Music'}, {}))

    def test_capabilities_do_not_assume_unavailable_controls_exist(self):
        self.assertFalse(permitted({},'Next'))
        self.assertFalse(permitted({'CanControl':False,'CanGoNext':True},'Next'))
        self.assertTrue(permitted({'CanControl':True,'CanGoNext':True},'Next'))
        self.assertFalse(permitted({'CanControl':True,'CanPlay':True},'Pause'))
        self.assertFalse(permitted({'CanControl':True},'Quit'))

    def test_chrome_family_match_does_not_link_a_different_browser(self):
        self.assertTrue(is_browser({'Identity':'Chromium'},'org.mpris.MediaPlayer2.chromium.instance1','chrome'))
        self.assertFalse(is_browser({'Identity':'Brave'},'org.mpris.MediaPlayer2.chromium.instance2','chrome'))
        self.assertTrue(is_browser({'Identity':'Brave'},'org.mpris.MediaPlayer2.chromium.instance2','brave'))

    def test_last_track_survives_restart_with_private_permissions(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'music.json';history=LastTrack(path)
            value={'title':'Fixture track','artist':'Fixture artist','url':'https://music.youtube.com/watch?v=abcdefghijk'}
            history.remember(value)
            self.assertEqual(LastTrack(path).value,value)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            previous=path.read_bytes();history.remember({'title':'','artist':'','url':''})
            self.assertEqual(path.read_bytes(),previous)
            path.write_text('{broken');history=LastTrack(path);history.remember(value)
            self.assertEqual(path.read_text(),'{broken');self.assertTrue(history.error)

    def test_remembered_connection_is_bound_to_track_and_session(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'music.json';history=LastTrack(path)
            value={'title':'Fixture track','artist':'Fixture artist','url':''}
            connection=dict(bus='bus-fixture',owner=':1.4',name='org.mpris.MediaPlayer2.chrome',track=fingerprint(value))
            history.remember(value,connection)
            self.assertEqual(LastTrack(path).connection,connection)
            self.assertNotEqual(fingerprint({**value,'title':'Other track'}),connection['track'])
            history.remember({**value,'title':'Different identified player'})
            self.assertIsNone(LastTrack(path).connection)


if __name__=='__main__':unittest.main()
