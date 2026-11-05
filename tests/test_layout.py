import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from layout import Layout,clamp_rect,MINIMUM


class LayoutTests(unittest.TestCase):
    def test_save_reload_and_independent_widgets(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'layout.json';layout=Layout(path)
            layout.save('clock',[120,150,600,250],(1920,1080))
            layout.save('icon-gmail',[800,500,100,120],(1920,1080))
            again=Layout(path)
            self.assertEqual(again.resolve('clock',[0,0,1,1],(1920,1080)),[120,150,600,250])
            self.assertEqual(again.resolve('icon-gmail',[0,0,1,1],(1920,1080)),[800,500,100,120])
            self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_smaller_screen_retains_bottom_right_and_bounds(self):
        with TemporaryDirectory() as folder:
            layout=Layout(Path(folder)/'layout.json');layout.save('cloudflare',[1524,616,356,412],(1920,1080))
            x,y,w,h=layout.resolve('cloudflare',[0,0,1,1],(1366,768))
            self.assertTrue(900<x<1000);self.assertTrue(280<y<340)
            self.assertLessEqual(x+w,1366);self.assertLessEqual(y+h,768)

    def test_invalid_saved_geometry_is_ignored(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'layout.json';path.write_text(json.dumps({'clock':{'rect':[float('nan'),0,1,1],'screen':[0,0]}}))
            self.assertEqual(Layout(path).items,{})

    def test_minimum_and_edge_limits(self):
        self.assertEqual(clamp_rect([-20,-100,40,20],(1366,768),MINIMUM['clock']),[12,48,240,140])
        rect=clamp_rect([9000,9000,5000,5000],(1366,768),MINIMUM['clock'])
        self.assertLessEqual(rect[0]+rect[2],1366);self.assertLessEqual(rect[1]+rect[3],768)

    def test_reset_and_undo_preserve_previous_customization(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'layout.json';layout=Layout(path)
            layout.save('clock',[120,150,600,250],(1920,1080));previous=layout.items.copy()
            layout.reset();self.assertEqual(layout.items,{})
            layout.restore();self.assertEqual(layout.items,previous)
            self.assertEqual(Layout(path).items,previous)


if __name__=='__main__':unittest.main()
