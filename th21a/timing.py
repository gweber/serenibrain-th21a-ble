"""Sample numbers and times from the headband's 16-bit counter, with gap detection.

The counter is the device's own sample clock: one tick per sample at 250 Hz, wrapping at 65536. Times derived from it
are evenly spaced, unlike arrival times, which come in bursts of 10 (one BLE notification) plus connection-interval jitter.
"""
from __future__ import annotations

from . import protocol as p

WRAP = 65536


class SampleClock:
    """Unwraps the counter into a running sample number and counts the samples lost between notifications.

        clock = SampleClock()
        n = clock.feed(sample.counter)     # 0, 1, 2, ... (jumps forward over lost samples)

    A gap is any step other than +1. A step of 0 or a step backwards (more than half the range) is a repeat or an
    out-of-order sample: it is counted in `glitches` and gets the previous number. A gap of 65536 samples or more
    (over 4 minutes) cannot be told apart from a shorter one.
    """

    def __init__(self):
        self.last: int | None = None   # raw counter of the previous sample
        self.n = -1                    # running number of the previous sample
        self.gaps = 0                  # how many times samples went missing
        self.lost = 0                  # how many samples went missing in total
        self.glitches = 0              # repeated or out-of-order samples

    def feed(self, counter: int) -> int:
        """The running sample number for this counter value; the first sample is 0."""
        if self.last is None:
            self.last, self.n = counter, 0
            return 0
        step = (counter - self.last) % WRAP
        if step == 0 or step > WRAP // 2:
            self.glitches += 1
            return self.n
        if step > 1:
            self.gaps += 1
            self.lost += step - 1
        self.last, self.n = counter, self.n + step
        return self.n


def sample_time(n: int, t0: float, rate: float = p.SAMPLING_RATE) -> float:
    """The time of sample number `n` when sample 0 was taken at `t0` (seconds)."""
    return t0 + n / rate
