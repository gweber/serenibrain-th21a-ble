"""Read the SereniBrain TH21A EEG headband over Bluetooth LE, without the vendor app."""
from .protocol import (CALIBRATE_GYRO, CONTROL, GET_INFO, NOTIFY, SAMPLING_RATE, SELF_CHECK, SERVICE, START, STOP,
                       EEGPacket, InfoPacket, PacketError, Sample, command, mark, parse)

__version__ = "0.1.0"
__all__ = ["CALIBRATE_GYRO", "CONTROL", "GET_INFO", "NOTIFY", "SAMPLING_RATE", "SELF_CHECK", "SERVICE", "START", "STOP",
           "EEGPacket", "InfoPacket", "PacketError", "Sample", "command", "mark", "parse", "Headband", "find"]


def __getattr__(name):            # the client needs bleak; the parser does not
    if name in ("Headband", "find"):
        from . import client
        return getattr(client, name)
    raise AttributeError(name)
