"""The TH21A wire format: commands to the headband and the packets it sends back.

Everything here was worked out from the device's own behaviour (captures on Linux with bleak) and checked against
how the vendor's app talks to it. See PROTOCOL.md for the evidence behind each field.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

SERVICE = "8653000a-43e6-47b7-9cb0-5fc21d4ae340"
NOTIFY = "8653000b-43e6-47b7-9cb0-5fc21d4ae340"   # packets from the headband
CONTROL = "8653000c-43e6-47b7-9cb0-5fc21d4ae340"  # commands to the headband
# 0000fe59-... is Nordic's buttonless DFU service (firmware update). Never write to it.

NAME_PREFIX = "TH21A_"
SAMPLING_RATE = 250          # Hz, nominal; measured 241-250 over Bluetooth with no gaps in the counter
SAMPLES_PER_PACKET = 10
ADC_MAX = 0x7FFFFF           # a sample at either rail means the input is open or saturated (band off the head)
ADC_MIN = -0x800000


def command(group: int, code: int) -> bytes:
    """A control command: ASCII 'CTRL', then two big-endian 16-bit words."""
    return b"CTRL" + struct.pack(">HH", group, code)


GET_INFO = command(3, 5)            # the headband answers with an INFO packet
SELF_CHECK = command(4, 1)
START = command(3, 3)               # start streaming DATA packets
STOP = command(3, 4)                # stop streaming
CALIBRATE_GYRO = command(4, 2)


def mark(value: int) -> bytes:
    """An event marker (1-255): it appears in the marker byte of the next sample, timed by the headband itself."""
    if not 1 <= value <= 255:
        raise ValueError("marker must be 1-255")
    return command(5, value)


MAGIC = b"DATA"
TYPE_INFO = 1
TYPE_EEG = 2
HEADER = struct.Struct(">4sHH")     # magic, type, channel count (big-endian); then the payload length, u32 little-endian
SAMPLE = 7                          # int24 LE value, u8 marker, u8 unknown (always 0 so far), u16 LE counter


class PacketError(ValueError):
    pass


@dataclass
class Sample:
    value: int          # raw ADC counts, signed 24 bit; the scale to microvolts is not known yet
    marker: int         # 0, or the value of a mark() command
    counter: int        # running sample number, wraps at 65536
    aux: int = 0        # unknown byte, 0 in every capture so far

    @property
    def saturated(self) -> bool:
        return self.value >= ADC_MAX or self.value <= ADC_MIN


@dataclass
class EEGPacket:
    channels: int
    samples: list[Sample]
    battery_mv: int
    trailer: bytes = field(repr=False)     # the 10 trailing bytes; only the first two (battery) are understood


@dataclass
class InfoPacket:
    channels: int
    model: str
    payload: bytes = field(repr=False)


def _header(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 12 or data[:4] != MAGIC:
        raise PacketError("not a DATA packet")
    _, kind, channels = HEADER.unpack_from(data)
    length = struct.unpack_from("<I", data, 8)[0]
    payload = data[12:]
    if len(payload) != length:
        raise PacketError("payload length %d, header says %d" % (len(payload), length))
    return kind, channels, payload


def parse(data: bytes) -> EEGPacket | InfoPacket:
    kind, channels, payload = _header(bytes(data))
    if kind == TYPE_EEG:
        n = SAMPLES_PER_PACKET * SAMPLE
        if len(payload) < n + 2:
            raise PacketError("EEG payload too short: %d" % len(payload))
        samples = []
        for i in range(SAMPLES_PER_PACKET):
            o = i * SAMPLE
            value = int.from_bytes(payload[o:o + 3], "little", signed=True)
            counter = struct.unpack_from("<H", payload, o + 5)[0]
            samples.append(Sample(value, payload[o + 3], counter, payload[o + 4]))
        trailer = payload[n:]
        return EEGPacket(channels, samples, struct.unpack_from("<H", trailer)[0], trailer)
    if kind == TYPE_INFO:
        model = payload[:8].split(b"\0")[0].decode("ascii", "replace")
        return InfoPacket(channels, model, payload)
    raise PacketError("unknown packet type %d" % kind)
