"""Small, local Linux readings. No process enumeration, network, or shell polling.

CPU and memory accounting: https://docs.kernel.org/filesystems/proc.html
"""
from dataclasses import dataclass
from pathlib import Path
import os
import time

SAMPLE_SECONDS = 2
STORAGE_SECONDS = 30


@dataclass(frozen=True)
class Usage:
    total: int
    used: int
    available: int

    @property
    def percent(self):
        return 100 * self.used / self.total


@dataclass(frozen=True)
class Snapshot:
    cpu: float | None
    memory: Usage | None
    storage: Usage | None
    errors: dict
    reset_history: bool = False


def cpu_counters(line):
    fields = line.split()
    if not fields or fields[0] != 'cpu' or len(fields) < 5:
        raise ValueError('Missing aggregate CPU counters')
    # Guest and guest_nice (fields 9/10) are already included in user/nice.
    values = [int(value) for value in fields[1:9]]
    values += [0] * (8 - len(values))
    if any(value < 0 for value in values):
        raise ValueError('Invalid CPU counter')
    return tuple(values)


def memory_usage(source):
    values = {}
    for line in source.splitlines():
        fields = line.split()
        if fields and fields[0] in ('MemTotal:', 'MemAvailable:'):
            if len(fields) != 3 or fields[2] != 'kB':
                raise ValueError('Invalid memory units')
            values[fields[0][:-1]] = int(fields[1]) * 1024
    total, available = values['MemTotal'], values['MemAvailable']
    if total <= 0 or not 0 <= available <= total:
        raise ValueError('Invalid memory counters')
    return Usage(total, total - available, available)


def storage_usage(stat):
    size = stat.f_frsize or stat.f_bsize
    if size <= 0 or stat.f_blocks <= 0 or not 0 <= stat.f_bavail <= stat.f_bfree <= stat.f_blocks:
        raise ValueError('Invalid filesystem counters')
    return Usage(stat.f_blocks * size, (stat.f_blocks - stat.f_bfree) * size, stat.f_bavail * size)


class SystemSampler:
    def __init__(self, proc=Path('/proc'), filesystem='/', clock=time.monotonic, statvfs=os.statvfs):
        self.proc = Path(proc)
        self.filesystem = filesystem
        self.clock = clock
        self.statvfs = statvfs
        self.reset()

    def reset(self):
        self.previous = None
        self.disk_at = None
        self.disk = None
        self.disk_error = ''

    def sample(self):
        now = self.clock()
        cpu, memory, errors = None, None, {}
        reset_history = False
        try:
            with (self.proc / 'stat').open() as stream:
                counters = cpu_counters(stream.readline())
            old = self.previous
            self.previous = (now, counters)
            if old is None or not 0 < now - old[0] <= SAMPLE_SECONDS * 4:
                reset_history = True
            else:
                deltas = [current - previous for current, previous in zip(counters, old[1])]
                if any(delta < 0 for delta in deltas) or sum(deltas) <= 0:
                    reset_history = True
                else:
                    total = sum(deltas)
                    cpu = max(0.0, min(100.0, 100 * (total - deltas[3] - deltas[4]) / total))
        except (OSError, ValueError):
            self.previous = None
            reset_history = True
            errors['cpu'] = 'CPU reading unavailable'
        try:
            memory = memory_usage((self.proc / 'meminfo').read_text())
        except (OSError, ValueError, KeyError):
            errors['memory'] = 'RAM reading unavailable'
        if self.disk_at is None or now - self.disk_at >= STORAGE_SECONDS or now < self.disk_at:
            self.disk_at = now
            try:
                self.disk = storage_usage(self.statvfs(self.filesystem))
                self.disk_error = ''
            except (OSError, ValueError):
                self.disk = None
                self.disk_error = 'Storage reading unavailable'
        if self.disk_error:
            errors['storage'] = self.disk_error
        return Snapshot(cpu, memory, self.disk, errors, reset_history)
