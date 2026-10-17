import time


class Cooldown:
    """In-memory per-key cooldown. Per instance only, which is enough to stop accidental spam on Cloud Run."""

    def __init__(self, seconds: float, clock=time.monotonic):
        self.seconds = seconds
        self._clock = clock
        self._last: dict[int, float] = {}

    def try_acquire(self, key: int) -> float:
        """Returns 0 and records the hit if allowed, otherwise the seconds left to wait."""
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self.seconds:
            return self.seconds - (now - last)
        self._last[key] = now
        return 0.0
