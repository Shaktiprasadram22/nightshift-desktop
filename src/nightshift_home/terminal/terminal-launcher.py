#!/usr/bin/python3
"""Open GNOME Terminal without stale per-window D-Bus routing."""
import os
import sys

environment = os.environ.copy()
environment.pop('GNOME_TERMINAL_SERVICE', None)
environment.pop('GNOME_TERMINAL_SCREEN', None)
environment['GTK_THEME'] = 'Midnight-Cyan'
arguments = sys.argv[1:] or ['--window']
if arguments == ['--window']:
    startup = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'start-shell.py')
    if os.path.isfile(startup):
        arguments += ['--', '/usr/bin/python3', startup]
os.execve('/usr/bin/gnome-terminal', ['gnome-terminal', *arguments], environment)
