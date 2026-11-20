import pytest

from th21a import protocol as p
from th21a.timing import SampleClock, sample_time


def feed(counters):
    clock = SampleClock()
    return clock, [clock.feed(c) for c in counters]


def test_counts_up_from_zero_whatever_the_first_counter():
    clock, ns = feed([40000, 40001, 40002])
    assert ns == [0, 1, 2] and (clock.gaps, clock.lost, clock.glitches) == (0, 0, 0)


def test_unwraps_at_65536():
    clock, ns = feed([65534, 65535, 0, 1])
    assert ns == [0, 1, 2, 3] and clock.lost == 0


def test_dropped_notification_is_a_gap_not_a_join():
    # one 10-sample notification missing, across the wrap
    clock, ns = feed([65530, 65531, 6, 7])
    assert ns == [0, 1, 12, 13] and (clock.gaps, clock.lost) == (1, 10)


def test_repeats_and_steps_back_are_glitches():
    clock, ns = feed([10, 11, 11, 5, 12])
    assert ns == [0, 1, 1, 1, 2] and (clock.glitches, clock.lost) == (2, 0)


def test_times_are_evenly_spaced_and_skip_the_gap():
    _, ns = feed([100, 101, 112])
    ts = [sample_time(n, 1000.0) for n in ns]
    assert ts[1] - ts[0] == pytest.approx(1 / p.SAMPLING_RATE)
    assert ts[2] - ts[1] == pytest.approx(11 / p.SAMPLING_RATE)
