"""Thread-safe concurrency and request-start spacing for a single channel."""
import threading
import time


class ChannelLimiter:
    def __init__(self, concurrency, min_interval_s, *, clock=time.monotonic, sleep=time.sleep):
        if concurrency < 1 or min_interval_s < 0:
            raise ValueError('concurrency must be positive and interval nonnegative')
        self.concurrency = concurrency
        self.min_interval_s = min_interval_s
        self.clock, self.sleep = clock, sleep
        self._slots = threading.BoundedSemaphore(concurrency)
        self._lock = threading.Lock()
        self._next = 0.0

    def __enter__(self):
        self._slots.acquire()
        try:
            with self._lock:
                delay = self._next - self.clock()
                if delay > 0:
                    self.sleep(delay)
                self._next = self.clock() + self.min_interval_s
        except BaseException:
            self._slots.release()
            raise
        return self

    def __exit__(self, *exc):
        self._slots.release()
