from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from focus_timer import FocusTimer
from launcher_catalog import discover_projects, search_items
from detail_popup import popup_position


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.clock = lambda: self.now
        self.timer = FocusTimer(now=self.clock)

    def test_pause_resume_and_finish_once(self):
        self.timer.start()
        self.now += 60
        self.assertEqual(self.timer.display, '24:00')
        self.timer.pause()
        self.now += 500
        self.assertEqual(self.timer.display, '24:00')
        self.timer.start()
        self.now += 1440
        self.assertTrue(self.timer.tick())
        self.assertFalse(self.timer.tick())
        self.assertEqual(self.timer.state, 'complete')

    def test_restart_accounts_for_time_while_closed(self):
        self.timer.select(50)
        self.timer.start()
        saved = self.timer.snapshot()
        self.now += 900
        restored = FocusTimer(saved, self.clock)
        self.assertEqual(restored.display, '35:00')
        self.now += 4000
        self.assertTrue(restored.tick())

    def test_presets_do_not_interrupt_active_timer(self):
        self.timer.start()
        self.assertFalse(self.timer.select(50))
        self.timer.pause()
        self.assertFalse(self.timer.select(50))
        self.timer.reset()
        self.assertTrue(self.timer.select(50))
        self.assertEqual(self.timer.display, '50:00')

    def test_corrupt_or_nonfinite_saved_state(self):
        for saved in [None, {}, {'duration': 1500, 'state': 'running', 'remaining': 20, 'deadline': float('nan')},
                      {'duration': 123, 'state': 'paused', 'remaining': 22},
                      {'duration': 1500, 'state': 'paused', 'remaining': float('inf')}]:
            timer = FocusTimer(saved, self.clock)
            self.assertEqual(timer.state, 'idle')
            self.assertEqual(timer.display, '25:00')


class CatalogTests(unittest.TestCase):
    def test_only_bounded_project_roots_and_explicit_session_folders(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            for relative in ['website/.git', 'Projects/team/service/pyproject.toml',
                             '.private/secret/.git', 'Downloads/unrelated/deep/.git',
                             'Projects/node_modules/package/.git']:
                p = home / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                if p.name == '.git':p.mkdir()
                else:p.touch()
            (home / 'notes').mkdir()
            found = set(discover_projects(home, [{'cwd': str(home / 'notes')}, {'cwd': '/tmp'}]))
            self.assertEqual(found, {home / 'website', home / 'Projects/team/service', home / 'notes'})

    def test_symlinked_trees_are_not_scanned(self):
        with TemporaryDirectory() as temp:
            home = Path(temp) / 'home';home.mkdir()
            external = Path(temp) / 'external';external.mkdir();(external / '.git').mkdir()
            (home / 'linked').symlink_to(external, target_is_directory=True)
            self.assertEqual(discover_projects(home), [])

    def test_search_ranks_title_matches_and_filters_kind(self):
        items = [{'kind': 'session', 'title': 'Review', 'subtitle': 'calendar', 'payload': 1},
                 {'kind': 'project', 'title': 'Calendar app', 'subtitle': '~/calendar', 'payload': 2},
                 {'kind': 'app', 'title': 'Café', 'subtitle': 'Coffee timer', 'payload': 3}]
        self.assertEqual(search_items(items, 'calendar')[0][0]['payload'], 2)
        self.assertEqual(search_items(items, 'calendar', 'session')[0][0]['payload'], 1)
        self.assertEqual(search_items(items, 'cafe')[0][0]['payload'], 3)
        self.assertEqual(search_items(items, '$(touch /tmp/test)')[1], 0)

    def test_result_limit_retains_honest_count(self):
        items = [dict(kind='app', title=f'App {n}') for n in range(100)]
        visible, total = search_items(items, limit=60)
        self.assertEqual((len(visible), total), (60, 100))


class CalendarPlacementTests(unittest.TestCase):
    def test_calendar_sits_beside_clock_at_supported_sizes(self):
        for width, height in [(1920, 1080), (1366, 768)]:
            anchor = ((width-440)//2, round(height*.24), 440, 175)
            px, py = popup_position(anchor, (400, 550), (0, 44, width, height-44), placement='beside')
            self.assertGreater(px, anchor[0] + anchor[2])
            self.assertLessEqual(px + 400, width - 12)
            self.assertLessEqual(py + 550, height - 12)


if __name__ == '__main__':
    unittest.main()
