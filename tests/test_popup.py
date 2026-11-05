import unittest
from detail_popup import popup_position

class PopupPlacementChecks(unittest.TestCase):
    def test_opens_below_when_space_is_available(self):
        x,y=popup_position((1054,470,68,68),(400,180),(0,38,1920,1042))
        self.assertGreaterEqual(y,538)
        self.assertLessEqual(x,1088)
        self.assertGreaterEqual(x+400,1088)

    def test_opens_above_near_bottom_edge(self):
        x,y=popup_position((1054,1000,68,68),(400,220),(0,38,1920,1042))
        self.assertLessEqual(y+220,1000)

    def test_stays_inside_edges_and_offset_monitors(self):
        for area in [(0,38,1920,1042),(1920,38,1280,986),(-1920,0,1920,1080),(0,34,1366,734)]:
            mx,my,mw,mh=area
            for ax in [mx,mx+mw//2,mx+mw-68]:
                for ay in [my,my+mh//2,my+mh-68]:
                    x,y=popup_position((ax,ay,68,68),(400,230),area)
                    self.assertGreaterEqual(x,mx+12)
                    self.assertGreaterEqual(y,my+12)
                    self.assertLessEqual(x+400,mx+mw-12)
                    self.assertLessEqual(y+230,my+mh-12)

if __name__=='__main__':unittest.main()
