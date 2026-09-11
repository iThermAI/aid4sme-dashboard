"""Host master clock.

On Windows 7 time.time() advances in ~15.6 ms steps. perf_counter() is anchored
to the wall clock once, on a tick edge, and every timestamp in a session is
derived from it, so all streams share one monotonic, high-resolution timebase.
"""
import datetime
import time


class HiResClock(object):
    def __init__(self):
        t0 = time.time()
        deadline = time.perf_counter() + 0.1
        while True:
            t1 = time.time()
            if t1 != t0 or time.perf_counter() > deadline:
                break
        self.perf0 = time.perf_counter()
        self.wall0 = t1

    def now(self):
        return self.wall0 + (time.perf_counter() - self.perf0)


CLOCK = HiResClock()


def iso(epoch):
    """Local time with UTC offset, millisecond precision."""
    dt = datetime.datetime.fromtimestamp(epoch).astimezone()
    return dt.isoformat(timespec="milliseconds")
