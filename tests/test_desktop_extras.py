from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import copy
import json
import subprocess
import unittest
from network_stats import NetworkSampler, speed
from site_health import check, description
from music_progress import Progress, seekable, duration
from layout_profiles import Profiles, commit, recover, built_in, validate, KEYS, visibility_key
from personal_store import private_write
from project_status import inspect, parse_status


class NetworkTests(unittest.TestCase):
    def test_physical_interfaces_rate_reset_suspend_and_no_double_count(self):
        with TemporaryDirectory() as folder:
            root = Path(folder);interfaces = root/'net';interfaces.mkdir()
            for name,physical in (('wlan0',True),('tun0',False),('lo',False)):
                path = interfaces/name;path.mkdir();(path/'operstate').write_text('up')
                if physical: (path/'device').mkdir()
            now = [0];proc = root/'dev'
            sampler = NetworkSampler(proc,interfaces,lambda:now[0])
            def write(rx,tx): proc.write_text(f'wlan0: {rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0\ntun0: 999999 0 0 0 0 0 0 0 999999 0 0 0 0 0 0 0\n')
            write(100,200);self.assertIsNone(sampler.sample()['download'])
            now[0]=2;write(2148,1224);self.assertEqual(sampler.sample()['download'],1024)
            now[0]=4;write(2148,1224);self.assertEqual(sampler.sample()['upload'],0)
            now[0]=6;write(1,1);self.assertIsNone(sampler.sample()['download'])
            now[0]=30;write(999999,999999);self.assertIsNone(sampler.sample()['download'])
            (interfaces/'wlan0'/'operstate').write_text('down');self.assertEqual(sampler.sample()['interfaces'],[])
            proc.unlink();self.assertIn('unavailable',sampler.sample()['state'])
            self.assertEqual(speed(1024),'1.0 KiB/s');self.assertEqual(speed(None),'—')


class HealthTests(unittest.TestCase):
    def check(self, host, runner):
        with patch('site_health.HOSTS', ('example.com', 'example.net')):
            return check(host, runner)

    def test_http_distinguished_from_local_network_failure(self):
        for code,expected in ((200,'up'),(204,'up'),(403,'blocked'),(429,'warning'),(503,'error')):
            value = self.check('example.com',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps({'http_code':code,'time_starttransfer':.123})))
            self.assertEqual(value['state'],expected);self.assertEqual(value['milliseconds'],123)
        value = self.check('example.com',lambda *a,**k:SimpleNamespace(returncode=6,stdout='{}'))
        self.assertEqual(value['state'],'unknown');self.assertIn('does not establish a global outage',description(value)[1])
        with self.assertRaises(ValueError): check('127.0.0.1')

    def test_head_fallback_and_timeouts_are_bounded(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args.copy());self.assertEqual(kwargs['timeout'],10)
            return SimpleNamespace(returncode=0,stdout=json.dumps({'http_code':405 if '--head' in args else 200,'time_starttransfer':.1}))
        self.assertEqual(self.check('example.net',run)['state'],'up')
        self.assertEqual(len(calls),2);self.assertIn('--range',calls[1]);self.assertIn('--max-redirs',calls[0])
        def timeout(*a,**k):raise subprocess.TimeoutExpired('curl',10)
        self.assertEqual(self.check('example.net',timeout)['state'],'unknown')


class ProgressTests(unittest.TestCase):
    def test_position_pause_rate_seek_signal_and_track_change(self):
        now=[0];progress=Progress(lambda:now[0]);props={'Metadata':{'mpris:trackid':'/track/one','mpris:length':120000000},'PlaybackStatus':'Playing','Rate':1.0,'CanControl':True,'CanSeek':True}
        progress.sync(props,10000000);now[0]=5;self.assertEqual(progress.position(),15)
        props['PlaybackStatus']='Paused';progress.sync(props);now[0]=10;self.assertEqual(progress.position(),15)
        props.update(PlaybackStatus='Playing',Rate=2.0);progress.sync(props,30000000);now[0]=15;self.assertEqual(progress.position(),40)
        self.assertTrue(seekable(props));props['CanSeek']=False;self.assertFalse(seekable(props))
        props['Metadata']['mpris:trackid']='/track/two';progress.sync(props);self.assertIsNone(progress.position())
        props['Metadata']['mpris:length']=float('nan');self.assertIsNone(duration(props))
        props['Metadata']['mpris:length']=120000000;props['Metadata']['mpris:trackid']='/org/mpris/MediaPlayer2/TrackList/NoTrack';props['CanSeek']=True;self.assertFalse(seekable(props))


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)
        self.snap={'items':{'clock':{'rect':[100,100,440,175],'screen':[1920,1080]}},'visibility':{key:True for key in KEYS}}

    def test_save_replace_and_undo_do_not_apply_or_overwrite_corruption(self):
        store=Profiles(self.root);store.save('Coding',self.snap)
        self.assertFalse((self.root/'layout.json').exists())
        other=copy.deepcopy(self.snap);other['items']['clock']['rect'][0]=500
        store.save('Coding',other);store.undo_save()
        self.assertEqual(store.data['profiles']['Coding'],self.snap)
        self.assertEqual(store.path.stat().st_mode&0o777,0o600)
        store.path.write_text('{bad');broken=Profiles(self.root)
        with self.assertRaises(OSError):broken.save('Focus',other)
        self.assertEqual(store.path.read_text(),'{bad')

    def test_transaction_rolls_back_after_partial_write_and_recovers_interruption(self):
        names=('config.json','layout.json','profiles.json');before={name:{'original':name} for name in names}
        for name,value in before.items():private_write(self.root/name,value)
        calls=[0]
        def fail_once(path,value):
            calls[0]+=1
            if calls[0]==3: raise OSError('Fixture disk failure')
            private_write(path,value)
        with patch('layout_profiles.private_write',fail_once):
            with self.assertRaises(OSError):commit(self.root,{name:{'new':True} for name in names})
        for name,value in before.items():self.assertEqual(json.loads((self.root/name).read_text()),value)
        private_write(self.root/'layout-transaction.json',before);private_write(self.root/'config.json',{'interrupted':True})
        recover(self.root);self.assertEqual(json.loads((self.root/'config.json').read_text()),before['config.json'])
        commit(self.root,{name:{'success':True} for name in names});self.assertFalse((self.root/'layout-transaction.json').exists())

    def test_presets_keep_controls_and_valid_on_smaller_displays(self):
        for dimensions in ((1920,1080),(1366,768),(800,600)):
            for name in ('Coding','Focus','Chill'):
                value=validate(built_in(name,self.snap,dimensions));self.assertTrue(value['visibility']['show_shortcuts'])
                if name!='Coding':
                    for item in value['items'].values():
                        x,y,w,h=item['rect'];self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0);self.assertLessEqual(x+w,dimensions[0]);self.assertLessEqual(y+h,dimensions[1])
                    visible=[item['rect'] for widget,item in value['items'].items() if value['visibility'].get(visibility_key(widget))]
                    for index,(x,y,w,h) in enumerate(visible):
                        for a,b,c,d in visible[index+1:]:
                            self.assertFalse(min(x+w,a+c)>max(x,a) and min(y+h,b+d)>max(y,b),(name,dimensions,visible))
        self.assertTrue(all(self.snap['visibility'].values()))


class GitTests(unittest.TestCase):
    def test_real_repo_unborn_modified_untracked_rename_detached_nonrepo(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            def git(*args):return subprocess.run(['git','-C',folder,*args],check=True,capture_output=True)
            with self.assertRaises(RuntimeError):inspect(root)
            git('init','-b','main');self.assertIn('no commits',inspect(root)['branch'])
            (root/'one').write_text('one');git('add','one');git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','Fixture')
            self.assertEqual(inspect(root)['changed'],0)
            (root/'one').write_text('two');(root/'newline\nfile').write_text('test')
            value=inspect(root);self.assertEqual((value['unstaged'],value['untracked']),(1,1))
            git('add','one');git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','Changed')
            git('mv','one','renamed\nfile');value=inspect(root)
            self.assertEqual(value['staged'],1);self.assertEqual(value['untracked'],1)
            git('checkout','--detach');self.assertTrue(inspect(root)['branch'].startswith('Detached'))

    def test_porcelain_conflicts_and_remote_counts(self):
        value=parse_status(b'# branch.oid abcdef123456\0# branch.head feature/test\0# branch.upstream origin/main\0# branch.ab +2 -3\0u UU N... fixture\0? strange\nname\0')
        self.assertEqual((value['conflicts'],value['untracked'],value['ahead'],value['behind']),(1,1,2,3))


if __name__=='__main__':unittest.main()
