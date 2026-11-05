"""Persisted, deadline-based focus timer. No scheduler runs while idle or paused."""
import math
import time


class FocusTimer:
    DURATIONS = (25 * 60, 50 * 60)

    def __init__(self, saved=None, now=time.time):
        self.now = now
        self.duration = self.DURATIONS[0]
        self.state = 'idle'
        self.deadline = None
        self.remaining = self.duration
        if isinstance(saved, dict):
            try:
                duration = int(saved['duration'])
                state = saved['state']
                remaining = float(saved['remaining'])
                deadline = saved.get('deadline')
                if duration not in self.DURATIONS or state not in ('idle', 'running', 'paused', 'complete'):
                    return
                if not math.isfinite(remaining) or not 0 <= remaining <= duration:
                    return
                if state == 'running' and (not isinstance(deadline, (int, float)) or not math.isfinite(deadline)):
                    return
                self.duration, self.state, self.remaining = duration, state, remaining
                self.deadline = deadline if state == 'running' else None
            except (KeyError, TypeError, ValueError, OverflowError):
                pass

    def seconds_left(self):
        remaining = self.deadline - self.now() if self.state == 'running' else self.remaining
        return max(0, min(self.duration, math.ceil(remaining)))

    def select(self, minutes):
        duration = int(minutes) * 60
        if duration not in self.DURATIONS:
            raise ValueError('Choose 25 or 50 minutes.')
        if self.state not in ('idle', 'complete'):
            return False
        self.duration = duration
        self.reset()
        return True

    def start(self):
        if self.state == 'running':
            return
        if self.state == 'complete':
            self.remaining = self.duration
        self.deadline = self.now() + self.remaining
        self.state = 'running'

    def pause(self):
        if self.state == 'running':
            self.remaining = self.seconds_left()
            self.deadline = None
            self.state = 'paused' if self.remaining else 'complete'

    def reset(self):
        self.state, self.remaining, self.deadline = 'idle', self.duration, None

    def tick(self):
        """Return True exactly once when a running timer reaches its deadline."""
        if self.state == 'running' and self.seconds_left() == 0:
            self.state, self.remaining, self.deadline = 'complete', 0, None
            return True
        return False

    def snapshot(self):
        return dict(duration=self.duration, state=self.state,
                    remaining=self.seconds_left(), deadline=self.deadline)

    @property
    def display(self):
        seconds = self.seconds_left()
        return f'{seconds // 60:02}:{seconds % 60:02}'
