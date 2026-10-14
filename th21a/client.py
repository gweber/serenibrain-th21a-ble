"""An asyncio client for the headband (needs bleak)."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from bleak import BleakClient, BleakScanner

from . import protocol as p


async def find(timeout: float = 20.0):
    """The first TH21A in range (a BLEDevice), or None. The headband stops advertising while the phone app holds it."""
    return await BleakScanner.find_device_by_filter(lambda d, ad: (d.name or ad.local_name or "").startswith(p.NAME_PREFIX),
                                                    timeout=timeout)


class Headband:
    """
        async with Headband(device_or_address) as band:
            print(await band.info())
            async for packet in band.stream():
                ...
    """

    def __init__(self, device, timeout: float = 25.0):
        self._client = BleakClient(device, timeout=timeout)
        self._queue: asyncio.Queue = asyncio.Queue()
        self.errors = 0

    async def __aenter__(self):
        await self._client.connect()
        await self._client.start_notify(p.NOTIFY, self._on_packet)
        return self

    async def __aexit__(self, *exc):
        try:
            if self._client.is_connected:
                await self.send(p.STOP)
        finally:
            await self._client.disconnect()

    def _on_packet(self, _char, data: bytearray):
        try:
            self._queue.put_nowait(p.parse(data))
        except p.PacketError:
            self.errors += 1

    async def send(self, cmd: bytes):
        await self._client.write_gatt_char(p.CONTROL, cmd, response=True)

    async def info(self, timeout: float = 5.0) -> p.InfoPacket | None:
        await self.send(p.GET_INFO)
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while (left := end - loop.time()) > 0:
            try:
                pkt = await asyncio.wait_for(self._queue.get(), left)
            except asyncio.TimeoutError:
                break
            if isinstance(pkt, p.InfoPacket):
                return pkt
        return None

    async def mark(self, value: int):
        await self.send(p.mark(value))

    async def stream(self) -> AsyncIterator[p.EEGPacket]:
        """Start streaming and yield EEG packets (25 a second, 10 samples each) until the caller stops iterating."""
        await self.send(p.SELF_CHECK)
        await self.send(p.START)
        while True:
            pkt = await self._queue.get()
            if isinstance(pkt, p.EEGPacket):
                yield pkt
