import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from data import BASE
from theme_palette import *
from theme_apply import ThemeEngine,digest

class FakeBackend:
    def __init__(self):self.values={};self.fail_once=None
    def get(self,schema,key,path=None):
        return self.values.get((schema,key,path),'fixture' if key=='default' else 'Midnight-Cyan' if key in ('name','gtk-theme') else 'previous')
    def check(self,entry):pass
    def set(self,entry):
        schema,key,value,path=entry
        if key==self.fail_once:self.fail_once=None;raise OSError('Simulated settings failure')
        self.values[(schema,key,path)]=value
    def sync(self):pass

class PaletteTests(unittest.TestCase):
    def test_validation_rejects_css_injection_and_invalid_channels(self):
        for invalid in ['red','#fff','#000000; background:red','#gg0011']:
            with self.assertRaises(ValueError):validate({**DEFAULT,'primary':invalid})
        for invalid in [-1,101,True,12.5]:
            with self.assertRaises(ValueError):validate({**DEFAULT,'glow':invalid})
        self.assertEqual(validate({'primary':'#AABBCC'})['primary'],'#aabbcc')
    def test_extreme_colors_remain_readable(self):
        for value in ['#000000','#010101','#ff0000','#0000ff','#003300','#ffffff']:
            self.assertGreaterEqual(contrast(readable(value),'#152030'),4.5)
        for preset in PRESETS.values():self.assertLess(luminance(color('#0b1423',preset)),.08)
        for primary in ['#000000','#0000ff','#ff0000','#ffffff']:
            for darkness in (0,60,100):
                p={**DEFAULT,'primary':primary,'darkness':darkness}
                self.assertGreaterEqual(contrast(color('#8ee7f6',p),color('#0b1423',p)),4.5)
                self.assertGreaterEqual(contrast(color('#9de8f5',p),color('#182a40',p)),4.5)
    def test_transform_preserves_alpha_and_semantic_colors(self):
        p=PRESETS['Cyber violet']
        result=recolor('a{color:#58d8f2aa;background:rgba(88,216,242,0.15);border-color:#fb7c7c}',p)
        self.assertIn('aa;',result);self.assertIn(',0.15)',result);self.assertIn('#fb7c7c',result)
        self.assertNotIn('#58d8f2',result)
    def test_default_dark_surface_and_cached_paint(self):
        self.assertEqual(color('#0b1423',DEFAULT),'#0b1423')
        set_live(PRESETS['Ember']);self.assertNotEqual(paint('#58d8f2'),'#58d8f2')
        set_live(None);self.assertEqual(paint('#58d8f2'),'#58d8f2')

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.backend=FakeBackend();self.engine=ThemeEngine(self.root,BASE,self.backend)
        self.target=self.root/'.config/Code/User/settings.json';self.target.parent.mkdir(parents=True)
        self.target.write_text('// keep this comment\n{"editor.fontSize": 19, "unrelated": "keep", "workbench.colorCustomizations": {"focusBorder":"#112233"}}\n')
    def test_prepare_commit_and_undo_preserve_unrelated_preferences(self):
        previous=self.target.read_text();plan=self.engine.prepare({**PRESETS['Cyber violet'],'editors':True})
        self.assertFalse(self.engine.state.exists());self.engine.commit(plan)
        self.assertIn('// keep this comment',self.target.read_text());self.assertIn('"editor.fontSize": 19',self.target.read_text())
        self.assertEqual(self.engine.undo_path.stat().st_mode&0o777,0o600)
        # An unrelated editor preference changed after Apply must survive Undo.
        self.target.write_text(self.target.read_text().replace('"editor.fontSize": 19','"editor.fontSize": 21'))
        result=self.engine.undo();text=self.target.read_text()
        self.assertIn('"editor.fontSize": 21',text);self.assertIn('"#112233"',text);self.assertIn('// keep this comment',text)
        self.assertIsNone(result['applied_at']);self.assertFalse(self.engine.state.exists());self.assertFalse(self.engine.undo_path.exists())
    def test_failed_setting_rolls_back_files_and_values(self):
        before=self.target.read_bytes();plan=self.engine.prepare({**PRESETS['Aurora mint'],'editors':True});self.backend.fail_once='window-border-color'
        with self.assertRaises(OSError):self.engine.commit(plan)
        self.assertEqual(self.target.read_bytes(),before);self.assertFalse(self.engine.state.exists());self.assertFalse(self.engine.undo_path.exists())
        self.assertEqual(self.backend.get('org.gnome.shell.extensions.user-theme','name'),'Midnight-Cyan')
    def test_concurrent_editor_change_is_not_overwritten(self):
        plan=self.engine.prepare({**DEFAULT,'editors':True});self.target.write_text('{"new_setting":true}')
        with self.assertRaises(RuntimeError):self.engine.commit(plan)
        self.assertEqual(self.target.read_text(),'{"new_setting":true}');self.assertFalse(self.engine.state.exists())
    def test_invalid_editor_json_is_preflight_failure(self):
        self.target.write_text('{bad syntax')
        with self.assertRaises(ValueError):self.engine.prepare({**DEFAULT,'editors':True})
        self.assertFalse(self.engine.state.exists())
    def test_apply_targets_only_appearance(self):
        plan=self.engine.prepare({**DEFAULT,'editors':False})
        paths=[str(path) for path in plan['files']]
        self.assertFalse(any(path.endswith(('notes.json','todos.json','layout.json','config.json')) for path in paths))
        self.assertFalse(any('keybinding' in schema or 'keyboard' in schema for schema,_,_,_ in plan['settings']))
        self.assertFalse(plan['editors'])

if __name__=='__main__':unittest.main()
