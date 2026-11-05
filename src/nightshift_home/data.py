from paths import user_home, desktop_quote
"""Read-only data sources and safe launch commands for Nightshift Home."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from contextlib import closing
import json
import os
import re
import sqlite3
import shutil
import subprocess
import uuid

HOME = user_home()
BASE = Path(__file__).resolve().parent
CONFIG = HOME / '.config/nightshift-home/config.json'
CACHE = HOME / '.cache/nightshift-home/github.json'
DEFAULTS = {
    'github_username': '', 'side': 'left', 'autostart': False,
    'show_clock': True, 'show_shortcuts': True, 'show_github': False,
    'show_codex': False, 'show_session_titles': False,
    'show_gmail': False, 'show_photos': False, 'gmail_account': '',
    'reduced_motion': False, 'project_editor': 'code',
    'show_cloudflare': False, 'cloudflare_placement': 'right',
    'show_notes': True, 'show_todo': True, 'show_ai_feed': False, 'show_handy': False,
    'show_theme': True, 'show_system': True, 'show_music': True, 'show_google': True,
}

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)

def load_config():
    result = DEFAULTS.copy()
    try:
        value = json.loads(CONFIG.read_text())
        if isinstance(value, dict):
            result.update({k: v for k, v in value.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    for key, default in DEFAULTS.items():
        if not isinstance(result[key], type(default)): result[key] = default
    if result['side'] not in ('left', 'right'): result['side'] = 'left'
    if result['project_editor'] not in ('code', 'cursor'): result['project_editor'] = 'code'
    if result['cloudflare_placement'] not in ('right', 'bottom'): result['cloudflare_placement'] = 'right'
    return result

def valid_login(login):
    return bool(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?', login)) and '--' not in login

def fetch_github(login):
    if not valid_login(login): raise ValueError('Enter a valid GitHub username.')
    query = '''query($login: String!) {
      user(login: $login) { login contributionsCollection {
        contributionCalendar { totalContributions weeks { contributionDays {
          date contributionCount contributionLevel
        } } }
      } }
    }'''
    try:
        result = subprocess.run(['/usr/bin/gh', 'api', 'graphql', '-f', 'query=' + query,
                                 '-f', 'login=' + login], capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        raise RuntimeError('GitHub timed out. Try again when you are online.') from None
    except OSError:
        raise RuntimeError('GitHub CLI is unavailable.') from None
    if result.returncode:
        if 'auth login' in result.stderr.lower() or 'authentication' in result.stderr.lower():
            raise RuntimeError('Sign in with gh auth login, then refresh.')
        raise RuntimeError('GitHub is unavailable. Saved activity remains visible.')
    try:
        response = json.loads(result.stdout)
        if response.get('errors'): raise ValueError()
        user = response['data']['user']
        if user is None: raise RuntimeError('That GitHub username was not found.')
        user['contributionsCollection']['contributionCalendar']['weeks']
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('GitHub returned an incomplete calendar.') from None
    return {'fetched_at': datetime.now(timezone.utc).timestamp(), 'data': user}

def load_cache(login):
    try:
        value = json.loads(CACHE.read_text())
        if value['data']['login'].lower() == login.lower(): return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None

def contribution_summary(record, today=None):
    today = today or datetime.now(timezone.utc).date()
    calendar = record['data']['contributionsCollection']['contributionCalendar']
    days = {date.fromisoformat(d['date']): d for w in calendar['weeks'] for d in w['contributionDays']
            if date.fromisoformat(d['date']) <= today}
    # An unfinished day without contributions preserves yesterday's streak.
    cursor = today if days.get(today, {}).get('contributionCount', 0) else today - timedelta(days=1)
    streak = 0
    while days.get(cursor, {}).get('contributionCount', 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    lower_bound = bool(streak and days and cursor < min(days))
    return {'days': days, 'streak': streak, 'lower_bound': lower_bound,
            'total': calendar['totalContributions'],
            'today': days.get(today, {}).get('contributionCount', 0)}

def read_sessions(limit=3):
    root = HOME / '.codex' if os.environ.get('NIGHTSHIFT_HOME') else Path(os.environ.get('CODEX_HOME', str(HOME / '.codex')))
    databases = sorted(root.glob('state_*.sqlite'), key=lambda p: int(re.search(r'_(\d+)', p.name)[1]), reverse=True)
    for path in databases:
        try:
            with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)) as con:
                con.execute('pragma query_only=on')
                columns = {r[1] for r in con.execute('pragma table_info(threads)')}
                if not {'id', 'title', 'cwd', 'updated_at', 'archived', 'source'} <= columns: continue
                name = 'name' if 'name' in columns else 'NULL'
                role = "and coalesce(agent_role,'')=''" if 'agent_role' in columns else ''
                rows = con.execute(f'''select id,{name},title,cwd,updated_at from threads
                  where archived=0 and source not like '%subagent%' {role}
                  order by updated_at desc limit ?''', (limit,)).fetchall()
            return [{'id': str(uuid.UUID(r[0])), 'title': (r[1] or r[2] or 'Untitled session').strip(),
                     'cwd': r[3], 'updated_at': r[4]} for r in rows]
        except (sqlite3.Error, ValueError, OSError):
            continue
    return []

def codex_command(session=None):
    cwd = Path(session['cwd']) if session else HOME
    if not cwd.is_dir(): cwd = HOME
    terminal = HOME / '.local/bin/midnight-terminal'
    executable = shutil.which('codex') or str(HOME / '.local/bin/codex')
    command = [str(terminal), '--window', '--title=Codex', '--working-directory=' + str(cwd), '--', str(executable), 'resume']
    if session:
        command += ['--cd', str(cwd), str(uuid.UUID(session['id']))]
    else:
        command += ['--all']
    return command

def write_autostart(enabled):
    target = HOME / '.config/autostart/nightshift-home.desktop'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('[Desktop Entry]\nType=Application\nName=Nightshift Home\n'
                      f'Exec=/usr/bin/python3 {desktop_quote(BASE / "home.py")}\n'
                      'Terminal=false\nOnlyShowIn=GNOME;\nX-GNOME-Autostart-Delay=4\n'
                      f'X-GNOME-Autostart-enabled={str(bool(enabled)).lower()}\n')

def age_label(timestamp):
    seconds = max(0, datetime.now(timezone.utc).timestamp() - float(timestamp))
    if seconds < 60: return 'just now'
    if seconds < 3600: return f'{int(seconds // 60)}m ago'
    if seconds < 86400: return f'{int(seconds // 3600)}h ago'
    return f'{int(seconds // 86400)}d ago'
