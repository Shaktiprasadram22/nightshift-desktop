#!/usr/bin/python3
"""Print a small system card once, then replace this process with the real shell."""
from pathlib import Path
import os
import pwd
import subprocess
import sys

base = Path(__file__).resolve().parent
try:
    subprocess.run([sys.executable, str(base / 'info.py')], timeout=3, check=False)
except (OSError, subprocess.TimeoutExpired):
    pass
shell = pwd.getpwuid(os.getuid()).pw_shell or '/bin/bash'
os.execv(shell, [shell, '-i'])
