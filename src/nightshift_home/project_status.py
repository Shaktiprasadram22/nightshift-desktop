from paths import user_home
"""On-demand local Git status. Never fetch, modify files, or run a shell."""
from pathlib import Path
import os
import shutil
import subprocess


def parse_status(output):
    result = dict(branch='', oid='', upstream='', ahead=0, behind=0, staged=0, unstaged=0, untracked=0, conflicts=0, changed=0)
    entries = iter(output.split(b'\0'))
    for entry in entries:
        if entry.startswith(b'# branch.'):
            key, _, value = entry.partition(b' ')
            # branch headers have two space-separated prefix words.
            key, _, value = value.partition(b' ')
            value = value.decode('utf-8','replace')
            if key == b'branch.head': result['branch'] = value
            elif key == b'branch.oid': result['oid'] = value
            elif key == b'branch.upstream': result['upstream'] = value
            elif key == b'branch.ab':
                try: result['ahead'],result['behind'] = (int(v.lstrip('+-')) for v in value.split())
                except ValueError: pass
        elif entry.startswith((b'1 ',b'2 ',b'u ')):
            fields = entry.split(b' ',2)
            if len(fields) < 3 or len(fields[1]) != 2: continue
            result['changed'] += 1
            if entry[:1] == b'u': result['conflicts'] += 1
            else:
                result['staged'] += fields[1][:1] != b'.'
                result['unstaged'] += fields[1][1:] != b'.'
            if entry[:1] == b'2': next(entries,None)  # rename/copy source, including arbitrary newlines
        elif entry.startswith(b'? '):
            result['untracked'] += 1; result['changed'] += 1
    if result['branch'] == '(detached)': result['branch'] = 'Detached · '+result['oid'][:8]
    if result['oid'] == '(initial)': result['branch'] += ' · no commits yet'
    result['branch'] = ' '.join(result['branch'].split())[:150] or 'Branch unavailable'
    return result


def inspect(path):
    path = Path(path).expanduser()
    if not path.is_dir(): raise RuntimeError('This project folder is unavailable. Choose another folder.')
    git = shutil.which('git')
    if not git: raise RuntimeError('Git is not installed. Editor and terminal shortcuts still work.')
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    try:
        result = subprocess.run([git,'--no-optional-locks','-C',str(path),'-c','core.fsmonitor=false','-c','core.untrackedCache=false',
                                 'status','--porcelain=v2','--branch','--untracked-files=normal','-z'],
                                capture_output=True,timeout=6,env=environment)
    except subprocess.TimeoutExpired:
        raise RuntimeError('This repository is taking too long to inspect. Refresh to retry.') from None
    except OSError:
        raise RuntimeError('Could not read Git status. Refresh to retry.') from None
    if result.returncode:
        if b'not a git repository' in result.stderr: raise RuntimeError('No Git repository here. Editor and terminal shortcuts are ready.')
        if b'dubious ownership' in result.stderr: raise RuntimeError('Git does not trust this folder’s owner. No trust settings were changed.')
        raise RuntimeError('Git status is unavailable for this folder.')
    return parse_status(result.stdout)


def launch(path, kind, editor='code'):
    path = Path(path).expanduser().resolve()
    if not path.is_dir(): raise RuntimeError('This project folder is unavailable.')
    if kind == 'editor':
        executable = shutil.which(editor if editor in ('code','cursor') else 'code')
        if not executable: raise RuntimeError('Choose an installed editor in desktop settings.')
        args = [executable,'--new-window',str(path)]
    elif kind == 'terminal':
        args = [str(user_home()/'.local/bin/midnight-terminal'),'--window','--working-directory='+str(path)]
    else: raise ValueError('Unknown project action')
    subprocess.Popen(args,cwd=path,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
