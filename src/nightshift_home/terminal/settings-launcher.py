#!/usr/bin/python3
"""Use native libadwaita widgets with the user's Nightshift color layer."""
import os
import sys

environment = os.environ.copy()
environment.pop('GTK_THEME', None)
os.execve('/usr/bin/gnome-control-center', ['gnome-control-center', *sys.argv[1:]], environment)
