"""Thread-safe concurrency and request-start spacing for a single channel."""
import random
import threading
import time


class ChannelLimiter:
    def __init__(self, concurrency, min_interval_s, *, jitter=0.2, rng=random.random, clock=time.monotonic, sleep=time.sleep):
        if concurrency < 1 or min_interval_s < 0:
            raise ValueError('concurrency must be positive and interval nonnegative')
        if not 0 <= jitter < 1:
            raise ValueError('jitter must be between 0 (inclusive) and 1 (exclusive)')
        self.jitter, self.rng = jitter, rng
        self.concurrency = concurrency
        self.min_interval_s = min_interval_s
        self.clock, self.sleep = clock, sleep
        self._slots = threading.BoundedSemaphore(concurrency)
        self._lock = threading.Lock()
        self._next = 0.0

    def __enter__(self):
        self._slots.acquire()
        try:
            self.wait_start()
        except BaseException:
            self._slots.release()
            raise
        return self

    def __exit__(self, *exc):
        self._slots.release()

    def wait_start(self):
        """Space starts when the coordinator already owns a concurrency slot."""
        with self._lock:
            delay = self._next - self.clock()
            if delay > 0:
                self.sleep(delay)
            interval = self.min_interval_s
            if interval:
                interval *= 1 + self.jitter * (2 * self.rng() - 1)
            self._next = self.clock() + interval
