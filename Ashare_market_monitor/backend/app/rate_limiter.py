import threading
import time


class RateLimiter:
    """Simple thread-safe min-interval rate limiter."""

    def __init__(self, qps: float) -> None:
        if qps <= 0:
            raise ValueError("qps must be > 0")
        self._min_interval = 1.0 / qps
        self._lock = threading.Lock()
        self._next_time = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_time:
                time.sleep(self._next_time - now)
                now = time.monotonic()
            self._next_time = now + self._min_interval
