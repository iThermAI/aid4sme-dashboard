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

    def wall_offset(self):
        """How far this clock has parted from the PC's wall clock, in seconds.
        perf_counter drifts on laptops, and NTP corrects the PC clock underneath us."""
        return time.time() - self.now()

    def resync(self):
        """Re-anchor to the wall clock. Only ever called between runs: inside a run
        the timebase must stay continuous. Returns the correction applied."""
        before = self.now()
        self.__init__()
        return self.now() - before


CLOCK = HiResClock()


def iso(epoch):
    """Local time with UTC offset, millisecond precision."""
    dt = datetime.datetime.fromtimestamp(epoch).astimezone()
    return dt.isoformat(timespec="milliseconds")
