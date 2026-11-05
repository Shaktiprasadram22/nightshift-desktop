import unittest
from datetime import date
from pathlib import Path
from data import contribution_summary, codex_command, valid_login

def calendar(values):
    return {'data':{'contributionsCollection':{'contributionCalendar':{
        'totalContributions':sum(values.values()),'weeks':[{'contributionDays':[
            {'date':d,'contributionCount':n,'contributionLevel':'FIRST_QUARTILE' if n else 'NONE'} for d,n in values.items()
        ]}]}}}}

class DataChecks(unittest.TestCase):
    def test_unfinished_today_preserves_yesterday_streak(self):
        result=contribution_summary(calendar({'2026-11-01':0,'2026-11-02':2,'2026-11-03':3,'2026-11-04':0}),date(2026,11,4))
        self.assertEqual(result['streak'],2)
        self.assertFalse(result['lower_bound'])

    def test_missing_calendar_day_breaks_streak(self):
        result=contribution_summary(calendar({'2026-11-01':5,'2026-11-03':3}),date(2026,11,3))
        self.assertEqual(result['streak'],1)

    def test_future_days_never_extend_streak(self):
        result=contribution_summary(calendar({'2026-11-02':0,'2026-11-03':3,'2026-11-04':7}),date(2026,11,3))
        self.assertEqual(result['streak'],1)
        self.assertNotIn(date(2026,11,4),result['days'])

    def test_calendar_boundary_reports_lower_bound(self):
        result=contribution_summary(calendar({'2026-11-02':2,'2026-11-03':3}),date(2026,11,3))
        self.assertEqual(result['streak'],2)
        self.assertTrue(result['lower_bound'])

    def test_empty_activity_is_zero_not_a_fake_streak(self):
        self.assertEqual(contribution_summary(calendar({'2026-11-03':0}),date(2026,11,3))['streak'],0)

    def test_command_has_no_prompt_or_shell_interpolation(self):
        session={'id':'01a1a74b-1982-7c02-9a42-62d319bc7f3f','cwd':str(Path.home()),'title':'$(touch /tmp/unsafe)'}
        command=codex_command(session)
        self.assertNotIn(session['title'],command)
        self.assertIn('resume',command)
        self.assertEqual(command[-1],session['id'])
        self.assertNotIn('--yolo',command)

    def test_invalid_session_id_is_rejected(self):
        with self.assertRaises(ValueError):codex_command({'id':'x; touch /tmp/unsafe','cwd':str(Path.home())})

    def test_github_login_validation(self):
        self.assertTrue(valid_login('octocat'))
        for value in ['-x','x-','a--b','../x','a b','', 'a'*40]:self.assertFalse(valid_login(value),value)

if __name__=='__main__':unittest.main()
