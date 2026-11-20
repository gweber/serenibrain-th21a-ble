"""th21a stream end to end, with a fake bleak that delivers packets like the headband (one notification dropped)."""
import argparse
import asyncio
import sys
import types

from tests.test_protocol import eeg_packet

PACKETS = [eeg_packet(list(range(10)), start=65520), eeg_packet(list(range(10)), start=65530),
           # the notification starting at counter 4 (65540 % 65536) is lost
           eeg_packet(list(range(10)), start=14)]


class FakeClient:
    def __init__(self, device, timeout=None):
        self.is_connected = False

    async def connect(self):
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, char, callback):
        self._callback = callback

    async def write_gatt_char(self, char, data, response=True):
        from th21a import protocol as p
        if data == p.START:
            for raw in PACKETS:
                self._callback(char, bytearray(raw))


def test_stream_csv_times_follow_the_counter_and_gaps_are_reported(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "bleak", types.SimpleNamespace(BleakClient=FakeClient, BleakScanner=None))
    monkeypatch.delitem(sys.modules, "th21a.client", raising=False)
    from th21a import cli
    clock = iter([1000.0, 1000.004, 1000.004, 1000.05])      # arrival times: bursty, as over BLE
    monkeypatch.setattr(cli.time, "time", lambda: next(clock))

    asyncio.run(cli.stream(argparse.Namespace(address="AA:BB", seconds=0.01)))
    out, err = capsys.readouterr()
    rows = [line.split(",") for line in out.splitlines()[1:]]
    times = [float(r[0]) for r in rows]
    counters = [int(r[1]) for r in rows]

    assert len(rows) == 30 and counters[15:17] == [65535, 0]
    steps = [round((b - a) * 250, 3) for a, b in zip(times, times[1:])]
    assert steps[:19] == [1.0] * 19                  # evenly spaced, across the counter wrap
    assert steps[19] == 11.0                         # the 10 lost samples leave a hole in time
    assert "gap: 10 samples missing before counter 14" in err
    assert "10 samples lost in 1 gaps" in err
