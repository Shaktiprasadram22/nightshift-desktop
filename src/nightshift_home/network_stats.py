"""Network throughput from physical Linux interfaces, excluding virtual duplicates."""
from pathlib import Path
import time


class NetworkSampler:
    def __init__(self, proc=Path('/proc/net/dev'), interfaces=Path('/sys/class/net'), clock=time.monotonic):
        self.proc, self.interfaces, self.clock = Path(proc), Path(interfaces), clock
        self.previous = None

    def reset(self):
        self.previous = None

    def sample(self):
        now = self.clock()
        try:
            active = set()
            for interface in self.interfaces.iterdir():
                if (interface/'device').exists() and (interface/'operstate').read_text().strip() in ('up', 'unknown'):
                    active.add(interface.name)
            counters = {}
            for line in self.proc.read_text().splitlines():
                name, sep, fields = line.partition(':')
                if sep and name.strip() in active:
                    values = fields.split()
                    counters[name.strip()] = (int(values[0]), int(values[8]))
            if any(min(pair) < 0 for pair in counters.values()):
                raise ValueError()
        except (OSError, ValueError, IndexError):
            self.reset()
            return dict(download=None, upload=None, interfaces=[], state='Network reading unavailable')
        old, self.previous = self.previous, (now, counters)
        result = dict(download=None, upload=None, interfaces=sorted(counters), state='Sampling network…' if counters else 'No active physical network link')
        if not old or not counters or set(old[1]) != set(counters) or not 0 < now-old[0] <= 8:
            return result
        deltas = [(pair[0]-old[1][name][0], pair[1]-old[1][name][1]) for name, pair in counters.items()]
        if any(min(pair) < 0 for pair in deltas):
            return result
        result.update(download=sum(p[0] for p in deltas)/(now-old[0]), upload=sum(p[1] for p in deltas)/(now-old[0]), state='')
        return result


def speed(value):
    if value is None:
        return '—'
    for unit in ('B/s', 'KiB/s', 'MiB/s', 'GiB/s'):
        if value < 1024 or unit == 'GiB/s':
            return f'{value:.0f} {unit}' if unit == 'B/s' else f'{value:.1f} {unit}'
        value /= 1024
