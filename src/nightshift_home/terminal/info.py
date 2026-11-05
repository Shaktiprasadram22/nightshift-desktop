#!/usr/bin/env python3
"""An on-demand system card. No daemon, network requests, or background work."""
from pathlib import Path
import argparse
import platform
import time

p = argparse.ArgumentParser()
p.add_argument('--preview', action='store_true')
args = p.parse_args()
c = '\033[38;2;88;216;242m'
fg = '\033[38;2;216;232;247m'
muted = '\033[38;2;145;167;192m'
reset = '\033[0m'
memory = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) > 1}
used = (memory['MemTotal'] - memory['MemAvailable']) / 1048576
total = memory['MemTotal'] / 1048576
seconds = float(Path('/proc/uptime').read_text().split()[0])
osinfo = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
art = ['           /\\', '          /  \\', '         / /\\ \\', '        / /  \\ \\', '       / /____\\ \\', '      /__________\\']
details = [f'{c}NIGHTSHIFT  \033[38;2;214;133;244m/  RGB', f'{fg}{osinfo["PRETTY_NAME"].strip(chr(34))}', f'{muted}kernel   {fg}{platform.release()}', f'{muted}memory   {fg}{used:.1f} / {total:.1f} GiB', f'{muted}uptime   {fg}{int(seconds // 3600)}h {int(seconds % 3600 // 60)}m', f'{muted}desktop  {fg}GNOME  ·  X11']
print('\n')
for left, right in zip(art, details): print(f'  {c}{left:<27}{right}{reset}')
print('\n  ' + muted + '────────────────────────────────────────────────────────────────────' + reset)
print(f'\n  {c}Super{muted}  overview        {c}Super + arrows{muted}  tile windows')
print(f'  {c}Super + D{muted}  desktop      {c}Ctrl + Alt + T{muted}  terminal\n')
palette = ['18243a', 'f7768e', '9ece6a', 'e0af68', '7aa2f7', 'bb9af7', '58d8f2', 'c0d2e6']
print('  ' + ''.join(f'\033[48;2;{int(h[:2],16)};{int(h[2:4],16)};{int(h[4:],16)}m     ' for h in palette) + reset + '\n')
if args.preview:
    print(muted + '  Theme preview · closes automatically' + reset, flush=True)
    time.sleep(12)
