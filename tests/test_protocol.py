import struct

import pytest

from th21a import protocol as p
from th21a.cli import contact_report

# The INFO packet exactly as a TH21A sent it (no personal data in it).
INFO = bytes.fromhex("444154410001000320000000544832314100000000000001000000010000000a00000002000000180000000c")


def eeg_packet(values, start=0, markers=None, battery=3944):
    markers = markers or {}
    body = b"".join(v.to_bytes(3, "little", signed=True) + bytes([markers.get(i, 0), 0]) + struct.pack("<H", (start + i) % 65536)
                    for i, v in enumerate(values))
    payload = body + struct.pack("<H", battery) + bytes(8)
    return b"DATA" + struct.pack(">HH", 2, 3) + struct.pack("<I", len(payload)) + payload


def test_commands():
    assert p.START == b"CTRL\x00\x03\x00\x03" and p.STOP == b"CTRL\x00\x03\x00\x04"
    assert p.GET_INFO == b"CTRL\x00\x03\x00\x05" and p.SELF_CHECK == b"CTRL\x00\x04\x00\x01"
    assert p.mark(7) == b"CTRL\x00\x05\x00\x07"
    with pytest.raises(ValueError):
        p.mark(0)


def test_info_packet():
    pkt = p.parse(INFO)
    assert isinstance(pkt, p.InfoPacket) and pkt.model == "TH21A" and pkt.channels == 3


def test_eeg_packet_values_markers_counter_battery():
    vals = [171895, -5, 0, 8388607, -8388608, 1, 2, 3, 4, 65535]
    pkt = p.parse(eeg_packet(vals, start=65530, markers={3: 2}))
    assert [s.value for s in pkt.samples] == vals
    assert [s.counter for s in pkt.samples][:7] == [65530, 65531, 65532, 65533, 65534, 65535, 0]
    assert pkt.samples[3].marker == 2 and sum(s.marker for s in pkt.samples) == 2
    assert pkt.battery_mv == 3944 and len(pkt.samples) == 10
    assert pkt.samples[3].saturated and pkt.samples[4].saturated and not pkt.samples[0].saturated


def test_real_packet_layout():
    # first EEG packet of a capture: 92 bytes, 12 header + 10 x 7 + 10 trailer
    raw = bytes.fromhex("444154410002000350000000f4910202000000319102000001003a92020000020079920200000300f791020000040047910200000500b59102000006000192020000070016920200000800bd910200000900680fca5e293ac6460000")
    pkt = p.parse(raw)
    assert [s.counter for s in pkt.samples] == list(range(10))
    assert pkt.samples[0].value == 0x0291F4 and pkt.samples[0].marker == 2
    assert pkt.battery_mv == 0x0F68


@pytest.mark.parametrize("raw", [b"", b"NOPE" + bytes(20), INFO[:-1], b"DATA" + struct.pack(">HH", 9, 3) + struct.pack("<I", 0)])
def test_bad_packets(raw):
    with pytest.raises(p.PacketError):
        p.parse(raw)


def test_contact_report():
    import math
    rail = [p.ADC_MAX] * 1000
    assert contact_report(rail)["verdict"].startswith("NO CONTACT")
    hum = [170000 + 3000 * math.sin(2 * math.pi * 50 * i / 250) for i in range(2500)]
    r = contact_report(hum)
    assert r["verdict"].startswith("POOR") and 2100 < r["hum_rms_counts"] < 2140      # RMS of a 3000-count tone
    quiet = [170000 + 100 * math.sin(2 * math.pi * 50 * i / 250) for i in range(2500)]
    assert contact_report(quiet)["verdict"] == "GOOD"
