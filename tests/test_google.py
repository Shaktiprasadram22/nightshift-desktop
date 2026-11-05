import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
import google_mail as mail
import google_photos as photos
class GoogleChecks(unittest.TestCase):
    def test_inbox_fetch_never_marks_read(self):
        bus=MagicMock();bus.call_sync.return_value.unpack.return_value=('TEST-TOKEN',3600)
        client=MagicMock();client.select.return_value=('OK',[b'20'])
        client.status.return_value=('OK',[b'INBOX (UNSEEN 7)'])
        client.fetch.return_value=('OK',[(b'20 (FLAGS () BODY[HEADER.FIELDS] {70}',b'From: =?utf-8?q?R=C3=A9my?= <r@example.invalid>\r\nSubject: Example\r\nMessage-ID: <abc@example.invalid>\r\n\r\n'),b')'])
        with patch.object(mail,'google_accounts',return_value=(bus,[{'path':'/test','email':'a@example.invalid','enabled':True}])),patch.object(mail.imaplib,'IMAP4_SSL',return_value=client):
            value=mail.fetch_inbox()
        client.select.assert_called_once_with('INBOX',readonly=True)
        self.assertIn('BODY.PEEK',client.fetch.call_args.args[1])
        self.assertEqual(value['unread'],7);self.assertEqual(value['messages'][0]['sender'],'Rémy')
        self.assertTrue(value['messages'][0]['unread'])
        client.store.assert_not_called();client.expunge.assert_not_called();client.logout.assert_called_once()
    def test_multiple_accounts_require_choice(self):
        with patch.object(mail,'google_accounts',return_value=(None,[{'email':'a'},{'email':'b'}])):
            with self.assertRaisesRegex(mail.MailError,'Choose'):mail.fetch_inbox()
    def test_mail_disabled_never_requests_token(self):
        bus=MagicMock()
        with patch.object(mail,'google_accounts',return_value=(bus,[{'email':'a','enabled':False}])):
            with self.assertRaisesRegex(mail.MailError,'Enable Mail'):mail.fetch_inbox()
        bus.call_sync.assert_not_called()
    def test_web_oauth_client_is_not_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'client.json';target.write_text(json.dumps({'web':{'client_id':'id.apps.googleusercontent.com'}}))
            with self.assertRaises(photos.PhotosError):photos.import_client(target)
    def test_failed_photo_download_keeps_previous_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);old=root/'old';old.mkdir();image=old/'000.jpg';image.write_bytes(b'original')
            index=root/'selection.json';original={'photos':[{'path':str(image)}]};index.write_text(json.dumps(original))
            def api(url,*args,**kwargs):
                if url.endswith('sessions'):return {'id':'test','pickerUri':'https://photos.google.com/picker/test','mediaItemsSet':True}
                if 'mediaItems?' in url:return {'mediaItems':[{'type':'PHOTO','mediaFile':{'baseUrl':'https://lh3.googleusercontent.com/test'}}]}
                return {}
            import threading
            with patch.object(photos,'ROOT',root),patch.object(photos,'INDEX',index),patch.object(photos,'authorize',return_value='TEST'),patch.object(photos,'request_json',side_effect=api),patch.object(photos,'urlopen',side_effect=OSError('offline')):
                with self.assertRaises(photos.PhotosError):photos.select_photos(lambda _:None,lambda _:None,threading.Event())
            self.assertEqual(json.loads(index.read_text()),original);self.assertEqual(image.read_bytes(),b'original')
            self.assertEqual(sorted(p.name for p in root.iterdir()),['old','selection.json'])
if __name__=='__main__':unittest.main()
